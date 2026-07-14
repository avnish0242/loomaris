"""
Celery task: cloud_deploy_task
Runs the full cloud deployment pipeline:
  1. Load files from git
  2. Detect app type
  3. Generate + validate Pulumi program
  4. pulumi preview (returns preview for cost confirmation)
  5. pulumi up (if confirm_cost=True)
  6. Update Deployment record throughout
"""
import logging
import uuid

from celery import Task

from app.workers.celery_app import celery_app

log = logging.getLogger(__name__)


def _update_deployment_sync(deployment_id: str, org_slug: str, **kwargs) -> None:
    """Synchronously update deployment record via a fresh sync DB connection."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.core.config import settings
    from app.models.org import Deployment

    sync_url = settings.DATABASE_URL.replace("+asyncpg", "")
    engine = create_engine(sync_url)
    real_schema = "org_" + org_slug.replace("-", "_")

    with engine.connect() as conn:
        conn.execute(
            __import__("sqlalchemy").text(f"SET search_path TO {real_schema}, platform, public")
        )
        with Session(conn) as session:
            dep = session.get(Deployment, uuid.UUID(deployment_id))
            if dep:
                for key, value in kwargs.items():
                    setattr(dep, key, value)
                session.commit()
    engine.dispose()


@celery_app.task(
    name="app.workers.deploy_task.cloud_deploy_task",
    bind=True,
    max_retries=0,
    track_started=True,
)
def cloud_deploy_task(
    self: Task,
    *,
    app_id: str,
    deployment_id: str,
    cloud_account_id: str,
    environment: str,
    confirm_cost: bool,
    env_vars: dict,
    org_slug: str,
) -> dict:
    """Execute a full cloud deployment via Pulumi."""
    from datetime import datetime, timezone

    from app.services.git_service import get_current_files
    from app.services.iac.detector import detect_app_type
    from app.services.iac.generator import generate_pulumi_program
    from app.services.iac.validator import validate
    from app.services.iac.runner import pulumi_preview, pulumi_up

    log.info("Starting cloud deploy task: app=%s deployment=%s", app_id, deployment_id)
    _update_deployment_sync(deployment_id, org_slug, status="planning")

    # ── Load files from git ───────────────────────────────────────────────────
    files = get_current_files(_slugify(app_id, org_slug))
    if not files:
        _update_deployment_sync(deployment_id, org_slug, status="failed", outputs={"error": "No files"})
        return {"success": False, "error": "No generated files found"}

    # ── Resolve cloud account credentials ─────────────────────────────────────
    aws_creds = _get_aws_creds(cloud_account_id, org_slug)
    if not aws_creds:
        _update_deployment_sync(deployment_id, org_slug, status="failed",
                                outputs={"error": "Cloud account not found or not verified"})
        return {"success": False, "error": "Cloud account credentials unavailable"}

    # ── Detect app type + generate Pulumi program ─────────────────────────────
    target = detect_app_type(files)
    program = generate_pulumi_program(
        app_slug=_get_app_slug(app_id, org_slug),
        files=files,
        aws_region=aws_creds.get("region", "us-east-1"),
        aws_account_id=aws_creds.get("account_id", ""),
        target=target,
    )

    # ── Validate program ──────────────────────────────────────────────────────
    plan_result = _get_org_plan(org_slug)
    validation = validate(program, org_plan=plan_result)
    if not validation.valid:
        _update_deployment_sync(deployment_id, org_slug, status="failed",
                                outputs={"error": validation.error})
        return {"success": False, "error": validation.error}

    # ── Pulumi preview ────────────────────────────────────────────────────────
    stack_name = f"loomaris-{org_slug}-{_get_app_slug(app_id, org_slug)}-{environment}"
    preview = pulumi_preview(program, aws_creds, stack_name)

    if not preview.success:
        _update_deployment_sync(deployment_id, org_slug, status="failed",
                                outputs={"error": preview.error, "stage": "preview"})
        return {"success": False, "error": preview.error}

    _update_deployment_sync(
        deployment_id, org_slug,
        status="preview_ready",
        cost_snapshot={"plan_summary": preview.plan_summary, "resource_count": preview.resource_count},
    )

    if not confirm_cost:
        return {
            "success": True,
            "stage": "preview",
            "deployment_id": deployment_id,
            "resource_count": preview.resource_count,
            "message": "Preview ready. Set confirm_cost=true to apply.",
        }

    # ── Pulumi up ─────────────────────────────────────────────────────────────
    _update_deployment_sync(deployment_id, org_slug, status="applying")
    apply_result = pulumi_up(program, aws_creds, stack_name)

    if not apply_result.success:
        _update_deployment_sync(deployment_id, org_slug, status="failed",
                                outputs={"error": apply_result.error})
        return {"success": False, "error": apply_result.error}

    _update_deployment_sync(
        deployment_id, org_slug,
        status="success",
        pulumi_stack_id=stack_name,
        outputs=apply_result.outputs,
        deployed_at=datetime.now(timezone.utc),
    )

    log.info("Cloud deploy complete: deployment=%s outputs=%s", deployment_id, apply_result.outputs)
    return {
        "success": True,
        "deployment_id": deployment_id,
        "outputs": apply_result.outputs,
        "stack_name": stack_name,
    }


def _slugify(app_id: str, org_slug: str) -> str:
    """Look up the app slug from the DB synchronously."""
    return _get_app_slug(app_id, org_slug)


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
            conn.execute(text(f"SET search_path TO {real_schema}, platform, public"))
            with Session(conn) as session:
                app = session.get(App, uuid.UUID(app_id))
                slug = app.slug if app else app_id
        engine.dispose()
        return slug
    except Exception as exc:
        log.warning("Could not look up app slug: %s", exc)
        return app_id


def _get_aws_creds(cloud_account_id: str, org_slug: str) -> dict | None:
    """Retrieve AWS credentials via STS AssumeRole using the stored role ARN.
    Returns None if the account is not found, not verified, or uses legacy key-based auth.
    """
    try:
        import boto3
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import Session
        from app.core.config import settings
        from app.models.platform import CloudAccount

        sync_url = settings.DATABASE_URL.replace("+asyncpg", "")
        engine = create_engine(sync_url)

        with engine.connect() as conn:
            conn.execute(text("SET search_path TO platform, public"))
            with Session(conn) as session:
                account = session.get(CloudAccount, uuid.UUID(cloud_account_id))
                if not account or account.status not in ("verified",):
                    if account and account.status == "reconnect_required":
                        log.error(
                            "Cloud account %s requires reconnection via STS role (legacy keys rejected)",
                            cloud_account_id,
                        )
                    return None

                if account.connection_type != "role" or not account.role_arn or not account.sts_external_id:
                    log.error(
                        "Cloud account %s is not configured for STS role-based access", cloud_account_id
                    )
                    return None

                role_arn = account.role_arn
                sts_external_id = account.sts_external_id
                region = account.region or "us-east-1"
                account_id = account.external_id

        engine.dispose()

        # Assume the org's role using Loomaris's deployer credentials
        deployer_session = boto3.Session(
            aws_access_key_id=settings.LOOMARIS_DEPLOYER_ACCESS_KEY,
            aws_secret_access_key=settings.LOOMARIS_DEPLOYER_SECRET_KEY,
            region_name="us-east-1",
        )
        sts = deployer_session.client("sts")
        resp = sts.assume_role(
            RoleArn=role_arn,
            RoleSessionName=f"loomaris-deploy-{cloud_account_id[:8]}",
            ExternalId=sts_external_id,
            DurationSeconds=3600,
        )
        c = resp["Credentials"]
        return {
            "access_key_id": c["AccessKeyId"],
            "secret_access_key": c["SecretAccessKey"],
            "session_token": c["SessionToken"],
            "region": region,
            "account_id": account_id,
        }

    except Exception as exc:
        log.error("Failed to retrieve cloud credentials via STS: %s", exc)
        return None


def _get_org_plan(org_slug: str) -> str:
    try:
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import Session
        from app.core.config import settings

        sync_url = settings.DATABASE_URL.replace("+asyncpg", "")
        engine = create_engine(sync_url)

        with engine.connect() as conn:
            conn.execute(text("SET search_path TO platform, public"))
            with Session(conn) as session:
                org = session.execute(
                    text("SELECT plan FROM platform.organizations WHERE slug = :slug"),
                    {"slug": org_slug},
                ).fetchone()
                plan = org[0] if org else "pro"
        engine.dispose()
        return plan
    except Exception:
        return "pro"
