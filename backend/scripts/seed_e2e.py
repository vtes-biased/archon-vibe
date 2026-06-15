"""Seed E2E test data: organizer with auth + 10 named players.

Run via: uv run python backend/scripts/seed_e2e.py [--output /path/to/seed.json] [--cleanup]
"""

import asyncio
import json
import os
import sys
from pathlib import Path

# Add backend to path for imports
backend_dir = Path(__file__).parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from datetime import UTC, datetime  # noqa: E402

from argon2 import PasswordHasher  # noqa: E402
from src.db import (  # noqa: E402
    delete_object,
    get_connection,
    init_db,
    insert_auth_method,
    save_user,
)
from src.models import (  # noqa: E402
    AuthMethod,
    AuthMethodType,
    CommunityLink,
    CommunityLinkType,
    LinkModeration,
    Role,
    User,
)
from src.snapshots import generate_snapshots  # noqa: E402
from uuid import uuid7  # noqa: E402

ph = PasswordHasher()

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

PLAYER_LINKS: list[list[CommunityLink]] = [
    [
        CommunityLink(
            type=CommunityLinkType.BLOG,
            url="https://alice-vtes.blog",
            label="Alice's Blog",
            languages=["en"],
        )
    ],
    [],  # Bob
    [
        CommunityLink(
            type=CommunityLinkType.DISCORD,
            url="https://discord.gg/vtes-france",
            label="VTES France",
        ),
        CommunityLink(
            type=CommunityLinkType.YOUTUBE,
            url="https://youtube.com/@vtes-fr",
            label="VTES FR",
            languages=["fr"],
        ),
    ],
    [
        CommunityLink(
            type=CommunityLinkType.TELEGRAM,
            url="https://t.me/vtes_germany",
            label="VTES Germany",
        )
    ],
    [],
    [],
    [],
    [],
    [],
    [],  # Eve through Jack
]


async def seed() -> dict:
    await init_db()
    now = datetime.now(UTC)

    # Destructive-op guard: this wipes ALL objects/auth_methods. Refuse to run
    # against a non-empty DB unless explicitly forced (E2E_FORCE=1), so a stray
    # DATABASE_URL pointing at a real DB can't be silently truncated.
    if os.environ.get("E2E_FORCE") != "1":
        async with get_connection() as conn:
            result = await conn.execute("SELECT count(*) FROM objects")
            (count,) = await result.fetchone()
        if count:
            raise SystemExit(
                f"Refusing to seed: target DB has {count} objects and this script "
                "runs DELETE FROM objects/auth_methods.\n"
                "Point DATABASE_URL at a throwaway DB (e.g. create a fresh "
                "archon_e2e database), or set E2E_FORCE=1 to override."
            )

    # Truncate all objects so the test DB only contains our mock data.
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
            CommunityLink(
                type=CommunityLinkType.DISCORD,
                url="https://discord.gg/vtes-global",
                label="VTES Global",
                # Globally-pinned by the IC so it surfaces under Global Resources
                # (the section only lists scope="global" promotions post-97dee76).
                moderation=LinkModeration(
                    status="promoted", by=org_uid, at=now, scope="global"
                ),
            ),
            CommunityLink(
                type=CommunityLinkType.YOUTUBE,
                url="https://youtube.com/@vtes-channel",
                label="VTES Channel",
                languages=["en"],
            ),
        ],
    )
    await save_user(organizer)

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
            contact_email=f"{name.split()[0].lower()}@example.com" if roles else None,
        )
        await save_user(user)

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
    async with get_connection() as conn:
        await conn.execute(
            "DELETE FROM auth_methods WHERE data->>'identifier' = %s",
            (ORGANIZER_EMAIL,),
        )
    async with get_connection() as conn:
        result = await conn.execute(
            """SELECT uid FROM objects WHERE type = 'user'
               AND ("full"->>'vekn_id' LIKE '9999%'
                    OR "full"->>'vekn_id' LIKE '9990%')"""
        )
        rows = await result.fetchall()
        for row in rows:
            await delete_object(row[0])
    async with get_connection() as conn:
        result = await conn.execute(
            """SELECT uid FROM objects WHERE type IN ('tournament', 'league')
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
        output = json.dumps(result)
        print(output)
        # Write to file if --output is specified
        if "--output" in sys.argv:
            idx = sys.argv.index("--output")
            out_path = Path(sys.argv[idx + 1])
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(output)
