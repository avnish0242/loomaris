import io
import json
import uuid
import zipfile
from datetime import datetime, timezone
from typing import Literal

import boto3
from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import TenantContext, get_current_user, get_tenant_context
from app.core.config import settings
from app.database import get_db
from app.models.org import App, ChatSession, CostEstimate, Deployment
from app.models.platform import User
from app.services.chat_service import create_session, get_or_create_app
from app.services.deploy_service import build_and_deploy, get_container_status
from app.services.git_service import (
    checkout_commit,
    create_zip_archive,
    get_commit_log,
    get_current_files,
)
from app.services.iac.generator import generate_pulumi_program
from app.services.iac.detector import detect_app_type

router = APIRouter(prefix="/apps", tags=["apps"])


class CreateAppRequest(BaseModel):
    name: str
    app_type: str = "web"


class CreateSessionRequest(BaseModel):
    title: str | None = None


class CloudDeployRequest(BaseModel):
    cloud_account_id: uuid.UUID
    environment: Literal["preview", "staging", "production"] = "preview"
    confirm_cost: bool = False
    env_vars: dict[str, str] = {}


class RollbackRequest(BaseModel):
    deployment_id: uuid.UUID | None = None
    commit_sha: str | None = None


def _app_out(app: App) -> dict:
    return {
        "id": str(app.id),
        "name": app.name,
        "slug": app.slug,
        "app_type": app.app_type,
        "created_at": app.created_at.isoformat() if app.created_at else None,
    }


def _session_out(s: ChatSession) -> dict:
    return {
        "id": str(s.id),
        "app_id": str(s.app_id) if s.app_id else None,
        "title": s.title,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "last_active_at": s.last_active_at.isoformat() if s.last_active_at else None,
    }


def _deployment_out(d: Deployment) -> dict:
    return {
        "id": str(d.id),
        "app_id": str(d.app_id),
        "environment": d.environment,
        "status": d.status,
        "pulumi_stack_id": d.pulumi_stack_id,
        "outputs": d.outputs,
        "cost_snapshot": d.cost_snapshot,
        "deployed_at": d.deployed_at.isoformat() if d.deployed_at else None,
        "created_at": d.created_at.isoformat() if d.created_at else None,
    }


# ─── CRUD ──────────────────────────────────────────────────────────────────────

@router.post("", status_code=status.HTTP_201_CREATED, summary="Create a new app")
async def create_app(
    body: CreateAppRequest,
    ctx: TenantContext = Depends(get_tenant_context),
):
    app = await get_or_create_app(ctx.session, name=body.name, app_type=body.app_type)
    await ctx.session.commit()
    await ctx.session.refresh(app)
    return _app_out(app)


@router.get("", summary="List all apps")
async def list_apps(
    ctx: TenantContext = Depends(get_tenant_context),
):
    result = await ctx.session.execute(
        select(App).where(App.archived_at.is_(None)).order_by(App.created_at.desc())
    )
    return [_app_out(a) for a in result.scalars().all()]


@router.get("/{app_id}", summary="Get a single app")
async def get_app(
    app_id: uuid.UUID,
    ctx: TenantContext = Depends(get_tenant_context),
):
    return _app_out(await _get_app_or_404(app_id, ctx.session))


@router.post(
    "/{app_id}/sessions",
    status_code=status.HTTP_201_CREATED,
    summary="Start a chat session for an app",
)
async def create_app_session(
    app_id: uuid.UUID,
    body: CreateSessionRequest,
    ctx: TenantContext = Depends(get_tenant_context),
):
    result = await ctx.session.execute(select(App).where(App.id == app_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="App not found")

    session = await create_session(
        ctx.session, user_id=ctx.user.id, app_id=app_id, title=body.title
    )
    await ctx.session.commit()
    await ctx.session.refresh(session)
    return _session_out(session)


@router.get("/{app_id}/sessions", summary="List chat sessions for an app")
async def list_app_sessions(
    app_id: uuid.UUID,
    ctx: TenantContext = Depends(get_tenant_context),
):
    result = await ctx.session.execute(
        select(ChatSession)
        .where(ChatSession.app_id == app_id)
        .order_by(ChatSession.last_active_at.desc())
    )
    return [_session_out(s) for s in result.scalars().all()]


# ─── Files / Git ───────────────────────────────────────────────────────────────

@router.get("/{app_id}/files", summary="Get current generated files from git")
async def get_app_files(
    app_id: uuid.UUID,
    ctx: TenantContext = Depends(get_tenant_context),
):
    app = await _get_app_or_404(app_id, ctx.session)
    files = get_current_files(app.slug)
    commits = get_commit_log(app.slug, limit=5)
    return {
        "app_slug": app.slug,
        "files": [{"path": f.path, "content": f.content} for f in files],
        "recent_commits": commits,
    }


@router.get("/{app_id}/archive", summary="Download current files as a zip")
async def download_archive(
    app_id: uuid.UUID,
    ctx: TenantContext = Depends(get_tenant_context),
):
    app = await _get_app_or_404(app_id, ctx.session)
    archive_bytes = create_zip_archive(app.slug)
    if not archive_bytes:
        raise HTTPException(status_code=404, detail="No files generated yet for this app")
    return Response(
        content=archive_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={app.slug}.zip"},
    )


# ─── Local Docker Deploy ────────────────────────────────────────────────────────

@router.get("/{app_id}/deploy/status", summary="Current local Docker container status")
async def deploy_status(
    app_id: uuid.UUID,
    ctx: TenantContext = Depends(get_tenant_context),
):
    app = await _get_app_or_404(app_id, ctx.session)
    container_status = await get_container_status(app.slug)

    result = await ctx.session.execute(
        select(Deployment)
        .where(Deployment.app_id == app_id)
        .order_by(Deployment.created_at.desc())
        .limit(1)
    )
    dep = result.scalar_one_or_none()
    return {
        **container_status,
        "last_deployment": _deployment_out(dep) if dep else None,
    }


@router.post("/{app_id}/deploy", summary="Build and run locally via Docker (SSE stream)")
async def deploy_app(
    app_id: uuid.UUID,
    ctx: TenantContext = Depends(get_tenant_context),
):
    app = await _get_app_or_404(app_id, ctx.session)
    files = get_current_files(app.slug)
    if not files:
        raise HTTPException(status_code=400, detail="No files generated yet. Chat with Loomaris first.")

    deployment = Deployment(
        app_id=app_id,
        environment="preview",
        status="building",
    )
    ctx.session.add(deployment)
    await ctx.session.commit()
    await ctx.session.refresh(deployment)
    dep_id = deployment.id

    async def _stream():
        final_status = "failed"
        outputs: dict = {}

        async for event in build_and_deploy(app.slug, files):
            yield event
            if event.startswith("data: "):
                try:
                    data = json.loads(event[6:].strip())
                    if data.get("type") == "done":
                        final_status = "running"
                        outputs = {
                            "url": data.get("url"),
                            "port": data.get("port"),
                            "container_id": data.get("container_id"),
                            "image_tag": data.get("image_tag"),
                        }
                except Exception:
                    pass

        result = await ctx.session.execute(select(Deployment).where(Deployment.id == dep_id))
        dep = result.scalar_one_or_none()
        if dep:
            dep.status = final_status
            dep.outputs = outputs if outputs else None
            dep.deployed_at = datetime.now(timezone.utc) if final_status == "running" else None
            await ctx.session.commit()

    return StreamingResponse(_stream(), media_type="text/event-stream")


@router.delete("/{app_id}/preview", summary="Stop and remove the local preview container")
async def stop_preview(
    app_id: uuid.UUID,
    ctx: TenantContext = Depends(get_tenant_context),
):
    import docker as docker_sdk
    from docker.errors import NotFound as DockerNotFound

    app = await _get_app_or_404(app_id, ctx.session)
    container_name = f"loomaris-preview-{app.slug}"
    try:
        client = docker_sdk.from_env()
        container = client.containers.get(container_name)
        container.stop(timeout=5)
        container.remove()
    except DockerNotFound:
        pass
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to stop preview: {exc}")
    return {"ok": True}


# ─── Cloud Deploy (Pulumi) ─────────────────────────────────────────────────────

@router.post("/{app_id}/cloud-deploy", summary="Deploy to cloud via Pulumi (async task)")
async def cloud_deploy(
    app_id: uuid.UUID,
    body: CloudDeployRequest,
    ctx: TenantContext = Depends(get_tenant_context),
):
    from app.workers.deploy_task import cloud_deploy_task

    app = await _get_app_or_404(app_id, ctx.session)
    files = get_current_files(app.slug)
    if not files:
        raise HTTPException(status_code=400, detail="No files generated yet. Chat with Loomaris first.")

    deployment = Deployment(
        app_id=app_id,
        cloud_account_id=body.cloud_account_id,
        environment=body.environment,
        status="queued",
    )
    ctx.session.add(deployment)
    await ctx.session.commit()
    await ctx.session.refresh(deployment)

    task = cloud_deploy_task.apply_async(
        kwargs={
            "app_id": str(app_id),
            "deployment_id": str(deployment.id),
            "cloud_account_id": str(body.cloud_account_id),
            "environment": body.environment,
            "confirm_cost": body.confirm_cost,
            "env_vars": body.env_vars,
            "org_slug": ctx.org.slug,
        },
        queue="deploy",
    )

    return {
        "deployment_id": str(deployment.id),
        "task_id": task.id,
        "status": "queued",
        "message": "Deploy task queued. Poll /cloud-deploy/{deployment_id}/status for progress.",
    }


@router.get(
    "/{app_id}/cloud-deploy/{deployment_id}/status",
    summary="Poll cloud deployment status",
)
async def cloud_deploy_status(
    app_id: uuid.UUID,
    deployment_id: uuid.UUID,
    ctx: TenantContext = Depends(get_tenant_context),
):
    result = await ctx.session.execute(
        select(Deployment).where(
            Deployment.id == deployment_id,
            Deployment.app_id == app_id,
        )
    )
    dep = result.scalar_one_or_none()
    if not dep:
        raise HTTPException(status_code=404, detail="Deployment not found")
    return _deployment_out(dep)


@router.delete(
    "/{app_id}/cloud-deploy/{deployment_id}",
    summary="Destroy a cloud deployment (runs pulumi destroy)",
)
async def destroy_cloud_deploy(
    app_id: uuid.UUID,
    deployment_id: uuid.UUID,
    ctx: TenantContext = Depends(get_tenant_context),
):
    from app.workers.destroy_task import cloud_destroy_task

    result = await ctx.session.execute(
        select(Deployment).where(
            Deployment.id == deployment_id,
            Deployment.app_id == app_id,
        )
    )
    dep = result.scalar_one_or_none()
    if not dep:
        raise HTTPException(status_code=404, detail="Deployment not found")

    if dep.status in ("destroying", "destroyed"):
        raise HTTPException(status_code=409, detail=f"Deployment is already {dep.status}")

    if not dep.pulumi_stack_id:
        raise HTTPException(status_code=400, detail="No Pulumi stack recorded — nothing to destroy")

    if not dep.cloud_account_id:
        raise HTTPException(status_code=400, detail="No cloud account linked to this deployment")

    task = cloud_destroy_task.apply_async(
        kwargs={
            "deployment_id": str(deployment_id),
            "cloud_account_id": str(dep.cloud_account_id),
            "stack_name": dep.pulumi_stack_id,
            "org_slug": ctx.org.slug,
        },
        queue="deploy",
    )

    dep.status = "queued_destroy"
    await ctx.session.commit()

    return {"deployment_id": str(deployment_id), "task_id": task.id, "status": "queued_destroy"}


# ─── Rollback ──────────────────────────────────────────────────────────────────

@router.post("/{app_id}/rollback", summary="Roll back to a previous deployment or commit")
async def rollback_app(
    app_id: uuid.UUID,
    body: RollbackRequest,
    ctx: TenantContext = Depends(get_tenant_context),
):
    from app.workers.deploy_task import cloud_deploy_task

    app = await _get_app_or_404(app_id, ctx.session)

    commit_sha: str | None = body.commit_sha

    if not commit_sha and body.deployment_id:
        dep_result = await ctx.session.execute(
            select(Deployment).where(
                Deployment.id == body.deployment_id,
                Deployment.app_id == app_id,
            )
        )
        prev_dep = dep_result.scalar_one_or_none()
        if not prev_dep:
            raise HTTPException(status_code=404, detail="Deployment not found")

        if prev_dep.turn_id:
            turn_result = await ctx.session.execute(
                select(ChatSession).where(ChatSession.id == prev_dep.turn_id)
            )
            # Fetch the chat turn for the commit SHA
            from app.models.org import ChatTurn
            turn_result = await ctx.session.execute(
                select(ChatTurn).where(ChatTurn.id == prev_dep.turn_id)
            )
            turn = turn_result.scalar_one_or_none()
            if turn:
                commit_sha = turn.git_commit_sha

    if not commit_sha:
        raise HTTPException(
            status_code=400,
            detail="Provide deployment_id (with a linked git commit) or commit_sha",
        )

    try:
        checkout_commit(app.slug, commit_sha)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Git checkout failed: {exc}")

    new_deployment = Deployment(
        app_id=app_id,
        environment="preview",
        status="rolling_back",
    )
    ctx.session.add(new_deployment)
    await ctx.session.commit()
    await ctx.session.refresh(new_deployment)

    if body.deployment_id:
        task = cloud_deploy_task.apply_async(
            kwargs={
                "app_id": str(app_id),
                "deployment_id": str(new_deployment.id),
                "cloud_account_id": str(prev_dep.cloud_account_id) if prev_dep.cloud_account_id else None,
                "environment": "preview",
                "confirm_cost": True,
                "env_vars": {},
                "org_slug": ctx.org.slug,
            },
            queue="deploy",
        )
        task_id = task.id
    else:
        task_id = None

    return {
        "new_deployment_id": str(new_deployment.id),
        "task_id": task_id,
        "rolled_back_to": commit_sha,
    }


# ─── Export ────────────────────────────────────────────────────────────────────

@router.post("/{app_id}/export", summary="Export source code + IaC as a ZIP (S3 signed URL)")
async def export_app(
    app_id: uuid.UUID,
    ctx: TenantContext = Depends(get_tenant_context),
):
    app = await _get_app_or_404(app_id, ctx.session)
    files = get_current_files(app.slug)
    if not files:
        raise HTTPException(status_code=404, detail="No files generated yet for this app")

    # Generate Pulumi IaC for the current state
    iac_content: str | None = None
    try:
        target = detect_app_type(files)
        iac_content = generate_pulumi_program(
            app_slug=app.slug,
            files=files,
            aws_region="us-east-1",
            aws_account_id="000000000000",
            target=target,
        )
    except Exception:
        iac_content = None

    # Build the ZIP bundle
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.writestr(f"source_code/{f.path}", f.content)
        if iac_content:
            zf.writestr("iac/pulumi/__main__.py", iac_content)
            zf.writestr("iac/pulumi/Pulumi.yaml", f"name: {app.slug}\nruntime: python\n")
        zf.writestr(
            "README.md",
            f"# {app.name}\n\nExported from Loomaris.\n\n"
            "## Source code\nSee `source_code/`\n\n"
            "## Infrastructure as Code\nSee `iac/pulumi/` — run `pulumi up` to deploy.\n",
        )
    zip_bytes = buf.getvalue()

    # Try uploading to S3 for a signed URL; fall back to direct download
    try:
        if settings.AWS_ENDPOINT_URL or not settings.is_dev:
            s3_kwargs: dict = {}
            if settings.AWS_ENDPOINT_URL:
                s3_kwargs["endpoint_url"] = settings.AWS_ENDPOINT_URL
            s3 = boto3.client(
                "s3",
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_DEFAULT_REGION,
                **s3_kwargs,
            )
            bucket = "loomaris-exports"
            key = f"{ctx.org.slug}/{app_id}/{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}.zip"
            s3.put_object(Bucket=bucket, Key=key, Body=zip_bytes, ContentType="application/zip")
            url = s3.generate_presigned_url(
                "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=3600
            )
            return {"download_url": url, "expires_in_seconds": 3600}
    except (ClientError, Exception):
        pass

    # Direct download fallback (dev mode)
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={app.slug}-export.zip"},
    )


# ─── Permission Preflight ──────────────────────────────────────────────────────

class PreflightRequest(BaseModel):
    cloud_account_id: uuid.UUID


@router.post("/{app_id}/preflight", summary="Verify IAM permissions before cloud deploy")
async def run_preflight(
    app_id: uuid.UUID,
    body: PreflightRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    platform_db: AsyncSession = Depends(get_db),
):
    from app.services.cloud_service import run_permission_preflight
    from app.models.platform import CloudAccount

    app = await _get_app_or_404(app_id, ctx.session)

    result = await platform_db.execute(
        select(CloudAccount).where(
            CloudAccount.id == body.cloud_account_id,
            CloudAccount.org_id == ctx.org.id,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Cloud account not found")

    return await run_permission_preflight(
        platform_db, app.slug, body.cloud_account_id, ctx.org.id
    )


# ─── Simulation ────────────────────────────────────────────────────────────────

@router.post("/{app_id}/simulate", summary="Start an ephemeral ECS Fargate simulation session")
async def start_simulation(
    app_id: uuid.UUID,
    ctx: TenantContext = Depends(get_tenant_context),
    current_user: User = Depends(get_current_user),
):
    from app.workers.simulate_task import run_simulation
    from app.models.org import SimulationSession

    app = await _get_app_or_404(app_id, ctx.session)
    files = get_current_files(app.slug)
    if not files:
        raise HTTPException(status_code=400, detail="No files generated yet. Chat with Loomaris first.")

    session = SimulationSession(
        app_id=app_id,
        user_id=current_user.id,
        status="building",
    )
    ctx.session.add(session)
    await ctx.session.commit()
    await ctx.session.refresh(session)

    run_simulation.apply_async(
        kwargs={
            "app_id": str(app_id),
            "org_slug": ctx.org.slug,
            "user_id": str(current_user.id),
            "session_id": str(session.id),
        },
        queue="deploy",
    )

    return {
        "session_id": str(session.id),
        "status": "building",
        "url": None,
        "expires_at": None,
        "ttl_seconds": session.ttl_seconds,
    }


@router.get("/{app_id}/simulate/status", summary="Poll the latest simulation session status")
async def get_simulation_status(
    app_id: uuid.UUID,
    ctx: TenantContext = Depends(get_tenant_context),
):
    from app.models.org import SimulationSession
    from sqlalchemy import desc

    result = await ctx.session.execute(
        select(SimulationSession)
        .where(SimulationSession.app_id == app_id)
        .order_by(desc(SimulationSession.created_at))
        .limit(1)
    )
    sim = result.scalar_one_or_none()
    if not sim:
        raise HTTPException(status_code=404, detail="No simulation session found")
    return {
        "session_id": str(sim.id),
        "status": sim.status,
        "url": sim.url,
        "expires_at": sim.expires_at.isoformat() if sim.expires_at else None,
        "ttl_seconds": sim.ttl_seconds,
    }


@router.delete("/{app_id}/simulate", summary="Stop an active simulation session")
async def stop_simulation_endpoint(
    app_id: uuid.UUID,
    ctx: TenantContext = Depends(get_tenant_context),
):
    from app.models.org import SimulationSession
    from app.services.sim_service import stop_simulation
    from sqlalchemy import desc

    result = await ctx.session.execute(
        select(SimulationSession)
        .where(SimulationSession.app_id == app_id, SimulationSession.status == "running")
        .order_by(desc(SimulationSession.created_at))
        .limit(1)
    )
    sim = result.scalar_one_or_none()
    if not sim:
        raise HTTPException(status_code=404, detail="No active simulation found")

    await stop_simulation(sim.task_arn, sim.image_uri)
    sim.status = "stopped"
    await ctx.session.commit()
    return {"ok": True}


# ─── Cost Estimate ─────────────────────────────────────────────────────────────

@router.post("/{app_id}/cost-estimate", summary="Estimate cloud deployment costs (async task)")
async def start_cost_estimate(
    app_id: uuid.UUID,
    body: dict = {},
    ctx: TenantContext = Depends(get_tenant_context),
):
    from app.workers.cost_task import run_cost_estimate

    await _get_app_or_404(app_id, ctx.session)
    cloud_providers = body.get("cloud_providers", ["aws"]) if body else ["aws"]
    region_prefs = body.get("region_prefs", {}) if body else {}

    task = run_cost_estimate.apply_async(
        kwargs={
            "app_id": str(app_id),
            "cloud_providers": cloud_providers,
            "region_prefs": region_prefs,
            "org_slug": ctx.org.slug,
        },
        queue="cost",
    )
    return {"task_id": task.id, "status": "computing"}


@router.get("/{app_id}/cost-estimate/latest", summary="Get latest cost estimate for this app")
async def get_cost_estimate(
    app_id: uuid.UUID,
    ctx: TenantContext = Depends(get_tenant_context),
):
    await _get_app_or_404(app_id, ctx.session)
    result = await ctx.session.execute(
        select(CostEstimate)
        .where(CostEstimate.app_id == app_id)
        .order_by(CostEstimate.created_at.desc())
        .limit(1)
    )
    est = result.scalar_one_or_none()
    if not est:
        # Return placeholder options while no real estimate exists yet
        return {
            "status": "no_estimate",
            "options": [
                {
                    "id": "local",
                    "label": "Local Preview",
                    "cost_monthly": 0,
                    "cost_label": "Free",
                    "description": "Runs on your machine via Docker. No cloud costs.",
                    "recommended": True,
                    "available": True,
                },
            ],
        }
    return {
        "status": "complete",
        "estimate_id": str(est.id),
        "cloud_provider": est.cloud_provider,
        "tier_matrix": est.tier_matrix,
        "created_at": est.created_at.isoformat(),
    }


# ─── Internal helpers ──────────────────────────────────────────────────────────

async def _get_app_or_404(app_id: uuid.UUID, db: AsyncSession) -> App:
    result = await db.execute(select(App).where(App.id == app_id))
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="App not found")
    return app
