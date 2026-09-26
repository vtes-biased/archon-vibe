import logging
import re
import uuid
from contextvars import ContextVar

import psycopg

request_id: ContextVar[str | None] = ContextVar("request_id", default=None)

_REQUEST_ID = re.compile(r"[0-9a-f]{32}")
_CREDENTIAL = re.compile(r"([?&](?:token|code|state)=)[^&\s\"]+")


def mask(text: str) -> str:
    return _CREDENTIAL.sub(r"\1***", text)


class RequestIdMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        sent = dict(scope["headers"]).get(b"x-request-id", b"").decode("latin-1")
        # Never reset: the 500 and uvicorn's traceback are logged after this
        # returns, still inside uvicorn's per-request task.
        request_id.set(sent if _REQUEST_ID.fullmatch(sent) else uuid.uuid4().hex)
        await self.app(scope, receive, send)


class _RequestFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = mask(record.getMessage())
        rid = request_id.get()
        record.msg = f"[{rid}] {message}" if rid else message
        record.args = None
        return True


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )
    handler.addFilter(_RequestFilter())
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    # uvicorn's CLI configures its own handlers before importing the app; route
    # them through the filtered root handler so its access line is masked too.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True


async def tag_connection(conn: psycopg.AsyncConnection, app: str) -> None:
    rid = request_id.get()
    name = f"{app}/{rid}" if rid else app
    if conn.info.parameter_status("application_name") != name:
        await conn.execute("SELECT set_config('application_name', %s, false)", (name,))
