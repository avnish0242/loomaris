"""Hard cap enforcement — checks estimated costs against the org's monthly cap."""
import logging
from dataclasses import dataclass
from decimal import Decimal

log = logging.getLogger(__name__)


@dataclass
class CostCapResult:
    allowed: bool
    exceeded_at_tier: str | None = None
    estimated_cost: Decimal | None = None
    hard_cap: Decimal | None = None
    reason: str | None = None
    warning_at_80_pct: bool = False


def check_cap(
    tier_estimates: dict,          # {tier_key: TierEstimate}
    hard_cap_usd: Decimal,
    target_tier: str = "1k_users",
) -> CostCapResult:
    """Check if any tier exceeds the org's hard cap."""
    target = tier_estimates.get(target_tier)
    if not target:
        return CostCapResult(allowed=True)

    cost = target.monthly_cost_usd

    if cost > hard_cap_usd:
        log.warning(
            "Cost cap exceeded: estimated=$%.2f cap=$%.2f tier=%s",
            cost, hard_cap_usd, target_tier,
        )
        return CostCapResult(
            allowed=False,
            exceeded_at_tier=target_tier,
            estimated_cost=cost,
            hard_cap=hard_cap_usd,
            reason=(
                f"Estimated monthly cost ${cost:.2f} exceeds org cap ${hard_cap_usd:.2f} "
                f"at '{target_tier}' scale. Resize resources or contact support to increase cap."
            ),
        )

    warning = cost > hard_cap_usd * Decimal("0.8")
    if warning:
        log.info("Cost at 80%% of cap: estimated=$%.2f cap=$%.2f", cost, hard_cap_usd)

    return CostCapResult(
        allowed=True,
        estimated_cost=cost,
        hard_cap=hard_cap_usd,
        warning_at_80_pct=warning,
    )
