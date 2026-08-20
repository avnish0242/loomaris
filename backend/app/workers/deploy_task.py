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
import json
import logging
import uuid

from celery import Task

from app.workers.celery_app import celery_app

log = logging.getLogger(__name__)


def _update_deployment_sync(deployment_id: str, org_slug: str, **kwargs) -> None:
    """Synchronously update deployment record via a fresh sync DB connection."""
    from app.database import sync_tenant_session
    from app.models.org import Deployment

    with sync_tenant_session(org_slug) as session:
        dep = session.get(Deployment, uuid.UUID(deployment_id))
        if dep:
            for key, value in kwargs.items():
                setattr(dep, key, value)
            session.commit()


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

    # ── Resolve cloud account credentials (provider determined by the account itself) ──
    resolved = _get_provider_creds(cloud_account_id, org_slug)
    if not resolved:
        _update_deployment_sync(deployment_id, org_slug, status="failed",
                                outputs={"error": "Cloud account not found or not verified"})
        return {"success": False, "error": "Cloud account credentials unavailable"}
    provider, creds = resolved
    _update_deployment_sync(deployment_id, org_slug, cloud_provider=provider)

    # ── Detect app type + generate Pulumi program ─────────────────────────────
    target = detect_app_type(files)
    program = generate_pulumi_program(
        app_slug=_get_app_slug(app_id, org_slug),
        files=files,
        aws_region=creds.get("region", "us-east-1"),
        aws_account_id=creds.get("account_id", creds.get("project_id", creds.get("subscription_id", ""))),
        target=target,
        provider=provider,
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
    preview = pulumi_preview(program, creds, stack_name, provider=provider)

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
    apply_result = pulumi_up(program, creds, stack_name, provider=provider)

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
        from app.database import sync_tenant_session
        from app.models.org import App

        with sync_tenant_session(org_slug) as session:
            app = session.get(App, uuid.UUID(app_id))
            return app.slug if app else app_id
    except Exception as exc:
        log.warning("Could not look up app slug: %s", exc)
        return app_id


def _get_provider_creds(cloud_account_id: str, org_slug: str) -> tuple[str, dict] | None:
    """Resolve (provider, credentials) for a cloud account — the provider is read off
    the account itself, not passed in, so callers never have to know it up front.

    AWS: ephemeral session credentials via STS AssumeRole using Loomaris's deployer
    identity (unchanged from the original AWS-only implementation).
    Azure/GCP: the org's own service-principal / service-account credentials,
    decrypted here and never persisted outside this process — read from the generic
    `credentials_enc` column, with a fallback to the legacy AWS-named columns for
    Azure rows created before that column existed.
    """
    try:
        from app.core.config import settings
        from app.core.security import decrypt_value
        from app.database import sync_platform_session
        from app.models.platform import CloudAccount

        with sync_platform_session() as session:
            account = session.get(CloudAccount, uuid.UUID(cloud_account_id))
            if not account or account.status not in ("verified",):
                if account and account.status == "reconnect_required":
                    log.error(
                        "Cloud account %s requires reconnection (legacy keys rejected)",
                        cloud_account_id,
                    )
                return None
            provider = account.provider
            connection_type = account.connection_type
            role_arn = account.role_arn
            sts_external_id = account.sts_external_id
            region = account.region
            external_id = account.external_id
            credentials_enc = account.credentials_enc
            access_key_enc = account.access_key_enc
            secret_key_enc = account.secret_key_enc

        if provider == "aws":
            if connection_type != "role" or not role_arn or not sts_external_id:
                log.error(
                    "Cloud account %s is not configured for STS role-based access", cloud_account_id
                )
                return None
            import boto3
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
            return "aws", {
                "access_key_id": c["AccessKeyId"],
                "secret_access_key": c["SecretAccessKey"],
                "session_token": c["SessionToken"],
                "region": region or "us-east-1",
                "account_id": external_id,
            }

        if provider == "azure":
            if credentials_enc:
                creds = json.loads(decrypt_value(credentials_enc))
            elif access_key_enc and secret_key_enc and region:
                # Legacy rows (pre credentials_enc): client_id/client_secret/tenant_id
                # were stuffed into the AWS-named columns.
                creds = {
                    "client_id": decrypt_value(access_key_enc),
                    "client_secret": decrypt_value(secret_key_enc),
                    "tenant_id": decrypt_value(region),
                }
            else:
                log.error("Azure cloud account %s has no usable stored credentials", cloud_account_id)
                return None
            creds["subscription_id"] = external_id
            return "azure", creds

        if provider == "gcp":
            if not credentials_enc:
                log.error("GCP cloud account %s has no stored credentials", cloud_account_id)
                return None
            creds = json.loads(decrypt_value(credentials_enc))
            return "gcp", creds

        log.error("Unsupported cloud provider on account %s: %r", cloud_account_id, provider)
        return None

    except Exception as exc:
        log.error("Failed to retrieve cloud credentials: %s", exc)
        return None


def _get_org_plan(org_slug: str) -> str:
    try:
        from sqlalchemy import text

        from app.database import sync_platform_session

        with sync_platform_session() as session:
            org = session.execute(
                text("SELECT plan FROM platform.organizations WHERE slug = :slug"),
                {"slug": org_slug},
            ).fetchone()
            return org[0] if org else "pro"
    except Exception:
        return "pro"
