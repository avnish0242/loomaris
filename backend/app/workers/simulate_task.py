"""
Celery task: run_simulation
Orchestrates a full ephemeral simulation session:
  1. Budget gate
  2. Detect app type → TTL
  3. Build Docker image + push to ECR
  4. Run ECS Fargate task
  5. Poll for public IP
  6. Update SimulationSession: running + URL
  7. Schedule teardown via EventBridge Scheduler
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone

from celery import Task

from app.workers.celery_app import celery_app

log = logging.getLogger(__name__)


def _update_sim_sync(session_id: str, org_slug: str, **kwargs) -> None:
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session
    from app.core.config import settings
    from app.models.org import SimulationSession

    sync_url = settings.DATABASE_URL.replace("+asyncpg", "")
    engine = create_engine(sync_url)
    real_schema = "org_" + org_slug.replace("-", "_")

    with engine.connect() as conn:
        conn.execute(text(f"SET search_path TO {real_schema}, public"))
        with Session(conn) as session:
            sim = session.get(SimulationSession, uuid.UUID(session_id))
            if sim:
                for k, v in kwargs.items():
                    setattr(sim, k, v)
                session.commit()
    engine.dispose()


@celery_app.task(
    name="app.workers.simulate_task.run_simulation",
    bind=True,
    max_retries=0,
    track_started=True,
)
def run_simulation(
    self: Task,
    *,
    app_id: str,
    org_slug: str,
    user_id: str,
    session_id: str,
) -> dict:
    """Run an ephemeral ECS Fargate simulation for the given app."""
    import asyncio

    from app.services.git_service import get_current_files
    from app.services.iac.detector import detect_app_type
    from app.services.sim_service import (
        build_and_push_image,
        check_user_budget,
        get_ttl_for_app_type,
        poll_task_public_ip,
        record_cost_sync,
        run_fargate_task,
        schedule_teardown,
        stop_simulation,
    )

    def run(coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    log.info("Starting simulation: session=%s app=%s org=%s", session_id, app_id, org_slug)

    # ── 1. Budget gate ──────────────────────────────────────────────────────
    try:
        run(check_user_budget(user_id, _get_org_id(org_slug)))
    except ValueError as exc:
        _update_sim_sync(session_id, org_slug, status="failed", url=None)
        return {"success": False, "error": str(exc), "budget_exceeded": True}

    # ── 2. Detect app type + TTL ────────────────────────────────────────────
    app_slug = _get_app_slug(app_id, org_slug)
    files = get_current_files(app_slug)
    if not files:
        _update_sim_sync(session_id, org_slug, status="failed")
        return {"success": False, "error": "No generated files found"}

    target = detect_app_type(files)
    ttl_seconds = get_ttl_for_app_type(target.type)
    log.info("App type: %s, TTL: %ds", target.type, ttl_seconds)

    # ── 3. Build + push image ───────────────────────────────────────────────
    try:
        image_uri = run(build_and_push_image(app_slug, files, org_slug))
    except Exception as exc:
        log.error("Image build failed: %s", exc)
        _update_sim_sync(session_id, org_slug, status="failed")
        return {"success": False, "error": f"Image build failed: {exc}"}

    # ── 4. Run Fargate task ─────────────────────────────────────────────────
    try:
        task_arn = run(run_fargate_task(image_uri, app_slug, org_slug, ttl_seconds, session_id))
    except Exception as exc:
        log.error("Fargate task failed to start: %s", exc)
        _update_sim_sync(session_id, org_slug, status="failed")
        return {"success": False, "error": f"ECS task failed: {exc}"}

    _update_sim_sync(session_id, org_slug, task_arn=task_arn, image_uri=image_uri)

    # ── 5. Poll for public IP ───────────────────────────────────────────────
    public_ip = run(poll_task_public_ip(task_arn))
    if not public_ip:
        log.error("Could not resolve public IP for task %s", task_arn)
        run(stop_simulation(task_arn, image_uri))
        _update_sim_sync(session_id, org_slug, status="failed")
        return {"success": False, "error": "Fargate task did not get a public IP"}

    # ── 6. Update session: running ──────────────────────────────────────────
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
    sim_url = f"http://{public_ip}:8000"
    _update_sim_sync(
        session_id, org_slug,
        status="running",
        public_ip=public_ip,
        url=sim_url,
        image_uri=image_uri,
        ttl_seconds=ttl_seconds,
        expires_at=expires_at,
    )

    # ── 7. Schedule teardown ────────────────────────────────────────────────
    try:
        run(schedule_teardown(task_arn, image_uri, session_id, expires_at))
    except Exception as exc:
        log.warning("Could not schedule teardown: %s", exc)

    # ── 8. Record cost in budget log ────────────────────────────────────────
    try:
        cost = record_cost_sync(user_id, _get_org_id(org_slug), session_id, ttl_seconds)
        _update_sim_sync(session_id, org_slug, cost_usd=cost)
    except Exception as exc:
        log.warning("Could not record simulation cost: %s", exc)

    log.info("Simulation ready: session=%s url=%s expires=%s", session_id, sim_url, expires_at)
    return {
        "success": True,
        "session_id": session_id,
        "url": sim_url,
        "ttl_seconds": ttl_seconds,
        "expires_at": expires_at.isoformat(),
    }


def _get_app_slug(app_id: str, org_slug: str) -> str:
    try:
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import Session
        from app.core.config import settings
        from app.models.org import App

        sync_url = settings.DATABASE_URL.replace("+asyncpg", "")
        engine = create_engine(sync_url)
        real_schema = "org_" + org_slug.replace("-", "_")
        with engine.connect() as conn:
            conn.execute(text(f"SET search_path TO {real_schema}, public"))
            with Session(conn) as session:
                app = session.get(App, uuid.UUID(app_id))
                slug = app.slug if app else app_id
        engine.dispose()
        return slug
    except Exception as exc:
        log.warning("Could not look up app slug: %s", exc)
        return app_id


def _get_org_id(org_slug: str) -> str:
    try:
        from sqlalchemy import create_engine, text
        from app.core.config import settings

        sync_url = settings.DATABASE_URL.replace("+asyncpg", "")
        engine = create_engine(sync_url)
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT id FROM platform.organizations WHERE slug = :slug"),
                {"slug": org_slug},
            ).fetchone()
        engine.dispose()
        return str(row[0]) if row else org_slug
    except Exception:
        return org_slug
