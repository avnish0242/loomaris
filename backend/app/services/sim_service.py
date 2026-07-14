"""
Ephemeral ECS Fargate simulation service.

Uses Loomaris's own deployer credentials (LOOMARIS_DEPLOYER_ACCESS_KEY/SECRET)
to run short-lived Fargate tasks in the dedicated Loomaris sim AWS account.
All AWS calls happen in executors to avoid blocking the event loop.
"""
import asyncio
import base64
import hashlib
import logging
import time
from datetime import datetime, timedelta, timezone

import boto3
from botocore.exceptions import ClientError

from app.core.config import settings

log = logging.getLogger(__name__)

_FARGATE_VCPU_PER_HOUR = 0.04048     # $ per vCPU-hour (us-east-1, Fargate)
_FARGATE_MEM_GB_PER_HOUR = 0.004445  # $ per GB-hour


def _deployer_session() -> boto3.Session:
    return boto3.Session(
        aws_access_key_id=settings.LOOMARIS_DEPLOYER_ACCESS_KEY,
        aws_secret_access_key=settings.LOOMARIS_DEPLOYER_SECRET_KEY,
        region_name="us-east-1",
    )


def get_ttl_for_app_type(app_type: str) -> int:
    """Return simulation TTL in seconds based on detected app type."""
    return {"static": 120, "lambda": 300, "container": 600}.get(app_type, 900)


# ─── Budget gate ──────────────────────────────────────────────────────────────

def check_user_budget_sync(user_id: str, org_id: str) -> float:
    """Synchronous check: sum cost_usd from platform.simulation_budget_log in last 30 days.
    Returns remaining budget (max $5.00 - spent). Raises ValueError if exceeded.
    """
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import create_engine, text
    from app.core.config import settings

    sync_url = settings.DATABASE_URL.replace("+asyncpg", "")
    engine = create_engine(sync_url)
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)

    with engine.connect() as conn:
        result = conn.execute(
            text("""
                SELECT COALESCE(SUM(cost_usd), 0)
                FROM platform.simulation_budget_log
                WHERE user_id = :uid AND created_at >= :cutoff
            """),
            {"uid": user_id, "cutoff": cutoff},
        )
        spent = float(result.scalar() or 0)

    engine.dispose()
    remaining = round(5.00 - spent, 4)
    if remaining <= 0:
        raise ValueError(
            f"Monthly simulation budget exceeded (spent ${spent:.2f} / $5.00). "
            "Budget resets 30 days after your first simulation."
        )
    return remaining


async def check_user_budget(user_id: str, org_id: str) -> float:
    return await asyncio.get_event_loop().run_in_executor(
        None, check_user_budget_sync, user_id, org_id
    )


# ─── Docker image build + ECR push ───────────────────────────────────────────

def _build_and_push_sync(app_slug: str, files: list, org_slug: str) -> str:
    """Build a Docker image from generated files and push to ECR. Returns image URI."""
    import docker as docker_sdk
    import tempfile
    import os

    if not settings.SIM_ECR_BASE_URI:
        raise ValueError("SIM_ECR_BASE_URI is not configured — cannot push simulation image")

    commit_sha = hashlib.sha256(
        "\n".join(f.path + f.content for f in files).encode()
    ).hexdigest()[:12]
    tag = f"sim-{commit_sha}"
    repo_name = f"{org_slug}-{app_slug}"
    image_uri = f"{settings.SIM_ECR_BASE_URI}/{repo_name}:{tag}"

    # Build image via host Docker socket
    client = docker_sdk.from_env()

    with tempfile.TemporaryDirectory() as tmpdir:
        for f in files:
            dest = os.path.join(tmpdir, f.path)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "w") as fh:
                fh.write(f.content)

        # Ensure there's a Dockerfile; generate a minimal one if missing
        dockerfile_path = os.path.join(tmpdir, "Dockerfile")
        if not os.path.exists(dockerfile_path):
            with open(dockerfile_path, "w") as fh:
                fh.write(
                    "FROM python:3.11-slim\n"
                    "WORKDIR /app\n"
                    "COPY . .\n"
                    "RUN pip install --no-cache-dir -r requirements.txt 2>/dev/null || true\n"
                    "EXPOSE 8000\n"
                    'CMD ["python", "-m", "http.server", "8000"]\n'
                )

        image, _ = client.images.build(path=tmpdir, tag=image_uri, rm=True)

    # ECR auth + push
    session = _deployer_session()
    ecr = session.client("ecr")

    # Ensure repo exists
    repo_base = settings.SIM_ECR_BASE_URI.split(".amazonaws.com/")[-1]
    full_repo = f"{repo_base}/{repo_name}"
    try:
        ecr.create_repository(repositoryName=full_repo)
    except ecr.exceptions.RepositoryAlreadyExistsException:
        pass

    # Get auth token
    token_resp = ecr.get_authorization_token()
    auth = token_resp["authorizationData"][0]
    auth_token = base64.b64decode(auth["authorizationToken"]).decode()
    username, password = auth_token.split(":", 1)
    registry = auth["proxyEndpoint"]

    client.login(username=username, password=password, registry=registry)
    for _ in client.images.push(image_uri, stream=True, decode=True):
        pass  # consume push output

    return image_uri


async def build_and_push_image(app_slug: str, files: list, org_slug: str) -> str:
    return await asyncio.get_event_loop().run_in_executor(
        None, _build_and_push_sync, app_slug, files, org_slug
    )


# ─── ECS Fargate task ─────────────────────────────────────────────────────────

def _run_fargate_task_sync(image_uri: str, app_slug: str, org_slug: str, ttl_seconds: int, session_id: str) -> str:
    if not settings.SIM_ECS_CLUSTER:
        raise ValueError("SIM_ECS_CLUSTER is not configured")

    session = _deployer_session()
    ecs = session.client("ecs")

    task_family = f"loomaris-sim-{org_slug}-{app_slug}"
    expires_iso = (datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)).isoformat()

    # Register a fresh task definition (ephemeral, not reused between sims)
    ecs.register_task_definition(
        family=task_family,
        networkMode="awsvpc",
        requiresCompatibilities=["FARGATE"],
        cpu="256",
        memory="512",
        executionRoleArn=settings.SIM_TASK_EXECUTION_ROLE,
        containerDefinitions=[{
            "name": "app",
            "image": image_uri,
            "portMappings": [{"containerPort": 8000, "protocol": "tcp"}],
            "logConfiguration": {
                "logDriver": "awslogs",
                "options": {
                    "awslogs-group": "/loomaris/sim",
                    "awslogs-region": "us-east-1",
                    "awslogs-stream-prefix": session_id,
                    "awslogs-create-group": "true",
                },
            },
            "environment": [
                {"name": "PORT", "value": "8000"},
                {"name": "LOOMARIS_SIM_SESSION", "value": session_id},
            ],
        }],
        tags=[
            {"key": "loomaris:sim-session", "value": session_id},
            {"key": "loomaris:expires-at", "value": expires_iso},
            {"key": "loomaris:sim-cost-center", "value": "sim"},
        ],
    )

    resp = ecs.run_task(
        cluster=settings.SIM_ECS_CLUSTER,
        launchType="FARGATE",
        taskDefinition=task_family,
        networkConfiguration={
            "awsvpcConfiguration": {
                "subnets": [settings.SIM_SUBNET_ID],
                "securityGroups": [settings.SIM_SECURITY_GROUP_ID],
                "assignPublicIp": "ENABLED",
            }
        },
        tags=[
            {"key": "loomaris:sim-session", "value": session_id},
            {"key": "loomaris:expires-at", "value": expires_iso},
        ],
    )

    if not resp["tasks"]:
        failures = resp.get("failures", [])
        raise RuntimeError(f"ECS run_task failed: {failures}")

    return resp["tasks"][0]["taskArn"]


async def run_fargate_task(image_uri: str, app_slug: str, org_slug: str, ttl_seconds: int, session_id: str) -> str:
    return await asyncio.get_event_loop().run_in_executor(
        None, _run_fargate_task_sync, image_uri, app_slug, org_slug, ttl_seconds, session_id
    )


# ─── Poll for public IP ───────────────────────────────────────────────────────

def _poll_public_ip_sync(task_arn: str, timeout: int = 120) -> str | None:
    session = _deployer_session()
    ecs = session.client("ecs")
    ec2 = session.client("ec2")

    deadline = time.time() + timeout
    cluster = settings.SIM_ECS_CLUSTER

    while time.time() < deadline:
        time.sleep(4)
        tasks = ecs.describe_tasks(cluster=cluster, tasks=[task_arn])["tasks"]
        if not tasks:
            continue
        task = tasks[0]
        if task["lastStatus"] in ("STOPPED", "DEPROVISIONING"):
            return None

        attachments = task.get("attachments", [])
        for att in attachments:
            if att.get("type") != "ElasticNetworkInterface":
                continue
            eni_id = next(
                (d["value"] for d in att.get("details", []) if d["name"] == "networkInterfaceId"),
                None,
            )
            if not eni_id:
                continue
            ifaces = ec2.describe_network_interfaces(NetworkInterfaceIds=[eni_id])
            assoc = ifaces["NetworkInterfaces"][0].get("Association", {})
            ip = assoc.get("PublicIp")
            if ip:
                return ip

    return None


async def poll_task_public_ip(task_arn: str) -> str | None:
    return await asyncio.get_event_loop().run_in_executor(None, _poll_public_ip_sync, task_arn)


# ─── Teardown ─────────────────────────────────────────────────────────────────

def _stop_simulation_sync(task_arn: str | None, image_uri: str | None) -> None:
    session = _deployer_session()

    if task_arn and settings.SIM_ECS_CLUSTER:
        try:
            ecs = session.client("ecs")
            ecs.stop_task(cluster=settings.SIM_ECS_CLUSTER, task=task_arn, reason="Loomaris simulation ended")
        except ClientError as exc:
            log.warning("Could not stop ECS task %s: %s", task_arn, exc)

    if image_uri and settings.SIM_ECR_BASE_URI:
        try:
            ecr = session.client("ecr")
            # image_uri format: REGISTRY/REPO:TAG
            parts = image_uri.split("/", 1)
            repo_and_tag = parts[-1]
            repo_name, tag = repo_and_tag.rsplit(":", 1)
            ecr.batch_delete_image(
                repositoryName=repo_name,
                imageIds=[{"imageTag": tag}],
            )
        except ClientError as exc:
            log.warning("Could not delete ECR image %s: %s", image_uri, exc)


async def stop_simulation(task_arn: str | None, image_uri: str | None) -> None:
    await asyncio.get_event_loop().run_in_executor(None, _stop_simulation_sync, task_arn, image_uri)


def _schedule_teardown_sync(task_arn: str, image_uri: str, session_id: str, expires_at: datetime) -> None:
    if not settings.SIM_TEARDOWN_LAMBDA_ARN:
        log.warning("SIM_TEARDOWN_LAMBDA_ARN not set — teardown will not be scheduled")
        return

    session = _deployer_session()
    scheduler = session.client("scheduler")

    # EventBridge Scheduler one-time schedule (at expression)
    at_expr = expires_at.strftime("at(%Y-%m-%dT%H:%M:%S)")
    schedule_name = f"loomaris-sim-{session_id[:16]}"

    try:
        scheduler.create_schedule(
            GroupName="loomaris-sim-teardowns",
            Name=schedule_name,
            ScheduleExpression=at_expr,
            ScheduleExpressionTimezone="UTC",
            FlexibleTimeWindow={"Mode": "OFF"},
            Target={
                "Arn": settings.SIM_TEARDOWN_LAMBDA_ARN,
                "RoleArn": settings.SIM_TASK_EXECUTION_ROLE,
                "Input": f'{{"task_arn": "{task_arn}", "image_uri": "{image_uri}", "session_id": "{session_id}"}}',
            },
            ActionAfterCompletion="DELETE",
        )
    except ClientError as exc:
        log.warning("Could not schedule teardown for session %s: %s", session_id, exc)


async def schedule_teardown(task_arn: str, image_uri: str, session_id: str, expires_at: datetime) -> None:
    await asyncio.get_event_loop().run_in_executor(
        None, _schedule_teardown_sync, task_arn, image_uri, session_id, expires_at
    )


# ─── Cost recording ───────────────────────────────────────────────────────────

def record_cost_sync(user_id: str, org_id: str, session_id: str, ttl_seconds: int) -> float:
    """Compute and persist simulation cost based on actual TTL."""
    vcpu = 0.25
    mem_gb = 0.5
    hours = ttl_seconds / 3600
    cost = round((vcpu * _FARGATE_VCPU_PER_HOUR + mem_gb * _FARGATE_MEM_GB_PER_HOUR) * hours, 6)

    from sqlalchemy import create_engine, text
    sync_url = settings.DATABASE_URL.replace("+asyncpg", "")
    engine = create_engine(sync_url)
    with engine.connect() as conn:
        conn.execute(
            text("""
                INSERT INTO platform.simulation_budget_log
                    (user_id, org_id, simulation_session_id, cost_usd)
                VALUES (:uid, :oid, :sid, :cost)
            """),
            {"uid": user_id, "oid": org_id, "sid": session_id, "cost": cost},
        )
        conn.commit()
    engine.dispose()
    return cost
