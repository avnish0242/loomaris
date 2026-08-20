"""
GCP pricing. Unlike Azure's Retail Prices API, GCP's Cloud Billing Catalog API
requires an API key and a service+SKU lookup dance rather than a simple filtered
GET — not worth the extra config surface for an estimate that's already
approximate. This mirrors azure_pricing.py's shape but uses published on-demand
list prices (us-central1) as fixed constants, refreshed periodically by hand.
"""
from decimal import Decimal, ROUND_HALF_UP

_FALLBACK_PRICES = {
    "cloud_run_vcpu_per_hour": Decimal("0.0576"),  # after 240k vCPU-s free tier
    "cloud_run_gb_per_hour": Decimal("0.0072"),
    "cloud_functions_per_million_invocations": Decimal("0.40"),
    "cloud_functions_per_gb_second": Decimal("0.0000025"),
    "gcs_standard_per_gb_month": Decimal("0.020"),
    "gcs_per_10k_class_a_op": Decimal("0.05"),   # writes/lists
    "gcs_per_10k_class_b_op": Decimal("0.004"),  # reads
}


def get_cloud_run_price(vcpu: float = 0.5, memory_gb: float = 0.5, hours_per_month: float = 730) -> Decimal:
    """Monthly Cloud Run cost (always-on; ignores the generous free tier for simplicity)."""
    vcpu_price = _FALLBACK_PRICES["cloud_run_vcpu_per_hour"]
    gb_price = _FALLBACK_PRICES["cloud_run_gb_per_hour"]
    monthly = (Decimal(str(vcpu)) * vcpu_price + Decimal(str(memory_gb)) * gb_price) * Decimal(str(hours_per_month))
    return monthly.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def get_cloud_functions_price(invocations_per_month: int = 100_000, avg_duration_ms: int = 500, memory_mb: int = 256) -> Decimal:
    """Monthly Cloud Functions (2nd gen) cost, net of the free tier (2M invocations, 400k GB-s)."""
    gb_seconds = (memory_mb / 1024) * (avg_duration_ms / 1000) * invocations_per_month
    compute = Decimal(str(gb_seconds)) * _FALLBACK_PRICES["cloud_functions_per_gb_second"]
    requests = Decimal(str(invocations_per_month / 1_000_000)) * _FALLBACK_PRICES["cloud_functions_per_million_invocations"]
    free_compute = Decimal("400000") * _FALLBACK_PRICES["cloud_functions_per_gb_second"]
    free_requests = Decimal("2") * _FALLBACK_PRICES["cloud_functions_per_million_invocations"]
    total = max(Decimal("0"), compute - free_compute) + max(Decimal("0"), requests - free_requests)
    return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def get_gcs_price(storage_gb: float = 1.0, class_a_ops: int = 10_000, class_b_ops: int = 100_000) -> Decimal:
    """Monthly Google Cloud Storage cost (Standard class, single region)."""
    storage = Decimal(str(storage_gb)) * _FALLBACK_PRICES["gcs_standard_per_gb_month"]
    writes = Decimal(str(class_a_ops / 10_000)) * _FALLBACK_PRICES["gcs_per_10k_class_a_op"]
    reads = Decimal(str(class_b_ops / 10_000)) * _FALLBACK_PRICES["gcs_per_10k_class_b_op"]
    return (storage + writes + reads).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
