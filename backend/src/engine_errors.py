"""Structured engine rejections.

The Rust engine raises ValueError whose message is the EngineError wire JSON
``{"code": ..., "params": {...}, "message": ...}`` (see engine/src/error.rs).
``EngineRejection`` carries that triple to the HTTP error body via the handler
registered in main.py: ``{"detail": <message>, "code": ..., "params": {...}}``
— ``detail`` stays a human-readable string so the Discord bot and any legacy
client keep working; ``code``/``params`` are additive for frontend i18n.

App-level checks that mirror engine rules (e.g. the cross-tournament barred
check) raise EngineRejection directly, reusing the engine's codes so the same
condition localizes identically on every path.
"""

import json


class EngineRejection(Exception):
    """A domain rejection with a stable code and i18n params."""

    def __init__(
        self,
        message: str,
        code: str = "internal",
        params: dict[str, str] | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.params = params or {}

    @classmethod
    def from_engine(cls, e: ValueError) -> "EngineRejection":
        """Parse the engine's wire JSON; legacy plain text passes through as detail."""
        text = str(e)
        try:
            body = json.loads(text)
            return cls(
                body["message"], body.get("code", "internal"), body.get("params") or {}
            )
        except (json.JSONDecodeError, TypeError, KeyError):
            return cls(text)
