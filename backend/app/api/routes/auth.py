import logging
from typing import Any

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.security import create_access_token
from app.database import get_db
from app.models.platform import CloudAccount, OrgMembership, Organization, User
from app.services.auth_service import (
    get_active_membership,
    get_anthropic_key,
    get_or_create_user,
    get_pending_membership,
    store_org_anthropic_key,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

oauth = OAuth()

oauth.register(
    name="google",
    client_id=settings.GOOGLE_CLIENT_ID,
    client_secret=settings.GOOGLE_CLIENT_SECRET,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "consent",
    },
)

oauth.register(
    name="github",
    client_id=settings.GITHUB_CLIENT_ID,
    client_secret=settings.GITHUB_CLIENT_SECRET,
    access_token_url="https://github.com/login/oauth/access_token",
    authorize_url="https://github.com/login/oauth/authorize",
    api_base_url="https://api.github.com/",
    client_kwargs={"scope": "read:user user:email"},
)


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_user_org(db: AsyncSession, user_id: Any) -> tuple[Organization, str] | tuple[None, None]:
    result = await db.execute(
        select(Organization, OrgMembership.role)
        .join(OrgMembership, OrgMembership.org_id == Organization.id)
        .where(
            OrgMembership.user_id == user_id,
            OrgMembership.status == "active",
        )
        .limit(1)
    )
    row = result.first()
    if row is None:
        return None, None
    return row[0], row[1]


def _redirect_after_login(access_token: str, destination: str) -> RedirectResponse:
    """Build the post-OAuth frontend redirect with token."""
    base = "http://localhost:3000" if settings.is_dev else settings.FRONTEND_URL
    url = f"{base}/#token={access_token}&next={destination}"
    if not settings.is_dev:
        url = f"{settings.FRONTEND_URL}/auth/callback?access_token={access_token}&next={destination}"
    resp = RedirectResponse(url=url)
    if not settings.is_dev:
        resp.set_cookie(
            key="loomaris_token",
            value=access_token,
            httponly=True,
            samesite="lax",
            secure=True,
            max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )
    return resp


async def _finish_oauth(db: AsyncSession, user: User) -> RedirectResponse:
    """Determine where to send the user after OAuth and issue the JWT."""
    org, _role = await _get_user_org(db, user.id)
    token = create_access_token(
        subject=str(user.id),
        extra={
            "email": user.email,
            "org_id": str(org.id) if org else None,
            "name": user.name,
            "is_superadmin": user.is_superadmin,
        },
    )

    if user.is_superadmin and not org:
        destination = "/admin"
    elif not org:
        pending = await get_pending_membership(db, user.id)
        destination = "/waiting" if pending else "/onboarding"
    else:
        destination = "/chat"

    return _redirect_after_login(token, destination)


# ── Google OAuth ──────────────────────────────────────────────────────────────

@router.get("/google", summary="Initiate Google OAuth login")
async def google_login(request: Request):
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth is not configured.",
        )
    return await oauth.google.authorize_redirect(request, settings.GOOGLE_REDIRECT_URI)


@router.get("/google/callback", summary="Google OAuth callback")
async def google_callback(request: Request, db: AsyncSession = Depends(get_db)):
    try:
        token = await oauth.google.authorize_access_token(request)
    except OAuthError as exc:
        log.error("Google OAuth error: %s — %s", exc.error, exc.description)
        raise HTTPException(status_code=400, detail=f"Google OAuth error: {exc.error}")

    user_info = token.get("userinfo")
    if not user_info:
        raise HTTPException(status_code=400, detail="Could not retrieve user info from Google")

    user = await get_or_create_user(
        db,
        google_sub=user_info["sub"],
        email=user_info["email"],
        name=user_info.get("name"),
        picture=user_info.get("picture"),
        google_refresh_token=token.get("refresh_token"),
    )
    return await _finish_oauth(db, user)


# ── GitHub OAuth ──────────────────────────────────────────────────────────────

@router.get("/github", summary="Initiate GitHub OAuth login")
async def github_login(request: Request):
    if not settings.GITHUB_CLIENT_ID or not settings.GITHUB_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GitHub OAuth is not configured.",
        )
    return await oauth.github.authorize_redirect(request, settings.GITHUB_REDIRECT_URI)


@router.get("/github/callback", summary="GitHub OAuth callback")
async def github_callback(request: Request, db: AsyncSession = Depends(get_db)):
    try:
        token = await oauth.github.authorize_access_token(request)
    except OAuthError as exc:
        log.error("GitHub OAuth error: %s — %s", exc.error, exc.description)
        raise HTTPException(status_code=400, detail=f"GitHub OAuth error: {exc.error}")

    # Fetch user profile
    resp = await oauth.github.get("user", token=token)
    profile = resp.json()

    # GitHub may not expose email publicly — fetch via emails endpoint
    email: str | None = profile.get("email")
    if not email:
        emails_resp = await oauth.github.get("user/emails", token=token)
        for entry in emails_resp.json():
            if entry.get("primary") and entry.get("verified"):
                email = entry["email"]
                break

    if not email:
        raise HTTPException(status_code=400, detail="Could not retrieve verified email from GitHub.")

    user = await get_or_create_user(
        db,
        github_sub=str(profile["id"]),
        email=email,
        name=profile.get("name") or profile.get("login"),
        picture=profile.get("avatar_url"),
    )
    return await _finish_oauth(db, user)


# ── Current user ──────────────────────────────────────────────────────────────

@router.get("/me", summary="Get current user and org")
async def get_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    org, role = await _get_user_org(db, current_user.id)
    pending = None
    if not org:
        pending = await get_pending_membership(db, current_user.id)

    has_claude_key = False
    has_cloud_account = False
    if org:
        has_claude_key = bool(await get_anthropic_key(db, org.id))
        result = await db.execute(
            select(CloudAccount).where(
                CloudAccount.org_id == org.id,
                CloudAccount.status == "verified",
            ).limit(1)
        )
        has_cloud_account = result.scalar_one_or_none() is not None

    return {
        "user": {
            "id": str(current_user.id),
            "email": current_user.email,
            "name": current_user.name,
            "picture": current_user.picture,
            "is_superadmin": current_user.is_superadmin,
            "has_claude_key": has_claude_key,
            "has_cloud_account": has_cloud_account,
        },
        "org": {
            "id": str(org.id),
            "name": org.name,
            "slug": org.slug,
            "plan": org.plan,
            "description": org.description,
            "join_policy": org.join_policy,
        } if org else None,
        "role": role,
        "membership_status": (
            "active" if org else
            ("pending" if pending else "none")
        ),
    }


# ── Org-level Anthropic API key ───────────────────────────────────────────────

class ClaudeKeyRequest(BaseModel):
    api_key: str = Field(min_length=20, description="Anthropic API key (starts with sk-ant-)")


@router.post(
    "/claude-key",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Store org's Anthropic API key (encrypted at rest)",
)
async def save_claude_key(
    body: ClaudeKeyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not body.api_key.startswith("sk-ant-"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid Anthropic API key format. Key must start with 'sk-ant-'.",
        )
    org, role = await _get_user_org(db, current_user.id)
    if not org:
        raise HTTPException(status_code=403, detail="No active org — complete onboarding first.")

    if not current_user.is_superadmin and role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only org admins can set the API key.")

    await store_org_anthropic_key(db, org_id=org.id, api_key=body.api_key)


@router.get("/claude-key/status", summary="Check if a Claude API key is configured for the org")
async def claude_key_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    org, _role = await _get_user_org(db, current_user.id)
    if not org:
        return {"configured": bool(settings.ANTHROPIC_API_KEY), "source": "env" if settings.ANTHROPIC_API_KEY else "none"}
    key = await get_anthropic_key(db, org.id)
    from sqlalchemy import select as sa_select
    org_result = await db.execute(sa_select(type(org)).where(type(org).id == org.id))
    org_fresh = org_result.scalar_one_or_none()
    source = (
        "org_key" if (org_fresh and org_fresh.anthropic_api_key_enc)
        else ("env" if settings.ANTHROPIC_API_KEY else "none")
    )
    return {"configured": bool(key), "source": source}
