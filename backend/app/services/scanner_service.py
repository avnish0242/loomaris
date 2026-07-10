"""
Post-generation code scanner.
Runs detect-secrets and Semgrep against generated files to catch
leaked credentials and common security anti-patterns before code ships.
"""
import json
import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass, field

log = logging.getLogger(__name__)


@dataclass
class ScanIssue:
    severity: str       # critical | warning | info
    rule_id: str
    message: str
    file_path: str
    line: int = 0
    source: str = "semgrep"  # semgrep | detect-secrets


@dataclass
class ScanResult:
    passed: bool
    blocked: bool
    issues: list[ScanIssue] = field(default_factory=list)


def _run_detect_secrets(files: dict[str, str]) -> list[ScanIssue]:
    """Scan for secrets using detect-secrets (pure Python, no subprocess)."""
    issues: list[ScanIssue] = []
    try:
        from detect_secrets import SecretsCollection
        from detect_secrets.settings import default_settings

        with default_settings():
            collection = SecretsCollection()
            for path, content in files.items():
                collection.scan_file(path, content)

            for path, secrets in collection:
                for secret in secrets:
                    issues.append(ScanIssue(
                        severity="critical",
                        rule_id="detect-secrets/" + (secret.type or "UNKNOWN"),
                        message=f"Potential secret detected: {secret.type}",
                        file_path=path,
                        line=secret.line_number or 0,
                        source="detect-secrets",
                    ))
    except ImportError:
        log.warning("detect-secrets not installed; skipping secret scan")
    except Exception as exc:
        log.warning("detect-secrets scan failed: %s", exc)
    return issues


def _run_semgrep(files: dict[str, str], custom_rules_path: str | None = None) -> list[ScanIssue]:
    """Run semgrep via subprocess and parse JSON output."""
    issues: list[ScanIssue] = []
    if not files:
        return issues

    with tempfile.TemporaryDirectory() as tmpdir:
        # Write files to temp dir
        for path, content in files.items():
            full_path = os.path.join(tmpdir, path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)

        configs = ["p/secrets", "p/python", "p/javascript"]
        if custom_rules_path and os.path.exists(custom_rules_path):
            configs.append(custom_rules_path)

        cmd = [
            "semgrep",
            "--json",
            "--no-git-ignore",
            "--quiet",
        ]
        for cfg in configs:
            cmd += ["--config", cfg]
        cmd.append(tmpdir)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.stdout:
                data = json.loads(result.stdout)
                for finding in data.get("results", []):
                    severity = finding.get("extra", {}).get("severity", "WARNING").lower()
                    if severity == "error":
                        severity = "critical"
                    elif severity in ("warning", "warn"):
                        severity = "warning"
                    else:
                        severity = "info"

                    rel_path = os.path.relpath(finding.get("path", ""), tmpdir)
                    issues.append(ScanIssue(
                        severity=severity,
                        rule_id=finding.get("check_id", "unknown"),
                        message=finding.get("extra", {}).get("message", ""),
                        file_path=rel_path,
                        line=finding.get("start", {}).get("line", 0),
                        source="semgrep",
                    ))
        except FileNotFoundError:
            log.warning("semgrep not installed; skipping SAST scan")
        except subprocess.TimeoutExpired:
            log.warning("semgrep timed out after 60s")
        except json.JSONDecodeError as exc:
            log.warning("Failed to parse semgrep output: %s", exc)

    return issues


_CUSTOM_RULES_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "semgrep-rules", "loomaris-iac.yaml"
)


def scan_files(files: dict[str, str]) -> ScanResult:
    """Synchronous scan — call from a Celery task, not from an async route."""
    issues: list[ScanIssue] = []
    issues.extend(_run_detect_secrets(files))
    issues.extend(_run_semgrep(files, _CUSTOM_RULES_PATH))

    critical = [i for i in issues if i.severity == "critical"]
    return ScanResult(
        passed=len(critical) == 0,
        blocked=len(critical) > 0,
        issues=issues,
    )
