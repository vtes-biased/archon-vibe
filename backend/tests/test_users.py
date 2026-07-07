"""Tests for user API endpoints."""

from datetime import UTC, datetime
from uuid import uuid7

import pytest
from httpx import AsyncClient
from src import db
from src.models import Role, User

from tests.conftest import make_auth_header


async def _mk_user(country: str, roles: list[Role], vekn: str | None = None) -> User:
    """Persist a minimal user with explicit country/roles (deterministic tests)."""
    user = User(
        uid=str(uuid7()),
        modified=datetime.now(UTC),
        name="Test",
        country=country,
        vekn_id=vekn,
        roles=list(roles),
        local_modifications=set(),
    )
    await db.save_user(user)
    return user


@pytest.mark.asyncio
async def test_create_user(test_client: AsyncClient, populated_db):
    """Test creating a new user (requires IC/NC/Prince auth)."""
    # Find a user with NC or Prince role to act as creator
    admin = next(
        u for u in populated_db if Role.NC in u.roles or Role.PRINCE in u.roles
    )

    response = await test_client.post(
        "/api/users/",
        json={
            "name": "Test User",
            "country": "US",
            "city": "New York",
            "nickname": "testuser",
        },
        headers=make_auth_header(admin.uid),
    )

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test User"
    assert data["country"] == "US"
    assert data["city"] == "New York"
    assert data["nickname"] == "testuser"
    assert "uid" in data
    assert "modified" in data


@pytest.mark.asyncio
async def test_create_user_dedup_email_conflict(test_db, test_client: AsyncClient):
    """An email already on a live member 409s (case-insensitively) with the match
    uid, so the door flow pivots to sponsor+register instead of a duplicate."""
    ic = await _mk_user("US", [Role.IC], vekn="3000001")
    existing = User(
        uid=str(uuid7()),
        modified=datetime.now(UTC),
        name="Jane Doe",
        country="US",
        vekn_id="3000002",
        contact_email="jane@example.com",
        local_modifications=set(),
    )
    await db.save_user(existing)

    resp = await test_client.post(
        "/api/users/",
        json={"name": "Jane D", "country": "US", "email": "JANE@example.com"},
        headers=make_auth_header(ic.uid),
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body["code"] == "user.email_exists"
    assert body["params"]["uid"] == existing.uid


@pytest.mark.asyncio
async def test_update_user(test_client: AsyncClient, populated_db):
    """Test updating a user's information (requires auth)."""
    # IC can edit any user in any country (mock targets have random countries).
    admin = next(u for u in populated_db if Role.IC in u.roles)
    target = next(u for u in populated_db if u.uid != admin.uid)
    headers = make_auth_header(admin.uid)

    # Update the user
    response = await test_client.put(
        f"/api/users/{target.uid}",
        json={
            "name": "Updated Name",
            "country": "CA",
        },
        headers=headers,
    )

    assert response.status_code == 200
    updated_user = response.json()
    assert updated_user["uid"] == target.uid
    assert updated_user["name"] == "Updated Name"
    assert updated_user["country"] == "CA"
    assert datetime.fromisoformat(updated_user["modified"]) > target.modified


@pytest.mark.asyncio
async def test_role_change_resyncs_only_for_access_roles(
    test_client: AsyncClient, populated_db
):
    """Only NC/Prince/IC role changes nudge a resync; other roles must not.

    Resync clears every client's IndexedDB and forces a snapshot re-fetch (~10s
    blank community page). Only NC/Prince/IC change what a user can see or is seen
    as, so only those warrant it. The online nudge is broadcast_resync (asserted
    here via the user's SSE connection); the offline path is the access-version fp
    (test_access_version: a non-overlay role like PT doesn't move it).
    """
    import json

    from src import db
    from src.broadcast import SSEConnection, _sse_connections

    # IC can change any role; target needs a vekn_id to be assigned roles.
    admin = next(u for u in populated_db if Role.IC in u.roles)
    target = next(
        u
        for u in populated_db
        if u.uid != admin.uid
        and u.vekn_id
        and not (set(u.roles) & {Role.NC, Role.PRINCE, Role.IC})
    )
    headers = make_auth_header(admin.uid)

    conn = SSEConnection(user=target)
    _sse_connections.clear()
    _sse_connections.add(conn)

    def drained_types() -> list[str]:
        types = []
        while not conn.queue.empty():
            msg = conn.queue.get_nowait()
            types.append(json.loads(msg.removeprefix("data: ").strip()).get("type"))
        return types

    try:
        # Non-access role change (add PT) must NOT emit a resync.
        resp = await test_client.put(
            f"/api/users/{target.uid}",
            json={"roles": [*(r.value for r in target.roles), Role.PT.value]},
            headers=headers,
        )
        assert resp.status_code == 200
        after = await db.get_user_by_uid(target.uid)
        assert Role.PT in after.roles
        assert "resync" not in drained_types()

        # Access role change (add Prince) MUST emit a resync.
        resp = await test_client.put(
            f"/api/users/{target.uid}",
            json={"roles": [*(r.value for r in after.roles), Role.PRINCE.value]},
            headers=headers,
        )
        assert resp.status_code == 200
        after = await db.get_user_by_uid(target.uid)
        assert Role.PRINCE in after.roles
        assert "resync" in drained_types()
    finally:
        _sse_connections.clear()


@pytest.mark.asyncio
async def test_create_user_requires_auth(test_client: AsyncClient, populated_db):
    """Test that creating a user without auth returns 401."""
    response = await test_client.post(
        "/api/users/",
        json={"name": "Test", "country": "US"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_update_user_requires_auth(test_client: AsyncClient, populated_db):
    """Test that updating a user without auth returns 401."""
    response = await test_client.put(
        f"/api/users/{populated_db[0].uid}",
        json={"name": "Nope"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_update_user_requires_edit_authority(test_db, test_client: AsyncClient):
    """A member with no official role cannot edit another user's profile.

    Closes the gap where PUT /api/users/{uid} had no edit-authority gate at all —
    any authenticated user could change any user's name/country. Now gated by
    can_edit_user (self / IC / NC-Prince same-country).
    """
    actor = await _mk_user("FR", [], vekn="2000001")
    target = await _mk_user("FR", [], vekn="2000002")
    resp = await test_client.put(
        f"/api/users/{target.uid}",
        json={"name": "Hijacked"},
        headers=make_auth_header(actor.uid),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_country_change_authority_for_officials(
    test_db, test_client: AsyncClient
):
    """Changing an official's country (it scopes their FULL-data overlay) takes the
    authority that could change their official role; a regular member keeps
    self-service country edit."""
    ic = await _mk_user("US", [Role.IC], vekn="3000001")
    nc_fr = await _mk_user("FR", [Role.NC], vekn="3000002")
    prince_fr = await _mk_user("FR", [Role.PRINCE], vekn="3000003")
    nc_fr2 = await _mk_user("FR", [Role.NC], vekn="3000004")
    member_fr = await _mk_user("FR", [], vekn="3000005")

    # An NC may NOT change their OWN country (self-edit).
    resp = await test_client.patch(
        "/auth/me", json={"country": "DE"}, headers=make_auth_header(nc_fr.uid)
    )
    assert resp.status_code == 403

    # An NC MAY change a same-country Prince's country.
    resp = await test_client.put(
        f"/api/users/{prince_fr.uid}",
        json={"country": "DE"},
        headers=make_auth_header(nc_fr.uid),
    )
    assert resp.status_code == 200

    # An NC may NOT change another NC's country (IC only), even same-country.
    resp = await test_client.put(
        f"/api/users/{nc_fr2.uid}",
        json={"country": "DE"},
        headers=make_auth_header(nc_fr.uid),
    )
    assert resp.status_code == 403

    # IC may change an NC's country.
    resp = await test_client.put(
        f"/api/users/{nc_fr2.uid}",
        json={"country": "DE"},
        headers=make_auth_header(ic.uid),
    )
    assert resp.status_code == 200

    # A regular member keeps self-service country edit.
    resp = await test_client.patch(
        "/auth/me", json={"country": "DE"}, headers=make_auth_header(member_fr.uid)
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_get_users_by_uids_batch_matches_per_uid(populated_db):
    """Batch fetch returns exactly the per-uid users keyed by uid, and silently
    omits unknown uids — the rating recompute relies on this to skip missing
    players in one query instead of a round-trip each."""
    uids = {u.uid for u in populated_db[:50]}
    batch = await db.get_users_by_uids(uids | {"no-such-uid"})
    assert set(batch) == uids  # unknown uid omitted; every real uid present
    for uid in uids:
        one = await db.get_user_by_uid(uid)
        assert batch[uid].uid == one.uid and batch[uid].name == one.name
    assert await db.get_users_by_uids(set()) == {}  # empty in → empty out


@pytest.mark.asyncio
async def test_delete_member(test_db, test_client: AsyncClient):
    """IC soft-deletes a VEKN-less member; every other case is refused.

    These guards are route-only — the engine permission knows just "IC-only".
    The VEKN-bearing 400 is load-bearing: a soft-deleted VEKN member would be
    resurrected as a tombstone by the next VEKN member sync, so it must stay.
    """
    ic = await _mk_user("US", [Role.IC], vekn="4000001")
    junk = await _mk_user("FR", [])  # VEKN-less ETL residue
    member = await _mk_user("FR", [], vekn="4000002")  # real VEKN member

    # Non-IC cannot delete.
    resp = await test_client.delete(
        f"/api/users/{junk.uid}", headers=make_auth_header(member.uid)
    )
    assert resp.status_code == 403

    # IC cannot delete their own account.
    resp = await test_client.delete(
        f"/api/users/{ic.uid}", headers=make_auth_header(ic.uid)
    )
    assert resp.status_code == 403

    # IC cannot delete a VEKN-bearing member (would resurrect on next sync).
    resp = await test_client.delete(
        f"/api/users/{member.uid}", headers=make_auth_header(ic.uid)
    )
    assert resp.status_code == 400

    # Unknown uid → 404.
    resp = await test_client.delete(
        f"/api/users/{uuid7()}", headers=make_auth_header(ic.uid)
    )
    assert resp.status_code == 404

    # Happy path: IC soft-deletes the VEKN-less member (row kept, deleted_at set).
    resp = await test_client.delete(
        f"/api/users/{junk.uid}", headers=make_auth_header(ic.uid)
    )
    assert resp.status_code == 200
    deleted = await db.get_user_by_uid(junk.uid)
    assert deleted is not None and deleted.deleted_at is not None
