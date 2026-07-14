"""
AWS pricing lookups via boto3 Price List API.
All pricing is cached in Redis for 24h (prices change rarely).
"""
import json
import logging
from decimal import Decimal, ROUND_HALF_UP

import boto3

log = logging.getLogger(__name__)

# Fallback prices (USD) used when the Price List API is unavailable (e.g. LocalStack)
_FALLBACK_PRICES = {
    "fargate_vcpu_per_hour": Decimal("0.04048"),
    "fargate_gb_per_hour": Decimal("0.004445"),
    "lambda_per_gb_second": Decimal("0.0000166667"),
    "lambda_per_request": Decimal("0.0000002"),
    "s3_per_gb_month": Decimal("0.023"),
    "s3_per_1k_put": Decimal("0.005"),
    "s3_per_1k_get": Decimal("0.0004"),
    "cloudfront_per_gb": Decimal("0.0085"),
    "cloudfront_per_10k_requests": Decimal("0.01"),
    "ec2_t3_micro_per_hour": Decimal("0.0104"),
    "rds_t3_micro_per_hour": Decimal("0.017"),
}


def _redis_client():
    try:
        from app.core.config import settings
        import redis as redis_lib
        return redis_lib.from_url(settings.REDIS_URL, decode_responses=True)
    except Exception:
        return None


def _cached_price(key: str) -> Decimal | None:
    r = _redis_client()
    if not r:
        return None
    try:
        val = r.get(f"aws_price:{key}")
        return Decimal(val) if val else None
    except Exception:
        return None


def _cache_price(key: str, value: Decimal, ttl: int = 86400) -> None:
    r = _redis_client()
    if not r:
        return
    try:
        r.setex(f"aws_price:{key}", ttl, str(value))
    except Exception:
        pass


def _pricing_client():
    from app.core.config import settings
    kwargs: dict = {"region_name": "us-east-1"}
    if settings.AWS_ENDPOINT_URL:
        # LocalStack doesn't fully support Price List API — use fallbacks
        return None
    return boto3.client("pricing", **kwargs)


def get_fargate_price(vcpu: float, memory_gb: float, hours_per_month: float = 730) -> Decimal:
    """Monthly cost for a Fargate task (vCPU + memory)."""
    cached = _cached_price(f"fargate_{vcpu}_{memory_gb}")
    if cached:
        return cached

    vcpu_price = _FALLBACK_PRICES["fargate_vcpu_per_hour"]
    gb_price = _FALLBACK_PRICES["fargate_gb_per_hour"]

    try:
        client = _pricing_client()
        if client:
            # Fetch Fargate compute pricing
            resp = client.get_products(
                ServiceCode="AmazonECS",
                Filters=[
                    {"Type": "TERM_MATCH", "Field": "usagetype", "Value": "Fargate-vCPU-Hours:perCPU"},
                ],
                MaxResults=1,
            )
            if resp.get("PriceList"):
                price_data = json.loads(resp["PriceList"][0])
                terms = price_data.get("terms", {}).get("OnDemand", {})
                for term in terms.values():
                    for pd in term.get("priceDimensions", {}).values():
                        vcpu_price = Decimal(pd["pricePerUnit"]["USD"])
    except Exception as exc:
        log.debug("AWS Price List API unavailable, using fallback: %s", exc)

    monthly = (Decimal(str(vcpu)) * vcpu_price + Decimal(str(memory_gb)) * gb_price) * Decimal(str(hours_per_month))
    monthly = monthly.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    _cache_price(f"fargate_{vcpu}_{memory_gb}", monthly)
    return monthly


def get_lambda_price(memory_mb: int = 256, avg_duration_ms: int = 500, invocations_per_month: int = 100_000) -> Decimal:
    """Monthly cost for a Lambda function."""
    gb_seconds = (memory_mb / 1024) * (avg_duration_ms / 1000) * invocations_per_month
    compute_cost = Decimal(str(gb_seconds)) * _FALLBACK_PRICES["lambda_per_gb_second"]
    request_cost = Decimal(str(invocations_per_month)) * _FALLBACK_PRICES["lambda_per_request"]
    # Free tier: 400k GB-seconds and 1M requests per month
    free_compute = Decimal("400000") * _FALLBACK_PRICES["lambda_per_gb_second"]
    total = max(Decimal("0"), compute_cost - free_compute) + max(Decimal("0"), request_cost)
    return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def get_s3_price(storage_gb: float = 1.0, put_requests: int = 10_000, get_requests: int = 100_000) -> Decimal:
    """Monthly S3 cost."""
    storage = Decimal(str(storage_gb)) * _FALLBACK_PRICES["s3_per_gb_month"]
    puts = Decimal(str(put_requests / 1000)) * _FALLBACK_PRICES["s3_per_1k_put"]
    gets = Decimal(str(get_requests / 1000)) * _FALLBACK_PRICES["s3_per_1k_get"]
    return (storage + puts + gets).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def get_cloudfront_price(data_transfer_gb: float = 10.0, requests_per_month: int = 1_000_000) -> Decimal:
    """Monthly CloudFront cost."""
    transfer = Decimal(str(data_transfer_gb)) * _FALLBACK_PRICES["cloudfront_per_gb"]
    reqs = Decimal(str(requests_per_month / 10_000)) * _FALLBACK_PRICES["cloudfront_per_10k_requests"]
    return (transfer + reqs).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def get_ec2_price(instance_type: str = "t3.micro", hours_per_month: float = 730) -> Decimal:
    """Monthly EC2 on-demand cost."""
    key = f"ec2_{instance_type}"
    cached = _cached_price(key)
    if cached:
        return (cached * Decimal(str(hours_per_month))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    hourly = _FALLBACK_PRICES.get("ec2_t3_micro_per_hour", Decimal("0.01"))
    try:
        client = _pricing_client()
        if client:
            resp = client.get_products(
                ServiceCode="AmazonEC2",
                Filters=[
                    {"Type": "TERM_MATCH", "Field": "instanceType", "Value": instance_type},
                    {"Type": "TERM_MATCH", "Field": "operatingSystem", "Value": "Linux"},
                    {"Type": "TERM_MATCH", "Field": "tenancy", "Value": "Shared"},
                    {"Type": "TERM_MATCH", "Field": "capacitystatus", "Value": "Used"},
                    {"Type": "TERM_MATCH", "Field": "preInstalledSw", "Value": "NA"},
                ],
                MaxResults=1,
            )
            if resp.get("PriceList"):
                price_data = json.loads(resp["PriceList"][0])
                terms = price_data.get("terms", {}).get("OnDemand", {})
                for term in terms.values():
                    for pd in term.get("priceDimensions", {}).values():
                        hourly = Decimal(pd["pricePerUnit"]["USD"])
    except Exception as exc:
        log.debug("EC2 pricing lookup failed: %s", exc)

    _cache_price(key, hourly)
    return (hourly * Decimal(str(hours_per_month))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
