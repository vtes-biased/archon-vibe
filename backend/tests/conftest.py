"""Test fixtures and configuration."""

import os
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import psycopg
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Add backend/src to path for imports
backend_src = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(backend_src.parent))

# Set test database URL before importing app modules
_TEST_DB_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://archon:archon_dev_password@localhost:5433/archon_test",
)
os.environ["DATABASE_URL"] = _TEST_DB_URL
os.environ["VEKN_SYNC_ENABLED"] = "false"  # Disable VEKN sync in tests


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
            conn.execute(psycopg.sql.SQL("CREATE DATABASE {}").format(
                psycopg.sql.Identifier(db_name)
            ))


# Auto-create test database before any test collection
_ensure_test_db_exists()

from src import db
from src.main import app
from src.routes.auth import create_access_token
from tests.mock_vekn_data import generate_mock_users


def make_auth_header(user_uid: str) -> dict[str, str]:
    """Create an Authorization header with a valid access token for the given user."""
    token, _ = create_access_token(user_uid)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def test_db() -> AsyncIterator[None]:
    """Initialize test database and clean it up after tests."""
    # Initialize database
    await db.init_db()
    
    # Clean existing data
    async with db.get_connection() as conn:
        await conn.execute("DELETE FROM objects WHERE type = 'user'")

    yield

    # Clean up after test
    async with db.get_connection() as conn:
        await conn.execute("DELETE FROM objects WHERE type = 'user'")
    
    await db.close_db()


@pytest_asyncio.fixture
async def test_client(test_db) -> AsyncIterator[AsyncClient]:
    """Create test client for API requests."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client


@pytest_asyncio.fixture
async def populated_db(test_db) -> list:
    """Populate database with mock users for testing."""
    users = generate_mock_users(400)
    
    # Insert all users
    for user in users:
        await db.insert_user(user)
    
    return users

