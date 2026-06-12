import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.org import App, ChatSession, Deployment
from app.models.platform import User
from app.services.chat_service import create_session, get_or_create_app
from app.services.deploy_service import build_and_deploy, get_container_status
from app.services.git_service import create_zip_archive, get_commit_log, get_current_files

router = APIRouter(prefix="/apps", tags=["apps"])


class CreateAppRequest(BaseModel):
    name: str
    app_type: str = "web"


class CreateSessionRequest(BaseModel):
    title: str | None = None


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


# ─── CRUD ──────────────────────────────────────────────────────────────────────

@router.post("", status_code=status.HTTP_201_CREATED, summary="Create a new app")
async def create_app(
    body: CreateAppRequest,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    app = await get_or_create_app(db, name=body.name, app_type=body.app_type)
    await db.commit()
    await db.refresh(app)
    return _app_out(app)


@router.get("", summary="List all apps")
async def list_apps(
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(App).where(App.archived_at.is_(None)).order_by(App.created_at.desc())
    )
    return [_app_out(a) for a in result.scalars().all()]


@router.get("/{app_id}", summary="Get a single app")
async def get_app(
    app_id: uuid.UUID,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return _app_out(await _get_app_or_404(app_id, db))


@router.post(
    "/{app_id}/sessions",
    status_code=status.HTTP_201_CREATED,
    summary="Start a chat session for an app",
)
async def create_app_session(
    app_id: uuid.UUID,
    body: CreateSessionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(App).where(App.id == app_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="App not found")

    session = await create_session(
        db, user_id=current_user.id, app_id=app_id, title=body.title
    )
    await db.commit()
    await db.refresh(session)
    return _session_out(session)


@router.get("/{app_id}/sessions", summary="List chat sessions for an app")
async def list_app_sessions(
    app_id: uuid.UUID,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.app_id == app_id)
        .order_by(ChatSession.last_active_at.desc())
    )
    return [_session_out(s) for s in result.scalars().all()]


# ─── Files / Git ───────────────────────────────────────────────────────────────

@router.get("/{app_id}/files", summary="Get current generated files from git")
async def get_app_files(
    app_id: uuid.UUID,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    app = await _get_app_or_404(app_id, db)
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
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    app = await _get_app_or_404(app_id, db)
    archive_bytes = create_zip_archive(app.slug)
    if not archive_bytes:
        raise HTTPException(status_code=404, detail="No files generated yet for this app")
    return Response(
        content=archive_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={app.slug}.zip"},
    )


# ─── Deploy ────────────────────────────────────────────────────────────────────

@router.get("/{app_id}/deploy/status", summary="Current deploy container status")
async def deploy_status(
    app_id: uuid.UUID,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    app = await _get_app_or_404(app_id, db)
    container_status = await get_container_status(app.slug)

    # Also include the latest deployment record
    result = await db.execute(
        select(Deployment)
        .where(Deployment.app_id == app_id)
        .order_by(Deployment.created_at.desc())
        .limit(1)
    )
    dep = result.scalar_one_or_none()
    return {
        **container_status,
        "last_deployment": {
            "id": str(dep.id),
            "status": dep.status,
            "created_at": dep.created_at.isoformat(),
            "deployed_at": dep.deployed_at.isoformat() if dep.deployed_at else None,
        } if dep else None,
    }


@router.post("/{app_id}/deploy", summary="Build and deploy the app (SSE stream)")
async def deploy_app(
    app_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    app = await _get_app_or_404(app_id, db)
    files = get_current_files(app.slug)
    if not files:
        raise HTTPException(status_code=400, detail="No files generated yet. Chat with Loomaris first.")

    # Create a deployment record
    deployment = Deployment(
        app_id=app_id,
        environment="preview",
        status="building",
    )
    db.add(deployment)
    await db.commit()
    await db.refresh(deployment)
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

        # Update deployment record once the stream is fully consumed
        result = await db.execute(select(Deployment).where(Deployment.id == dep_id))
        dep = result.scalar_one_or_none()
        if dep:
            dep.status = final_status
            dep.outputs = outputs if outputs else None
            dep.deployed_at = datetime.now(timezone.utc) if final_status == "running" else None
            await db.commit()

    return StreamingResponse(_stream(), media_type="text/event-stream")


# ─── Cost estimate ─────────────────────────────────────────────────────────────

@router.get("/{app_id}/cost-estimate", summary="Preview estimated deployment costs")
async def cost_estimate(
    app_id: uuid.UUID,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_app_or_404(app_id, db)
    return {
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
            {
                "id": "aws_fargate",
                "label": "AWS ECS Fargate",
                "cost_monthly": 12.00,
                "cost_label": "~$12 / mo",
                "description": "0.25 vCPU + 0.5 GB RAM. Auto-scales to zero.",
                "recommended": False,
                "available": False,
                "available_note": "Phase 2 — cloud deploy coming soon",
            },
            {
                "id": "aws_ec2",
                "label": "AWS EC2 t3.micro",
                "cost_monthly": 8.50,
                "cost_label": "~$8.50 / mo",
                "description": "Always-on t3.micro. Best for low-latency workloads.",
                "recommended": False,
                "available": False,
                "available_note": "Phase 2 — cloud deploy coming soon",
            },
        ]
    }


# ─── Internal helpers ──────────────────────────────────────────────────────────

async def _get_app_or_404(app_id: uuid.UUID, db: AsyncSession) -> App:
    result = await db.execute(select(App).where(App.id == app_id))
    app = result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="App not found")
    return app
