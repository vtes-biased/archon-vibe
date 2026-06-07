"""Regression tests for VEKN account-surgery (pst #59 / #64).

Covers the three db-layer primitives the detach/merge invariant rests on
(.pst/details/59-vekn-detach.md) plus the self-abandon suspension guard:

- ``merge_users``       — survivor keeps identity + ``resync_after``; the dying
                          uid's contacts/roles/sanctions/decks/auth migrate over.
- ``detach_user_from_vekn`` — the vekn-bearing uid is immovable (keeps vekn_id,
                          roles, ratings, wins, links, and its sanctions+decks);
                          only PII + login walk away on a fresh uid.
- ``user_has_active_suspension`` — true only for live suspension/probation.
- ``/vekn/abandon`` guard — 403 while suspended; ``/vekn/force-abandon`` exempt.

Style matches test_calendar.py / test_action_conn_reuse.py: direct db calls on
the real ``test_db`` Postgres, models built with uuid7, extra object types torn
down explicitly (the test_db fixture only wipes ``type='user'``).
"""

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
import src.db as db
from src.models import (
    AuthMethod,
    AuthMethodType,
    CategoryRating,
    CommunityLink,
    DeckObject,
    ObjectType,
    Role,
    Sanction,
    SanctionCategory,
    SanctionLevel,
    User,
)
from uuid6 import uuid7

from tests.conftest import make_auth_header


@asynccontextmanager
async def _cleanup_surgery():
    """Tear down the object types the test_db fixture does not clean itself."""
    try:
        yield
    finally:
        async with db.get_connection() as conn:
            await conn.execute("DELETE FROM objects WHERE type IN ('sanction', 'deck')")
            await conn.execute("DELETE FROM auth_methods")


def _auth(user_uid: str, identifier: str) -> AuthMethod:
    return AuthMethod(
        uid=str(uuid7()),
        modified=datetime.now(UTC),
        user_uid=user_uid,
        method_type=AuthMethodType.EMAIL,
        identifier=identifier,
        credential_hash="hash",
        verified=True,
    )


def _sanction(
    user_uid: str,
    level: SanctionLevel,
    *,
    lifted: bool = False,
    expires_at: datetime | None = None,
    deleted: bool = False,
) -> Sanction:
    return Sanction(
        uid=str(uuid7()),
        modified=datetime.now(UTC),
        deleted_at=datetime.now(UTC) if deleted else None,
        user_uid=user_uid,
        issued_by_uid="issuer",
        level=level,
        category=SanctionCategory.UNSPORTSMANLIKE_CONDUCT,
        description="test",
        issued_at=datetime.now(UTC),
        expires_at=expires_at,
        lifted_at=datetime.now(UTC) if lifted else None,
    )


def _deck(user_uid: str) -> DeckObject:
    return DeckObject(
        uid=str(uuid7()),
        modified=datetime.now(UTC),
        tournament_uid=str(uuid7()),
        user_uid=user_uid,
        name="A deck",
    )


async def _deck_uids_for_user(user_uid: str) -> set[str]:
    """No get_decks_for_user helper exists; mirror reassign_decks' own query."""
    async with db.get_connection() as conn:
        result = await conn.execute(
            """SELECT uid FROM objects
            WHERE type = 'deck' AND "full"->>'user_uid' = %s""",
            (user_uid,),
        )
        rows = await result.fetchall()
    return {row[0] for row in rows}


# ---------------------------------------------------------------------------
# merge_users
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_merge_preserves_resync_after_and_identity(test_db):
    """The latent bug: rebuilding User(...) from scratch dropped resync_after.

    msgspec.structs.replace(keep_user, …) must carry every unlisted field —
    here resync_after — through the merge, while identity stays with the
    survivor and contact info prefers the dying (claiming) account.
    """
    resync = datetime.now(UTC) - timedelta(minutes=5)
    keep = User(
        uid=str(uuid7()),
        modified=datetime.now(UTC),
        name="Keep Name",
        vekn_id="1234567",
        roles=[Role.PRINCE],
        contact_email="keep@example.com",
        resync_after=resync,
    )
    delete = User(
        uid=str(uuid7()),
        modified=datetime.now(UTC),
        name="Delete Name",
        roles=[Role.JUDGE],
        contact_email="claimer@example.com",
        contact_phone="+15550001111",
    )
    await db.insert_user(keep)
    await db.insert_user(delete)

    merged = await db.merge_users(keep.uid, delete.uid)

    assert merged is not None
    # (a) resync_after PRESERVED from keep_user (the regression).
    assert merged.resync_after == resync
    # identity prefers keep_user.
    assert merged.uid == keep.uid
    assert merged.name == "Keep Name"
    assert merged.vekn_id == "1234567"
    # contact info prefers the claiming (delete) account.
    assert merged.contact_email == "claimer@example.com"
    assert merged.contact_phone == "+15550001111"
    # roles are the union.
    assert set(merged.roles) == {Role.PRINCE, Role.JUDGE}
    # the dying account is soft-deleted.
    gone = await db.get_user_by_uid(delete.uid)
    assert gone is None or gone.deleted_at is not None


@pytest.mark.asyncio
async def test_merge_reassigns_decks_sanctions_auth(test_db):
    """#64: decks (and sanctions, auth) on the dying uid migrate to the survivor.

    The /claim bug orphaned the claimer's decks on their soon-deleted uid.
    """
    keep = User(
        uid=str(uuid7()), modified=datetime.now(UTC), name="Survivor", vekn_id="7654321"
    )
    delete = User(uid=str(uuid7()), modified=datetime.now(UTC), name="Claimer")
    await db.insert_user(keep)
    await db.insert_user(delete)

    async with _cleanup_surgery():
        deck = _deck(delete.uid)
        sanction = _sanction(delete.uid, SanctionLevel.WARNING)
        auth = _auth(delete.uid, "claimer@example.com")
        await db.save_object_from_model(ObjectType.DECK, deck)
        await db.insert_sanction(sanction)
        await db.insert_auth_method(auth)

        await db.merge_users(keep.uid, delete.uid)

        # decks reassigned to the survivor (the #64 fix).
        assert await _deck_uids_for_user(keep.uid) == {deck.uid}
        assert await _deck_uids_for_user(delete.uid) == set()

        # sanctions reassigned.
        keep_sanctions = await db.get_sanctions_for_user(keep.uid)
        assert {s.uid for s in keep_sanctions} == {sanction.uid}

        # auth methods reassigned.
        keep_auth = await db.get_auth_methods_for_user(keep.uid)
        assert {a.uid for a in keep_auth} == {auth.uid}
        assert await db.get_auth_methods_for_user(delete.uid) == []


# ---------------------------------------------------------------------------
# detach_user_from_vekn
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detach_vekn_record_is_immovable(test_db):
    """The invariant: the vekn-bearing uid keeps its uid and all competitive data.

    Sanctions and decks key on that stable uid, so they stay attached for free.
    """
    coopter = str(uuid7())
    coopted_at = datetime.now(UTC) - timedelta(days=30)
    rating = CategoryRating(total=42)
    user = User(
        uid=str(uuid7()),
        modified=datetime.now(UTC),
        name="Holder",
        vekn_id="9000001",
        roles=[Role.PRINCE, Role.JUDGE],
        coopted_by=coopter,
        coopted_at=coopted_at,
        vekn_prefix="NC-FR",
        community_links=[CommunityLink(type="website", url="https://example.org")],
        constructed_online=rating,
        wins=["tourney-uid-1"],
        # PII that must walk away:
        nickname="holdy",
        contact_email="holder@example.com",
        discord_id="discord-123",
    )
    await db.insert_user(user)

    async with _cleanup_surgery():
        deck = _deck(user.uid)
        sanction = _sanction(user.uid, SanctionLevel.SUSPENSION)
        auth = _auth(user.uid, "holder@example.com")
        await db.save_object_from_model(ObjectType.DECK, deck)
        await db.insert_sanction(sanction)
        await db.insert_auth_method(auth)

        result = await db.detach_user_from_vekn(user.uid)
        assert result is not None
        personal, vekn_record = result

        # --- vekn_record is immovable: same uid, keeps competitive identity ---
        assert vekn_record.uid == user.uid
        assert vekn_record.vekn_id == "9000001"
        assert set(vekn_record.roles) == {Role.PRINCE, Role.JUDGE}
        assert vekn_record.coopted_by == coopter
        assert vekn_record.coopted_at == coopted_at
        assert vekn_record.vekn_prefix == "NC-FR"
        assert vekn_record.constructed_online == rating
        assert vekn_record.wins == ["tourney-uid-1"]
        assert len(vekn_record.community_links) == 1

        # sanctions + decks stay attached (uid unchanged, never reassigned).
        assert {s.uid for s in await db.get_sanctions_for_user(user.uid)} == {
            sanction.uid
        }
        assert await _deck_uids_for_user(user.uid) == {deck.uid}

        # PII wiped off the record (the split bug: discord_id must be nulled).
        assert vekn_record.nickname is None
        assert vekn_record.contact_email is None
        assert vekn_record.discord_id is None
        # modified bumped on the record (the other split bug).
        assert vekn_record.modified >= user.modified

        # --- personal account: fresh uid, login + PII only, no VEKN data ---
        assert personal.uid != user.uid
        assert personal.vekn_id is None
        assert personal.roles == []
        assert personal.coopted_by is None
        assert personal.vekn_prefix is None
        assert personal.community_links == []
        assert personal.constructed_online is None
        assert personal.wins == []
        # PII follows the person.
        assert personal.name == "Holder"
        assert personal.nickname == "holdy"
        assert personal.contact_email == "holder@example.com"
        assert personal.discord_id == "discord-123"
        # auth methods reassigned to the new uid.
        assert {a.uid for a in await db.get_auth_methods_for_user(personal.uid)} == {
            auth.uid
        }
        assert await db.get_auth_methods_for_user(user.uid) == []


@pytest.mark.asyncio
async def test_detach_moves_calendar_token_to_personal(test_db):
    """The .ics feed token follows the human, not the orphaned VEKN record.

    calendar_token lives in a dedicated column (stripped from "full"), so detach
    reads it explicitly and re-homes it on the personal account; the orphan is
    cleared first so the token is never duplicated. This matches merge_users and
    keeps the owner's existing subscription URL resolving.
    """
    user = User(
        uid=str(uuid7()),
        modified=datetime.now(UTC),
        name="Feed Owner",
        vekn_id="9000002",
        calendar_token="feed-token-xyz",
    )
    await db.insert_user(user)
    assert await db.get_calendar_token(user.uid) == "feed-token-xyz"

    async with _cleanup_surgery():
        result = await db.detach_user_from_vekn(user.uid)
        assert result is not None
        personal, _vekn_record = result

        # token gone from the VEKN record (no stale feed on the orphan)...
        assert await db.get_calendar_token(user.uid) is None
        # ...and re-homed on the personal account, so the URL still resolves.
        assert await db.get_calendar_token(personal.uid) == "feed-token-xyz"
        resolved = await db.get_user_by_calendar_token("feed-token-xyz")
        assert resolved is not None
        assert resolved.uid == personal.uid


# ---------------------------------------------------------------------------
# user_has_active_suspension
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_active_suspension_true_for_live_suspension(test_db):
    uid = str(uuid7())
    async with _cleanup_surgery():
        await db.insert_sanction(_sanction(uid, SanctionLevel.SUSPENSION))
        assert await db.user_has_active_suspension(uid) is True


@pytest.mark.asyncio
async def test_active_suspension_true_for_future_probation(test_db):
    uid = str(uuid7())
    future = datetime.now(UTC) + timedelta(days=30)
    async with _cleanup_surgery():
        await db.insert_sanction(
            _sanction(uid, SanctionLevel.PROBATION, expires_at=future)
        )
        assert await db.user_has_active_suspension(uid) is True


@pytest.mark.asyncio
async def test_active_suspension_false_for_lower_levels(test_db):
    uid = str(uuid7())
    async with _cleanup_surgery():
        await db.insert_sanction(_sanction(uid, SanctionLevel.CAUTION))
        await db.insert_sanction(_sanction(uid, SanctionLevel.WARNING))
        assert await db.user_has_active_suspension(uid) is False


@pytest.mark.asyncio
async def test_active_suspension_false_when_lifted_expired_or_deleted(test_db):
    uid = str(uuid7())
    past = datetime.now(UTC) - timedelta(days=1)
    async with _cleanup_surgery():
        await db.insert_sanction(_sanction(uid, SanctionLevel.SUSPENSION, lifted=True))
        await db.insert_sanction(
            _sanction(uid, SanctionLevel.SUSPENSION, expires_at=past)
        )
        await db.insert_sanction(_sanction(uid, SanctionLevel.PROBATION, deleted=True))
        assert await db.user_has_active_suspension(uid) is False


# ---------------------------------------------------------------------------
# /vekn/abandon route guard (active suspension blocks self-abandon)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_abandon_blocked_while_suspended(test_client):
    """POST /vekn/abandon → 403 when the caller holds an active suspension."""
    user = User(
        uid=str(uuid7()),
        modified=datetime.now(UTC),
        name="Suspended Player",
        vekn_id="9000003",
    )
    await db.insert_user(user)

    async with _cleanup_surgery():
        await db.insert_sanction(_sanction(user.uid, SanctionLevel.SUSPENSION))

        resp = await test_client.post(
            "/vekn/abandon", headers=make_auth_header(user.uid)
        )
        assert resp.status_code == 403
        assert "suspension" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_abandon_allowed_without_active_suspension(test_client):
    """A clean VEKN holder can self-abandon (control for the guard above)."""
    user = User(
        uid=str(uuid7()),
        modified=datetime.now(UTC),
        name="Clean Player",
        vekn_id="9000004",
    )
    await db.insert_user(user)

    async with _cleanup_surgery():
        resp = await test_client.post(
            "/vekn/abandon", headers=make_auth_header(user.uid)
        )
        assert resp.status_code == 200
        body = resp.json()
        # detach issued a fresh uid for the new personal account.
        assert body["user"]["uid"] != user.uid
        assert body["user"]["vekn_id"] is None
