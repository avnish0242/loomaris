"""
GitHub App integration — repo export/push, kept deliberately separate from the
login-only OAuth app registered in auth.py. A GitHub App gives fine-grained,
installation-scoped, independently-revocable access (only `contents: write` +
`metadata: read` on repos the org explicitly picks) instead of a broad `repo`
scope tied to the same credentials used for authentication.

Two credential lifetimes are involved:
  - The app's own private key (GITHUB_APP_PRIVATE_KEY) — long-lived, platform-level,
    used only to mint short JWTs.
  - Installation access tokens — minted per-operation from that JWT, ~1hr expiry,
    never persisted.
"""
import time
import uuid

import httpx
from jose import jwt as jose_jwt

from app.core.config import settings
from app.services.git_service import push_to_remote

_GITHUB_API = "https://api.github.com"


def build_manifest_form_html(state: str) -> str:
    """GitHub's app-manifest flow is a browser-submitted POST form (not a plain
    redirect) carrying the manifest JSON as a hidden field — this returns a tiny
    self-submitting HTML page that performs that POST to github.com. The caller
    (an authenticated superadmin) is sent this page; GitHub then prompts them to
    confirm the app, and redirects to our manifest-callback route with a `code`."""
    import html
    import json

    manifest = {
        "name": f"Loomaris Export ({settings.DOMAIN})",
        "url": settings.FRONTEND_URL,
        "hook_attributes": {"url": f"{settings.BACKEND_URL}/api/v1/github/webhook"},
        "redirect_url": f"{settings.BACKEND_URL}/api/v1/github/manifest-callback",
        "public": False,
        "default_permissions": {
            "contents": "write",
            "metadata": "read",
            "administration": "write",  # needed to create repos on the installing account/org
        },
    }
    manifest_json = html.escape(json.dumps(manifest))
    action_url = html.escape(f"https://github.com/settings/apps/new?state={state}")
    return f"""<!doctype html>
<html><body onload="document.forms[0].submit()">
<form action="{action_url}" method="post">
  <input type="hidden" name="manifest" value="{manifest_json}">
</form>
Redirecting to GitHub to confirm the Loomaris export app…
</body></html>"""


async def exchange_manifest_code(code: str) -> dict:
    """Exchange the one-time manifest code for the new app's real credentials.
    Returns the raw GitHub response — id, pem, webhook_secret, client_id, client_secret, slug."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{_GITHUB_API}/app-manifests/{code}/conversions", timeout=15)
        resp.raise_for_status()
        return resp.json()


def build_app_jwt() -> str:
    """Short-lived (10 min) JWT identifying the app itself, used to mint installation tokens."""
    if not settings.GITHUB_APP_ID or not settings.GITHUB_APP_PRIVATE_KEY:
        raise ValueError(
            "GitHub App is not configured — complete the one-time setup at "
            "/api/v1/github/manifest-redirect first."
        )
    now = int(time.time())
    payload = {"iat": now - 60, "exp": now + 600, "iss": settings.GITHUB_APP_ID}
    return jose_jwt.encode(payload, settings.GITHUB_APP_PRIVATE_KEY, algorithm="RS256")


async def get_installation_token(installation_id: int) -> str:
    """Exchange the app JWT for a ~1hr token scoped to one installation. Never persisted."""
    app_jwt = build_app_jwt()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{_GITHUB_API}/app/installations/{installation_id}/access_tokens",
            headers={"Authorization": f"Bearer {app_jwt}", "Accept": "application/vnd.github+json"},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()["token"]


async def get_installation(installation_id: int) -> dict:
    """Look up the account (user or org) an installation belongs to."""
    app_jwt = build_app_jwt()
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{_GITHUB_API}/app/installations/{installation_id}",
            headers={"Authorization": f"Bearer {app_jwt}", "Accept": "application/vnd.github+json"},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()


async def create_repo(
    token: str, account_login: str, account_type: str, repo_name: str, private: bool
) -> dict:
    """Create a repo under the installed account. Returns the repo object (html_url, clone_url, ...)."""
    path = f"/orgs/{account_login}/repos" if account_type == "Organization" else "/user/repos"
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{_GITHUB_API}{path}",
            headers={"Authorization": f"token {token}", "Accept": "application/vnd.github+json"},
            json={"name": repo_name, "private": private},
            timeout=15,
        )
        if resp.status_code == 422:
            # Already exists — fetch it instead of failing the export.
            get_resp = await client.get(
                f"{_GITHUB_API}/repos/{account_login}/{repo_name}",
                headers={"Authorization": f"token {token}", "Accept": "application/vnd.github+json"},
                timeout=15,
            )
            get_resp.raise_for_status()
            return get_resp.json()
        resp.raise_for_status()
        return resp.json()


def push_app_to_repo(app_slug: str, token: str, clone_url: str) -> None:
    """Push the app's real local commit history to the given repo — preserves the
    full per-turn generation history rather than re-committing files one by one
    through the Contents API."""
    authed_url = clone_url.replace("https://", f"https://x-access-token:{token}@")
    push_to_remote(app_slug, authed_url, branch="main")


def new_state_token() -> str:
    """CSRF-style state token for the per-org install flow's redirect round-trip."""
    return uuid.uuid4().hex
