"""In-app feedback -> GitHub issues.

Authenticated users submit feedback (category + title + description) which is
filed as a GitHub issue on this repo via a dedicated GitHub App (Issues:write,
installed only on this repo) -- never exposed client-side; the repo is public.
A separate App from the TWDA importer so the two integrations stay isolated.

Configuration (env vars):
- FEEDBACK_GITHUB_CLIENT_ID: GitHub App client ID (used as the JWT iss).
- FEEDBACK_GITHUB_PRIVATE_KEY: PEM private key contents, or path to the .pem file.
- FEEDBACK_GITHUB_INSTALLATION_ID: the App's installation id on this repo (numeric).
  Any unset -> the endpoint returns 503, so the feature degrades gracefully (same
  pattern as the TWDA importer when its App isn't configured).
"""

import json
import logging
import os
import time
from typing import Literal

import aiohttp
import msgspec
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from .. import github_app
from ..middleware.auth import CurrentUser

router = APIRouter(prefix="/api/feedback", tags=["feedback"])
logger = logging.getLogger(__name__)
encoder = msgspec.json.Encoder()

FEEDBACK_GITHUB_CLIENT_ID = os.environ.get("FEEDBACK_GITHUB_CLIENT_ID", "")
FEEDBACK_GITHUB_PRIVATE_KEY = os.environ.get("FEEDBACK_GITHUB_PRIVATE_KEY", "")
FEEDBACK_GITHUB_INSTALLATION_ID = os.environ.get("FEEDBACK_GITHUB_INSTALLATION_ID", "")
FEEDBACK_TARGET_REPO = "vtes-biased/archon-vibe"


def _is_configured() -> bool:
    return bool(
        FEEDBACK_GITHUB_CLIENT_ID
        and FEEDBACK_GITHUB_PRIVATE_KEY
        and FEEDBACK_GITHUB_INSTALLATION_ID
    )


# category -> (title prefix, GitHub label). "feature" maps to GitHub's built-in
# "enhancement" label so it lands in the conventional bucket.
_CATEGORIES: dict[str, tuple[str, str]] = {
    "bug": ("Bug", "bug"),
    "feature": ("Feature", "enhancement"),
    "question": ("Question", "question"),
}

# Lightweight per-user abuse guard. In-process (per-worker) -- fine for the
# tournament-scale audience; the hard length caps on the body below are the real
# protection against body-bombing. Stale timestamps are pruned per-user on access
# (a never-returning user's empty list lingers, but that's a tiny, bounded leak at
# this scale -- not worth a sweeper).
_COOLDOWN_S = 60
_DAILY_CAP = 10
_recent: dict[str, list[float]] = {}


def _rate_limited(user_uid: str) -> bool:
    now = time.monotonic()
    times = [t for t in _recent.get(user_uid, []) if now - t < 86400]
    limited = (times and now - times[-1] < _COOLDOWN_S) or len(times) >= _DAILY_CAP
    if not limited:
        times.append(now)
    _recent[user_uid] = times
    return limited


class FeedbackRequest(BaseModel):
    """JSON body for POST /api/feedback/. Length caps mirror the frontend maxlength
    and keep us well under GitHub's 65k issue-body limit."""

    category: Literal["bug", "feature", "question"]
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=4000)
    # Client-supplied context appended to the issue body (best-effort, optional).
    app_version: str | None = Field(default=None, max_length=50)
    route: str | None = Field(default=None, max_length=200)
    locale: str | None = Field(default=None, max_length=10)
    user_agent: str | None = Field(default=None, max_length=400)


@router.post("/", status_code=201)
async def submit_feedback(body: FeedbackRequest, current_user: CurrentUser) -> Response:
    """File the submission as a GitHub issue; returns the created issue URL + number."""
    if not _is_configured():
        raise HTTPException(
            status_code=503, detail="Feedback channel is not configured"
        )

    # Members only: a VEKN id ties every report to an identifiable person (it's the
    # sole public handle in the issue body) and keeps drive-by accounts out.
    if not current_user.vekn_id:
        raise HTTPException(status_code=403, detail="Feedback requires a VEKN ID")

    if _rate_limited(current_user.uid):
        raise HTTPException(
            status_code=429,
            detail="Too many feedback submissions; please wait a moment",
        )

    prefix, category_label = _CATEGORIES[body.category]

    # Identity in the public issue: VEKN id, plus the linked GitHub @handle (a
    # public handle) so the reporter can be mentioned. No other PII (no-PII rule).
    roles = ", ".join(r.value for r in current_user.roles) or "player"
    mention = current_user.github_login
    vekn = f"VEKN {current_user.vekn_id}"
    who = f"@{mention} ({vekn})" if mention else vekn

    meta = [
        f"- **Submitted by:** {who} — role: {roles}",
        f"- **App version:** {body.app_version or 'unknown'}",
    ]
    if body.route:
        meta.append(f"- **Page:** `{body.route}`")
    if body.locale:
        meta.append(f"- **Locale:** {body.locale}")
    if body.user_agent:
        meta.append(f"- **User agent:** {body.user_agent}")
    issue_body = body.description.strip() + "\n\n---\n" + "\n".join(meta)

    try:
        token = await github_app.get_installation_token(
            FEEDBACK_GITHUB_CLIENT_ID,
            github_app.load_private_key(FEEDBACK_GITHUB_PRIVATE_KEY),
            FEEDBACK_GITHUB_INSTALLATION_ID,
            {"issues": "write"},
        )
        async with aiohttp.ClientSession(
            base_url="https://api.github.com",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": github_app.GH_API_VERSION,
            },
            timeout=aiohttp.ClientTimeout(total=15.0),
        ) as session:
            issue: dict = {
                "title": f"[{prefix}] {body.title}",
                "body": issue_body,
                "labels": ["feedback", category_label],
            }
            # Non-collaborator assignees are silently dropped by the API; the
            # body @-mention still notifies them.
            if mention:
                issue["assignees"] = [mention]
            async with session.post(
                f"/repos/{FEEDBACK_TARGET_REPO}/issues",
                json=issue,
            ) as resp:
                text = await resp.text()
                if resp.status != 201:
                    logger.error(
                        "Feedback issue creation failed: %s %s", resp.status, text[:500]
                    )
                    raise HTTPException(
                        status_code=502,
                        detail="Could not file feedback right now; please try again later",
                    )
                data = json.loads(text)
    # ValueError = token fetch returned non-201 (github_app.get_installation_token).
    except (aiohttp.ClientError, TimeoutError, ValueError):
        logger.exception("Feedback issue creation transport error")
        raise HTTPException(
            status_code=502,
            detail="Could not file feedback right now; please try again later",
        ) from None

    return Response(
        content=encoder.encode(
            {"issue_url": data["html_url"], "issue_number": data["number"]}
        ),
        media_type="application/json",
        status_code=201,
    )
