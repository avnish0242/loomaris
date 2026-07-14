import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import decrypt_value, encrypt_value
from app.models.platform import OrgMembership, Organization, User
from app.services.tenant_service import add_user_to_org, get_or_create_default_org


async def get_or_create_user(
    db: AsyncSession,
    *,
    email: str,
    name: str | None,
    picture: str | None,
    google_sub: str | None = None,
    github_sub: str | None = None,
    zoho_sub: str | None = None,
    google_refresh_token: str | None = None,
) -> User:
    # Prefer matching on OAuth subject, fall back to email
    user: User | None = None
    if google_sub:
        result = await db.execute(select(User).where(User.google_sub == google_sub))
        user = result.scalar_one_or_none()
    if not user and github_sub:
        result = await db.execute(select(User).where(User.github_sub == github_sub))
        user = result.scalar_one_or_none()
    if not user and zoho_sub:
        result = await db.execute(select(User).where(User.zoho_sub == zoho_sub))
        user = result.scalar_one_or_none()
    if not user:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

    if user:
        user.name = name or user.name
        user.picture = picture or user.picture
        if google_sub:
            user.google_sub = google_sub
        if github_sub:
            user.github_sub = github_sub
        if zoho_sub:
            user.zoho_sub = zoho_sub
        if google_refresh_token:
            user.google_refresh_token_enc = encrypt_value(google_refresh_token)
        user.last_login_at = datetime.now(timezone.utc)
        # is_superadmin is a DB-level role — never overwritten at login
    else:
        user = User(
            email=email,
            name=name,
            picture=picture,
            google_sub=google_sub,
            github_sub=github_sub,
            zoho_sub=zoho_sub,
            is_superadmin=False,
            last_login_at=datetime.now(timezone.utc),
            google_refresh_token_enc=(
                encrypt_value(google_refresh_token) if google_refresh_token else None
            ),
        )
        db.add(user)
        await db.flush()

    await db.commit()
    await db.refresh(user)
    return user


async def get_active_membership(
    db: AsyncSession, user_id: uuid.UUID
) -> OrgMembership | None:
    """Return the user's active (non-pending) org membership, if any."""
    result = await db.execute(
        select(OrgMembership).where(
            OrgMembership.user_id == user_id,
            OrgMembership.status == "active",
        ).limit(1)
    )
    return result.scalar_one_or_none()


async def get_pending_membership(
    db: AsyncSession, user_id: uuid.UUID
) -> OrgMembership | None:
    result = await db.execute(
        select(OrgMembership).where(
            OrgMembership.user_id == user_id,
            OrgMembership.status == "pending",
        ).limit(1)
    )
    return result.scalar_one_or_none()


async def store_org_anthropic_key(
    db: AsyncSession, org_id: uuid.UUID, api_key: str
) -> None:
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if not org:
        raise ValueError("Organization not found")
    org.anthropic_api_key_enc = encrypt_value(api_key)
    await db.commit()


async def get_anthropic_key(db: AsyncSession, org_id: uuid.UUID) -> str | None:
    """Returns the decrypted Anthropic API key for the org.
    Falls back to the master key from env if the org hasn't stored one."""
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if org and org.anthropic_api_key_enc:
        return decrypt_value(org.anthropic_api_key_enc)
    return settings.ANTHROPIC_API_KEY or None
