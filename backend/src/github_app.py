"""Shared GitHub App authentication: App JWT -> short-lived installation token.

Two GitHub Apps use this: the TWDA importer (twda.py, installed on the community
TWD archive) and the in-app feedback endpoint (routes/feedback.py, installed on
this repo). Each passes its own App ID / private key / installation id, so the
fragile JWT-signing + token-exchange dance lives here once.
"""

import logging
import os
import time

import aiohttp

logger = logging.getLogger(__name__)

GH_API_VERSION = "2022-11-28"


def load_private_key(key: str) -> str:
    """Resolve a GitHub App private key from an env value: inline PEM, or a path
    to a .pem file (the multi-line secret is vault-delivered to a runtime path)."""
    if not key:
        return ""
    if not key.startswith("-----") and os.path.isfile(key):
        with open(key) as f:
            return f.read()
    return key


def create_jwt(client_id: str, private_key: str) -> str:
    """Create a short-lived RS256 JWT for GitHub App authentication."""
    import jwt

    now = int(time.time())
    payload = {
        "iat": now - 60,  # clock-drift margin
        "exp": now + 600,  # max 10 minutes
        # Client ID (the App ID also works) as a STRING -- PyJWT >= 2.10 rejects a
        # non-str iss ("Issuer (iss) must be a string."); GitHub accepts the string.
        "iss": client_id,
    }
    return jwt.encode(payload, private_key, algorithm="RS256")


async def get_installation_token(
    client_id: str,
    private_key: str,
    installation_id: str,
    permissions: dict[str, str],
) -> str:
    """Exchange an App JWT for a scoped installation access token (1h TTL).

    Raises ValueError on a non-201 response; aiohttp.ClientError / TimeoutError
    propagate to the caller's transport handling.
    """
    app_jwt = create_jwt(client_id, private_key)
    async with aiohttp.ClientSession(
        base_url="https://api.github.com",
        timeout=aiohttp.ClientTimeout(total=15.0),
    ) as session:
        async with session.post(
            f"/app/installations/{installation_id}/access_tokens",
            headers={
                "Authorization": f"Bearer {app_jwt}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": GH_API_VERSION,
            },
            json={"permissions": permissions},
        ) as resp:
            if resp.status != 201:
                raise ValueError(
                    f"Failed to get installation token: {resp.status} {(await resp.text())[:500]}"
                )
            data = await resp.json(content_type=None)
            return data["token"]
