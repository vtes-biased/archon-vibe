"""The stored-value migration runner, against a real database.

The guards are jsonb predicates over shapes no model can express, so a fixture
built through `save_user` would already hold the new one and cover nothing. Two
invariants: an old-shape row decodes after the run, and a second run rewrites
nothing.
"""

import json
from datetime import UTC, datetime
from uuid import uuid7

import msgspec
import pytest
from src import db
from src.migrations import run_migrations
from src.models import User


async def _insert_raw(full_data: dict) -> str:
    """Seed the pre-migration shape. `save_object` recomputes projections from
    `full`, so only a raw INSERT can put a shape there the models refuse."""
    uid = str(uuid7())
    full_data = {"uid": uid, "modified": datetime.now(UTC).isoformat(), **full_data}
    async with db.get_connection() as conn:
        await conn.execute(
            'INSERT INTO objects (uid, type, "public", "member", "api", "full")'
            " VALUES (%s, 'user', NULL, %s::jsonb, NULL, %s::jsonb)",
            (uid, json.dumps(full_data), json.dumps(full_data)),
        )
    return uid


async def _load(uid: str) -> User:
    async with db.get_connection() as conn:
        result = await conn.execute('SELECT "full" FROM objects WHERE uid = %s', (uid,))
        row = await result.fetchone()
    return msgspec.convert(row[0], User, strict=False)


@pytest.mark.asyncio
async def test_migrations_make_the_old_shapes_decode(test_db):
    judgekin = await _insert_raw({"name": "Old Role", "roles": ["Judgekin", "Prince"]})
    moderated = await _insert_raw(
        {
            "name": "Old Moderation",
            "community_links": [
                {
                    "type": "discord",
                    "url": "https://discord.gg/vtes",
                    "label": "VTES",
                    "moderation": {
                        "status": "promoted",
                        "scope": "national",
                        "by": str(uuid7()),
                        "at": datetime.now(UTC).isoformat(),
                    },
                },
                {
                    "type": "discord",
                    "url": "https://discord.gg/hidden",
                    "label": "Hidden",
                    "moderation": {
                        "status": "hidden",
                        "scope": None,
                        "by": str(uuid7()),
                        "at": datetime.now(UTC).isoformat(),
                    },
                },
            ],
        }
    )

    for uid in (judgekin, moderated):
        with pytest.raises(msgspec.ValidationError):
            await _load(uid)

    counts = await run_migrations()
    assert counts == {
        "rename-judgekin-to-sheriff": 1,
        "collapse-link-moderation": 1,
    }

    assert [str(r) for r in (await _load(judgekin)).roles] == ["Sheriff", "Prince"]
    links = (await _load(moderated)).community_links
    assert [link.moderation for link in links] == ["national", "hidden"]

    # The projections come back from `full`, not from the stale columns.
    async with db.get_connection() as conn:
        result = await conn.execute(
            "SELECT \"member\"->'roles' FROM objects WHERE uid = %s", (judgekin,)
        )
        assert (await result.fetchone())[0] == ["Sheriff", "Prince"]

    assert await run_migrations() == {}
