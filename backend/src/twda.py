"""TWDA (Tournament Winning Deck Archive) GitHub integration.

Auto-creates PRs to GiottoVerducci/TWD when a sanctioned tournament finishes
and the winner's decklist is available.

Uses a GitHub App installed on the TWD repo with permissions:
- Contents: write (to create branches and commit files)
- Pull requests: write (to open PRs)

Configuration (env vars):
- TWDA_GITHUB_CLIENT_ID: GitHub App client ID (used as the JWT iss)
- TWDA_GITHUB_PRIVATE_KEY: PEM private key contents, or path to .pem file
- TWDA_GITHUB_INSTALLATION_ID: Installation ID on the TWD repo (numeric)
"""

import base64
import json
import logging
import os

import aiohttp

from . import github_app

logger = logging.getLogger(__name__)

TWDA_GITHUB_CLIENT_ID = os.environ.get("TWDA_GITHUB_CLIENT_ID", "")
TWDA_GITHUB_PRIVATE_KEY = os.environ.get("TWDA_GITHUB_PRIVATE_KEY", "")
TWDA_GITHUB_INSTALLATION_ID = os.environ.get("TWDA_GITHUB_INSTALLATION_ID", "")
TWDA_TARGET_REPO = "GiottoVerducci/TWD"
TWDA_TARGET_OWNER = TWDA_TARGET_REPO.split("/")[0]  # "GiottoVerducci"

_GH_API_VERSION = github_app.GH_API_VERSION


def _is_configured() -> bool:
    return bool(
        TWDA_GITHUB_CLIENT_ID
        and TWDA_GITHUB_PRIVATE_KEY
        and TWDA_GITHUB_INSTALLATION_ID
    )


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
        token = await github_app.get_installation_token(
            TWDA_GITHUB_CLIENT_ID,
            github_app.load_private_key(TWDA_GITHUB_PRIVATE_KEY),
            TWDA_GITHUB_INSTALLATION_ID,
            {"contents": "write", "pull_requests": "write"},
        )
    except Exception:
        logger.exception("Failed to get TWDA GitHub installation token")
        return None

    branch = f"archon/{vekn_event_id}"
    file_path = f"decks/{vekn_event_id}.txt"

    timeout = aiohttp.ClientTimeout(total=30.0)
    async with aiohttp.ClientSession(
        base_url="https://api.github.com",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": _GH_API_VERSION,
        },
        timeout=timeout,
    ) as session:

        async def _req(method: str, path: str, **kwargs) -> tuple[int, str]:
            """Run a GitHub API request, returning (status, body_text). Reads the
            body inside the response context so it's available after it closes."""
            async with session.request(method, path, **kwargs) as resp:
                return resp.status, await resp.text()

        try:
            # 1. Get master branch SHA
            status, text = await _req(
                "GET", f"/repos/{TWDA_TARGET_REPO}/git/refs/heads/master"
            )
            if status != 200:
                logger.error(f"Failed to get TWD master ref: {status}")
                return None
            base_sha = json.loads(text)["object"]["sha"]

            # 2. Create or reset the feature branch
            ref_status, _ = await _req(
                "GET", f"/repos/{TWDA_TARGET_REPO}/git/refs/heads/{branch}"
            )
            if ref_status == 200:
                await _req(
                    "PATCH",
                    f"/repos/{TWDA_TARGET_REPO}/git/refs/heads/{branch}",
                    json={"sha": base_sha, "force": True},
                )
            else:
                create_status, create_text = await _req(
                    "POST",
                    f"/repos/{TWDA_TARGET_REPO}/git/refs",
                    json={"ref": f"refs/heads/{branch}", "sha": base_sha},
                )
                if create_status not in (200, 201):
                    logger.error(
                        f"Failed to create branch: {create_status} {create_text}"
                    )
                    return None

            # 3. Create or update the deck file on the branch
            file_status, file_text = await _req(
                "GET",
                f"/repos/{TWDA_TARGET_REPO}/contents/{file_path}",
                params={"ref": branch},
            )
            content_b64 = base64.b64encode(deck_text.encode()).decode()
            file_data: dict = {
                "message": f"Add TWD: {tournament_name}",
                "content": content_b64,
                "branch": branch,
            }
            if file_status == 200:
                # File exists on branch — include its sha to update
                file_data["sha"] = json.loads(file_text)["sha"]

            put_status, put_text = await _req(
                "PUT",
                f"/repos/{TWDA_TARGET_REPO}/contents/{file_path}",
                json=file_data,
            )
            if put_status not in (200, 201):
                logger.error(f"Failed to commit deck file: {put_status} {put_text}")
                return None

            # 4. Find existing open PR or create a new one
            #    head filter needs "owner:branch" when branch is on same repo
            pr_status, pr_text = await _req(
                "GET",
                f"/repos/{TWDA_TARGET_REPO}/pulls",
                params={
                    "head": f"{TWDA_TARGET_OWNER}:{branch}",
                    "state": "open",
                },
            )
            if pr_status == 200:
                prs = json.loads(pr_text)
                if prs:
                    pr_url = prs[0]["html_url"]
                    logger.info(
                        f"TWDA PR already open, updated via branch push: {pr_url}"
                    )
                    return pr_url

            pr_create_status, pr_create_text = await _req(
                "POST",
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
            if pr_create_status == 201:
                pr_url = json.loads(pr_create_text)["html_url"]
                logger.info(f"TWDA PR created: {pr_url}")
                return pr_url

            logger.error(
                f"Failed to create TWDA PR: {pr_create_status} {pr_create_text}"
            )
            return None

        except Exception:
            logger.exception("TWDA PR submission failed")
            return None
