"""
Pre-prompt guardrail: two-layer safety classifier.
Layer 1 — regex rule engine (<1ms, catches obvious patterns)
Layer 2 — Claude Haiku LLM classifier (<200ms, called only when rules pass)
Combined decision: ALLOW / BLOCK / REVIEW
"""
import logging
import re
from dataclasses import dataclass, field
from enum import Enum

from anthropic import AsyncAnthropic
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.org import AuditLog

log = logging.getLogger(__name__)

# ── Blocklist regex patterns ──────────────────────────────────────────────────

_BLOCKLIST: list[tuple[str, str]] = [
    # Malware / exploits
    (r"\b(keylogger|rootkit|ransomware|botnet|C2[ -]server|command[- ]and[- ]control)\b", "malware"),
    (r"\b(exploit|CVE-\d{4}-\d+|zero[- ]?day|privilege[- ]?escalat)\b", "exploit"),
    # Spam / phishing
    (r"\b(mass[- ]?email|bulk[- ]?SMS|phishing|credential[- ]?harvest)\b", "phishing"),
    # Surveillance
    (r"\b(stalk(erware)?|spy[- ]?on|track[- ]?location[- ]?without|hidden[- ]?camera)\b", "surveillance"),
    # Crypto scams
    (r"\b(rug[- ]?pull|fake[- ]?token|pump[- ]?and[- ]?dump|honeypot[- ]?contract)\b", "crypto_scam"),
    # Hate speech / harassment
    (r"\b(generate[- \w]*hate|write[- \w]*slur|create[- \w]*propaganda)\b", "hate_speech"),
]

_CLASSIFIER_SYSTEM = """\
You are a safety classifier for a code generation platform.
Determine if the user's request is asking to build something harmful.

Categories to BLOCK:
- MALWARE: malware, spyware, ransomware, botnets, keyloggers, rootkits
- EXPLOIT: tools to exploit CVEs, bypass security, escalate privileges
- PHISHING: phishing sites, credential harvesters, scam landing pages
- SPAM: spam bots, bulk unsolicited message senders
- SURVEILLANCE: stalkerware, covert location tracking, hidden monitoring
- HATE: hate speech generators, targeted harassment tools
- SCAM: crypto rug pulls, fake investment platforms, Ponzi structures

If clearly benign: ALLOW
If ambiguous but concerning: REVIEW
Format: DECISION|CATEGORY|CONFIDENCE(0.00-1.00)|BRIEF_REASON
Example: BLOCK|MALWARE|0.97|User asked to build a keylogger
"""


class GuardrailAction(str, Enum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    REVIEW = "REVIEW"


@dataclass
class GuardrailDecision:
    action: GuardrailAction
    category: str | None = None
    risk_score: float = 0.0
    source: str = "rule"
    reason: str = ""


def _rule_classify(message: str) -> GuardrailDecision | None:
    for pattern, category in _BLOCKLIST:
        if re.search(pattern, message, re.IGNORECASE):
            return GuardrailDecision(
                action=GuardrailAction.BLOCK,
                category=category,
                risk_score=0.95,
                source="rule",
                reason=f"Matched blocklist pattern for '{category}'",
            )
    return None


def _parse_llm_response(text: str) -> tuple[str, str, float, str]:
    """Parse DECISION|CATEGORY|CONFIDENCE|REASON from Haiku response."""
    try:
        parts = text.strip().split("|", 3)
        decision = parts[0].strip().upper()
        category = parts[1].strip() if len(parts) > 1 else "UNKNOWN"
        confidence = float(parts[2].strip()) if len(parts) > 2 else 0.5
        reason = parts[3].strip() if len(parts) > 3 else ""
        return decision, category, confidence, reason
    except Exception:
        return "ALLOW", "UNKNOWN", 0.5, "parse error"


async def _llm_classify(message: str, api_key: str) -> GuardrailDecision:
    try:
        client = AsyncAnthropic(api_key=api_key)
        resp = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=100,
            system=_CLASSIFIER_SYSTEM,
            messages=[{"role": "user", "content": message[:2000]}],
        )
        raw = resp.content[0].text
        decision, category, confidence, reason = _parse_llm_response(raw)

        if decision == "BLOCK" and confidence >= 0.7:
            return GuardrailDecision(
                action=GuardrailAction.BLOCK,
                category=category.lower(),
                risk_score=confidence,
                source="llm",
                reason=reason,
            )
        if decision == "REVIEW" or confidence >= 0.5:
            return GuardrailDecision(
                action=GuardrailAction.REVIEW,
                category=category.lower(),
                risk_score=confidence,
                source="llm",
                reason=reason,
            )
        return GuardrailDecision(
            action=GuardrailAction.ALLOW,
            risk_score=1.0 - confidence,
            source="llm",
            reason=reason,
        )
    except Exception as exc:
        log.warning("LLM guardrail failed, defaulting to ALLOW: %s", exc)
        return GuardrailDecision(action=GuardrailAction.ALLOW, source="llm_error")


async def _log_decision(
    db: AsyncSession,
    decision: GuardrailDecision,
    user_id: str,
    org_id: str,
    message: str,
) -> None:
    if decision.action == GuardrailAction.ALLOW:
        return
    try:
        entry = AuditLog(
            event_type=f"GUARDRAIL_{decision.action.value}",
            user_id=user_id,  # type: ignore[arg-type]
            resource_type="chat_message",
            details={
                "org_id": org_id,
                "category": decision.category,
                "risk_score": decision.risk_score,
                "source": decision.source,
                "reason": decision.reason,
                "message_preview": message[:200],
            },
        )
        db.add(entry)
        await db.commit()
    except Exception as exc:
        log.warning("Failed to write guardrail audit log: %s", exc)


async def classify_message(
    *,
    message: str,
    api_key: str,
    org_id: str,
    user_id: str,
    db: AsyncSession,
) -> GuardrailDecision:
    """Classify a user message as ALLOW / BLOCK / REVIEW.

    Layer 1: fast regex rules — blocks immediately at confidence >0.9.
    Layer 2: Claude Haiku LLM — called only if rules don't block outright.
    """
    rule_result = _rule_classify(message)
    if rule_result and rule_result.risk_score >= 0.9:
        await _log_decision(db, rule_result, user_id, org_id, message)
        return rule_result

    llm_result = await _llm_classify(message, api_key)

    # If rule flagged (lower confidence) and LLM says ALLOW — escalate to REVIEW
    if rule_result and llm_result.action == GuardrailAction.ALLOW:
        combined = GuardrailDecision(
            action=GuardrailAction.REVIEW,
            category=rule_result.category,
            risk_score=0.6,
            source="combined",
            reason=f"Rule flagged '{rule_result.category}' but LLM cleared — needs review",
        )
        await _log_decision(db, combined, user_id, org_id, message)
        return combined

    await _log_decision(db, llm_result, user_id, org_id, message)
    return llm_result
