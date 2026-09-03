"""Shared OAuth utilities for PKCE and URL generation."""

import hashlib
import secrets
from base64 import urlsafe_b64encode
from urllib.parse import urlencode

from . import config


def generate_state() -> str:
    return secrets.token_urlsafe(32)


def generate_pkce() -> tuple[str, str]:
    """Generate PKCE code_verifier and code_challenge (S256)."""
    code_verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return code_verifier, code_challenge


def make_oauth_url(state: str, code_challenge: str, tournament_uid: str) -> str:
    """Build Archon OAuth authorize URL with login_hint=discord. `event:run`
    is granted per event, so the tournament rides the request and the consent page
    names it to the user."""
    params = {
        "response_type": "code",
        "client_id": config.OAUTH_CLIENT_ID,
        "redirect_uri": config.OAUTH_REDIRECT_URI,
        "scope": "profile:read event:run",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "login_hint": "discord",
        "tournament": tournament_uid,
    }
    return f"{config.ARCHON_FRONTEND_URL}/consent?{urlencode(params)}"
