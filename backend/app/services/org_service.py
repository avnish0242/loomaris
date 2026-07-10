"""
Org lifecycle service: create, join-request, approve/reject, invite, accept-invite.
"""
import re
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.platform import OrgInvite, OrgMembership, Organization, User
from app.services.tenant_service import add_user_to_org, create_org_schema


def _slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")[:50]


async def create_org(
    db: AsyncSession,
    *,
    name: str,
    slug: str,
    description: str | None,
    join_policy: str,
    plan: str = "trial",
    created_by: uuid.UUID,
) -> Organization:
    existing = await db.execute(select(Organization).where(Organization.slug == slug))
    if existing.scalar_one_or_none():
        raise ValueError(f"Slug '{slug}' is already taken.")

    org = Organization(
        name=name,
        slug=slug,
        description=description,
        join_policy=join_policy,
        plan=plan,
        cost_hard_cap=500.00,
        metadata_={},
    )
    db.add(org)
    await db.flush()
    await create_org_schema(db, org.slug)

    membership = OrgMembership(
        org_id=org.id,
        user_id=created_by,
        role="owner",
        status="active",
    )
    db.add(membership)
    await db.commit()
    await db.refresh(org)
    return org


async def list_orgs_public(db: AsyncSession) -> list[dict]:
    result = await db.execute(
        select(
            Organization.id,
            Organization.name,
            Organization.slug,
            Organization.description,
            Organization.join_policy,
            func.count(OrgMembership.user_id).label("member_count"),
        )
        .join(OrgMembership, OrgMembership.org_id == Organization.id, isouter=True)
        .where(
            (OrgMembership.status == "active") | (OrgMembership.status.is_(None))
        )
        .where(Organization.suspended_at.is_(None))
        .group_by(
            Organization.id,
            Organization.name,
            Organization.slug,
            Organization.description,
            Organization.join_policy,
        )
        .order_by(Organization.name)
    )
    return [
        {
            "id": str(row.id),
            "name": row.name,
            "slug": row.slug,
            "description": row.description,
            "join_policy": row.join_policy,
            "member_count": row.member_count,
        }
        for row in result
    ]


async def request_to_join(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
) -> OrgMembership:
    result = await db.execute(
        select(Organization).where(
            Organization.id == org_id,
            Organization.suspended_at.is_(None),
        )
    )
    org = result.scalar_one_or_none()
    if not org:
        raise ValueError("Organization not found or suspended.")
    if org.join_policy == "invite_only":
        raise ValueError("This organization only accepts members via invite.")

    existing = await db.execute(
        select(OrgMembership).where(
            OrgMembership.org_id == org_id,
            OrgMembership.user_id == user_id,
        )
    )
    membership = existing.scalar_one_or_none()
    if membership:
        if membership.status == "active":
            raise ValueError("You are already a member of this organization.")
        if membership.status == "pending":
            raise ValueError("You already have a pending join request.")
        if membership.status == "rejected":
            membership.status = "pending"
            await db.commit()
            await db.refresh(membership)
            return membership

    status = "active" if org.join_policy == "open" else "pending"
    membership = OrgMembership(
        org_id=org_id,
        user_id=user_id,
        role="member",
        status=status,
    )
    db.add(membership)
    await db.commit()
    await db.refresh(membership)
    return membership


async def list_join_requests(db: AsyncSession, org_id: uuid.UUID) -> list[dict]:
    result = await db.execute(
        select(OrgMembership, User)
        .join(User, User.id == OrgMembership.user_id)
        .where(
            OrgMembership.org_id == org_id,
            OrgMembership.status == "pending",
        )
        .order_by(OrgMembership.joined_at)
    )
    return [
        {
            "user_id": str(u.id),
            "email": u.email,
            "name": u.name,
            "picture": u.picture,
            "requested_at": m.joined_at.isoformat(),
        }
        for m, u in result
    ]


async def approve_join_request(
    db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID
) -> OrgMembership:
    result = await db.execute(
        select(OrgMembership).where(
            OrgMembership.org_id == org_id,
            OrgMembership.user_id == user_id,
            OrgMembership.status == "pending",
        )
    )
    membership = result.scalar_one_or_none()
    if not membership:
        raise ValueError("No pending join request found.")
    membership.status = "active"
    await db.commit()
    await db.refresh(membership)
    return membership


async def reject_join_request(
    db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    result = await db.execute(
        select(OrgMembership).where(
            OrgMembership.org_id == org_id,
            OrgMembership.user_id == user_id,
            OrgMembership.status == "pending",
        )
    )
    membership = result.scalar_one_or_none()
    if not membership:
        raise ValueError("No pending join request found.")
    membership.status = "rejected"
    await db.commit()


async def create_invite(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    invited_email: str,
    role: str,
    created_by: uuid.UUID,
    expires_hours: int = 72,
) -> OrgInvite:
    invite = OrgInvite(
        org_id=org_id,
        invited_email=invited_email.lower().strip(),
        role=role,
        created_by=created_by,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=expires_hours),
    )
    db.add(invite)
    await db.commit()
    await db.refresh(invite)
    return invite


async def accept_invite(
    db: AsyncSession,
    *,
    token: uuid.UUID,
    user: User,
) -> OrgMembership:
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(OrgInvite).where(
            OrgInvite.token == token,
            OrgInvite.accepted_at.is_(None),
        )
    )
    invite = result.scalar_one_or_none()
    if not invite:
        raise ValueError("Invite not found or already used.")
    if invite.expires_at and invite.expires_at.replace(tzinfo=timezone.utc) < now:
        raise ValueError("This invite link has expired.")
    if invite.invited_email.lower() != user.email.lower():
        raise ValueError("This invite was sent to a different email address.")

    membership = await add_user_to_org(
        db, user_id=user.id, org_id=invite.org_id, role=invite.role
    )
    membership.status = "active"
    invite.accepted_at = now
    await db.commit()
    await db.refresh(membership)
    return membership


async def list_members(db: AsyncSession, org_id: uuid.UUID) -> list[dict]:
    result = await db.execute(
        select(OrgMembership, User)
        .join(User, User.id == OrgMembership.user_id)
        .where(OrgMembership.org_id == org_id)
        .order_by(OrgMembership.joined_at)
    )
    return [
        {
            "user_id": str(u.id),
            "email": u.email,
            "name": u.name,
            "picture": u.picture,
            "role": m.role,
            "status": m.status,
            "joined_at": m.joined_at.isoformat(),
        }
        for m, u in result
    ]


async def remove_member(
    db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    result = await db.execute(
        select(OrgMembership).where(
            OrgMembership.org_id == org_id,
            OrgMembership.user_id == user_id,
        )
    )
    membership = result.scalar_one_or_none()
    if membership:
        await db.delete(membership)
        await db.commit()
