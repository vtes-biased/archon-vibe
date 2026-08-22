# Not `..db`: its pool is the app's global, which nothing in this process fills.

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import psycopg
from psycopg_pool import AsyncConnectionPool

DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://archon:archon_dev_password@localhost:5433/archon",
)

POOL_MAX_SIZE = int(os.getenv("PUBLIC_API_DB_POOL_MAX_SIZE", "4"))

STATEMENT_TIMEOUT_MS = int(os.getenv("PUBLIC_API_STATEMENT_TIMEOUT_MS", "15000"))

_pool: AsyncConnectionPool | None = None


async def open_pool() -> None:
    global _pool
    _pool = AsyncConnectionPool(
        conninfo=DB_URL,
        min_size=1,
        max_size=POOL_MAX_SIZE,
        open=False,
        kwargs={
            "autocommit": True,
            "options": f"-c statement_timeout={STATEMENT_TIMEOUT_MS}",
        },
    )
    await _pool.open()


async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


@asynccontextmanager
async def get_connection() -> AsyncIterator[psycopg.AsyncConnection]:
    if _pool is None:
        raise RuntimeError("Public API pool not initialized")
    async with _pool.connection() as conn:
        yield conn
