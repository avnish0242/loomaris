"""
Azure Retail Prices REST API (public, no auth required).
https://prices.azure.com/api/retail/prices
"""
import logging
from decimal import Decimal, ROUND_HALF_UP

log = logging.getLogger(__name__)

_AZURE_PRICES_URL = "https://prices.azure.com/api/retail/prices"

_FALLBACK_PRICES = {
    "container_apps_vcpu_per_hour": Decimal("0.0566"),
    "container_apps_gb_per_hour": Decimal("0.0063"),
    "functions_per_million_executions": Decimal("0.20"),
    "functions_per_gb_second": Decimal("0.000016"),
    "blob_storage_per_gb_month": Decimal("0.018"),
    "blob_per_10k_write": Decimal("0.05"),
    "blob_per_10k_read": Decimal("0.004"),
}


def _fetch_price(filter_str: str) -> Decimal | None:
    try:
        import httpx
        resp = httpx.get(_AZURE_PRICES_URL, params={"$filter": filter_str}, timeout=10)
        resp.raise_for_status()
        items = resp.json().get("Items", [])
        if items:
            return Decimal(str(items[0]["retailPrice"]))
    except Exception as exc:
        log.debug("Azure pricing API unavailable: %s", exc)
    return None


def get_container_apps_price(vcpu: float = 0.5, memory_gb: float = 1.0, hours_per_month: float = 730) -> Decimal:
    """Monthly Azure Container Apps cost."""
    vcpu_price = _FALLBACK_PRICES["container_apps_vcpu_per_hour"]
    gb_price = _FALLBACK_PRICES["container_apps_gb_per_hour"]

    live = _fetch_price("serviceName eq 'Azure Container Apps' and skuName eq 'vCPU Duration'")
    if live:
        vcpu_price = live

    monthly = (Decimal(str(vcpu)) * vcpu_price + Decimal(str(memory_gb)) * gb_price) * Decimal(str(hours_per_month))
    return monthly.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def get_functions_price(invocations_per_month: int = 100_000, avg_duration_ms: int = 500, memory_mb: int = 256) -> Decimal:
    """Monthly Azure Functions cost (Consumption plan)."""
    gb_seconds = (memory_mb / 1024) * (avg_duration_ms / 1000) * invocations_per_month
    compute = Decimal(str(gb_seconds)) * _FALLBACK_PRICES["functions_per_gb_second"]
    requests = Decimal(str(invocations_per_month / 1_000_000)) * _FALLBACK_PRICES["functions_per_million_executions"]
    # Free tier: 1M executions + 400k GB-seconds
    free_compute = Decimal("400000") * _FALLBACK_PRICES["functions_per_gb_second"]
    total = max(Decimal("0"), compute - free_compute) + max(Decimal("0"), requests - Decimal("0.20"))
    return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def get_blob_storage_price(storage_gb: float = 1.0, write_ops: int = 10_000, read_ops: int = 100_000) -> Decimal:
    """Monthly Azure Blob Storage cost (LRS, Hot)."""
    storage = Decimal(str(storage_gb)) * _FALLBACK_PRICES["blob_storage_per_gb_month"]
    writes = Decimal(str(write_ops / 10_000)) * _FALLBACK_PRICES["blob_per_10k_write"]
    reads = Decimal(str(read_ops / 10_000)) * _FALLBACK_PRICES["blob_per_10k_read"]
    return (storage + writes + reads).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
