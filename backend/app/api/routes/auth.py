import logging
from typing import Any

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.security import create_access_token
from app.database import get_db
from app.models.platform import CloudAccount, OrgMembership, Organization, User
from app.services.auth_service import get_anthropic_key, get_or_create_user, store_anthropic_key

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
        "access_type": "offline",   # request refresh token
        "prompt": "consent",        # force consent screen to always issue refresh token
    },
)


async def _get_user_org(db: AsyncSession, user_id: Any) -> Organization | None:
    result = await db.execute(
        select(Organization)
        .join(OrgMembership, OrgMembership.org_id == Organization.id)
        .where(OrgMembership.user_id == user_id)
        .limit(1)
    )
    return result.scalar_one_or_none()


def _token_response(user: User, org: Organization | None) -> dict[str, Any]:
    token = create_access_token(
        subject=str(user.id),
        extra={
            "email": user.email,
            "org_id": str(org.id) if org else None,
            "name": user.name,
        },
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user": {
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
            "picture": user.picture,
        },
        "org": {
            "id": str(org.id),
            "name": org.name,
            "slug": org.slug,
            "plan": org.plan,
        } if org else None,
    }


@router.get("/google", summary="Initiate Google OAuth login")
async def google_login(request: Request):
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Google OAuth is not configured. "
                "Add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to .env.local"
            ),
        )
    return await oauth.google.authorize_redirect(request, settings.GOOGLE_REDIRECT_URI)


@router.get("/google/callback", summary="Google OAuth callback")
async def google_callback(request: Request, db: AsyncSession = Depends(get_db)):
    try:
        token = await oauth.google.authorize_access_token(request)
    except OAuthError as exc:
        log.error("Google OAuth callback failed: error=%s description=%s", exc.error, exc.description)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Google OAuth error: {exc.error} — {exc.description}",
        )

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

    org = await _get_user_org(db, user.id)
    resp_data = _token_response(user, org)
    access_token = resp_data["access_token"]

    if settings.is_dev:
        # Redirect to frontend with token in hash fragment — hash stays client-side
        # so the token is never sent to the Next.js server, only read by the browser.
        return RedirectResponse(url=f"http://localhost:3000/#token={access_token}")

    # Production: redirect frontend with token in query param + httponly cookie
    redirect = RedirectResponse(url=f"{settings.FRONTEND_URL}/auth/callback?access_token={access_token}")
    redirect.set_cookie(
        key="loomaris_token",
        value=access_token,
        httponly=True,
        samesite="lax",
        secure=True,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    return redirect


@router.get("/me", summary="Get current user and org")
async def get_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    org = await _get_user_org(db, current_user.id)
    has_claude_key = bool(current_user.anthropic_api_key_enc) or bool(settings.ANTHROPIC_API_KEY)

    has_cloud_account = False
    if org:
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
            "has_claude_key": has_claude_key,
            "has_cloud_account": has_cloud_account,
        },
        "org": {
            "id": str(org.id),
            "name": org.name,
            "slug": org.slug,
            "plan": org.plan,
        } if org else None,
    }


class ClaudeKeyRequest(BaseModel):
    api_key: str = Field(min_length=20, description="Anthropic API key (starts with sk-ant-)")


@router.post(
    "/claude-key",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Store your Anthropic API key (encrypted at rest)",
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
    await store_anthropic_key(db, user_id=current_user.id, api_key=body.api_key)


@router.get("/claude-key/status", summary="Check if a Claude API key is configured")
async def claude_key_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    key = await get_anthropic_key(db, current_user.id)
    source = (
        "user_key" if current_user.anthropic_api_key_enc
        else ("env" if settings.ANTHROPIC_API_KEY else "none")
    )
    return {"configured": bool(key), "source": source}


def _dev_success_page(token_data: dict, access_token: str) -> str:
    user = token_data.get("user", {})
    org = token_data.get("org", {}) or {}
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Loomaris — Authenticated</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ font-family: -apple-system, system-ui, sans-serif; max-width: 640px; margin: 64px auto;
           padding: 0 24px; color: #111; background: #fff; }}
    h1 {{ font-size: 22px; margin-bottom: 4px; }}
    .sub {{ color: #666; font-size: 14px; margin-bottom: 24px; }}
    .card {{ background: #f5f5f5; border-radius: 8px; padding: 16px 20px; margin: 16px 0; }}
    .token {{ background: #0d1117; color: #4ade80; font-family: 'SF Mono', monospace; font-size: 11px;
              padding: 12px; border-radius: 6px; word-break: break-all; margin: 8px 0; }}
    .badge {{ background: #dbeafe; color: #1e40af; padding: 2px 10px; border-radius: 999px;
              font-size: 12px; font-weight: 500; }}
    a.btn {{ display: inline-block; background: #111; color: #fff; text-decoration: none;
             padding: 10px 20px; border-radius: 6px; font-size: 14px; margin-top: 20px; }}
    .note {{ font-size: 12px; color: #888; margin-top: 8px; }}
    .step {{ display: flex; gap: 12px; align-items: flex-start; margin: 8px 0;
             font-size: 14px; color: #444; }}
    .step code {{ background: #e5e5e5; padding: 1px 5px; border-radius: 3px; font-size: 12px; }}
  </style>
</head>
<body>
  <h1>✓ Authenticated</h1>
  <p class="sub">
    Signed in as <strong>{user.get('email', '')}</strong>
    &nbsp;<span class="badge">{org.get('name', 'No org')}</span>
  </p>

  <div class="card">
    <strong>Access Token</strong> — auto-stored in localStorage
    <div class="token">{access_token}</div>
  </div>

  <div class="card">
    <strong>Next steps</strong>
    <div class="step">1. Click "Open API Docs" below and hit <code>Authorize</code></div>
    <div class="step">2. Paste: <code>Bearer &lt;token&gt;</code></div>
    <div class="step">3. Call <code>POST /api/v1/auth/claude-key</code> with your Anthropic key to enable generation</div>
  </div>

  <a class="btn" href="/docs">Open API Docs →</a>
  <p class="note">Dev mode only. Token stored as <code>loomaris_token</code> in localStorage.</p>

  <script>
    localStorage.setItem('loomaris_token', '{access_token}');
    console.log('%c[Loomaris] Token stored. Use as Bearer token in API calls.', 'color: #4ade80');
  </script>
</body>
</html>"""
