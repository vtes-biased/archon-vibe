"""Test fixtures and configuration."""

import os
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Add backend/src to path for imports
backend_src = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(backend_src.parent))

# Set test database URL before importing app modules
os.environ["DATABASE_URL"] = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://archon:archon_dev_password@localhost:5433/archon_test",
)
os.environ["VEKN_SYNC_ENABLED"] = "false"  # Disable VEKN sync in tests

from src import db
from src.main import app
from tests.mock_vekn_data import generate_mock_users


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

