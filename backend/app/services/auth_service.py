import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import decrypt_value, encrypt_value
from app.models.platform import User
from app.services.tenant_service import add_user_to_org, get_or_create_default_org


async def get_or_create_user(
    db: AsyncSession,
    *,
    google_sub: str,
    email: str,
    name: str | None,
    picture: str | None,
    google_refresh_token: str | None = None,
) -> User:
    # Try to find by Google subject first, then fall back to email
    result = await db.execute(select(User).where(User.google_sub == google_sub))
    user = result.scalar_one_or_none()

    if not user:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

    if user:
        user.name = name or user.name
        user.picture = picture or user.picture
        user.google_sub = google_sub
        user.last_login_at = datetime.now(timezone.utc)
        if google_refresh_token:
            user.google_refresh_token_enc = encrypt_value(google_refresh_token)
    else:
        user = User(
            email=email,
            name=name,
            picture=picture,
            google_sub=google_sub,
            last_login_at=datetime.now(timezone.utc),
            google_refresh_token_enc=(
                encrypt_value(google_refresh_token) if google_refresh_token else None
            ),
        )
        db.add(user)
        await db.flush()

        # Auto-join the default org (Phase 1: single-org model)
        org = await get_or_create_default_org(db)
        await add_user_to_org(db, user_id=user.id, org_id=org.id, role="owner")

    await db.commit()
    await db.refresh(user)
    return user


async def store_anthropic_key(db: AsyncSession, user_id: uuid.UUID, api_key: str) -> None:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise ValueError("User not found")
    user.anthropic_api_key_enc = encrypt_value(api_key)
    await db.commit()


async def get_anthropic_key(db: AsyncSession, user_id: uuid.UUID) -> str | None:
    """Returns the decrypted Anthropic API key for the user.
    Falls back to the master key from env if the user hasn't stored one (Phase 1 behaviour)."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user and user.anthropic_api_key_enc:
        return decrypt_value(user.anthropic_api_key_enc)

    return settings.ANTHROPIC_API_KEY or None
