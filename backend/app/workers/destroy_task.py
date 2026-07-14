"""
Celery task: cloud_destroy_task
Tears down a previously deployed Pulumi stack.
Requires a persistent Pulumi state backend (PULUMI_STATE_BUCKET) — without it
the state is not found and destroy will silently no-op.
"""
import logging

from app.workers.celery_app import celery_app
from app.workers.deploy_task import _get_aws_creds, _update_deployment_sync

log = logging.getLogger(__name__)


@celery_app.task(
    name="app.workers.destroy_task.cloud_destroy_task",
    bind=True,
    max_retries=1,
    default_retry_delay=30,
    track_started=True,
)
def cloud_destroy_task(
    self,
    *,
    deployment_id: str,
    cloud_account_id: str,
    stack_name: str,
    org_slug: str,
) -> dict:
    """Destroy a Pulumi stack and mark the deployment as destroyed."""
    from datetime import datetime, timezone
    from app.services.iac.runner import pulumi_destroy

    log.info("Starting destroy task: deployment=%s stack=%s", deployment_id, stack_name)
    _update_deployment_sync(deployment_id, org_slug, status="destroying")

    aws_creds = _get_aws_creds(cloud_account_id, org_slug)
    if not aws_creds:
        _update_deployment_sync(deployment_id, org_slug, status="failed",
                                outputs={"error": "Cloud account not found or not verified"})
        return {"success": False, "error": "Cloud credentials unavailable"}

    result = pulumi_destroy(stack_name=stack_name, aws_creds=aws_creds)

    if not result.success:
        log.error("Destroy failed for stack %s: %s", stack_name, result.error)
        _update_deployment_sync(deployment_id, org_slug, status="failed",
                                outputs={"error": result.error, "stage": "destroy"})
        return {"success": False, "error": result.error}

    _update_deployment_sync(
        deployment_id, org_slug,
        status="destroyed",
        destroyed_at=datetime.now(timezone.utc),
    )
    log.info("Destroy complete: deployment=%s stack=%s", deployment_id, stack_name)
    return {"success": True, "stack_name": stack_name}
