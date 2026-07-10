"""
Superadmin routes — all require is_superadmin=True on the User.
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_superadmin
from app.models.platform import OrgMembership, Organization, User

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/orgs", summary="List all orgs with usage stats")
async def list_all_orgs(
    _: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(
            Organization,
            func.count(OrgMembership.user_id).label("member_count"),
        )
        .join(OrgMembership, OrgMembership.org_id == Organization.id, isouter=True)
        .where(OrgMembership.status == "active")
        .group_by(Organization.id)
        .order_by(Organization.created_at.desc())
    )
    return [
        {
            "id": str(org.id),
            "name": org.name,
            "slug": org.slug,
            "plan": org.plan,
            "description": org.description,
            "join_policy": org.join_policy,
            "member_count": count,
            "suspended": org.suspended_at is not None,
            "suspended_at": org.suspended_at.isoformat() if org.suspended_at else None,
            "created_at": org.created_at.isoformat(),
        }
        for org, count in result
    ]


@router.post("/orgs/{org_id}/suspend", summary="Suspend an org")
async def suspend_org(
    org_id: uuid.UUID,
    _: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Org not found.")
    org.suspended_at = datetime.now(timezone.utc)
    await db.commit()
    return {"ok": True, "suspended_at": org.suspended_at.isoformat()}


@router.post("/orgs/{org_id}/unsuspend", summary="Unsuspend an org")
async def unsuspend_org(
    org_id: uuid.UUID,
    _: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Org not found.")
    org.suspended_at = None
    await db.commit()
    return {"ok": True}


@router.get("/users", summary="List all users")
async def list_all_users(
    _: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User).order_by(User.created_at.desc())
    )
    return [
        {
            "id": str(u.id),
            "email": u.email,
            "name": u.name,
            "picture": u.picture,
            "is_superadmin": u.is_superadmin,
            "created_at": u.created_at.isoformat(),
            "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
        }
        for u in result.scalars().all()
    ]


@router.post("/users/{user_id}/make-superadmin", summary="Grant superadmin to a user")
async def make_superadmin(
    user_id: uuid.UUID,
    current_admin: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    user.is_superadmin = True
    await db.commit()
    return {"ok": True, "email": user.email}


@router.post("/orgs/{org_id}/members/{user_id}/promote", summary="Promote member to org admin")
async def promote_to_admin(
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    _: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(OrgMembership).where(
            OrgMembership.org_id == org_id,
            OrgMembership.user_id == user_id,
        )
    )
    membership = result.scalar_one_or_none()
    if not membership:
        raise HTTPException(status_code=404, detail="Membership not found.")
    membership.role = "admin"
    membership.status = "active"
    await db.commit()
    return {"ok": True}
