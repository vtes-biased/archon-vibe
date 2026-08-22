import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from scalar_fastapi import get_scalar_api_reference

from .db import close_pool, open_pool
from .schemas import COMPONENTS
from .v1 import router

SITE_URL = os.getenv("SITE_URL_BASE", "http://localhost:8000")
API_URL = os.getenv("PUBLIC_API_URL_BASE", "http://localhost:8001")

DESCRIPTION = (
    """
Read-only access to Archon's organizational data: tournaments, leagues, published
decks, member ratings and community links.

Members are published by **VEKN ID, never by name**. No name, contact, city or
avatar is served here, and sanctions are never served. Card data belongs to
[krcg](https://v4.api.krcg.org/docs), not to us.

A single object comes back as JSON. A collection comes back as **JSON Lines**:
one object per line, opened by a `header` line and closed by an `eof` line.

```
{"type":"header","generated_at":"2026-08-22T15:04:05.123456"}
{"type":"tournament","data":{ … }}
{"type":"eof","count":1}
```

## Reading a list

A list endpoint streams, and its response is not a JSON document: it will not
parse as one. Read it line by line and decode each line on its own. Most clients
have this built in and most of them do not use it by default, which for
`/v1/tournaments` means holding tens of megabytes in memory for nothing. Ask for
the streaming variant: `iter_lines()` on a `stream=True` request in Python's
requests or httpx, the response body as an async iterator in Node,
`curl --no-buffer`.

Three consequences worth knowing:

* **There is no pagination.** Read as far as you want, then close the
  connection. For the ten most recently created tournaments, read ten lines and
  hang up. Nothing is lost and nothing needs resuming.
* **Check for the `eof` line before you trust what came before it.** A response
  cut short mid-flight looks exactly like a short one until the trailer is
  missing, and by then you have already written rows.
* **The server reads in blocks of 250 rows**, holding no database connection
  between them, which is why a slow reader costs nothing. You never see those
  boundaries: they are not chunks, not packets, and not something to align on.

## Ordering and freshness

Lists arrive **newest first**, ordered by `uid`. Uids are UUIDv7, so they sort by
the moment a record was created, which is not the same as when the event
happened: a decade-old tournament imported last week sorts as new. Select by
event date with `start_after` and `start_before` instead.

A record's `uid` never changes, so a record never moves while you are reading.
It also means **there is no way to ask what changed since when**. That is
deliberate rather than missing: deleted records are not served, so anyone
diffing by date would accumulate rows that no longer exist. Read what you need
when you need it, or take `/v1/export` for the whole corpus in one gzipped pass.

## Getting a token

You need an Archon account with your VEKN membership, plus the DEV role, which an
IC grants. With it, open Developer in [your profile]({site}/profile), register a
client, tick `api:read` and keep the secret: it is shown once. A client that only
needs `api:read` has no redirect URI to declare.

Exchange the secret for a token that lasts an hour:

```
curl -X POST {api}/oauth/token \
  -d grant_type=client_credentials -d client_id=... -d client_secret=...
```

Form-encoded as RFC 6749 specifies, or a JSON body with the same keys, whichever
your client prefers. There is no refresh token: mint another when it expires.
Send it as `Authorization: Bearer <token>` on every request.
""".strip()
    .replace("{site}", SITE_URL)
    .replace("{api}", API_URL)
)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await open_pool()
    try:
        yield
    finally:
        await close_pool()


app = FastAPI(
    title="Archon Public API",
    version="1",
    description=DESCRIPTION,
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["Authorization"],
)

app.include_router(router)


def _openapi() -> dict:
    if app.openapi_schema is None:
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        components = schema.setdefault("components", {})
        components.setdefault("schemas", {}).update(COMPONENTS)
        components["securitySchemes"] = {
            "bearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
        }
        schema["security"] = [{"bearerAuth": []}]
        # FastAPI adds an `application/json` 200 of its own and `openapi_extra`
        # merges beside it rather than replacing it, so a stream would advertise
        # a JSON body it never returns — and Scalar would preview that one.
        for methods in schema["paths"].values():
            for operation in methods.values():
                content = operation["responses"]["200"]["content"]
                if len(content) > 1:
                    content.pop("application/json", None)
        app.openapi_schema = schema
    return app.openapi_schema


app.openapi = _openapi


@app.get("/docs", include_in_schema=False)
async def docs():
    return get_scalar_api_reference(openapi_url=app.openapi_url, title=app.title)
