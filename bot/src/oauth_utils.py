"""Shared OAuth utilities for PKCE and URL generation."""

import hashlib
import secrets
from base64 import urlsafe_b64encode
from urllib.parse import urlencode

from . import config


def generate_pkce() -> tuple[str, str]:
    """Generate PKCE code_verifier and code_challenge (S256)."""
    code_verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return code_verifier, code_challenge


def make_oauth_url(state: str, code_challenge: str) -> str:
    """Build Archon OAuth authorize URL with login_hint=discord."""
    params = {
        "response_type": "code",
        "client_id": config.OAUTH_CLIENT_ID,
        "redirect_uri": config.OAUTH_REDIRECT_URI,
        "scope": "profile:read user:impersonate",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "login_hint": "discord",
    }
    return f"{config.ARCHON_FRONTEND_URL}/oauth/consent?{urlencode(params)}"
