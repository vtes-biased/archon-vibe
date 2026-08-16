"""Shared utilities for route handlers."""

from .models import User


def user_to_context(user: User) -> dict:
    return {
        "roles": [r.value for r in user.roles],
        "country": user.country,
        "vekn_id": user.vekn_id,
    }
