from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from scalar_fastapi import get_scalar_api_reference

from .db import close_pool, open_pool
from .schemas import COMPONENTS
from .v1 import router

DESCRIPTION = """
Read-only access to Archon's organizational data: tournaments, leagues, published
decks, member ratings and community links.

Members are published by **VEKN ID, never by name** — no name, contact, city or
avatar is served here, and a player without a VEKN ID has no row at all. Sanctions
are never served. Card data is [krcg](https://static.krcg.org)'s, not ours.

Every endpoint requires a bearer token. A single object comes back as JSON; a
collection streams as **JSON Lines** — one object per line, opened by a `header`
line and closed by an `eof` line whose absence means the response was cut short.

```
{"type":"header","generated_at":"2026-08-22T15:04:05.123456"}
{"type":"tournament","data":{ … }}
{"type":"eof","count":1}
```

There is no pagination anywhere. Read as far into a stream as you want and close
the connection; for a top-ten ranking, read ten lines.

Only live, visible objects are ever served: nothing deleted, nothing unpublished,
and no way to ask what changed since when. This API is for building something new
on top of the data, not for keeping a copy of it in step — read what you need when
you need it, or take `/v1/export` for the whole corpus in one gzipped pass.
""".strip()


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
        app.openapi_schema = schema
    return app.openapi_schema


app.openapi = _openapi


@app.get("/docs", include_in_schema=False)
async def docs():
    return get_scalar_api_reference(openapi_url=app.openapi_url, title=app.title)
