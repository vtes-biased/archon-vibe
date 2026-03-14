"""Seed (or clean up) test data for Playwright E2E tests.

Run via: uv run python3 <this_script>  (from backend/ directory)
"""

import asyncio
import json
import os
import sys

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://archon:archon_dev_password@localhost:5433/archon",
)

from datetime import UTC, datetime  # noqa: E402

from argon2 import PasswordHasher  # noqa: E402
from src.db import (  # noqa: E402
    delete_object,
    get_connection,
    init_db,
    insert_auth_method,
    insert_user,
)
from src.models import AuthMethod, AuthMethodType, CommunityLink, CommunityLinkType, Role, User  # noqa: E402
from src.snapshots import generate_snapshots  # noqa: E402
from uuid6 import uuid7  # noqa: E402

ph = PasswordHasher()

# Stable prefix so we can find them for cleanup
E2E_PREFIX = "e2e-test-"

ORGANIZER_EMAIL = "e2e-organizer@example.com"
ORGANIZER_PASSWORD = "E2eT3stP@ss!"

PLAYER_NAMES = [
    "Alice Deckmaster",
    "Bob Ventrue",
    "Charlie Toreador",
    "Diana Tremere",
    "Eve Nosferatu",
    "Frank Brujah",
    "Grace Malkavian",
    "Hank Gangrel",
    "Ivy Lasombra",
    "Jack Tzimisce",
]

PLAYER_COUNTRIES = ["US", "US", "FR", "DE", "US", "GB", "JP", "BR", "US", "CA"]

# Some players have roles so they appear at the public access level
# (public only shows NC/Prince users)
PLAYER_ROLES: list[list[Role]] = [
    [],  # Alice
    [],  # Bob
    [Role.PRINCE],  # Charlie - Prince (FR)
    [Role.NC],  # Diana - NC (DE)
    [],  # Eve
    [],  # Frank
    [],  # Grace
    [],  # Hank
    [],  # Ivy
    [],  # Jack
]

# Community links for some players
PLAYER_LINKS: list[list[CommunityLink]] = [
    [  # Alice - regular member with links
        CommunityLink(type=CommunityLinkType.BLOG, url="https://alice-vtes.blog", label="Alice's Blog", language="en"),
    ],
    [],  # Bob
    [  # Charlie - Prince (FR)
        CommunityLink(type=CommunityLinkType.DISCORD, url="https://discord.gg/vtes-france", label="VTES France"),
        CommunityLink(type=CommunityLinkType.YOUTUBE, url="https://youtube.com/@vtes-fr", label="VTES FR", language="fr"),
    ],
    [  # Diana - NC (DE)
        CommunityLink(type=CommunityLinkType.TELEGRAM, url="https://t.me/vtes_germany", label="VTES Germany"),
    ],
    [], [], [], [], [], [],  # Eve through Jack
]


async def seed() -> dict:
    await init_db()
    now = datetime.now(UTC)

    # Truncate all objects so the test DB only contains our mock data.
    # This avoids syncing the entire VEKN dataset (~7MB) during E2E tests.
    async with get_connection() as conn:
        await conn.execute("DELETE FROM objects")
        await conn.execute("DELETE FROM auth_methods")

    # --- Organizer (IC) ---
    org_uid = str(uuid7())
    organizer = User(
        uid=org_uid,
        modified=now,
        name="E2E Organizer",
        country="US",
        vekn_id="9999901",
        roles=[Role.IC, Role.ETHICS],
        contact_email=ORGANIZER_EMAIL,
        community_links=[
            CommunityLink(type=CommunityLinkType.DISCORD, url="https://discord.gg/vtes-global", label="VTES Global"),
            CommunityLink(type=CommunityLinkType.YOUTUBE, url="https://youtube.com/@vtes-channel", label="VTES Channel", language="en"),
        ],
    )
    await insert_user(organizer)

    # Auth method (email + password)
    auth_uid = str(uuid7())
    auth_method = AuthMethod(
        uid=auth_uid,
        modified=now,
        user_uid=org_uid,
        method_type=AuthMethodType.EMAIL,
        identifier=ORGANIZER_EMAIL,
        credential_hash=ph.hash(ORGANIZER_PASSWORD),
        verified=True,
        created_at=now,
        last_used_at=now,
    )
    await insert_auth_method(auth_method)

    # --- Players ---
    player_uids: list[str] = []
    for i, (name, country, roles, links) in enumerate(
        zip(PLAYER_NAMES, PLAYER_COUNTRIES, PLAYER_ROLES, PLAYER_LINKS, strict=True)
    ):
        uid = str(uuid7())
        player_uids.append(uid)
        user = User(
            uid=uid,
            modified=now,
            name=name,
            country=country,
            vekn_id=f"999{i + 10:04d}",
            roles=roles,
            community_links=links,
            # Officials get contact info for the Officials Directory
            contact_email=f"{name.split()[0].lower()}@example.com" if roles else None,
        )
        await insert_user(user)

    # Regenerate snapshots so the frontend gets fresh data (not stale VEKN cache)
    await generate_snapshots()

    return {
        "organizer_uid": org_uid,
        "organizer_email": ORGANIZER_EMAIL,
        "organizer_password": ORGANIZER_PASSWORD,
        "player_uids": player_uids,
        "player_names": PLAYER_NAMES,
    }


async def cleanup() -> None:
    await init_db()
    # Delete auth methods for organizer email
    async with get_connection() as conn:
        await conn.execute(
            "DELETE FROM auth_methods WHERE data->>'identifier' = %s",
            (ORGANIZER_EMAIL,),
        )
    # Delete all objects with e2e vekn_ids (organizer 9999xxx + players 999xxxx)
    async with get_connection() as conn:
        result = await conn.execute(
            """SELECT uid FROM objects WHERE type = 'user'
               AND ("full"->>'vekn_id' LIKE '9999%'
                    OR "full"->>'vekn_id' LIKE '9990%')"""
        )
        rows = await result.fetchall()
        for row in rows:
            await delete_object(row[0])
    # Delete tournaments created by e2e organizer
    async with get_connection() as conn:
        result = await conn.execute(
            """SELECT uid FROM objects WHERE type = 'tournament'
               AND "full"->>'name' LIKE 'E2E %'"""
        )
        rows = await result.fetchall()
        for row in rows:
            await delete_object(row[0])


if __name__ == "__main__":
    if "--cleanup" in sys.argv:
        asyncio.run(cleanup())
        print(json.dumps({"status": "cleaned"}))
    else:
        result = asyncio.run(seed())
        print(json.dumps(result))
