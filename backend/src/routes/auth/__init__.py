"""Authentication API endpoints package."""

from fastapi import APIRouter

from ._tokens import create_access_token, create_refresh_token, verify_token
from .magic_link import send_invite_email
from . import _tokens, discord, email_password, magic_link, passkeys, profile

router = APIRouter(prefix="/auth", tags=["auth"])
router.include_router(_tokens.router)
router.include_router(email_password.router)
router.include_router(magic_link.router)
router.include_router(profile.router)
router.include_router(passkeys.router)
router.include_router(discord.router)

__all__ = [
    "create_access_token",
    "create_refresh_token",
    "router",
    "send_invite_email",
    "verify_token",
]
