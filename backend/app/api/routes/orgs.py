import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_org_admin
from app.models.platform import Organization, User
from app.services.org_service import (
    _slugify,
    accept_invite,
    approve_join_request,
    create_invite,
    create_org,
    list_join_requests,
    list_members,
    list_orgs_public,
    reject_join_request,
    remove_member,
    request_to_join,
)

router = APIRouter(prefix="/orgs", tags=["orgs"])


class CreateOrgRequest(BaseModel):
    name: str
    slug: str | None = None
    description: str | None = None
    join_policy: str = "approval_required"


class JoinRequest(BaseModel):
    org_id: uuid.UUID


class InviteRequest(BaseModel):
    email: str
    role: str = "member"


class ApproveRequest(BaseModel):
    user_id: uuid.UUID


# ── Public org listing (for onboarding join screen) ───────────────────────────

@router.get("", summary="List orgs (public info only — for join screen)")
async def list_orgs(db: AsyncSession = Depends(get_db)):
    return await list_orgs_public(db)


# ── Create org (self-serve, caller becomes owner) ─────────────────────────────

@router.post("", status_code=status.HTTP_201_CREATED, summary="Create a new organisation")
async def create_organisation(
    body: CreateOrgRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    slug = body.slug or _slugify(body.name)
    try:
        org = await create_org(
            db,
            name=body.name,
            slug=slug,
            description=body.description,
            join_policy=body.join_policy,
            created_by=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "id": str(org.id),
        "name": org.name,
        "slug": org.slug,
        "description": org.description,
        "join_policy": org.join_policy,
        "plan": org.plan,
    }


# ── Join request ──────────────────────────────────────────────────────────────

@router.post("/join-request", status_code=status.HTTP_201_CREATED, summary="Request to join an org")
async def join_request(
    body: JoinRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        membership = await request_to_join(db, org_id=body.org_id, user_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "status": membership.status,
        "org_id": str(membership.org_id),
        "message": (
            "You have joined the organization."
            if membership.status == "active"
            else "Your request is pending approval by the org admin."
        ),
    }


# ── Org admin endpoints ───────────────────────────────────────────────────────

@router.get("/{org_id}/join-requests", summary="List pending join requests (org admin)")
async def get_join_requests(
    org_id: uuid.UUID,
    admin: tuple[User, Organization] = Depends(require_org_admin),
    db: AsyncSession = Depends(get_db),
):
    user, org = admin
    if str(org.id) != str(org_id):
        raise HTTPException(status_code=403, detail="Access denied.")
    return await list_join_requests(db, org_id)


@router.post("/{org_id}/join-requests/{user_id}/approve", summary="Approve a join request")
async def approve_request(
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    admin: tuple[User, Organization] = Depends(require_org_admin),
    db: AsyncSession = Depends(get_db),
):
    _, org = admin
    if str(org.id) != str(org_id):
        raise HTTPException(status_code=403, detail="Access denied.")
    try:
        await approve_join_request(db, org_id=org_id, user_id=user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"ok": True}


@router.post("/{org_id}/join-requests/{user_id}/reject", summary="Reject a join request")
async def reject_request(
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    admin: tuple[User, Organization] = Depends(require_org_admin),
    db: AsyncSession = Depends(get_db),
):
    _, org = admin
    if str(org.id) != str(org_id):
        raise HTTPException(status_code=403, detail="Access denied.")
    try:
        await reject_join_request(db, org_id=org_id, user_id=user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"ok": True}


@router.post("/{org_id}/invite", status_code=status.HTTP_201_CREATED, summary="Invite a user by email")
async def invite_user(
    org_id: uuid.UUID,
    body: InviteRequest,
    admin: tuple[User, Organization] = Depends(require_org_admin),
    db: AsyncSession = Depends(get_db),
):
    user, org = admin
    if str(org.id) != str(org_id):
        raise HTTPException(status_code=403, detail="Access denied.")
    invite = await create_invite(
        db,
        org_id=org_id,
        invited_email=body.email,
        role=body.role,
        created_by=user.id,
    )
    # In production, send an email here; for now return the invite token
    invite_url = f"{_get_frontend_base()}/invite/{invite.token}"
    return {"invite_url": invite_url, "expires_at": invite.expires_at.isoformat() if invite.expires_at else None}


@router.get("/{org_id}/members", summary="List org members (org admin)")
async def get_members(
    org_id: uuid.UUID,
    admin: tuple[User, Organization] = Depends(require_org_admin),
    db: AsyncSession = Depends(get_db),
):
    _, org = admin
    if str(org.id) != str(org_id):
        raise HTTPException(status_code=403, detail="Access denied.")
    return await list_members(db, org_id)


@router.delete("/{org_id}/members/{user_id}", summary="Remove a member (org admin)")
async def kick_member(
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    admin: tuple[User, Organization] = Depends(require_org_admin),
    db: AsyncSession = Depends(get_db),
):
    admin_user, org = admin
    if str(org.id) != str(org_id):
        raise HTTPException(status_code=403, detail="Access denied.")
    if str(admin_user.id) == str(user_id):
        raise HTTPException(status_code=400, detail="You cannot remove yourself.")
    await remove_member(db, org_id=org_id, user_id=user_id)
    return {"ok": True}


# ── Accept invite (any authenticated user) ────────────────────────────────────

@router.get("/invite/{token}", summary="Accept an org invite")
async def accept_org_invite(
    token: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        membership = await accept_invite(db, token=token, user=current_user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "ok": True,
        "org_id": str(membership.org_id),
        "role": membership.role,
        "redirect": "/chat",
    }


def _get_frontend_base() -> str:
    from app.core.config import settings
    return "http://localhost:3000" if settings.is_dev else settings.FRONTEND_URL
