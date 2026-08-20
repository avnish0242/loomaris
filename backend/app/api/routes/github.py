import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from jose import JWTError
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import TenantContext, get_tenant_context, require_org_admin, require_superadmin
from app.core.config import settings
from app.core.security import create_access_token, decode_access_token
from app.database import get_db
from app.models.org import App
from app.models.platform import GitHubConnection, Organization, User
from app.services import github_service
from app.services.git_service import get_current_files

router = APIRouter(prefix="/github", tags=["github"])


# ─── One-time platform setup (superadmin) ──────────────────────────────────────

@router.get(
    "/manifest-redirect",
    summary="Start the one-time GitHub App registration flow (superadmin only)",
    response_class=HTMLResponse,
)
async def manifest_redirect(current_user: User = Depends(require_superadmin)):
    state = create_access_token(subject=str(current_user.id), extra={"purpose": "github_app_manifest"})
    return HTMLResponse(github_service.build_manifest_form_html(state))


@router.get(
    "/manifest-callback",
    summary="GitHub redirects here after the app manifest is confirmed",
    response_class=HTMLResponse,
)
async def manifest_callback(code: str, state: str):
    try:
        payload = decode_access_token(state)
        if payload.get("purpose") != "github_app_manifest":
            raise ValueError("wrong state purpose")
    except (JWTError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid or expired state")

    data = await github_service.exchange_manifest_code(code)

    # We can't write to the running process's env vars — display the credentials
    # once so the operator can paste them into .env.local (and each other
    # environment's secrets store) and restart, same as LOOMARIS_DEPLOYER_* today.
    return HTMLResponse(f"""<!doctype html>
<html><body style="font-family: monospace; white-space: pre-wrap; padding: 2rem;">
GitHub App created — copy these into .env.local (or your secrets manager) and restart:

GITHUB_APP_ID={data['id']}
GITHUB_APP_SLUG={data['slug']}
GITHUB_APP_WEBHOOK_SECRET={data['webhook_secret']}
GITHUB_APP_PRIVATE_KEY="{data['pem']}"

This page will not show these values again.
</body></html>""")


# ─── Per-org install flow ──────────────────────────────────────────────────────

@router.post("/orgs/{org_id}/connect", summary="Get the GitHub App install URL for this org")
async def start_install(
    org_id: uuid.UUID,
    user_and_org: tuple[User, Organization] = Depends(require_org_admin),
):
    user, org = user_and_org
    if org.id != org_id:
        raise HTTPException(status_code=403, detail="Org mismatch")
    if not settings.GITHUB_APP_SLUG:
        raise HTTPException(
            status_code=503,
            detail="GitHub App is not configured on this deployment yet.",
        )
    state = create_access_token(
        subject=str(user.id), extra={"purpose": "github_install", "org_id": str(org_id)}
    )
    return {
        "install_url": f"https://github.com/apps/{settings.GITHUB_APP_SLUG}/installations/new?state={state}"
    }


@router.get("/callback", summary="GitHub redirects here after an org installs the app")
async def install_callback(
    installation_id: int = Query(...),
    state: str = Query(...),
    setup_action: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    try:
        payload = decode_access_token(state)
        if payload.get("purpose") != "github_install":
            raise ValueError("wrong state purpose")
        org_id = uuid.UUID(payload["org_id"])
        user_id = uuid.UUID(payload["sub"])
    except (JWTError, ValueError, KeyError):
        raise HTTPException(status_code=400, detail="Invalid or expired state")

    info = await github_service.get_installation(installation_id)
    account = info.get("account", {})

    result = await db.execute(
        select(GitHubConnection).where(GitHubConnection.org_id == org_id)
    )
    conn = result.scalar_one_or_none()
    if conn:
        conn.installation_id = installation_id
        conn.account_login = account.get("login", "")
        conn.account_type = account.get("type", "User")
        conn.status = "active"
    else:
        conn = GitHubConnection(
            org_id=org_id,
            installation_id=installation_id,
            account_login=account.get("login", ""),
            account_type=account.get("type", "User"),
            connected_by_user_id=user_id,
        )
        db.add(conn)
    await db.commit()

    return RedirectResponse(f"{settings.FRONTEND_URL}/org-settings?tab=integrations")


# ─── Per-app export ─────────────────────────────────────────────────────────────

class ExportRequest(BaseModel):
    repo_name: str
    private: bool = True


@router.post("/apps/{app_id}/export", summary="Push the current app to a GitHub repo")
async def export_to_github(
    app_id: uuid.UUID,
    body: ExportRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    platform_db: AsyncSession = Depends(get_db),
):
    result = await platform_db.execute(
        select(GitHubConnection).where(
            GitHubConnection.org_id == ctx.org.id, GitHubConnection.status == "active"
        )
    )
    conn = result.scalar_one_or_none()
    if not conn:
        raise HTTPException(
            status_code=400,
            detail="No GitHub account connected — connect one in Settings first.",
        )

    app_result = await ctx.session.execute(select(App).where(App.id == app_id))
    app = app_result.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="App not found")

    if not get_current_files(app.slug):
        raise HTTPException(status_code=400, detail="No generated files yet for this app.")

    try:
        token = await github_service.get_installation_token(conn.installation_id)
        repo = await github_service.create_repo(
            token, conn.account_login, conn.account_type, body.repo_name, body.private
        )
        github_service.push_app_to_repo(app.slug, token, repo["clone_url"])
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"GitHub export failed: {exc}")

    app.git_repo_url = repo["html_url"]
    await ctx.session.commit()

    return {"repo_url": repo["html_url"]}


@router.get("/status", summary="Whether this org has an active GitHub connection")
async def github_status(
    ctx: TenantContext = Depends(get_tenant_context),
    platform_db: AsyncSession = Depends(get_db),
):
    result = await platform_db.execute(
        select(GitHubConnection).where(
            GitHubConnection.org_id == ctx.org.id, GitHubConnection.status == "active"
        )
    )
    conn = result.scalar_one_or_none()
    return {
        "connected": conn is not None,
        "account_login": conn.account_login if conn else None,
    }
