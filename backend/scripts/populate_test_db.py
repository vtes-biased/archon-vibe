"""Populate test database with mock users for E2E testing."""

import asyncio
import os
import sys
from pathlib import Path

# Add backend to path for local development
# This ensures backend/src and backend/tests are importable
backend_dir = Path(__file__).parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from src import db
from src.models import Role, User

# Import uuid7 for generating IDs
from uuid6 import uuid7
from datetime import UTC, datetime, timedelta
import random


def generate_mock_users(count: int = 300) -> list[User]:
    """Generate mock VEKN users for testing."""
    first_names = [
        "John", "Jane", "Michael", "Sarah", "David", "Emma", "Robert", "Lisa",
        "William", "Mary", "James", "Patricia", "Thomas", "Jennifer", "Charles",
        "Linda", "Daniel", "Elizabeth", "Matthew", "Barbara", "Anthony", "Susan",
    ]
    
    last_names = [
        "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
        "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez",
        "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin",
    ]
    
    countries = [
        "US", "CA", "GB", "DE", "FR", "ES", "IT", "AU", "NZ", "JP",
        "BR", "MX", "AR", "CL", "NL", "BE", "SE", "NO", "DK", "FI",
    ]
    
    all_roles = [Role.IC, Role.NC, Role.PRINCE, Role.ETHICS, Role.PTC, Role.PT, Role.RULEMONGER, Role.JUDGE]
    
    users = []
    base_time = datetime.now(UTC)
    
    for i in range(count):
        first_name = random.choice(first_names)
        last_name = random.choice(last_names)
        name = f"{first_name} {last_name}"
        country = random.choice(countries)
        vekn_id = f"{random.randint(1000000, 9999999)}" if random.random() > 0.2 else None
        nickname = f"{first_name[:3]}{random.randint(10, 99)}" if random.random() > 0.7 else None
        role_count = random.choices([0, 1, 2, 3], weights=[60, 25, 10, 5])[0]
        user_roles = random.sample(all_roles, min(role_count, len(all_roles))) if role_count > 0 else []
        modified = base_time - timedelta(days=random.randint(0, 365))
        
        user = User(
            uid=str(uuid7()),
            modified=modified,
            name=name,
            country=country,
            vekn_id=vekn_id,
            nickname=nickname,
            roles=user_roles,
        )
        users.append(user)
    
    return users


async def main():
    """Populate database with mock users."""
    db_url = os.getenv(
        "DATABASE_URL",
        "postgresql://archon:archon_dev_password@localhost:5433/archon",
    )
    os.environ["DATABASE_URL"] = db_url
    os.environ["VEKN_SYNC_ENABLED"] = "false"

    await db.init_db()

    # Clean existing users
    async with db.get_connection() as conn:
        await conn.execute("DELETE FROM users")

    # Generate and insert mock users
    users = generate_mock_users(300)
    for user in users:
        await db.insert_user(user)

    print(f"✅ Populated database with {len(users)} users")
    await db.close_db()


if __name__ == "__main__":
    asyncio.run(main())

