"""Test fixtures and configuration."""

import os
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import psycopg
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

backend_src = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(backend_src.parent))

_TEST_DB_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://archon:archon_dev_password@localhost:5433/archon_test",
)
os.environ["DATABASE_URL"] = _TEST_DB_URL
os.environ["VEKN_SYNC_ENABLED"] = "false"
# A two-card subset of the real card database: engine/data/cards.json is a
# generated artifact that CI never downloads, so tests pin their own.
os.environ["CARDS_JSON_PATH"] = str(Path(__file__).parent / "fixtures" / "cards.json")


def _ensure_test_db_exists() -> None:
    """Create the test database if it doesn't exist (connects to default DB)."""
    parsed = urlparse(_TEST_DB_URL)
    db_name = parsed.path.lstrip("/")
    # Connect to the default 'postgres' database to run CREATE DATABASE
    admin_url = urlunparse(parsed._replace(path="/postgres"))
    with psycopg.connect(admin_url, autocommit=True) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (db_name,)
        ).fetchone()
        if not exists:
            conn.execute(
                psycopg.sql.SQL("CREATE DATABASE {}").format(  # ty: ignore[possibly-missing-attribute]
                    psycopg.sql.Identifier(db_name)  # ty: ignore[possibly-missing-attribute]
                )
            )


# Auto-create test database before any test collection
_ensure_test_db_exists()

# migrate_from_archon.py imports as `backend.src.*`; this harness sets up `src.*`.
# Alias both names to one module object, or the script's db calls miss test_db()'s init_db().
import importlib
import types

from src import db
from src.main import app
from src.routes.auth import create_access_token

sys.modules.setdefault("backend", types.ModuleType("backend"))
sys.modules["backend"].src = sys.modules["src"]
sys.modules["backend.src"] = sys.modules["src"]
for _mod in ("db", "models", "vekn_sync"):
    sys.modules[f"backend.src.{_mod}"] = importlib.import_module(f"src.{_mod}")

from tests.mock_vekn_data import generate_mock_users


def make_auth_header(user_uid: str) -> dict[str, str]:
    token, _ = create_access_token(user_uid)
    return {"Authorization": f"Bearer {token}"}


async def seed_tournament(tournament):
    """Persist a tournament in test setup. save_tournament requires a conn (the prod
    row-lock invariant); a fresh seed just needs any connection, no FOR UPDATE lock."""
    async with db.get_connection() as conn:
        return await db.save_tournament(tournament, conn=conn)


@pytest_asyncio.fixture
async def test_db() -> AsyncIterator[None]:
    await db.init_db()

    async with db.get_connection() as conn:
        await conn.execute("DELETE FROM objects WHERE type = 'user'")
        await conn.execute("DELETE FROM auth_methods")

    yield

    async with db.get_connection() as conn:
        await conn.execute("DELETE FROM objects WHERE type = 'user'")
        await conn.execute("DELETE FROM auth_methods")

    await db.close_db()


@pytest_asyncio.fixture
async def test_client(test_db) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client


@pytest_asyncio.fixture
async def populated_db(test_db) -> list:
    users = generate_mock_users(400)

    for user in users:
        await db.save_user(user)

    return users
