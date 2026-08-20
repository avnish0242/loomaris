"""
Multi-cloud cost aggregator.
Orchestrates pricing calls per cloud provider, runs tier projector,
generates a Claude summary, and checks the hard cap.
"""
import logging
from decimal import Decimal

from anthropic import Anthropic

from app.services.cost_engine.aws_pricing import (
    get_cloudfront_price,
    get_fargate_price,
    get_lambda_price,
    get_s3_price,
)
from app.services.cost_engine.azure_pricing import (
    get_blob_storage_price,
    get_container_apps_price,
    get_functions_price,
)
from app.services.cost_engine.cap_enforcer import CostCapResult, check_cap
from app.services.cost_engine.gcp_pricing import (
    get_cloud_functions_price,
    get_cloud_run_price,
    get_gcs_price,
)
from app.services.cost_engine.tier_projector import BaseResourceCost, TierEstimate, project_tiers
from app.services.iac.detector import AppDeployTarget

log = logging.getLogger(__name__)


def _estimate_aws_base(target: AppDeployTarget) -> BaseResourceCost:
    """Compute baseline (1x) monthly costs for the detected AWS target."""
    if target.type == "static":
        return BaseResourceCost(
            compute_monthly=Decimal("0"),
            storage_monthly=get_s3_price(storage_gb=1.0),
            data_transfer_monthly=Decimal("0"),
            managed_services_monthly=get_cloudfront_price(data_transfer_gb=5.0),
        )
    if target.type == "lambda":
        return BaseResourceCost(
            compute_monthly=get_lambda_price(memory_mb=256, avg_duration_ms=500, invocations_per_month=100_000),
            storage_monthly=get_s3_price(storage_gb=0.5),
            data_transfer_monthly=Decimal("0"),
            managed_services_monthly=Decimal("0"),
        )
    # container (ECS Fargate)
    return BaseResourceCost(
        compute_monthly=get_fargate_price(vcpu=0.25, memory_gb=0.5),
        storage_monthly=get_s3_price(storage_gb=1.0),
        data_transfer_monthly=Decimal("0"),
        managed_services_monthly=Decimal("0"),
    )


def _estimate_azure_base(target: AppDeployTarget) -> BaseResourceCost:
    """Compute baseline monthly costs for the Azure equivalent."""
    if target.type == "static":
        return BaseResourceCost(
            compute_monthly=Decimal("0"),
            storage_monthly=get_blob_storage_price(storage_gb=1.0),
            data_transfer_monthly=Decimal("0"),
            managed_services_monthly=Decimal("0"),
        )
    if target.type == "lambda":
        return BaseResourceCost(
            compute_monthly=get_functions_price(invocations_per_month=100_000),
            storage_monthly=get_blob_storage_price(storage_gb=0.5),
            data_transfer_monthly=Decimal("0"),
            managed_services_monthly=Decimal("0"),
        )
    return BaseResourceCost(
        compute_monthly=get_container_apps_price(vcpu=0.5, memory_gb=1.0),
        storage_monthly=get_blob_storage_price(storage_gb=1.0),
        data_transfer_monthly=Decimal("0"),
        managed_services_monthly=Decimal("0"),
    )


def _estimate_gcp_base(target: AppDeployTarget) -> BaseResourceCost:
    """Compute baseline monthly costs for the GCP equivalent."""
    if target.type == "static":
        return BaseResourceCost(
            compute_monthly=Decimal("0"),
            storage_monthly=get_gcs_price(storage_gb=1.0),
            data_transfer_monthly=Decimal("0"),
            managed_services_monthly=Decimal("0"),
        )
    if target.type == "lambda":
        return BaseResourceCost(
            compute_monthly=get_cloud_functions_price(invocations_per_month=100_000),
            storage_monthly=get_gcs_price(storage_gb=0.5),
            data_transfer_monthly=Decimal("0"),
            managed_services_monthly=Decimal("0"),
        )
    return BaseResourceCost(
        compute_monthly=get_cloud_run_price(vcpu=0.5, memory_gb=0.5),
        storage_monthly=get_gcs_price(storage_gb=1.0),
        data_transfer_monthly=Decimal("0"),
        managed_services_monthly=Decimal("0"),
    )


def _generate_summary(
    tier_estimates: dict[str, dict[str, TierEstimate]],
    api_key: str,
) -> str:
    """Ask Claude to summarize the cost estimates in plain English."""
    try:
        # Build a compact summary for the prompt
        lines = []
        for provider, tiers in tier_estimates.items():
            for tier_key, est in tiers.items():
                lines.append(
                    f"{provider.upper()} {est.tier_label}: ${est.monthly_cost_usd:.2f}/mo"
                    f" (compute=${est.breakdown.get('compute', 0):.2f},"
                    f" storage=${est.breakdown.get('storage', 0):.2f},"
                    f" transfer=${est.breakdown.get('data_transfer', 0):.2f})"
                )

        client = Anthropic(api_key=api_key)
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{
                "role": "user",
                "content": (
                    "Here are cloud cost estimates for an application across usage tiers:\n\n"
                    + "\n".join(lines)
                    + "\n\nIn 2-3 sentences: explain these costs in plain English and suggest "
                    "1-2 cost optimization tips. Be concrete and actionable."
                ),
            }],
        )
        return resp.content[0].text.strip()
    except Exception as exc:
        log.warning("Cost summary generation failed: %s", exc)
        return "Cost estimates computed. See tier breakdown for details."


def estimate_costs(
    *,
    target: AppDeployTarget,
    cloud_providers: list[str],
    hard_cap_usd: Decimal,
    api_key: str,
    region_prefs: dict | None = None,
) -> dict:
    """
    Main entry point: estimate costs across providers and tiers.

    Returns a dict with:
      - tier_estimates: {provider: {tier_key: TierEstimate}}
      - summary_text: Claude-generated explanation
      - cap_result: CostCapResult for the target tier
      - recommendations: list[str]
    """
    tier_estimates: dict[str, dict[str, TierEstimate]] = {}

    if "aws" in cloud_providers:
        aws_base = _estimate_aws_base(target)
        tier_estimates["aws"] = project_tiers(aws_base)

    if "azure" in cloud_providers:
        azure_base = _estimate_azure_base(target)
        tier_estimates["azure"] = project_tiers(azure_base)

    if "gcp" in cloud_providers:
        gcp_base = _estimate_gcp_base(target)
        tier_estimates["gcp"] = project_tiers(gcp_base)

    # Hard cap check against the 1k_users tier (typical first production tier)
    cap_result: CostCapResult | None = None
    if tier_estimates:
        first_provider = next(iter(tier_estimates))
        cap_result = check_cap(
            tier_estimates[first_provider],
            hard_cap_usd=hard_cap_usd,
            target_tier="1k_users",
        )

    summary = _generate_summary(tier_estimates, api_key)

    recommendations: list[str] = []
    if target.type == "container":
        recommendations.append("Consider Lambda or Container Apps for sporadic workloads — saves 60-80% vs always-on containers.")
    if target.type == "static":
        recommendations.append("Static sites on S3+CloudFront are extremely cost-efficient — typically under $5/mo at 10k users.")
    if cap_result and cap_result.warning_at_80_pct:
        recommendations.append(f"Estimated cost is near your org cap (${cap_result.hard_cap:.2f}/mo). Consider rightsizing resources.")

    return {
        "tier_estimates": {
            provider: {
                tier_key: {
                    "tier_label": est.tier_label,
                    "monthly_cost_usd": str(est.monthly_cost_usd),
                    "breakdown": {k: str(v) for k, v in est.breakdown.items()},
                    "assumptions": est.assumptions,
                }
                for tier_key, est in tiers.items()
            }
            for provider, tiers in tier_estimates.items()
        },
        "summary_text": summary,
        "cap_result": {
            "allowed": cap_result.allowed if cap_result else True,
            "exceeded_at_tier": cap_result.exceeded_at_tier if cap_result else None,
            "estimated_cost": str(cap_result.estimated_cost) if cap_result and cap_result.estimated_cost else None,
            "hard_cap": str(cap_result.hard_cap) if cap_result and cap_result.hard_cap else None,
            "reason": cap_result.reason if cap_result else None,
            "warning_at_80_pct": cap_result.warning_at_80_pct if cap_result else False,
        },
        "recommendations": recommendations,
    }
