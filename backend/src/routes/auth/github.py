"""GitHub OAuth account-linking endpoints.

Link-only: GitHub is NOT a login method here. We capture the member's GitHub
login (+ stable numeric id) so in-app feedback issues can @-mention them instead
of showing only a VEKN id (see routes/feedback.py). No AuthMethod is created;
the fields live on the User (full projection only) and unlink clears them.

This is a user-facing GitHub *OAuth App* (client id + secret), distinct from the
GitHub *Apps* in github_app.py (TWDA / feedback) which mint installation tokens.

Configuration (env vars):
- GITHUB_OAUTH_CLIENT_ID / GITHUB_OAUTH_SECRET: the OAuth App credentials.
- GITHUB_OAUTH_REDIRECT_URI: must match the App's callback (default localhost).
  Unset client id -> /authorize redirects back with ?github_error=not_configured
  (graceful: a toast on the profile page, not a raw error, since /authorize is a
  full-page navigation).
"""

import logging
import os
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import aiohttp
from fastapi import APIRouter, Header, HTTPException, Query, Response
from fastapi.responses import RedirectResponse

from ...broadcast import broadcast_precomputed
from ...db import (
    delete_transient_token,
    get_transient_token,
    get_user_by_uid,
    save_user,
    store_transient_token,
)
from ...middleware.auth import CurrentUser
from ._tokens import verify_token

router = APIRouter()
logger = logging.getLogger(__name__)


def _get_github_config() -> tuple[str, str, str, str]:
    """GitHub OAuth App config (lazy, after dotenv is loaded)."""
    return (
        os.getenv("GITHUB_OAUTH_CLIENT_ID", ""),
        os.getenv("GITHUB_OAUTH_SECRET", ""),
        os.getenv(
            "GITHUB_OAUTH_REDIRECT_URI", "http://localhost:8000/auth/github/callback"
        ),
        os.getenv("FRONTEND_URL", "http://localhost:5173"),
    )


@router.get("/github/authorize")
async def github_authorize(
    redirect: str = Query(
        "/profile", description="Frontend path to redirect after OAuth"
    ),
    token: str | None = Query(
        None, description="Access token (headers are lost across the redirect)"
    ),
    authorization: str | None = Header(default=None),
) -> RedirectResponse:
    """Initiate GitHub OAuth to link the caller's GitHub account (auth required)."""
    client_id, _secret, redirect_uri, frontend_url = _get_github_config()
    if not client_id:
        # Toast, not a 500: /authorize is a top-level navigation.
        return RedirectResponse(
            url=f"{frontend_url}/profile?github_error=not_configured", status_code=302
        )

    auth_token = token
    if not auth_token and authorization and authorization.startswith("Bearer "):
        auth_token = authorization[7:]
    if not auth_token:
        raise HTTPException(
            status_code=401, detail="Must be authenticated to link GitHub account"
        )
    user_uid = verify_token(auth_token, expected_type="access")

    state = secrets.token_urlsafe(32)
    await store_transient_token(
        f"github:{state}",
        {"user_uid": user_uid, "redirect": redirect},
        datetime.now(UTC) + timedelta(minutes=5),
    )

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": "read:user",
        "state": state,
    }
    return RedirectResponse(
        url=f"https://github.com/login/oauth/authorize?{urlencode(params)}",
        status_code=302,
    )


@router.get("/github/callback")
async def github_callback(
    code: str = Query(..., description="Authorization code from GitHub"),
    state: str = Query(..., description="CSRF state token"),
) -> RedirectResponse:
    """Exchange the code, fetch the GitHub login + id, store them on the user."""
    client_id, client_secret, redirect_uri, frontend_url = _get_github_config()

    stored = await get_transient_token(f"github:{state}")
    if not stored:
        return RedirectResponse(
            url=f"{frontend_url}/profile?github_error=invalid_state", status_code=302
        )
    await delete_transient_token(f"github:{state}")  # single use

    user_uid = stored.get("user_uid")
    redirect_path = stored.get("redirect", "/profile")

    def fail(err: str) -> RedirectResponse:
        return RedirectResponse(
            url=f"{frontend_url}{redirect_path}?github_error={err}", status_code=302
        )

    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=15.0)
    ) as session:
        # GitHub returns HTTP 200 even on error, so check for access_token.
        try:
            async with session.post(
                "https://github.com/login/oauth/access_token",
                headers={"Accept": "application/json"},
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
            ) as token_response:
                tokens = await token_response.json(content_type=None)
        except Exception as e:
            logger.error(f"GitHub token exchange error: {e}")
            return fail("github_error")
        access_token = tokens.get("access_token")
        if not access_token:
            logger.error(
                f"GitHub token exchange failed: "
                f"{tokens.get('error_description') or tokens}"
            )
            return fail("github_token_failed")

        try:
            async with session.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                },
            ) as user_response:
                if user_response.status != 200:
                    logger.error(
                        f"GitHub user fetch failed: {await user_response.text()}"
                    )
                    return fail("github_user_failed")
                github_user = await user_response.json()
        except Exception as e:
            logger.error(f"GitHub user fetch error: {e}")
            return fail("github_error")

    gh_id = github_user.get("id")
    github_login = github_user.get("login")
    if gh_id is None or not github_login:
        logger.error(f"GitHub /user response missing id/login: {github_user}")
        return fail("github_user_failed")
    github_id = str(gh_id)

    user = await get_user_by_uid(user_uid)
    if not user or user.deleted_at:
        return fail("github_error")
    if user.github_id != github_id or user.github_login != github_login:
        user.github_id = github_id
        user.github_login = github_login
        user.modified = datetime.now(UTC)
        broadcast_precomputed(await save_user(user))

    return RedirectResponse(
        url=f"{frontend_url}{redirect_path}?github_linked=success", status_code=302
    )


@router.post("/github/unlink")
async def github_unlink(current_user: CurrentUser) -> Response:
    """Clear the caller's linked GitHub account."""
    user = current_user
    if user.github_id or user.github_login:
        user.github_id = None
        user.github_login = None
        user.modified = datetime.now(UTC)
        broadcast_precomputed(await save_user(user))
    return Response(status_code=204)
