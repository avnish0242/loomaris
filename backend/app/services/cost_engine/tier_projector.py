"""
Traffic-tier cost projector.
Applies usage multipliers to a base resource config to produce
4-tier cost estimates: baseline, 1k users, 10k users, 100k users.
"""
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP


# Multiplier table from architecture-blueprint §5c
_TIERS = {
    "baseline": {
        "label": "Baseline (dev)",
        "compute_factor": Decimal("1"),
        "storage_factor": Decimal("1"),
        "data_transfer_gb": Decimal("1"),
        "managed_factor": Decimal("1"),
        "assumptions": ["Minimal traffic", "Single instance", "Dev/staging environment"],
    },
    "1k_users": {
        "label": "1k users/month",
        "compute_factor": Decimal("2"),
        "storage_factor": Decimal("1.5"),
        "data_transfer_gb": Decimal("50"),
        "managed_factor": Decimal("1.5"),
        "assumptions": ["~33 daily active users", "Small tier managed services"],
    },
    "10k_users": {
        "label": "10k users/month",
        "compute_factor": Decimal("5"),
        "storage_factor": Decimal("3"),
        "data_transfer_gb": Decimal("500"),
        "managed_factor": Decimal("3"),
        "assumptions": ["~333 daily active users", "Medium tier managed services", "Multi-AZ recommended"],
    },
    "100k_users": {
        "label": "100k users/month",
        "compute_factor": Decimal("20"),
        "storage_factor": Decimal("10"),
        "data_transfer_gb": Decimal("5000"),
        "managed_factor": Decimal("10"),
        "assumptions": ["~3.3k daily active users", "Auto-scaling enabled", "Large tier managed services"],
    },
}


@dataclass
class TierEstimate:
    tier_key: str
    tier_label: str
    monthly_cost_usd: Decimal
    breakdown: dict[str, Decimal]
    assumptions: list[str]


@dataclass
class BaseResourceCost:
    """Base costs at baseline scale (1x multipliers)."""
    compute_monthly: Decimal = Decimal("0")
    storage_monthly: Decimal = Decimal("0")
    data_transfer_monthly: Decimal = Decimal("0")
    managed_services_monthly: Decimal = Decimal("0")


def project_tiers(base: BaseResourceCost) -> dict[str, TierEstimate]:
    """Apply traffic-tier multipliers to produce 4 TierEstimate objects."""
    estimates: dict[str, TierEstimate] = {}

    for tier_key, config in _TIERS.items():
        compute = (base.compute_monthly * config["compute_factor"]).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        storage = (base.storage_monthly * config["storage_factor"]).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        # Data transfer cost: $0.09/GB (AWS egress, approximate)
        data_transfer = (config["data_transfer_gb"] * Decimal("0.09")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        managed = (base.managed_services_monthly * config["managed_factor"]).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        total = compute + storage + data_transfer + managed

        estimates[tier_key] = TierEstimate(
            tier_key=tier_key,
            tier_label=config["label"],
            monthly_cost_usd=total,
            breakdown={
                "compute": compute,
                "storage": storage,
                "data_transfer": data_transfer,
                "managed_services": managed,
            },
            assumptions=config["assumptions"],
        )

    return estimates
