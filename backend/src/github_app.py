"""Shared GitHub App authentication: App JWT -> short-lived installation token.
Two Apps use this (twda.py, routes/feedback.py), each passing its own
App ID/private key/installation id."""

import logging
import os
import time

import aiohttp

logger = logging.getLogger(__name__)

GH_API_VERSION = "2022-11-28"


class InstallationTokenError(ValueError):
    """A non-201 from the token exchange, carrying GitHub's status so a caller
    can tell a permanent misconfiguration from a transient refusal."""

    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"Failed to get installation token: {status} {body}")
        self.status = status


def load_private_key(key: str) -> str:
    """Resolve a GitHub App private key from an env value: inline PEM, or a path
    to a .pem file (the multi-line secret is vault-delivered to a runtime path).

    A non-PEM value MUST be a readable file: falling through with the path string
    would surface later as PyJWT's cryptic InvalidKeyError instead of naming the
    misconfigured path. Raises OSError (FileNotFoundError/PermissionError)."""
    if not key or key.startswith("-----"):
        return key
    if not os.path.isfile(key):
        raise FileNotFoundError(f"GitHub App private key file not found: {key}")
    with open(key) as f:
        return f.read()


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

    Raises InstallationTokenError on a non-201 response; aiohttp.ClientError /
    TimeoutError propagate to the caller's transport handling.
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
                raise InstallationTokenError(resp.status, (await resp.text())[:500])
            data = await resp.json(content_type=None)
            return data["token"]
