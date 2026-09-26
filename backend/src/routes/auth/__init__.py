"""Authentication API endpoints package."""

from litestar import Router

from . import _tokens, discord, email_password, github, magic_link, passkeys, profile
from ._tokens import create_access_token, create_refresh_token, verify_token
from .magic_link import send_invite_email

router = Router(
    "/auth",
    route_handlers=[
        *_tokens.handlers,
        *email_password.handlers,
        *magic_link.handlers,
        *profile.handlers,
        *passkeys.handlers,
        *discord.handlers,
        *github.handlers,
    ],
)

__all__ = [
    "create_access_token",
    "create_refresh_token",
    "router",
    "send_invite_email",
    "verify_token",
]
