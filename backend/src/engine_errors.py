"""EngineRejection carries the Rust engine's ``{code, params, message}`` wire JSON
to the HTTP error body."""

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
