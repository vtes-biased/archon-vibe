"""TWDA (Tournament Winning Deck Archive) GitHub integration — auto-creates PRs to
GiottoVerducci/TWD when a sanctioned tournament finishes with a winner decklist.
One App installed twice: on our fork, which holds the branch and the deck commit,
and on the archive, which is asked for nothing but permission to open the PR.
Config: TWDA_GITHUB_{CLIENT_ID,PRIVATE_KEY,INSTALLATION_ID,FORK_INSTALLATION_ID,FORK_OWNER}."""

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
TWDA_GITHUB_FORK_INSTALLATION_ID = os.environ.get(
    "TWDA_GITHUB_FORK_INSTALLATION_ID", ""
)
TWDA_GITHUB_FORK_OWNER = os.environ.get("TWDA_GITHUB_FORK_OWNER", "")
TWDA_TARGET_REPO = "GiottoVerducci/TWD"
TWDA_FORK_REPO = f"{TWDA_GITHUB_FORK_OWNER}/{TWDA_TARGET_REPO.split('/')[1]}"

_GH_API_VERSION = github_app.GH_API_VERSION


def frontend_url() -> str:
    return os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")


def is_configured() -> bool:
    return bool(
        TWDA_GITHUB_CLIENT_ID
        and TWDA_GITHUB_PRIVATE_KEY
        and TWDA_GITHUB_INSTALLATION_ID
        and TWDA_GITHUB_FORK_INSTALLATION_ID
        and TWDA_GITHUB_FORK_OWNER
    )


async def submit_twda_pr(
    event_key: str,
    deck_text: str,
    tournament_name: str,
) -> str | None:
    """Create or update a PR on GiottoVerducci/TWD with the winner's deck.

    Every write lands on our own fork; the archive's installation is used only to
    open the pull request from it.

    Returns the PR URL on success, None on failure.
    """
    if not is_configured():
        logger.info("TWDA GitHub App not configured, skipping PR submission")
        return None

    try:
        private_key = github_app.load_private_key(TWDA_GITHUB_PRIVATE_KEY)
        fork_token = await github_app.get_installation_token(
            TWDA_GITHUB_CLIENT_ID,
            private_key,
            TWDA_GITHUB_FORK_INSTALLATION_ID,
            {"contents": "write"},
        )
        archive_token = await github_app.get_installation_token(
            TWDA_GITHUB_CLIENT_ID,
            private_key,
            TWDA_GITHUB_INSTALLATION_ID,
            {"pull_requests": "write"},
        )
    except Exception:
        logger.exception("Failed to get TWDA GitHub installation tokens")
        return None

    branch = f"archon/{event_key}"
    file_path = f"decks/{event_key}.txt"
    # The archive's token has no access to the fork, so it can only reference a
    # public head: the fork must never be flipped private.
    head = f"{TWDA_GITHUB_FORK_OWNER}:{branch}"

    timeout = aiohttp.ClientTimeout(total=30.0)
    async with aiohttp.ClientSession(
        base_url="https://api.github.com",
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": _GH_API_VERSION,
        },
        timeout=timeout,
    ) as session:

        async def _req(method: str, path: str, token: str, **kwargs) -> tuple[int, str]:
            """Run a GitHub API request, returning (status, body_text). Reads the
            body inside the response context so it's available after it closes."""
            async with session.request(
                method, path, headers={"Authorization": f"Bearer {token}"}, **kwargs
            ) as resp:
                return resp.status, await resp.text()

        try:
            # 1. Fast-forward the fork's master to the archive's, so the branch is
            #    cut from what the PR will actually be diffed against.
            sync_status, sync_text = await _req(
                "POST",
                f"/repos/{TWDA_FORK_REPO}/merge-upstream",
                fork_token,
                json={"branch": "master"},
            )
            if sync_status != 200:
                logger.error(f"Failed to sync TWD fork: {sync_status} {sync_text}")
                return None

            # 2. Get the fork's master SHA
            status, text = await _req(
                "GET", f"/repos/{TWDA_FORK_REPO}/git/refs/heads/master", fork_token
            )
            if status != 200:
                logger.error(f"Failed to get TWD fork master ref: {status}")
                return None
            base_sha = json.loads(text)["object"]["sha"]

            # 3. Create or reset the feature branch
            ref_status, _ = await _req(
                "GET",
                f"/repos/{TWDA_FORK_REPO}/git/refs/heads/{branch}",
                fork_token,
            )
            if ref_status == 200:
                await _req(
                    "PATCH",
                    f"/repos/{TWDA_FORK_REPO}/git/refs/heads/{branch}",
                    fork_token,
                    json={"sha": base_sha, "force": True},
                )
            else:
                create_status, create_text = await _req(
                    "POST",
                    f"/repos/{TWDA_FORK_REPO}/git/refs",
                    fork_token,
                    json={"ref": f"refs/heads/{branch}", "sha": base_sha},
                )
                if create_status not in (200, 201):
                    logger.error(
                        f"Failed to create branch: {create_status} {create_text}"
                    )
                    return None

            # 4. Create or update the deck file on the branch
            file_status, file_text = await _req(
                "GET",
                f"/repos/{TWDA_FORK_REPO}/contents/{file_path}",
                fork_token,
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
                f"/repos/{TWDA_FORK_REPO}/contents/{file_path}",
                fork_token,
                json=file_data,
            )
            if put_status not in (200, 201):
                logger.error(f"Failed to commit deck file: {put_status} {put_text}")
                return None

            # 5. Find existing open PR or create a new one, on the archive
            pr_status, pr_text = await _req(
                "GET",
                f"/repos/{TWDA_TARGET_REPO}/pulls",
                archive_token,
                params={"head": head, "state": "open"},
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
                archive_token,
                json={
                    "title": f"Add TWD: {tournament_name}",
                    "body": (
                        "Automatically submitted by Archon tournament manager.\n\n"
                        f"{frontend_url()}/t/{event_key}"
                    ),
                    "head": head,
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
