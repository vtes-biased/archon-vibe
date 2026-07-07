"""Tests for the legacy-archon daily merge (migrate_from_archon.py --merge).

Invariants guarded (one test each):
* rich data merges INTO the vekn-created copy — its uid survives, the archon
  marker is recorded — and a second run is a no-op (no duplicate decks);
* the archon-first interleave is deduped: at most one live tournament per vekn
  event id (rich copy wins, round-less copy tombstoned);
* a round-less incoming copy never overwrites a rich original (echo guard);
* both-rich conflicts are skipped, not merged;
* member merge writes only archon-owned fields, respecting local_modifications
  (identity and roles untouched);
* members are matched by VEKN id: the old-archon member merges INTO the live
  (possibly claimed) account and is NEVER tombstoned/detached;
* every old-archon member-uid reference is remapped to the live uid, and a
  vekn-less member is seeded as a shell so its references still resolve;
* (#216) a VEKN-less played throwaway remaps onto the player's real account and
  collapses its redundant same-event no-show registration (+ a phantom) to a
  single played entry — no duplicate;
* (#216) a KNOWN_REMAP source uid resolves to the LIVE uid of the account holding
  its target VEKN id (claimed → uuid7 ≠ source uid), so the throwaway's refs
  attribute to the real player rather than orphaning on the unseeded source;
* (#216) a genuinely VEKN-less participant is allocated a real, push-eligible
  VEKN id, idempotently, resurrecting any prior #169 shell.

The VEKN member sync's own role contract (CREATE seeds derived roles, UPDATE
never writes them) is covered in test_vekn_member_sync.py.
"""

from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pytest
import scripts.migrate_from_archon as mig
from scripts.migrate_from_archon import (
    KNOWN_REMAP,
    Stats,
    allocate_veknless_participant,
    build_user,
    deck_uid,
    merge_member,
    process_tournament_row,
    resolve_known_remaps,
)
from src import db
from src.models import (
    Role,
    Seat,
    Standing,
    Table,
    TableState,
    Tournament,
    TournamentState,
    User,
)

from tests.conftest import seed_tournament


@asynccontextmanager
async def _cleanup():
    """test_db only wipes type='user'; drop tournaments/decks we create here."""
    try:
        yield
    finally:
        async with db.get_connection() as conn:
            await conn.execute(
                "DELETE FROM objects WHERE type IN ('tournament', 'deck')"
            )


def _seats() -> list[Seat]:
    """A legal 5-seat finished table: VP 2(GW)/1/1/0.5/0.5."""
    from src.models import Score

    vps = [(1, 2.0), (0, 1.0), (0, 1.0), (0, 0.5), (0, 0.5)]
    return [
        Seat(player_uid=f"p{i + 1}", result=Score(gw=gw, vp=vp, tp=12))
        for i, (gw, vp) in enumerate(vps)
    ]


def _vekn_created(uid: str, event_id: str, *, rich: bool = False) -> Tournament:
    """A tournament as the VEKN sync creates it (round-less, folded standings),
    or a new-stack rich original when rich=True."""
    return Tournament(
        uid=uid,
        modified=datetime(2025, 5, 2, tzinfo=UTC),
        name=f"T {uid}",
        state=TournamentState.FINISHED,
        start=datetime(2025, 5, 1, 10, tzinfo=UTC),
        external_ids={"vekn": event_id},
        standings=[Standing(user_uid="p1", gw=1.0, vp=2.0, tp=12)],
        rounds=[[Table(seating=_seats(), state=TableState.FINISHED)]] if rich else [],
        vekn_pushed_at=datetime(2025, 5, 2, tzinfo=UTC),
    )


def _old_tournament_row(
    uid: str, *, vekn_id: str | None = None, rich: bool = True, with_deck: bool = False
) -> dict:
    players = {f"p{i}": {"state": "Finished", "toss": 0} for i in range(1, 6)}
    if with_deck:
        players["p1"]["deck"] = {
            "name": "Test Deck",
            "crypt": {"cards": [{"id": 100001, "count": 4}]},
            "library": {"cards": [{"cards": [{"id": 100100, "count": 2}]}]},
        }
    seating = [
        {"player_uid": "p1", "result": {"gw": 1, "vp": 2.0, "tp": 12}},
        {"player_uid": "p2", "result": {"gw": 0, "vp": 1.0, "tp": 12}},
        {"player_uid": "p3", "result": {"gw": 0, "vp": 1.0, "tp": 12}},
        {"player_uid": "p4", "result": {"gw": 0, "vp": 0.5, "tp": 12}},
        {"player_uid": "p5", "result": {"gw": 0, "vp": 0.5, "tp": 12}},
    ]
    data: dict = {
        "name": f"Old {uid}",
        "format": "Standard",
        "rank": "",
        "state": "Finished",
        "start": "2025-05-01T10:00:00+00:00",
        "finish": "2025-05-01T18:00:00+00:00",
        "players": players,
        "extra": {"vekn_id": vekn_id} if vekn_id else {},
    }
    if rich:
        data["rounds"] = [{"tables": [{"state": "Finished", "seating": seating}]}]
    return {"uid": uid, "data": data}


def _old_member_row(uid: str, vekn: str = "", **data) -> dict:
    return {
        "uid": uid,
        "vekn": vekn,
        "data": data,
        "last_updated": "2025-06-01T00:00:00+00:00",
    }


@pytest.mark.asyncio
async def test_rich_merge_into_vekn_copy_then_idempotent(test_db):
    async with _cleanup():
        await seed_tournament(_vekn_created("x-1", "555"))
        row = _old_tournament_row("o-1", vekn_id="555", with_deck=True)

        uid_map: dict[str, str] = {}
        await process_tournament_row(row, {}, Stats(), True, uid_map)

        merged = await db.get_tournament_by_uid("x-1")
        assert merged is not None and merged.deleted_at is None
        assert merged.rounds, "rich payload merged into the vekn-created copy"
        assert merged.external_ids == {"vekn": "555", "archon": "o-1"}
        assert merged.vekn_pushed_at is not None
        assert await db.get_tournament_by_uid("o-1") is None
        assert uid_map["o-1"] == "x-1"
        decks = await db.get_decks_for_tournament("x-1")
        assert [d.uid for d in decks] == [deck_uid("x-1", "p1", None)]

        # Second run: matched back via the archon marker, nothing rewritten.
        stats2 = Stats()
        await process_tournament_row(row, {}, stats2, True, {})
        assert stats2["tournaments.unchanged"] == 1
        assert stats2["tournaments.updated"] == 0
        assert stats2["decks.upserted"] == 0
        assert len(await db.get_decks_for_tournament("x-1")) == 1


@pytest.mark.asyncio
async def test_archon_first_interleave_tombstones_roundless_copy(test_db):
    async with _cleanup():
        # Run N inserted the rich tournament before old archon pushed to vekn…
        await process_tournament_row(_old_tournament_row("o-2"), {}, Stats(), True, {})
        # …then the VEKN sync created a round-less copy under a fresh uid…
        await seed_tournament(_vekn_created("c-2", "777"))

        # …and run N+1 sees the old tournament with its vekn id.
        stats = Stats()
        await process_tournament_row(
            _old_tournament_row("o-2", vekn_id="777"), {}, stats, True, {}
        )

        survivor = await db.get_tournament_by_uid("o-2")
        assert survivor.deleted_at is None
        assert survivor.external_ids.get("vekn") == "777"
        loser = await db.get_tournament_by_uid("c-2")
        assert loser.deleted_at is not None, "round-less copy tombstoned"
        assert stats["tournaments.roundless_copy_tombstoned"] == 1


@pytest.mark.asyncio
async def test_echo_guard_roundless_never_overwrites_rich(test_db):
    async with _cleanup():
        await seed_tournament(_vekn_created("x-3", "888", rich=True))

        stats = Stats()
        uid_map: dict[str, str] = {}
        await process_tournament_row(
            _old_tournament_row("o-3", vekn_id="888", rich=False),
            {},
            stats,
            True,
            uid_map,
        )

        assert stats["tournaments.echo_skipped"] == 1
        original = await db.get_tournament_by_uid("x-3")
        assert original.rounds, "rich original untouched"
        assert await db.get_tournament_by_uid("o-3") is None
        assert uid_map["o-3"] == "x-3"


@pytest.mark.asyncio
async def test_both_rich_conflict_is_skipped(test_db):
    async with _cleanup():
        await seed_tournament(_vekn_created("x-4", "999", rich=True))
        before = await db.get_tournament_by_uid("x-4")

        stats = Stats()
        await process_tournament_row(
            _old_tournament_row("o-4", vekn_id="999"), {}, stats, True, {}
        )

        assert stats["tournaments.both_rich_conflict"] == 1
        assert await db.get_tournament_by_uid("o-4") is None
        assert await db.get_tournament_by_uid("x-4") == before


@pytest.mark.asyncio
async def test_member_merge_respects_field_ownership(test_db):
    await db.save_user(
        User(
            uid="u-1",
            modified=datetime(2025, 6, 1, tzinfo=UTC),
            name="App Name",
            vekn_id="1000001",
            nickname="App Nick",
            contact_email="app@example.com",
            roles=[Role.JUDGE],
            local_modifications={"contact_email"},
        )
    )
    row = _old_member_row(
        "u-1",
        vekn="1000001",
        name="Legacy Name",
        email="legacy@example.com",
        nickname="Legacy Nick",
        roles=["Prince"],
    )

    stats = Stats()
    user, discord = build_user(row, stats)
    await merge_member(user, discord, stats)

    after = await db.get_user_by_uid("u-1")
    assert after.name == "App Name", "identity is the VEKN sync's, not merged"
    assert after.contact_email == "app@example.com", "local modification wins"
    assert after.nickname == "Legacy Nick", "archon-owned field merged"
    assert after.roles == [Role.JUDGE], "roles are app-managed, never merged"
    assert stats["members.updated"] == 1


@pytest.mark.asyncio
async def test_claimed_account_not_detached_by_merge(test_db):
    """regression: a user claimed a VEKN-sync copy (uuid7 ≠ old-archon uid),
    so the old-archon member arrives under a different uid. The merge must match
    on the vekn id and merge INTO the claimed account — never tombstone it or
    null its vekn_id (the old bug wiped the claimed identity + its community
    links)."""
    from src.models import CommunityLink, CommunityLinkType

    await db.save_user(
        User(
            uid="v-9",  # VEKN-sync uuid7, then claimed (≠ old-archon "o-9")
            modified=datetime(2025, 6, 1, tzinfo=UTC),
            name="Claimed Account",
            vekn_id="1000009",
            vekn_synced=True,
            community_links=[
                CommunityLink(type=CommunityLinkType.WEBSITE, url="https://me.example")
            ],
        )
    )

    stats = Stats()
    user, discord = build_user(
        _old_member_row("o-9", vekn="1000009", name="Old Member", nickname="Nick"),
        stats,
    )
    live_uid = await merge_member(user, discord, stats)

    assert live_uid == "v-9", "old member maps to the live claimed account"
    survivor = await db.get_user_by_uid("v-9")
    assert survivor.deleted_at is None, "claimed account NOT tombstoned"
    assert survivor.vekn_id == "1000009", "vekn id NOT detached"
    assert survivor.community_links, "community links survive the merge"
    assert survivor.nickname == "Nick", "archon-owned field merged in"
    assert await db.get_user_by_uid("o-9") is None, "no duplicate under the old uid"
    assert stats["members.vekn_copy_tombstoned"] == 0


@pytest.mark.asyncio
async def test_member_refs_remapped_and_vekn_less_seeded(test_db):
    """The load-bearing remap: a tournament's old-archon player uids are rewritten
    to the live (vekn-matched) uids, and a vekn-less player is seeded as a shell
    so its reference still resolves (no orphan)."""
    async with _cleanup():
        # p1 is the live account a user claimed (uuid7 'live-1', vekn 2000001);
        # p5 has no vekn id (stays under its old uid as a shell).
        await db.save_user(
            User(
                uid="live-1",
                modified=datetime(2025, 6, 1, tzinfo=UTC),
                name="Live One",
                vekn_id="2000001",
            )
        )
        # member_uid_map built from the members pass: p1→live-1 (vekn match),
        # p5→p5 (vekn-less shell), p2..p4 seeded under their own uids.
        member_uid_map: dict[str, str] = {}
        for old_uid, vekn in (
            ("p1", "2000001"),
            ("p2", "2000002"),
            ("p3", "2000003"),
            ("p4", "2000004"),
            ("p5", ""),  # vekn-less
        ):
            user, discord = build_user(
                _old_member_row(old_uid, vekn=vekn, name=old_uid), Stats()
            )
            member_uid_map[old_uid] = await merge_member(user, discord, Stats())

        assert member_uid_map["p1"] == "live-1"
        shell = await db.get_user_by_uid("p5")
        assert shell is not None and shell.deleted_at is not None, "vekn-less shell"

        row = _old_tournament_row("o-r", with_deck=True)
        row["data"]["winner"] = "p1"
        await process_tournament_row(row, {}, Stats(), True, {}, member_uid_map)

        t = await db.get_tournament_by_uid("o-r")
        seat_uids = {s.player_uid for tbl in t.rounds[0] for s in tbl.seating}
        assert "live-1" in seat_uids and "p1" not in seat_uids, "player_uid remapped"
        assert "p5" in seat_uids, "vekn-less ref preserved (resolves to the shell)"
        assert t.winner == "live-1", "winner remapped"
        assert {s.user_uid for s in t.standings} >= {"live-1", "p5"}
        decks = await db.get_decks_for_tournament("o-r")
        assert decks[0].user_uid == "live-1", "deck.user_uid remapped"


@pytest.mark.asyncio
async def test_veknless_played_throwaway_collapses_onto_real_noshow(
    test_db, monkeypatch
):
    """#216 core case: a player registered under their real VEKN account (a
    0-round no-show) yet PLAYED under a VEKN-less throwaway in the SAME event. The
    throwaway's refs remap onto the real account, the real account's redundant
    no-show registration is scoped-dropped, and a separate phantom registration is
    dropped wholesale — leaving ONE real-account entry carrying the played result
    (no duplicate)."""
    tuid, throwaway, real, phantom = "t-216", "throw-216", "real-216", "phan-216"
    monkeypatch.setattr(mig, "KNOWN_DROP", frozenset({phantom}))
    monkeypatch.setattr(mig, "KNOWN_DROP_IN_TOURNAMENT", frozenset({(tuid, real)}))

    async with _cleanup():
        # resolve_known_remaps result: throwaway → real; real maps to itself.
        member_uid_map = {throwaway: real, real: real}
        seating = [
            {"player_uid": throwaway, "result": {"gw": 1, "vp": 2.0, "tp": 12}},
            {"player_uid": "p2", "result": {"gw": 0, "vp": 1.0, "tp": 12}},
            {"player_uid": "p3", "result": {"gw": 0, "vp": 1.0, "tp": 12}},
            {"player_uid": "p4", "result": {"gw": 0, "vp": 0.5, "tp": 12}},
            {"player_uid": "p5", "result": {"gw": 0, "vp": 0.5, "tp": 12}},
        ]
        # real + phantom are registered-only (no seat); throwaway is seated.
        players = {
            u: {"state": "Finished", "toss": 0}
            for u in (throwaway, "p2", "p3", "p4", "p5", real, phantom)
        }
        row = {
            "uid": tuid,
            "data": {
                "name": "Collapse",
                "format": "Standard",
                "rank": "",
                "state": "Finished",
                "start": "2025-05-01T10:00:00+00:00",
                "finish": "2025-05-01T18:00:00+00:00",
                "players": players,
                "rounds": [{"tables": [{"state": "Finished", "seating": seating}]}],
            },
        }

        stats = Stats()
        await process_tournament_row(row, {}, stats, True, {}, member_uid_map)

        t = await db.get_tournament_by_uid(tuid)
        puids = [p.user_uid for p in t.players]
        assert puids.count(real) == 1, "single real-account entry, no duplicate"
        assert throwaway not in puids and phantom not in puids, (
            "throwaway + phantom gone"
        )
        survivor = next(p for p in t.players if p.user_uid == real)
        assert (survivor.result.gw, survivor.result.vp) == (1, 2.0), (
            "played result kept"
        )
        seat_uids = {s.player_uid for tbl in t.rounds[0] for s in tbl.seating}
        assert real in seat_uids and throwaway not in seat_uids, "seating remapped"
        assert stats["tournaments.veknless_player_dropped"] == 2, (
            "phantom + scoped real"
        )


@pytest.mark.asyncio
async def test_known_remap_resolves_to_live_account_by_vekn_id(test_db):
    """#216: resolve_known_remaps must rewrite the KNOWN_REMAP source uid to the
    LIVE uid of the account holding the target VEKN id — even when that account was
    claimed (live uid is a uuid7 ≠ the source uid). This is what makes the played
    throwaway's tournament refs attribute to the real player; a regression here
    silently leaves the source pointing at its own (unseeded) uid → orphan refs.
    Uses the shipped KNOWN_REMAP entry and the real by-vekn lookup, not a copy."""
    source_uid, target_vekn = next(iter(KNOWN_REMAP.items()))
    # The real account that holds the remap target VEKN, under a claimed uuid7.
    await db.save_user(
        User(
            uid="live-remap-target",
            modified=datetime(2025, 6, 1, tzinfo=UTC),
            name="Real Player",
            vekn_id=target_vekn,
        )
    )
    # migrate_members leaves the source as a self-placeholder (unseeded).
    member_uid_map = {source_uid: source_uid}

    stats = Stats()
    await resolve_known_remaps(member_uid_map, stats)

    assert member_uid_map[source_uid] == "live-remap-target", (
        "source uid now points at the live account holding the target VEKN id"
    )
    assert stats["members.veknless_remapped"] == 1
    assert stats["warn.remap_target_missing"] == 0


@pytest.mark.asyncio
async def test_veknless_participant_allocated_idempotent_and_resurrects_shell(test_db):
    """#216: a genuinely VEKN-less legacy participant is allocated a real VEKN id
    and becomes a LIVE, push-eligible member; a re-run never re-allocates; and a
    leftover #169 soft-deleted shell under the uid is resurrected into the live
    row (the prod-cutover state)."""
    # A Phase-1 (#169) run already shelled this participant.
    await db.save_user(
        User(
            uid="a-216",
            modified=datetime(2025, 6, 1, tzinfo=UTC),
            name="Played",
            deleted_at=datetime(2025, 6, 1, tzinfo=UTC),
        )
    )

    user, discord = build_user(
        _old_member_row("a-216", vekn="", name="Played"), Stats()
    )
    assert not user.vekn_id

    stats = Stats()
    await allocate_veknless_participant(user, discord, stats)
    live = await db.get_user_by_uid("a-216")
    assert live is not None and live.deleted_at is None, "shell resurrected as live"
    assert live.vekn_id and live.vekn_id.isdigit(), "real VEKN id allocated"
    assert live.vekn_synced is False, "push-eligible (batch_push registers the id)"
    assert stats["members.veknless_allocated"] == 1

    allocated = live.vekn_id
    await allocate_veknless_participant(user, discord, stats)
    again = await db.get_user_by_uid("a-216")
    assert again.vekn_id == allocated, "no re-allocation on re-run"
    assert stats["members.veknless_allocated"] == 1, "idempotent"
