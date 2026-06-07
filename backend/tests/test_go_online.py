"""Integration tests for pst #45: go-online resolves/creates offline players
BEFORE taking the FOR UPDATE lock.

The restructure moves user creation out of the lock, so the pre-lock checks must
still gate side effects: an unauthorized or wrong-device request must be rejected
WITHOUT creating any users.
"""

import json
from datetime import UTC, datetime

import msgspec
import pytest
import pytest_asyncio
import src.db as db
from src.models import Player, Seat, Table, Tournament, User
from uuid6 import uuid7

from tests.conftest import make_auth_header


@pytest_asyncio.fixture(autouse=True)
async def _cleanup_objects(test_db):
    """conftest's test_db only clears users; drop tournaments we create too."""
    yield
    async with db.get_connection() as conn:
        await conn.execute(
            "DELETE FROM objects WHERE type IN ('tournament', 'deck', 'sanction')"
        )


async def _count_users() -> int:
    async with db.get_connection() as conn:
        row = await (
            await conn.execute("SELECT count(*) FROM objects WHERE type = 'user'")
        ).fetchone()
    return row[0]


def _offline_tournament_payload(uid: str, org_uid: str, temp_uid: str) -> dict:
    """A full offline tournament, locked to device 'devA', with one temp player."""
    t = Tournament(
        uid=uid,
        modified=datetime.now(UTC),
        name="Offline T",
        organizers_uids=[org_uid],
        country="France",
        offline_mode=True,
        offline_device_id="devA",
        players=[Player(user_uid=temp_uid)],
    )
    return json.loads(msgspec.json.encode(t))


async def _seed(org_uid: str) -> str:
    """Insert the server-side offline tournament; return its uid."""
    uid = str(uuid7())
    t = msgspec.convert(
        _offline_tournament_payload(uid, org_uid, "TEMP-seed"), Tournament
    )
    await db.insert_tournament(t)
    return uid


@pytest.mark.asyncio
async def test_non_organizer_rejected_without_creating_users(test_client, test_db):
    org = User(uid=str(uuid7()), modified=datetime.now(UTC), name="Org")
    intruder = User(uid=str(uuid7()), modified=datetime.now(UTC), name="Intruder")
    await db.insert_user(org)
    await db.insert_user(intruder)
    uid = await _seed(org.uid)

    temp_uid = "TEMP-" + str(uuid7())
    body = {
        "device_id": "devA",
        "tournament": _offline_tournament_payload(uid, org.uid, temp_uid),
        "offline_players": [{"temp_uid": temp_uid, "name": "Should Not Exist"}],
    }
    before = await _count_users()
    resp = await test_client.post(
        f"/api/tournaments/{uid}/go-online",
        json=body,
        headers=make_auth_header(intruder.uid),
    )
    assert resp.status_code == 403
    assert await _count_users() == before  # no player created for a rejected request


@pytest.mark.asyncio
async def test_wrong_device_rejected_without_creating_users(test_client, test_db):
    org = User(uid=str(uuid7()), modified=datetime.now(UTC), name="Org")
    await db.insert_user(org)
    uid = await _seed(org.uid)

    temp_uid = "TEMP-" + str(uuid7())
    body = {
        "device_id": "devB",  # tournament is locked to devA, no force
        "tournament": _offline_tournament_payload(uid, org.uid, temp_uid),
        "offline_players": [{"temp_uid": temp_uid, "name": "Should Not Exist"}],
    }
    before = await _count_users()
    resp = await test_client.post(
        f"/api/tournaments/{uid}/go-online",
        json=body,
        headers=make_auth_header(org.uid),
    )
    assert resp.status_code == 409
    assert await _count_users() == before


@pytest.mark.asyncio
async def test_organizer_resolves_players_and_goes_online(test_client, test_db):
    org = User(uid=str(uuid7()), modified=datetime.now(UTC), name="Org")
    await db.insert_user(org)
    uid = await _seed(org.uid)

    temp_uid = str(uuid7())  # frontend uses crypto.randomUUID()
    temp_vekn = f"TEMP-{temp_uid[:8]}"  # placeholder vekn assigned offline
    body = {
        "device_id": "devA",
        "tournament": _offline_tournament_payload(uid, org.uid, temp_uid),
        "offline_players": [
            {"temp_uid": temp_uid, "name": "Alice Offline", "vekn_id": temp_vekn}
        ],
    }
    resp = await test_client.post(
        f"/api/tournaments/{uid}/go-online",
        json=body,
        headers=make_auth_header(org.uid),
    )
    assert resp.status_code == 200
    assert resp.json()["offline_mode"] is False

    # The temp player was resolved to a freshly created user and the tournament's
    # player reference was remapped to the real uid.
    saved = await db.get_tournament_by_uid(uid)
    player_uid = saved.players[0].user_uid
    assert player_uid != temp_uid
    created = await db.get_user_by_uid(player_uid)
    assert created is not None
    assert created.name == "Alice Offline"
    # The offline TEMP- vekn is replaced by a freshly allocated, real numeric VEKN.
    assert created.vekn_id != temp_vekn
    assert not created.vekn_id.startswith("TEMP-")
    assert created.vekn_id.isdigit() and int(created.vekn_id) >= 1000000


@pytest.mark.asyncio
async def test_nested_uids_and_deck_attribution_remapped(test_client, test_db):
    """Structural remap reaches seating/winner; deck attribution is recomputed
    from the resolved user (pst #15) — no stale TEMP- survives reconciliation."""
    org = User(uid=str(uuid7()), modified=datetime.now(UTC), name="Org")
    await db.insert_user(org)
    base_uid = await _seed(org.uid)

    temp_uid = str(uuid7())  # frontend uses crypto.randomUUID()
    temp_vekn = f"TEMP-{temp_uid[:8]}"  # vekn is the UID's 8-char prefix
    t = Tournament(
        uid=base_uid,
        modified=datetime.now(UTC),
        name="Offline T",
        organizers_uids=[org.uid],
        country="France",
        offline_mode=True,
        offline_device_id="devA",
        players=[Player(user_uid=temp_uid)],
        rounds=[[Table(seating=[Seat(player_uid=temp_uid)])]],
        winner=temp_uid,
    )
    body = {
        "device_id": "devA",
        "tournament": json.loads(msgspec.json.encode(t)),
        "offline_players": [
            {"temp_uid": temp_uid, "name": "Alice Offline", "vekn_id": temp_vekn}
        ],
        "offline_decks": [
            {
                "uid": str(uuid7()),
                "modified": datetime.now(UTC).isoformat(),
                "tournament_uid": base_uid,
                "user_uid": temp_uid,
                "attribution": temp_vekn,  # attributed to the temp vekn
                "name": "Alice's Deck",
            }
        ],
    }
    resp = await test_client.post(
        f"/api/tournaments/{base_uid}/go-online",
        json=body,
        headers=make_auth_header(org.uid),
    )
    assert resp.status_code == 200

    saved = await db.get_tournament_by_uid(base_uid)
    real_uid = saved.players[0].user_uid
    created = await db.get_user_by_uid(real_uid)
    # Nested references all remapped; nothing temp survives anywhere in the JSON.
    assert saved.rounds[0][0].seating[0].player_uid == real_uid
    assert saved.winner == real_uid
    assert temp_uid not in msgspec.json.encode(saved).decode()
    assert "TEMP-" not in msgspec.json.encode(saved).decode()

    # Deck owner repointed and attribution recomputed to the real vekn (not TEMP-).
    decks = await db.get_decks_for_tournament(base_uid)
    assert len(decks) == 1
    assert decks[0].user_uid == real_uid
    assert decks[0].attribution == created.vekn_id
    assert not decks[0].attribution.startswith("TEMP-")
