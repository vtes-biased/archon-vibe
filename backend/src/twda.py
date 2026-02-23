"""TWDA (Tournament Winning Deck Archive) GitHub integration.

Auto-creates PRs to GiottoVerducci/TWD when a sanctioned tournament finishes
and the winner's decklist is available.

Uses a GitHub App installed on the TWD repo with permissions:
- Contents: write (to create branches and commit files)
- Pull requests: write (to open PRs)

Configuration (env vars):
- TWDA_GITHUB_APP_ID: GitHub App ID (numeric)
- TWDA_GITHUB_PRIVATE_KEY: PEM private key contents, or path to .pem file
- TWDA_GITHUB_INSTALLATION_ID: Installation ID on the TWD repo (numeric)
"""

import base64
import logging
import os
import time

import httpx

logger = logging.getLogger(__name__)

TWDA_GITHUB_APP_ID = os.environ.get("TWDA_GITHUB_APP_ID", "")
TWDA_GITHUB_PRIVATE_KEY = os.environ.get("TWDA_GITHUB_PRIVATE_KEY", "")
TWDA_GITHUB_INSTALLATION_ID = os.environ.get("TWDA_GITHUB_INSTALLATION_ID", "")
TWDA_TARGET_REPO = "GiottoVerducci/TWD"
TWDA_TARGET_OWNER = TWDA_TARGET_REPO.split("/")[0]  # "GiottoVerducci"

_GH_API_VERSION = "2022-11-28"


def _load_private_key() -> str:
    """Load PEM private key from env var (inline or file path)."""
    key = TWDA_GITHUB_PRIVATE_KEY
    if not key:
        return ""
    # If it looks like a file path (not PEM content), read it
    if not key.startswith("-----") and os.path.isfile(key):
        with open(key) as f:
            return f.read()
    return key


def _create_jwt() -> str:
    """Create a short-lived JWT for GitHub App authentication (RS256)."""
    import jwt

    private_key = _load_private_key()
    if not private_key:
        raise ValueError("TWDA_GITHUB_PRIVATE_KEY not configured")

    now = int(time.time())
    payload = {
        "iat": now - 60,   # 60s clock-drift margin
        "exp": now + 600,  # max 10 minutes
        "iss": int(TWDA_GITHUB_APP_ID),  # GitHub expects integer
    }
    return jwt.encode(payload, private_key, algorithm="RS256")


async def _get_installation_token() -> str:
    """Exchange App JWT for a scoped installation access token (1h TTL)."""
    app_jwt = _create_jwt()
    async with httpx.AsyncClient(
        base_url="https://api.github.com",
        timeout=15.0,
    ) as client:
        resp = await client.post(
            f"/app/installations/{TWDA_GITHUB_INSTALLATION_ID}/access_tokens",
            headers={
                "Authorization": f"Bearer {app_jwt}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": _GH_API_VERSION,
            },
            json={
                "permissions": {
                    "contents": "write",
                    "pull_requests": "write",
                },
            },
        )
        if resp.status_code != 201:
            raise ValueError(
                f"Failed to get installation token: {resp.status_code} {resp.text}"
            )
        return resp.json()["token"]


def _is_configured() -> bool:
    return bool(TWDA_GITHUB_APP_ID and TWDA_GITHUB_PRIVATE_KEY and TWDA_GITHUB_INSTALLATION_ID)


async def submit_twda_pr(
    vekn_event_id: str,
    deck_text: str,
    tournament_name: str,
) -> str | None:
    """Create or update a PR on GiottoVerducci/TWD with the winner's deck.

    The GitHub App is installed directly on the TWD repo, so branches and
    PRs are created on the repo itself (no fork needed).

    Returns the PR URL on success, None on failure.
    """
    if not _is_configured():
        logger.info("TWDA GitHub App not configured, skipping PR submission")
        return None

    try:
        token = await _get_installation_token()
    except Exception:
        logger.exception("Failed to get TWDA GitHub installation token")
        return None

    branch = f"archon/{vekn_event_id}"
    file_path = f"decks/{vekn_event_id}.txt"

    async with httpx.AsyncClient(
        base_url="https://api.github.com",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": _GH_API_VERSION,
        },
        timeout=30.0,
    ) as client:
        try:
            # 1. Get master branch SHA
            resp = await client.get(
                f"/repos/{TWDA_TARGET_REPO}/git/refs/heads/master"
            )
            if resp.status_code != 200:
                logger.error(f"Failed to get TWD master ref: {resp.status_code}")
                return None
            base_sha = resp.json()["object"]["sha"]

            # 2. Create or reset the feature branch
            ref_resp = await client.get(
                f"/repos/{TWDA_TARGET_REPO}/git/refs/heads/{branch}"
            )
            if ref_resp.status_code == 200:
                await client.patch(
                    f"/repos/{TWDA_TARGET_REPO}/git/refs/heads/{branch}",
                    json={"sha": base_sha, "force": True},
                )
            else:
                create_resp = await client.post(
                    f"/repos/{TWDA_TARGET_REPO}/git/refs",
                    json={"ref": f"refs/heads/{branch}", "sha": base_sha},
                )
                if create_resp.status_code not in (200, 201):
                    logger.error(
                        f"Failed to create branch: {create_resp.status_code} {create_resp.text}"
                    )
                    return None

            # 3. Create or update the deck file on the branch
            file_resp = await client.get(
                f"/repos/{TWDA_TARGET_REPO}/contents/{file_path}",
                params={"ref": branch},
            )
            content_b64 = base64.b64encode(deck_text.encode()).decode()
            file_data: dict = {
                "message": f"Add TWD: {tournament_name}",
                "content": content_b64,
                "branch": branch,
            }
            if file_resp.status_code == 200:
                # File exists on branch — include its sha to update
                file_data["sha"] = file_resp.json()["sha"]

            put_resp = await client.put(
                f"/repos/{TWDA_TARGET_REPO}/contents/{file_path}",
                json=file_data,
            )
            if put_resp.status_code not in (200, 201):
                logger.error(
                    f"Failed to commit deck file: {put_resp.status_code} {put_resp.text}"
                )
                return None

            # 4. Find existing open PR or create a new one
            #    head filter needs "owner:branch" when branch is on same repo
            pr_resp = await client.get(
                f"/repos/{TWDA_TARGET_REPO}/pulls",
                params={
                    "head": f"{TWDA_TARGET_OWNER}:{branch}",
                    "state": "open",
                },
            )
            if pr_resp.status_code == 200 and pr_resp.json():
                pr_url = pr_resp.json()[0]["html_url"]
                logger.info(f"TWDA PR already open, updated via branch push: {pr_url}")
                return pr_url

            pr_create = await client.post(
                f"/repos/{TWDA_TARGET_REPO}/pulls",
                json={
                    "title": f"Add TWD: {tournament_name}",
                    "body": (
                        "Automatically submitted by Archon tournament manager.\n\n"
                        f"VEKN Event ID: {vekn_event_id}"
                    ),
                    "head": branch,
                    "base": "master",
                },
            )
            if pr_create.status_code == 201:
                pr_url = pr_create.json()["html_url"]
                logger.info(f"TWDA PR created: {pr_url}")
                return pr_url

            logger.error(
                f"Failed to create TWDA PR: {pr_create.status_code} {pr_create.text}"
            )
            return None

        except Exception:
            logger.exception("TWDA PR submission failed")
            return None
