"""
Celery task: run_cost_estimate
Estimates multi-cloud costs for an app's current code state.
Stores results in the cost_estimates table.
"""
import logging
import uuid
from decimal import Decimal

from app.workers.celery_app import celery_app

log = logging.getLogger(__name__)


@celery_app.task(
    name="app.workers.cost_task.run_cost_estimate",
    bind=True,
    max_retries=1,
    track_started=True,
)
def run_cost_estimate(
    self,
    *,
    app_id: str,
    cloud_providers: list[str],
    region_prefs: dict,
    org_slug: str,
) -> dict:
    """Estimate multi-cloud costs and store in cost_estimates table."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session

    from app.core.config import settings
    from app.core.security import decrypt_value
    from app.models.org import App, CostEstimate
    from app.models.platform import Organization
    from app.services.git_service import get_current_files
    from app.services.iac.detector import detect_app_type
    from app.services.cost_engine.aggregator import estimate_costs

    sync_url = settings.DATABASE_URL.replace("+asyncpg", "")
    engine = create_engine(sync_url)
    real_schema = "org_" + org_slug.replace("-", "_")

    try:
        # ── Load app + org ────────────────────────────────────────────────────
        with engine.connect() as conn:
            conn.execute(text(f"SET search_path TO {real_schema}, platform, public"))
            with Session(conn) as session:
                app = session.get(App, uuid.UUID(app_id))
                if not app:
                    return {"success": False, "error": "App not found"}
                app_slug = app.slug

            conn.execute(text("SET search_path TO platform, public"))
            with Session(conn) as session:
                org = session.execute(
                    text("SELECT plan, cost_hard_cap FROM platform.organizations WHERE slug = :slug"),
                    {"slug": org_slug},
                ).fetchone()
                org_plan = org[0] if org else "pro"
                hard_cap = Decimal(str(org[1])) if org else Decimal("500")

        # ── Load files + detect app type ──────────────────────────────────────
        files = get_current_files(app_slug)
        if not files:
            return {"success": False, "error": "No generated files found"}

        target = detect_app_type(files)

        # ── Get Anthropic API key (master fallback) ───────────────────────────
        api_key = settings.ANTHROPIC_API_KEY or ""

        # ── Run cost estimation ───────────────────────────────────────────────
        result = estimate_costs(
            target=target,
            cloud_providers=cloud_providers,
            hard_cap_usd=hard_cap,
            api_key=api_key,
            region_prefs=region_prefs,
        )

        # ── Persist result ────────────────────────────────────────────────────
        with engine.connect() as conn:
            conn.execute(text(f"SET search_path TO {real_schema}, platform, public"))
            with Session(conn) as session:
                for provider in cloud_providers:
                    est = CostEstimate(
                        app_id=uuid.UUID(app_id),
                        cloud_provider=provider,
                        tier_matrix=result,
                    )
                    session.add(est)
                session.commit()

        log.info("Cost estimate complete for app=%s providers=%s", app_id, cloud_providers)
        return {"success": True, **result}

    except Exception as exc:
        log.error("Cost estimate task failed: %s", exc, exc_info=True)
        raise self.retry(exc=exc, countdown=30)
    finally:
        engine.dispose()
