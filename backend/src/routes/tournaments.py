import asyncio
import json
import logging
import os
from datetime import UTC, datetime
from importlib.resources import files
from uuid import uuid7
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import msgspec
from archon_engine import PyEngine
from fastapi import APIRouter, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .. import permissions
from ..broadcast import (
    broadcast_judge_call,
    broadcast_personal,
    broadcast_precomputed,
)
from ..card_data import cards_json_text
from ..db import (
    TWDA_MIN_PLAYERS,
    BroadcastData,
    allocate_next_vekn_id,
    compute_access_version,
    delete_banner,
    ensure_event_code,
    get_all_leagues,
    get_auth_method_by_identifier,
    get_banner,
    get_connection,
    get_decks_for_tournament,
    get_league_by_uid,
    get_sanctions_for_tournament,
    get_sanctions_for_user,
    get_sanctions_for_users,
    get_tournament_by_uid,
    get_user_by_uid,
    get_user_by_vekn_id,
    resolve_event_code,
    save_object,
    save_object_from_model,
    save_tournament,
    save_user,
    soft_delete_tournament,
    tournament_transaction,
    upsert_banner,
)
from ..engine_errors import EngineRejection
from ..geonames import get_country, normalize_country, stored_country
from ..middleware.auth import OptionalUser
from ..models import (
    Announcement,
    DeckObject,
    ObjectType,
    PlayerState,
    Role,
    Sanction,
    SanctionLevel,
    TimerState,
    Tournament,
    TournamentFormat,
    TournamentState,
    TwdaOutcome,
    TwdaStatus,
    User,
)
from ..promo_stock import schedule_recompute
from .auth import send_invite_email

router = APIRouter(prefix="/api/tournaments", tags=["tournaments"])
logger = logging.getLogger(__name__)
encoder = msgspec.json.Encoder()

# Wire types are raw: list every deck-upsert alias the engine accepts or the one
# omitted skips the recompute. Rating-irrelevant only — the deck actions below do
# move the Hall of Fame, and the caller recomputes wins for them separately.
_RATING_IRRELEVANT_ACTIONS = frozenset(
    {
        "UpsertDeck",
        "UploadDeck",
        "UpdateDeck",
        "DeleteDeck",
        "SetPaymentStatus",
        "MarkAllPaid",
        # Rating recompute only reads FINISHED tournaments, and the engine
        # blocks this toggle once finished, so it never changes a live rating.
        "SetNonCompeting",
        "RaffleDraw",
        "RaffleUndo",
        "RaffleClear",
        "ReportPromos",
        "CheckIn",
        "CheckOut",
        "CheckInAll",
        "ResetCheckIn",
    }
)

_engine = PyEngine()
_engine_cards_loaded = False

SERVER_OWNED_TOURNAMENT_FIELDS = frozenset(
    {
        "banner_path",
        "external_ids",
        "checkin_code",
        "event_code",
        "vekn_pushed_at",
        "vekn_results_stale",
        "twda_status",
    }
)


def _promo_recompute_diff(old: Tournament | None, new: Tournament | None) -> None:
    """Re-derive promo stock for promos whose distribution may have changed —
    the union of old and new so a removed row recomputes too."""
    affected = {r.promo_uid for t in (old, new) if t for r in t.promos_distributed}
    if affected:
        schedule_recompute(list(affected))


async def _build_decks_json(tournament_uid: str, conn=None) -> str:
    decks = await get_decks_for_tournament(tournament_uid, conn=conn)
    return msgspec.json.encode(
        [{"user_uid": d.user_uid, "round": d.round, "uid": d.uid} for d in decks]
    ).decode()


async def _process_deck_ops(
    deck_ops: list,
    tournament_uid: str,
    existing_decks: list[DeckObject] | None = None,
    org_uids: list[str] | None = None,
) -> list[BroadcastData]:
    if not deck_ops:
        return []
    if existing_decks is None:
        existing_decks = await get_decks_for_tournament(tournament_uid)

    _org_uids = org_uids or []
    affected: list[BroadcastData] = []
    for op in deck_ops:
        op_type = op.get("op")
        if op_type == "upsert":
            deck_data = op["deck"]
            player_uid = op["player_uid"]
            round_val = deck_data.get("round")
            existing = next(
                (
                    d
                    for d in existing_decks
                    if d.user_uid == player_uid and d.round == round_val
                ),
                None,
            )
            if existing:
                deck_obj = existing
                deck_obj.modified = datetime.now(UTC)
            else:
                deck_obj = DeckObject(
                    uid=str(uuid7()),
                    modified=datetime.now(UTC),
                    tournament_uid=tournament_uid,
                    user_uid=player_uid,
                )
            deck_obj.round = round_val
            deck_obj.name = deck_data.get("name", "")
            deck_obj.author = deck_data.get("author", "")
            deck_obj.comments = deck_data.get("comments", "")
            deck_obj.cards = deck_data.get("cards", {})
            deck_obj.attribution = deck_data.get("attribution")
            deck_obj.public = deck_data.get("public", False)
            bd = await save_object_from_model(ObjectType.DECK, deck_obj)
            bd.org_uids = _org_uids
            affected.append(bd)

        elif op_type == "delete":
            player_uid = op["player_uid"]
            deck_index = op.get("deck_index")
            is_multideck = op.get("multideck", False)
            for d in existing_decks:
                if d.user_uid == player_uid:
                    if is_multideck and deck_index is not None:
                        if d.round != deck_index:
                            continue
                    d.deleted_at = datetime.now(UTC)
                    d.modified = datetime.now(UTC)
                    bd = await save_object_from_model(ObjectType.DECK, d)
                    bd.org_uids = _org_uids
                    affected.append(bd)

        elif op_type == "set_public":
            deck_uid = op.get("deck_uid")
            public_val = op.get("public", False)
            target = next((d for d in existing_decks if d.uid == deck_uid), None)
            if target:
                target.public = public_val
                target.modified = datetime.now(UTC)
                bd = await save_object_from_model(ObjectType.DECK, target)
                bd.org_uids = _org_uids
                affected.append(bd)

    return affected


async def _maybe_push_vekn(tournament: Tournament) -> None:
    try:
        from ..vekn_push import push_tournament_results, vekn_push_client

        async with vekn_push_client() as client:
            if client is not None:
                await push_tournament_results(client, tournament)
    except Exception:
        logger.exception("Failed to push VEKN results")


async def _maybe_push_seating(tournament: Tournament, event_type: str) -> None:
    try:
        from .. import push_service

        targets = push_service.build_seating_specs(tournament, event_type)
        await push_service.send_to_users(targets)
    except Exception:
        logger.exception("Failed to send seating push for %s", tournament.uid)


async def _maybe_push_reseat(old: Tournament, new: Tournament) -> None:
    try:
        from .. import push_service

        targets = push_service.build_reseat_specs(old, new)
        await push_service.send_to_users(targets)
    except Exception:
        logger.exception("Failed to send re-seat push for %s", new.uid)


async def _maybe_push_announcement(
    tournament: Tournament, body: str, exclude_uid: str
) -> None:
    try:
        from .. import push_service

        spec = push_service.build_announcement_spec(tournament, body)
        states = {PlayerState.CHECKED_IN, PlayerState.PLAYING, PlayerState.COMPLETED}
        if not tournament.rounds:
            states.add(PlayerState.REGISTERED)
        uids = {
            p.user_uid
            for p in tournament.players
            if p.user_uid and p.user_uid != exclude_uid and p.state in states
        }
        await push_service.send_to_users([(uid, spec) for uid in uids])
    except Exception:
        logger.exception("Failed to send announcement push for %s", tournament.uid)


async def _maybe_push_judge_call(
    tournament: Tournament,
    table: int,
    table_label: str | None,
    player_name: str,
    exclude_uid: str,
) -> None:
    """Same organizer audience as the ephemeral judge_call SSE — keep both in
    sync if the target set ever changes."""
    try:
        from .. import push_service

        spec = push_service.build_judge_call_spec(
            tournament_uid=tournament.uid,
            tournament_name=tournament.name,
            table=table,
            table_label=table_label,
            player_name=player_name,
        )
        uids = [u for u in (tournament.organizers_uids or []) if u != exclude_uid]
        await push_service.send_to_users([(uid, spec) for uid in uids])
    except Exception:
        logger.exception("Failed to send judge-call push for %s", tournament.uid)


async def _maybe_push_vekn_event(tournament: Tournament) -> None:
    try:
        from ..vekn_push import push_tournament_event, vekn_push_client

        async with vekn_push_client() as client:
            if client is not None:
                await push_tournament_event(client, tournament)
    except Exception:
        logger.exception("Failed to push VEKN event")
    # After the attempt, never before: a successful push writes the vekn event id
    # this event should carry as its handle, and the handle is written once.
    try:
        bd = await ensure_event_code(tournament.uid)
        if bd is not None:
            broadcast_precomputed(bd)
    except Exception:
        logger.exception("Failed to stamp event code")


async def _winner_deck_twda(tournament: Tournament) -> str | None:
    """TWDA-formatted winner decklist (event header + deck), or None if the
    winner has no stored deck."""
    if not tournament.winner:
        return None

    decks = await get_decks_for_tournament(tournament.uid)
    winner_deck = next((d for d in decks if d.user_uid == tournament.winner), None)
    if not winner_deck:
        return None

    player_user = await get_user_by_uid(tournament.winner)
    player_name = player_user.name if player_user else "Unknown"

    attribution = winner_deck.attribution
    self_ids = {i for i in (getattr(player_user, "vekn_id", ""), player_name) if i}
    if attribution == "twda":
        designer_credit = winner_deck.author
    elif not attribution or attribution in self_ids:
        designer_credit = ""
    else:
        designer = await get_user_by_vekn_id(attribution)
        designer_credit = (designer.name if designer else "") or winner_deck.author

    deck_json = json.dumps(
        {
            "name": winner_deck.name,
            "author": designer_credit,
            "comments": winner_deck.comments,
            "cards": winner_deck.cards,
        }
    )
    tournament_date = tournament.start or tournament.modified.isoformat()
    rounds_count = len(tournament.rounds)
    tournament_format = f"{rounds_count}R" + ("+F" if tournament.finals else "")
    from ..twda import frontend_url

    # The archive keeps this line forever, so it must be the citable form. Two
    # TWDA entries already point at legacy-archon uids that resolve to nothing.
    handle = (
        f"/t/{tournament.event_code}"
        if tournament.event_code
        else f"/tournaments/{tournament.uid}"
    )

    named = get_country(normalize_country(tournament.country or "") or "")

    _load_engine_cards()
    return _engine.export_twda(
        deck_json,
        tournament.name,
        str(tournament_date),
        named["name"] if named else (tournament.country or ""),
        tournament_format,
        f"{frontend_url()}{handle}",
        len(tournament.players),
        player_name,
    )


def _played_player_count(tournament: Tournament) -> int:
    """TWDA-gate count: seated players only, no standings fallback (0 for a
    rounds-less import), proxies subtracted. Deliberately distinct from other
    player-count implementations elsewhere in the app."""
    proxies = {p.user_uid for p in tournament.players if p.non_competing}
    seated: set[str] = set()
    for rnd in tournament.rounds:
        for table in rnd:
            seated.update(s.player_uid for s in table.seating if s.player_uid)
    if tournament.finals:
        seated.update(s.player_uid for s in tournament.finals.seating if s.player_uid)
    return len(seated - proxies)


async def _record_twda_status(
    uid: str, outcome: TwdaOutcome, reason: str = "", pr_url: str = ""
) -> None:
    """Locked fetch-modify-save so only twda_status lands on the CURRENT row,
    never clobbering concurrent edits; an unchanged outcome skips the write."""
    async with tournament_transaction(uid) as (fresh, tx_conn):
        if not fresh:
            return
        prev = fresh.twda_status
        if prev and (prev.outcome, prev.reason, prev.pr_url) == (
            outcome,
            reason,
            pr_url,
        ):
            return
        fresh.twda_status = TwdaStatus(
            outcome=outcome, reason=reason, pr_url=pr_url, at=datetime.now(UTC)
        )
        fresh.modified = datetime.now(UTC)
        bd = await save_tournament(fresh, conn=tx_conn)
    broadcast_precomputed(bd)


async def maybe_submit_twda(tournament: Tournament) -> None:
    """Self-contains its errors, recording outcome/reason on the tournament
    either way. `ranking_eligibility` (the ranked-badge predicate) is distinct
    from `rank` (the Basic/NC/CC championship axis) — don't conflate them."""
    from ..twda import is_configured, submit_twda_pr

    if tournament.state != TournamentState.FINISHED:
        return
    if not tournament.winner:
        outcome = (TwdaOutcome.SKIPPED, "no_winner", "")
    elif tournament.format == TournamentFormat.Limited:
        # Limited events are rated (own category) but draft/sealed decks
        # don't belong in a constructed-deck archive.
        outcome = (TwdaOutcome.SKIPPED, "limited", "")
    elif _played_player_count(tournament) < TWDA_MIN_PLAYERS:
        outcome = (TwdaOutcome.SKIPPED, "too_few_players", "")
    elif (
        _engine.ranking_eligibility(msgspec.json.encode(tournament).decode())
        != "eligible"
    ):
        outcome = (TwdaOutcome.SKIPPED, "unranked", "")
    elif not tournament.event_code:
        outcome = (TwdaOutcome.SKIPPED, "no_event_code", "")
    elif not is_configured():
        outcome = (TwdaOutcome.SKIPPED, "not_configured", "")
    else:
        try:
            deck_text = await _winner_deck_twda(tournament)
            if not deck_text:
                outcome = (TwdaOutcome.SKIPPED, "no_deck", "")
            else:
                pr_url = await submit_twda_pr(
                    tournament.event_code, deck_text, tournament.name
                )
                if pr_url:
                    outcome = (TwdaOutcome.SUBMITTED, "", pr_url)
                else:
                    outcome = (TwdaOutcome.FAILED, "", "")
        except Exception:
            logger.exception("Failed to submit TWDA PR")
            outcome = (TwdaOutcome.FAILED, "", "")

    try:
        await _record_twda_status(tournament.uid, *outcome)
    except Exception:
        logger.exception("Failed to record TWDA status")


def _build_actor_context(
    user, tournament: Tournament, can_organize_league_uids: list[str] | None = None
) -> dict:
    return {
        "uid": user.uid,
        "roles": [r.value if hasattr(r, "value") else str(r) for r in user.roles],
        "is_organizer": permissions.is_organizer(user, tournament),
        "can_organize_league_uids": can_organize_league_uids or [],
        # Request clock: lets the engine resolve suspension expiry (expires_at vs now).
        "now": datetime.now(UTC).isoformat(),
    }


async def _get_user_organizable_league_uids(user, conn=None) -> list[str]:
    """League uids the user may attach tournaments to, feeding the engine's
    UpdateConfig league gate."""
    # Not a gate — it mirrors the engine's own contract: an empty list means
    # "unrestricted", which is what IC already is, so skip the full scan.
    if Role.IC in user.roles:
        return []
    leagues = await get_all_leagues(conn=conn)
    return [
        lg.uid for lg in leagues if permissions.can_link_tournament_to_league(user, lg)
    ]


async def _check_player_barred(
    player_uid: str, tournament_uid: str, tournament: Tournament, conn=None
) -> None:
    """Raises EngineRejection if the player is suspended, or DQ'd in a
    sibling league tournament (league-wide DQ)."""
    user_sanctions = await get_sanctions_for_user(player_uid, conn=conn)
    now = datetime.now(UTC)
    for s in user_sanctions:
        if s.deleted_at or s.lifted_at:
            continue
        if s.level == SanctionLevel.SUSPENSION:
            if s.expires_at is None or s.expires_at > now:
                raise EngineRejection(
                    "Player is suspended and cannot participate",
                    code="tournament.player_suspended",
                )

    if tournament.league_uid:
        for s in user_sanctions:
            if s.deleted_at or s.lifted_at:
                continue
            if s.level == SanctionLevel.DISQUALIFICATION and s.tournament_uid:
                dq_tournament = await get_tournament_by_uid(s.tournament_uid, conn=conn)
                if dq_tournament and dq_tournament.league_uid == tournament.league_uid:
                    raise EngineRejection(
                        "Player is disqualified from a league tournament and cannot participate",
                        code="tournament.player_disqualified",
                    )


class OrganizerAction(BaseModel):
    user_uid: str


async def _invalidate_organizer_view(
    tournament: Tournament, user_uid: str, modified_at: str | None
) -> None:
    """Push the tournament + its decks to one user at their newly-entitled
    projection — broadcast_precomputed already handled everyone else and never
    delivers decks."""
    user = await get_user_by_uid(user_uid)
    if not user:
        return
    av = await compute_access_version(user)
    org_uids = tournament.organizers_uids
    broadcast_personal(
        user_uid,
        obj_type=ObjectType.TOURNAMENT,
        uid=tournament.uid,
        full_dict=msgspec.to_builtins(tournament),
        country=tournament.country,
        org_uids=org_uids,
        modified_at=modified_at,
        access_version=av,
    )
    for deck in await get_decks_for_tournament(tournament.uid):
        broadcast_personal(
            user_uid,
            obj_type=ObjectType.DECK,
            uid=deck.uid,
            full_dict=msgspec.to_builtins(deck),
            org_uids=org_uids,
            obj_user_uid=deck.user_uid,
            modified_at=modified_at,
            access_version=av,
        )


@router.post("/{uid}/organizers")
async def add_organizer(
    uid: str,
    body: OrganizerAction,
    current_user: OptionalUser = None,
) -> Response:
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    bd = None
    async with tournament_transaction(uid) as (tournament, tx_conn):
        if not tournament:
            raise HTTPException(status_code=404, detail="Tournament not found")
        if not permissions.is_organizer(current_user, tournament):
            raise HTTPException(
                status_code=403, detail="Only organizers can manage organizers"
            )
        # A non-member sits at public level, which carries no organizer view of
        # the event — same rule as league organizers.
        organizer = await get_user_by_uid(body.user_uid, conn=tx_conn)
        if not organizer or not organizer.vekn_id:
            raise HTTPException(
                status_code=400, detail="Organizer must be a VEKN member"
            )
        if body.user_uid not in tournament.organizers_uids:
            tournament.organizers_uids.append(body.user_uid)
            tournament.modified = datetime.now(UTC)
            bd = await save_tournament(tournament, conn=tx_conn)

    if bd is not None:
        broadcast_precomputed(bd)
        # broadcast_precomputed never delivers decks — grant the new organizer
        # full access to the tournament's private decks separately.
        await _invalidate_organizer_view(tournament, body.user_uid, bd.modified_at)

    return Response(
        content=encoder.encode(tournament),
        media_type="application/json",
    )


@router.post("/{uid}/push-vekn")
async def push_vekn(
    uid: str,
    current_user: OptionalUser = None,
) -> Response:
    """Registers the calendar event if missing; for a FINISHED tournament also
    pushes results (once) and submits the TWDA deck, mirroring the hourly
    batch_push immediately."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    tournament = await get_tournament_by_uid(uid)
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")

    if not permissions.is_organizer(current_user, tournament):
        raise HTTPException(status_code=403, detail="Only organizers can sync to VEKN")

    # Open-rounds / self-organized events are the non-VEKN house format — never pushed.
    if tournament.open_rounds or tournament.self_organized_rounds:
        raise HTTPException(
            status_code=400, detail="Open-rounds events are not reported to VEKN"
        )

    from ..vekn_api import VEKNAPIConnectionError, VEKNAPIError
    from ..vekn_push import (
        push_tournament_event,
        push_tournament_results,
        vekn_push_client,
    )

    try:
        async with vekn_push_client() as client:
            if client is None:
                raise HTTPException(status_code=400, detail="VEKN sync is not enabled")
            if not tournament.external_ids.get("vekn"):
                # push_tournament_event saves external_ids.vekn + broadcasts on success.
                event_id = await push_tournament_event(
                    client, tournament, raise_api_errors=True
                )
                if not event_id:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            "VEKN sync failed — needs a name (≥3 chars), a start "
                            "date, and an organizer with a VEKN ID"
                        ),
                    )
                tournament = await get_tournament_by_uid(uid) or tournament
            if tournament.state == TournamentState.FINISHED:
                if not tournament.vekn_pushed_at:
                    # A manual publish must report a real outcome — don't swallow a
                    # failed results push (e.g. a finalist with no VEKN ID) as success.
                    if not await push_tournament_results(
                        client, tournament, raise_api_errors=True
                    ):
                        raise HTTPException(
                            status_code=400,
                            detail=(
                                "Results couldn't be published to VEKN — check that "
                                "every player (including finalists) has a VEKN ID, "
                                "then try again."
                            ),
                        )
                    tournament = await get_tournament_by_uid(uid) or tournament
                await maybe_submit_twda(tournament)
    except VEKNAPIConnectionError as e:
        raise HTTPException(
            status_code=502, detail="VEKN API is unavailable, try again later"
        ) from e
    # Order matters: VEKNAPIConnectionError subclasses VEKNAPIError. A data
    # error carries VEKN's actual reason — show it instead of guessing.
    except VEKNAPIError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    updated = await get_tournament_by_uid(uid) or tournament
    return Response(content=encoder.encode(updated), media_type="application/json")


@router.delete("/{uid}/organizers/{organizer_uid}")
async def remove_organizer(
    uid: str,
    organizer_uid: str,
    current_user: OptionalUser = None,
) -> Response:
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    bd = None
    async with tournament_transaction(uid) as (tournament, tx_conn):
        if not tournament:
            raise HTTPException(status_code=404, detail="Tournament not found")
        if not permissions.is_organizer(current_user, tournament):
            raise HTTPException(
                status_code=403, detail="Only organizers can manage organizers"
            )
        if organizer_uid in tournament.organizers_uids:
            if len(tournament.organizers_uids) <= 1:
                raise HTTPException(
                    status_code=400, detail="Cannot remove the last organizer"
                )
            tournament.organizers_uids.remove(organizer_uid)
            tournament.modified = datetime.now(UTC)
            # modified_at self-heals the member projection via since-catch-up; the
            # targeted push below additionally tombstones now-invisible private decks.
            bd = await save_tournament(tournament, conn=tx_conn)

    if bd is not None:
        broadcast_precomputed(bd)
        # Offline organizer removal is caught by the access-version fingerprint
        # at the next connect; this handles the online case without a full resync.
        await _invalidate_organizer_view(tournament, organizer_uid, bd.modified_at)

    return Response(
        content=encoder.encode(tournament),
        media_type="application/json",
    )


MAX_BANNER_SIZE = 1024 * 1024


@router.post("/{uid}/banner")
async def upload_banner(
    uid: str,
    file: UploadFile,
    current_user: OptionalUser = None,
) -> Response:
    """Expects a 1.91:1 (1200×630) image, max 1MB; client crops before upload."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    async with tournament_transaction(uid) as (tournament, tx_conn):
        if not tournament:
            raise HTTPException(status_code=404, detail="Tournament not found")
        if not permissions.is_organizer(current_user, tournament):
            raise HTTPException(
                status_code=403, detail="Only organizers can set the banner"
            )
        # Refuse writes while offline-locked, or banner_path diverges during
        # the offline window and gets clobbered by the go-online snapshot overwrite.
        if tournament.offline_mode:
            raise HTTPException(status_code=423, detail="Tournament is in offline mode")

        if file.content_type not in ("image/webp", "image/png", "image/jpeg"):
            raise HTTPException(
                status_code=400, detail="Banner must be webp, png, or jpeg"
            )

        data = await file.read()
        if len(data) > MAX_BANNER_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"Banner too large. Max size: {MAX_BANNER_SIZE // 1024}KB",
            )

        await upsert_banner(uid, data, file.content_type or "image/webp")

        now = datetime.now(UTC)
        version = int(now.timestamp() * 1000)  # cache-busting token baked into the URL
        tournament.banner_path = f"/api/tournaments/{uid}/banner?v={version}"
        tournament.modified = now
        bd = await save_tournament(tournament, conn=tx_conn)
    broadcast_precomputed(bd)

    return Response(content=b'{"success": true}', media_type="application/json")


@router.get("/{uid}/banner")
async def get_banner_image(uid: str, request: Request) -> Response:
    """Serve a tournament banner. A versioned (?v=) URL is immutable, so it can
    be cached aggressively; an unversioned request gets a short TTL."""
    result = await get_banner(uid)
    if not result:
        raise HTTPException(status_code=404, detail="Banner not found")

    data, content_type = result
    cache = (
        "public, max-age=31536000, immutable"
        if request.query_params.get("v")
        else "public, max-age=3600"
    )
    return Response(
        content=data,
        media_type=content_type,
        headers={"Cache-Control": cache, "Content-Length": str(len(data))},
    )


@router.delete("/{uid}/banner")
async def delete_banner_image(
    uid: str,
    current_user: OptionalUser = None,
) -> Response:
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    bd = None
    async with tournament_transaction(uid) as (tournament, tx_conn):
        if not tournament:
            raise HTTPException(status_code=404, detail="Tournament not found")
        if not permissions.is_organizer(current_user, tournament):
            raise HTTPException(
                status_code=403, detail="Only organizers can remove the banner"
            )
        if tournament.offline_mode:
            raise HTTPException(status_code=423, detail="Tournament is in offline mode")

        deleted = await delete_banner(uid)
        if tournament.banner_path is not None:
            tournament.banner_path = None
            tournament.modified = datetime.now(UTC)
            bd = await save_tournament(tournament, conn=tx_conn)
        elif not deleted:
            raise HTTPException(status_code=404, detail="Banner not found")

    if bd is not None:
        broadcast_precomputed(bd)

    return Response(content=b'{"success": true}', media_type="application/json")


class CreateTournamentRequest(BaseModel):
    name: str
    format: str = "Standard"
    rank: str = ""
    online: bool = False
    start: str | None = None
    finish: str | None = None
    timezone: str = "UTC"
    country: str | None = None
    venue: str = ""
    venue_url: str = ""
    address: str = ""
    map_url: str = ""
    proxies: bool = False
    multideck: bool = False
    decklist_required: bool = False
    description: str = ""
    standings_mode: str = "Private"
    decklists_mode: str = "Winner"
    max_rounds: int = 0
    max_players: int = 0
    open_rounds: bool = False
    self_organized_rounds: bool = False
    table_rooms: list[dict] = Field(default_factory=list)
    league_uid: str | None = None
    round_time: int = 0
    finals_time: int = 0


def _parse_datetime(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s)


def _zone(tz_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def _wall_clock_now(tz_name: str) -> datetime:
    """Naive wall clock in `tz_name` — the stored shape of start/finish."""
    return datetime.now(_zone(tz_name)).replace(tzinfo=None)


def _wall_clock(dt: datetime | None, tz_name: str) -> datetime | None:
    """Coerce to the stored shape: naive wall clock in `tz_name`. An offset is
    CONVERTED, not truncated — truncating would shift the event by the zone delta."""
    if dt is None or dt.tzinfo is None:
        return dt
    return dt.astimezone(_zone(tz_name)).replace(tzinfo=None)


def _normalize_wall_clock(t: Tournament) -> None:
    """Apply `_wall_clock` to a client tournament payload — a tz-aware value
    here would read back shifted by the venue's offset everywhere it's stored."""
    t.start = _wall_clock(t.start, t.timezone)
    t.finish = _wall_clock(t.finish, t.timezone)


def _engine_create_tournament(config: dict, actor: User) -> str:
    actor_json = msgspec.json.encode(
        {
            "uid": actor.uid,
            "roles": [r.value for r in actor.roles],
            "is_organizer": True,
            "can_organize_league_uids": [],
        }
    ).decode()
    try:
        return _engine.create_tournament(
            msgspec.json.encode(config).decode(), actor_json
        )
    except ValueError as e:
        raise EngineRejection.from_engine(e) from e


@router.post("/", status_code=201)
async def create_tournament(
    request: CreateTournamentRequest,
    current_user: OptionalUser = None,
) -> Response:
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    if not permissions.can_create_tournament(current_user):
        raise HTTPException(
            status_code=403, detail="Only IC, NC, or Prince can create tournaments"
        )

    # VEKN_PUSH: standard tournaments need max_rounds 2-4. Open-rounds events are
    # non-VEKN (not pushed), so max_rounds there is a free per-player cap (0 = no limit).
    vekn_push = os.getenv("VEKN_PUSH", "").lower() == "true"
    if vekn_push and not request.open_rounds:
        if request.max_rounds < 2 or request.max_rounds > 4:
            raise HTTPException(
                status_code=400,
                detail="max_rounds must be 2, 3, or 4 when VEKN push is enabled",
            )

    country = stored_country(request.country)
    if request.country and country is None:
        raise HTTPException(
            status_code=422, detail=f"Invalid country: {request.country}"
        )

    # Validate league_uid: league editors, or same-country Princes when the
    # league is open to them (rule single-sourced in the engine).
    if request.league_uid:
        league = await get_league_by_uid(request.league_uid)
        if not league:
            raise HTTPException(status_code=400, detail="League not found")
        if not permissions.can_link_tournament_to_league(current_user, league):
            raise HTTPException(
                status_code=403,
                detail="You don't have permission to attach tournaments to this league",
            )

    start = _wall_clock(_parse_datetime(request.start), request.timezone)
    finish = _wall_clock(_parse_datetime(request.finish), request.timezone)
    config = request.model_dump() | {
        "uid": str(uuid7()),
        "now": datetime.now(UTC).isoformat(),
        "country": country,
        "start": start.isoformat() if start else None,
        "finish": finish.isoformat() if finish else None,
        "league_uid": request.league_uid or None,
    }
    tournament = msgspec.json.decode(
        _engine_create_tournament(config, current_user), type=Tournament
    )

    # Fresh uuid7 — no existing row to lock, but save_tournament requires a conn.
    async with get_connection() as conn:
        bd = await save_tournament(tournament, conn=conn)
    logger.info(f"Tournament {tournament.uid} created by {current_user.uid}")

    broadcast_precomputed(bd)

    # VEKN push: create calendar event. Background task — the response must not
    # wait on vekn.net (30-120s timeouts when it is down); batch_push retries.
    asyncio.create_task(_maybe_push_vekn_event(tournament))

    return Response(
        content=encoder.encode(tournament),
        media_type="application/json",
        status_code=201,
    )


# Must precede /{uid}: route match order, or the path param captures these.


@router.get("/archon-template")
async def download_archon_template() -> FileResponse:
    """Serve blank Archon v1.5l spreadsheet template. Public access."""
    # must live under backend/src/data to ship inside the installed wheel
    path = files("backend.src").joinpath("data", "thearchon1.5l.xlsx")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Template file not found")
    return FileResponse(
        path,
        filename="thearchon1.5l.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.get("/fetch-deck")
async def fetch_deck_proxy(
    url: str,
    current_user: OptionalUser = None,
) -> Response:
    """Proxies deck fetch from VDB/VTESDecks/Amaranth — works around CORS and
    maps provider-native card ids to VEKN ids via krcg."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    from ..providers import DeckFetchError, fetch_deck_from_url

    try:
        result = await fetch_deck_from_url(url)
    except DeckFetchError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception("Failed to fetch deck from URL")
        raise HTTPException(status_code=400, detail=f"Failed to fetch deck: {e}") from e

    return Response(
        content=msgspec.json.encode(result),
        media_type="application/json",
    )


@router.delete("/{uid}")
async def delete_tournament_endpoint(
    uid: str,
    current_user: OptionalUser = None,
) -> Response:
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    tournament = await get_tournament_by_uid(uid)
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")

    if not permissions.is_organizer(current_user, tournament):
        raise HTTPException(
            status_code=403, detail="Only organizers can delete this tournament"
        )

    # An offline-locked device holds authoritative state and would resurrect the
    # tournament (deleted_at=null) on go-online — force-unlock it before deleting.
    if tournament.offline_mode:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete a tournament locked for offline use; unlock it first",
        )

    # Deletable until it has a VEKN footprint (external_ids.vekn or
    # vekn_pushed_at) — past that, deleting here orphans the vekn.net record.
    if tournament.external_ids.get("vekn") or tournament.vekn_pushed_at is not None:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete a tournament that has been pushed to VEKN",
        )

    was_finished = tournament.state == TournamentState.FINISHED
    result = await soft_delete_tournament(uid)
    logger.info(f"Tournament {uid} soft-deleted by {current_user.uid}")

    if result:
        # Tombstone the tournament plus its cascaded decks/sanctions.
        for bd in result[1]:
            broadcast_precomputed(bd)
    # No state gate on ReportPromos, so even a Planned event may carry rows.
    _promo_recompute_diff(tournament, None)

    # A finished event fed player ratings; recompute now that it's soft-deleted
    # (recompute reads only live finished tournaments, so the deleted one drops out).
    if was_finished:
        try:
            from ..ratings import (
                rating_category_for_tournament,
                recompute_ratings_for_players,
                recompute_wins,
            )

            player_uids = {p.user_uid for p in tournament.players if p.user_uid}
            category = rating_category_for_tournament(tournament)
            for _user, bd in await recompute_ratings_for_players(player_uids, category):
                broadcast_precomputed(bd)
            for _user, bd in await recompute_wins(player_uids):
                broadcast_precomputed(bd)
        except Exception as e:
            logger.error(
                f"Error recomputing ratings after deleting {uid}: {e}", exc_info=True
            )

    return Response(
        content=encoder.encode({"message": "Tournament deleted"}),
        media_type="application/json",
    )


@router.post("/{uid}/archon-import")
async def archon_import(
    uid: str,
    file: UploadFile,
    current_user: OptionalUser = None,
) -> Response:
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    tournament = await get_tournament_by_uid(uid)
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")

    if not permissions.is_organizer(current_user, tournament):
        raise HTTPException(
            status_code=403,
            detail="Only organizers can import",
        )

    if not file.filename or not file.filename.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="File must be an .xlsx spreadsheet")

    file_bytes = await file.read()
    if len(file_bytes) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 5MB)")

    from ..archon_import import (
        apply_archon_import,
        parse_archon_file,
        validate_archon_import,
    )

    try:
        data = parse_archon_file(file_bytes)
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Failed to parse spreadsheet: {e}"
        ) from e

    engine = _engine
    errors = validate_archon_import(data, engine)
    if errors:
        return Response(
            content=msgspec.json.encode(
                {
                    "success": False,
                    "errors": errors,
                    "warnings": [],
                    "players_matched": 0,
                    "rounds_imported": 0,
                    "has_finals": False,
                }
            ).decode(),
            media_type="application/json",
            status_code=400,
        )

    result = await apply_archon_import(
        tournament_uid=uid,
        data=data,
        actor_uid=current_user.uid,
        engine=engine,
        broadcast_tournament_event=broadcast_precomputed,
        broadcast_user_event=broadcast_precomputed,
    )

    status = 200 if result.success else 400
    return Response(
        content=msgspec.json.encode(
            {
                "success": result.success,
                "errors": result.errors,
                "warnings": result.warnings,
                "players_matched": result.players_matched,
                "rounds_imported": result.rounds_imported,
                "has_finals": result.has_finals,
            }
        ).decode(),
        media_type="application/json",
        status_code=status,
    )


class BulkRegisterRow(BaseModel):
    vekn_id: str | None = None
    email: str | None = None
    name: str | None = None  # display only (unmatched-row reporting)
    paid: bool | None = None  # None → request default


class BulkRegisterRequest(BaseModel):
    rows: list[BulkRegisterRow]
    default_paid: bool = True  # they paid at the ticketing source


@router.post("/{uid}/bulk-register")
async def bulk_register(
    uid: str,
    request: BulkRegisterRequest,
    current_user: OptionalUser = None,
) -> Response:
    """Bulk-register externally-ticketed players by VEKN ID then email match.
    Unmatched rows are RETURNED for manual resolution — never silently created."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    if len(request.rows) > 500:
        raise HTTPException(status_code=400, detail="Too many rows (max 500)")

    existing = await get_tournament_by_uid(uid)
    if not existing:
        raise HTTPException(status_code=404, detail="Tournament not found")
    if not permissions.is_organizer(current_user, existing):
        raise HTTPException(
            status_code=403, detail="Only organizers can import registrations"
        )
    if existing.state != TournamentState.REGISTRATION:
        raise HTTPException(
            status_code=400, detail="Tournament must be in Registration state"
        )

    # Resolve rows to members (reads only — outside the row lock)
    matched: list[tuple[User, bool | None]] = []
    unmatched: list[dict] = []
    seen_uids: set[str] = set()
    for i, row in enumerate(request.rows):
        label = row.name or row.email or row.vekn_id or f"row {i + 1}"
        user = None
        if row.vekn_id and row.vekn_id.strip():
            user = await get_user_by_vekn_id(row.vekn_id.strip())
        if user is None and row.email and row.email.strip():
            am = await get_auth_method_by_identifier("email", row.email.strip().lower())
            if am:
                user = await get_user_by_uid(am.user_uid)
        if user is None:
            unmatched.append({"row": i, "name": label, "reason": "not_found"})
            continue
        if not user.vekn_id:
            unmatched.append({"row": i, "name": user.name, "reason": "no_vekn_id"})
            continue
        if user.uid in seen_uids:
            unmatched.append({"row": i, "name": user.name, "reason": "duplicate_row"})
            continue
        seen_uids.add(user.uid)
        matched.append((user, row.paid))

    registered: list[str] = []
    already: list[str] = []
    failed: list[dict] = []
    async with tournament_transaction(uid) as (tournament, tx_conn):
        if tournament is None:
            raise HTTPException(status_code=404, detail="Tournament not found")
        if not permissions.is_organizer(current_user, tournament):
            raise HTTPException(
                status_code=403, detail="Only organizers can import registrations"
            )
        if tournament.state != TournamentState.REGISTRATION:
            raise HTTPException(
                status_code=400, detail="Tournament must be in Registration state"
            )

        actor_json = msgspec.json.encode(
            _build_actor_context(current_user, tournament)
        ).decode("utf-8")
        sanctions_data = [
            {
                "user_uid": s.user_uid,
                "level": s.level.value,
                "round_number": s.round_number,
                "lifted_at": s.lifted_at.isoformat() if s.lifted_at else None,
                "deleted_at": s.deleted_at.isoformat() if s.deleted_at else None,
                "expires_at": (
                    s.expires_at.astimezone(UTC).isoformat() if s.expires_at else None
                ),
            }
            for s in await get_sanctions_for_users(seen_uids, conn=tx_conn)
            if not s.deleted_at and not s.lifted_at
        ]
        sanctions_json = msgspec.json.encode(sanctions_data).decode("utf-8")
        decks_json = await _build_decks_json(uid, conn=tx_conn)

        t_data = msgspec.to_builtins(tournament)
        in_tournament = {p.user_uid for p in tournament.players if p.user_uid}
        for user, paid in matched:
            if user.uid in in_tournament:
                already.append(user.name)
                continue
            try:
                await _check_player_barred(user.uid, uid, tournament, conn=tx_conn)
            except EngineRejection as e:
                failed.append({"name": user.name, "reason": e.message})
                continue
            events: list[dict] = [
                {"type": "AddPlayer", "user_uid": user.uid, "vekn_id": user.vekn_id}
            ]
            effective_paid = request.default_paid if paid is None else paid
            if effective_paid:
                events.append(
                    {
                        "type": "SetPaymentStatus",
                        "player_uid": user.uid,
                        "status": "Paid",
                    }
                )
            try:
                for event in events:
                    result_json = _engine.process_tournament_event(
                        msgspec.json.encode(t_data).decode("utf-8"),
                        msgspec.json.encode(event).decode("utf-8"),
                        actor_json,
                        sanctions_json,
                        decks_json,
                    )
                    t_data = json.loads(result_json)["tournament"]
            except ValueError as e:
                rejection = EngineRejection.from_engine(e)
                failed.append({"name": user.name, "reason": rejection.message})
                continue
            in_tournament.add(user.uid)
            registered.append(user.name)

        updated = msgspec.convert(t_data, Tournament)
        updated.modified = datetime.now(UTC)
        bd = await save_object(
            ObjectType.TOURNAMENT,
            updated.uid,
            msgspec.to_builtins(updated),
            conn=tx_conn,
        )

    broadcast_precomputed(bd)
    logger.info(
        f"Bulk-registered {len(registered)} players on {uid} "
        f"({len(already)} already in, {len(unmatched)} unmatched, {len(failed)} failed)"
    )
    return Response(
        content=msgspec.json.encode(
            {
                "registered": registered,
                "already_registered": already,
                "unmatched": unmatched,
                "failed": failed,
            }
        ).decode(),
        media_type="application/json",
    )


class TournamentActionRequest(BaseModel):
    type: str  # Event type: OpenRegistration, Register, CheckIn, StartRound, etc.
    user_uid: str | None = None  # For Register, AddPlayer, RemovePlayer
    player_uid: str | None = None  # For CheckIn
    # Discord guild nickname, display-only, never identity — vekn_id comes only
    # from the resolved user. max_length=32 mirrors Discord's own ceiling.
    display_name: str | None = Field(default=None, max_length=32)
    round: int | None = None  # For SetScore, SwapSeats
    table: int | None = None  # For SetScore
    table1: int | None = None  # For SwapSeats
    seat1: int | None = None  # For SwapSeats
    table2: int | None = None  # For SwapSeats
    seat2: int | None = None  # For SwapSeats
    seat: int | None = None  # For SeatPlayer
    scores: list[dict] | None = None  # For SetScore: [{player_uid, vp}]
    comment: str | None = None  # For Override
    toss: int | None = None  # For SetToss
    status: str | None = None  # For SetPaymentStatus
    non_competing: bool | None = None  # For SetNonCompeting (proxy toggle)
    seating: list[list[str]] | None = None  # For AlterSeating
    player_uids: list[str] | None = None  # For SelfOrganizeRound: the chosen pod
    config: dict | None = None  # For UpdateConfig: partial config fields
    deck: dict | None = None
    multideck: bool | None = None
    label: str | None = None
    pool: str | None = None
    exclude_drawn: bool | None = None
    count: int | None = None
    seed: int | None = None
    winner: str | None = None  # For SetArchivalResults
    players: list[str] | None = None  # For SetArchivalResults: the known roster
    reported_player_count: int | None = None  # For SetArchivalResults


# Every other field reaches the engine whenever it is not null — including the
# empty string, which is how `winner` clears. These nine are the exceptions: an
# empty value means "not part of this action", so it must not reach the engine.
_ACTION_TRUTHY_ONLY = frozenset(
    {
        "user_uid",
        "player_uid",
        "display_name",
        "scores",
        "comment",
        "status",
        "seating",
        "label",
        "pool",
    }
)


@router.post("/{uid}/action")
async def tournament_action(
    uid: str,
    request: TournamentActionRequest,
    current_user: OptionalUser = None,
) -> Response:
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    event_data = {"type": request.type} | {
        name: value
        for name, value in request.model_dump(
            exclude_none=True, exclude={"type"}
        ).items()
        if value or name not in _ACTION_TRUTHY_ONLY
    }
    if "config" in event_data and "country" in event_data["config"]:
        country = stored_country(event_data["config"]["country"])
        if event_data["config"]["country"] and country is None:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid country: {event_data['config']['country']}",
            )
        event_data["config"]["country"] = country

    # SELECT FOR UPDATE: serialize concurrent writes to this tournament
    async with tournament_transaction(uid) as (tournament, tx_conn):
        if not tournament:
            raise HTTPException(status_code=404, detail="Tournament not found")

        # VEKN_PUSH: max_rounds immutable once pushed to VEKN
        if (
            request.type == "UpdateConfig"
            and request.config
            and "max_rounds" in request.config
        ):
            if tournament.external_ids.get("vekn"):
                if request.config["max_rounds"] != tournament.max_rounds:
                    raise HTTPException(
                        status_code=409,
                        detail="max_rounds cannot be changed after tournament is pushed to VEKN",
                    )
            vekn_push = os.getenv("VEKN_PUSH", "").lower() == "true"
            # 2-4 max_rounds applies only to standard (non-open-rounds) tournaments;
            # open_rounds is the request's value if present, else the stored one.
            open_rounds = request.config.get("open_rounds", tournament.open_rounds)
            if (
                vekn_push
                and not open_rounds
                and request.config["max_rounds"] is not None
            ):
                mr = request.config["max_rounds"]
                if mr != 0 and (mr < 2 or mr > 4):
                    raise HTTPException(
                        status_code=400,
                        detail="max_rounds must be 2, 3, or 4 when VEKN push is enabled",
                    )

        if tournament.offline_mode:
            raise HTTPException(
                status_code=423,
                detail="Tournament is in offline mode on another device",
            )

        # Reads below reuse tx_conn instead of a fresh pooled connection while
        # holding FOR UPDATE, so one action never pins more than one pool slot.
        can_organize = None
        if request.type == "UpdateConfig" and request.config:
            can_organize = await _get_user_organizable_league_uids(
                current_user, conn=tx_conn
            )
        actor_data = _build_actor_context(current_user, tournament, can_organize)

        # Tournament sanctions plus user-level suspension/DQ for all players
        # (needed for CheckInAll etc.)
        tournament_sanctions = await get_sanctions_for_tournament(uid, conn=tx_conn)
        seen_uids = {s.uid for s in tournament_sanctions}
        player_uids = {p.user_uid for p in tournament.players if p.user_uid}
        for s in await get_sanctions_for_users(player_uids, conn=tx_conn):
            if s.uid in seen_uids or s.deleted_at or s.lifted_at:
                continue
            if s.level in (
                SanctionLevel.SUSPENSION,
                SanctionLevel.DISQUALIFICATION,
            ):
                tournament_sanctions.append(s)
                seen_uids.add(s.uid)
        sanctions_data = [
            {
                "user_uid": s.user_uid,
                "level": s.level.value,
                "round_number": s.round_number,
                "lifted_at": s.lifted_at.isoformat() if s.lifted_at else None,
                "deleted_at": s.deleted_at.isoformat() if s.deleted_at else None,
                # UTC-canonical to match actor.now's format for the engine's expiry compare.
                "expires_at": (
                    s.expires_at.astimezone(UTC).isoformat() if s.expires_at else None
                ),
            }
            for s in tournament_sanctions
        ]

        # vekn_id comes only from the resolved user — the request model has no
        # vekn_id field, so a fabricated id can never reach the engine.
        target_uid = None
        if request.type in ("Register", "AddPlayer"):
            target_uid = request.user_uid
        elif request.type == "CheckIn":
            target_uid = request.player_uid
        if target_uid:
            target_user = await get_user_by_uid(target_uid, conn=tx_conn)
            if not target_user:
                raise HTTPException(status_code=404, detail="User not found")
            # Empty means unsponsored: the engine rejects it for a new player and
            # ignores it for one already on the roster.
            event_data["vekn_id"] = target_user.vekn_id or ""

        tournament_json = encoder.encode(tournament).decode("utf-8")
        event_json = msgspec.json.encode(event_data).decode("utf-8")
        actor_json = msgspec.json.encode(actor_data).decode("utf-8")
        sanctions_json = msgspec.json.encode(sanctions_data).decode("utf-8")
        decks_json = await _build_decks_json(uid, conn=tx_conn)

        if request.type in ("CheckIn", "Register", "AddPlayer"):
            player_uid = request.player_uid or request.user_uid
            if player_uid:
                await _check_player_barred(player_uid, uid, tournament, conn=tx_conn)

        engine = _engine
        try:
            result_json = engine.process_tournament_event(
                tournament_json, event_json, actor_json, sanctions_json, decks_json
            )
        except ValueError as e:
            # Engine rejections arrive as ValueError carrying the wire JSON
            raise EngineRejection.from_engine(e) from e

        # Parse new result format: {"tournament": {...}, "deck_ops": [...]}
        result = json.loads(result_json)
        # Normalize datetime fields: frontend sends "YYYY-MM-DDTHH:MM" (no seconds)
        # but msgspec requires at least "YYYY-MM-DDTHH:MM:SS" for RFC3339 decoding
        t_data = result["tournament"]
        for dt_field in ("start", "finish"):
            v = t_data.get(dt_field)
            if isinstance(v, str) and len(v) == 16:  # "YYYY-MM-DDTHH:MM"
                t_data[dt_field] = v + ":00"
        # msgspec.convert applies the same coercion as JSON decode without the
        # redundant encode→decode round-trip — meaningful CPU on a large scoring burst.
        updated = msgspec.convert(t_data, Tournament)
        updated.modified = datetime.now(UTC)
        _normalize_wall_clock(updated)
        # Stamp finish when entering Finished with none set — the engine never
        # writes it, and ratings/VEKN push depend on it.
        if (
            updated.state == TournamentState.FINISHED
            and tournament.state != TournamentState.FINISHED
            and updated.finish is None
        ):
            updated.finish = _wall_clock_now(updated.timezone)
        deck_ops = result.get("deck_ops", [])

        # Timer lifecycle is backend-only: every round/finals transition resets to
        # a fresh paused timer and clears extra time. AddTable is excluded (no reset).
        TIMER_EVENTS = (
            "StartRound",
            "SelfOrganizeRound",
            "StartFinals",
            "RestoreRound",
            "FinishRound",
            "CancelRound",
            "FinishFinals",
            "FinishTournament",
            "CancelFinals",
        )
        if request.type in TIMER_EVENTS:
            updated.timer = TimerState()
            updated.table_extra_time = {}

        # Detected by CONTENT diff, not event type, so any edit touching those
        # fields after a VEKN push is caught; sticky, so this runs at most once.
        if updated.vekn_pushed_at and not updated.vekn_results_stale:
            if (
                tournament.winner != updated.winner
                or encoder.encode(tournament.standings)
                != encoder.encode(updated.standings)
                or encoder.encode(tournament.finals) != encoder.encode(updated.finals)
                or encoder.encode(tournament.rounds) != encoder.encode(updated.rounds)
            ):
                updated.vekn_results_stale = True

        tournament_bd = await save_object(
            ObjectType.TOURNAMENT,
            updated.uid,
            msgspec.to_builtins(updated),
            conn=tx_conn,
        )
        pre_state = tournament.state

    # Below runs unlocked — the tournament row's FOR UPDATE lock was released.
    logger.info(f"Tournament {uid} action {request.type} by {current_user.uid}")

    deck_bds = await _process_deck_ops(deck_ops, uid, org_uids=updated.organizers_uids)
    for bd in deck_bds:
        broadcast_precomputed(bd)

    broadcast_precomputed(tournament_bd)

    if request.type == "ReportPromos":
        _promo_recompute_diff(tournament, updated)

    # Fire-and-forget, post-commit (a DB-touching task must not run inside
    # tournament_transaction). RestoreRound re-seats no one, so it's excluded.
    if request.type in ("StartRound", "SelfOrganizeRound", "StartFinals"):
        asyncio.create_task(_maybe_push_seating(updated, request.type))
    elif request.type in ("AlterSeating", "SwapSeats", "SeatPlayer", "UnseatPlayer"):
        # Only players whose table/seat actually changed are pushed — the
        # stale seating notification they may act on gets replaced.
        asyncio.create_task(_maybe_push_reseat(tournament, updated))

    # Recompute on entering/leaving Finished, or on a result-affecting action on
    # an already-finished tournament (see _RATING_IRRELEVANT_ACTIONS for the skip list).
    was_finished = pre_state == TournamentState.FINISHED
    is_finished = updated.state == TournamentState.FINISHED
    state_changed = was_finished != is_finished
    results_may_change = is_finished and request.type not in _RATING_IRRELEVANT_ACTIONS
    if state_changed or results_may_change:
        try:
            from ..ratings import (
                rating_category_for_tournament,
                recompute_ratings_for_players,
                recompute_wins,
            )

            player_uids = {p.user_uid for p in updated.players if p.user_uid}
            category = rating_category_for_tournament(updated)
            results = await recompute_ratings_for_players(player_uids, category)
            results += await recompute_wins(player_uids)
            for _user, bd in results:
                broadcast_precomputed(bd)
            # If category changed (format/online toggle), also recompute old category
            old_category = rating_category_for_tournament(tournament)
            if old_category != category:
                old_results = await recompute_ratings_for_players(
                    player_uids, old_category
                )
                for _user, bd in old_results:
                    broadcast_precomputed(bd)
        except Exception as e:
            logger.error(f"Error recomputing ratings for {uid}: {e}", exc_info=True)

    # `set_public` carries no player_uid and needs none: the Hall of Fame asks
    # whether the deck exists, never whether it is publicly visible.
    winner_deck_ops = [op for op in deck_ops if op.get("player_uid") == updated.winner]

    # VEKN push backgrounds (vekn.net can take 30-120s or be down; batch_push
    # retries) — TWDA submission runs inline since it's local/fast.
    if is_finished and not was_finished:
        await maybe_submit_twda(updated)
        asyncio.create_task(_maybe_push_vekn(updated))
    elif is_finished and updated.winner and winner_deck_ops:
        if any(op.get("op") == "upsert" for op in winner_deck_ops):
            # Re-submit on a post-finish winner-deck edit (organizers only — players
            # are deck-locked); the TWDA PR is idempotent, keyed on the vekn event id.
            asyncio.create_task(maybe_submit_twda(updated))
        # The same edit moves the Hall of Fame in both directions — the win counts
        # only while the deck is on record — and every deck action is on
        # `_RATING_IRRELEVANT_ACTIONS`, so the recompute above skipped it.
        try:
            from ..ratings import recompute_wins

            for _user, bd in await recompute_wins({updated.winner}):
                broadcast_precomputed(bd)
        except Exception as e:
            logger.error(f"Error recomputing wins for {uid}: {e}", exc_info=True)

    return Response(
        content=encoder.encode(updated),
        media_type="application/json",
    )


class QrCheckinRequest(BaseModel):
    code: str


@router.post("/{uid}/qr-checkin")
async def qr_checkin(
    uid: str,
    request: QrCheckinRequest,
    current_user: OptionalUser = None,
) -> Response:
    """Self check-in via QR code scanned at the venue."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    tournament = await get_tournament_by_uid(uid)
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    # Defense-in-depth: an empty stored code must never authorize check-in (a
    # legacy event with checkin_code='' would otherwise accept code='').
    if not tournament.checkin_code or request.code != tournament.checkin_code:
        raise HTTPException(status_code=403, detail="Invalid check-in code")
    return await tournament_action(
        uid,
        TournamentActionRequest(type="CheckIn", player_uid=current_user.uid),
        current_user,
    )


def _load_engine_cards() -> None:
    """Hand cards.json to the engine, which parses and holds it."""
    global _engine_cards_loaded
    if _engine_cards_loaded:
        return
    text = cards_json_text()
    if text is None:
        raise HTTPException(
            status_code=503, detail="Cards data not available. Run: just cards"
        )
    _engine.load_cards(text)
    _engine_cards_loaded = True


def _validate_timer_tournament(user, tournament: Tournament | None):
    """Validate tournament state for timer operations (inside transaction)."""
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    if not permissions.is_organizer(user, tournament):
        raise HTTPException(status_code=403, detail="Organizer access required")
    if tournament.offline_mode:
        raise HTTPException(status_code=423, detail="Tournament is in offline mode")
    if tournament.state != TournamentState.PLAYING:
        raise HTTPException(status_code=400, detail="Tournament is not playing")


async def _save_timer_tx(tournament: Tournament, tx_conn) -> BroadcastData:
    """Save within transaction. Returns BroadcastData for broadcasting after commit."""
    tournament.modified = datetime.now(UTC)
    return await save_object(
        ObjectType.TOURNAMENT,
        tournament.uid,
        msgspec.to_builtins(tournament),
        conn=tx_conn,
    )


@router.post("/{uid}/timer/start")
async def timer_start(
    uid: str,
    user: OptionalUser = None,
) -> Response:
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    async with tournament_transaction(uid) as (tournament, tx_conn):
        _validate_timer_tournament(user, tournament)
        assert tournament is not None
        if not tournament.timer.paused:
            raise HTTPException(status_code=400, detail="Timer is already running")
        tournament.timer = TimerState(
            started_at=datetime.now(UTC),
            elapsed_before_pause=tournament.timer.elapsed_before_pause,
            paused=False,
        )
        bd = await _save_timer_tx(tournament, tx_conn)
    broadcast_precomputed(bd)
    return Response(content=encoder.encode(tournament), media_type="application/json")


@router.post("/{uid}/timer/pause")
async def timer_pause(
    uid: str,
    user: OptionalUser = None,
) -> Response:
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    async with tournament_transaction(uid) as (tournament, tx_conn):
        _validate_timer_tournament(user, tournament)
        assert tournament is not None
        if tournament.timer.paused:
            raise HTTPException(status_code=400, detail="Timer is already paused")
        elapsed = 0.0
        if tournament.timer.started_at:
            elapsed = (datetime.now(UTC) - tournament.timer.started_at).total_seconds()
        tournament.timer = TimerState(
            elapsed_before_pause=tournament.timer.elapsed_before_pause + elapsed,
            paused=True,
        )
        bd = await _save_timer_tx(tournament, tx_conn)
    broadcast_precomputed(bd)
    return Response(content=encoder.encode(tournament), media_type="application/json")


@router.post("/{uid}/timer/reset")
async def timer_reset(
    uid: str,
    user: OptionalUser = None,
) -> Response:
    """Reset the global timer to fresh paused state."""
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    async with tournament_transaction(uid) as (tournament, tx_conn):
        _validate_timer_tournament(user, tournament)
        assert tournament is not None
        tournament.timer = TimerState()
        tournament.table_extra_time = {}
        bd = await _save_timer_tx(tournament, tx_conn)
    broadcast_precomputed(bd)
    return Response(content=encoder.encode(tournament), media_type="application/json")


class AddTimeRequest(BaseModel):
    table: str  # table index as string key
    seconds: int


@router.post("/{uid}/timer/add-time")
async def timer_add_time(
    uid: str,
    request: AddTimeRequest,
    user: OptionalUser = None,
) -> Response:
    """Add extra time to a specific table."""
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    async with tournament_transaction(uid) as (tournament, tx_conn):
        _validate_timer_tournament(user, tournament)
        assert tournament is not None
        if request.seconds <= 0:
            raise HTTPException(status_code=400, detail="Seconds must be positive")
        current = tournament.table_extra_time.get(request.table, 0)
        # Sanity bound, not a VEKN rule (judges may grant generous extensions).
        if current + request.seconds > 1800:
            raise HTTPException(
                status_code=400, detail="Max 1800s (30 min) extra time per table"
            )
        tournament.table_extra_time[request.table] = current + request.seconds
        bd = await _save_timer_tx(tournament, tx_conn)
    broadcast_precomputed(bd)
    return Response(content=encoder.encode(tournament), media_type="application/json")


MAX_ANNOUNCEMENTS = 20  # bounds the member-projection payload
MAX_ANNOUNCEMENT_LEN = 280


def _validate_announce_tournament(user, tournament: Tournament | None):
    """Validate tournament for announcement operations (inside transaction)."""
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    if not permissions.is_organizer(user, tournament):
        raise HTTPException(status_code=403, detail="Organizer access required")
    if tournament.offline_mode:
        raise HTTPException(status_code=423, detail="Tournament is in offline mode")


class AnnounceRequest(BaseModel):
    body: str


@router.post("/{uid}/announce")
async def post_announcement(
    uid: str,
    request: AnnounceRequest,
    user: OptionalUser = None,
) -> Response:
    """Post a live announcement to all tournament participants."""
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    body = request.body.strip()
    if not body:
        raise HTTPException(status_code=400, detail="Announcement is empty")
    if len(body) > MAX_ANNOUNCEMENT_LEN:
        raise HTTPException(
            status_code=400, detail=f"Max {MAX_ANNOUNCEMENT_LEN} characters"
        )
    async with tournament_transaction(uid) as (tournament, tx_conn):
        _validate_announce_tournament(user, tournament)
        assert tournament is not None
        tournament.announcements.append(
            Announcement(
                id=uuid7().hex,
                body=body,
                created_at=datetime.now(UTC),
                author_uid=user.uid,
                author_name=user.name,
            )
        )
        # Prune on write so the projection never needs a separate cleanup job
        tournament.announcements = tournament.announcements[-MAX_ANNOUNCEMENTS:]
        tournament.modified = datetime.now(UTC)
        bd = await save_object(
            ObjectType.TOURNAMENT,
            tournament.uid,
            msgspec.to_builtins(tournament),
            conn=tx_conn,
        )
    broadcast_precomputed(bd)
    # Fire-and-forget to every participant except the posting organizer (who has
    # the composer open already). Post-commit, like seating above.
    asyncio.create_task(_maybe_push_announcement(tournament, body, user.uid))
    return Response(content=encoder.encode(tournament), media_type="application/json")


@router.delete("/{uid}/announce/{announcement_id}")
async def delete_announcement(
    uid: str,
    announcement_id: str,
    user: OptionalUser = None,
) -> Response:
    """Remove an announcement (wrong-room, typo, superseded)."""
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    async with tournament_transaction(uid) as (tournament, tx_conn):
        _validate_announce_tournament(user, tournament)
        assert tournament is not None
        kept = [a for a in tournament.announcements if a.id != announcement_id]
        if len(kept) == len(tournament.announcements):
            raise HTTPException(status_code=404, detail="Announcement not found")
        tournament.announcements = kept
        tournament.modified = datetime.now(UTC)
        bd = await save_object(
            ObjectType.TOURNAMENT,
            tournament.uid,
            msgspec.to_builtins(tournament),
            conn=tx_conn,
        )
    broadcast_precomputed(bd)
    return Response(content=encoder.encode(tournament), media_type="application/json")


class JudgeCallRequest(BaseModel):
    table: int


@router.post("/{uid}/call-judge", status_code=204)
async def call_judge(
    uid: str,
    request: JudgeCallRequest,
    user: OptionalUser = None,
) -> Response:
    """Player calls for judge assistance at their table."""
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    tournament = await get_tournament_by_uid(uid)
    if not tournament:
        raise HTTPException(status_code=404, detail="Tournament not found")
    if tournament.state != TournamentState.PLAYING:
        raise HTTPException(status_code=400, detail="Tournament is not playing")
    if tournament.offline_mode:
        raise HTTPException(status_code=423, detail="Tournament is in offline mode")
    if not tournament.rounds:
        raise HTTPException(status_code=400, detail="No active round")
    current_round = tournament.rounds[-1]
    if request.table < 0 or request.table >= len(current_round):
        raise HTTPException(status_code=400, detail="Invalid table index")
    table = current_round[request.table]
    if not any(s.player_uid == user.uid for s in table.seating):
        raise HTTPException(status_code=403, detail="You are not seated at this table")
    table_label = _engine.table_label(
        msgspec.json.encode(tournament.table_rooms).decode(), request.table
    )
    # Web Push the same organizer audience as the SSE broadcast, so one away from
    # the screen is alerted too. Fire-and-forget, exclude caller.
    await broadcast_judge_call(
        tournament_uid=tournament.uid,
        table=request.table,
        table_label=table_label,
        player_name=user.name,
        organizer_uids=tournament.organizers_uids,
    )
    asyncio.create_task(
        _maybe_push_judge_call(
            tournament, request.table, table_label, user.name, user.uid
        )
    )
    return Response(status_code=204)


class GoOfflineRequest(BaseModel):
    device_id: str


@router.post("/{uid}/go-offline")
async def go_offline(
    uid: str,
    request: GoOfflineRequest,
    current_user: OptionalUser = None,
) -> Response:
    """Lock a tournament for offline use on a specific device."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    # SELECT FOR UPDATE: serialize the offline-lock get-then-update (TOCTOU)
    async with tournament_transaction(uid) as (tournament, tx_conn):
        if not tournament:
            raise HTTPException(status_code=404, detail="Tournament not found")

        # Organizer AND member-creation power: offline play mints real members
        # at go-online, so the lock carries more than running the event.
        if not permissions.can_take_tournament_offline(current_user, tournament):
            raise HTTPException(
                status_code=403,
                detail="You don't have permission to take this tournament offline",
            )

        if tournament.offline_mode:
            raise HTTPException(
                status_code=409, detail="Tournament is already in offline mode"
            )

        tournament.offline_mode = True
        tournament.offline_device_id = request.device_id
        tournament.offline_user_uid = current_user.uid
        tournament.offline_since = datetime.now(UTC)
        tournament.modified = datetime.now(UTC)

        bd = await save_object(
            ObjectType.TOURNAMENT,
            tournament.uid,
            msgspec.to_builtins(tournament),
            conn=tx_conn,
        )

    logger.info(
        f"Tournament {uid} went offline (device={request.device_id}, user={current_user.uid})"
    )

    broadcast_precomputed(bd)

    return Response(content=encoder.encode(tournament), media_type="application/json")


class OfflinePlayerData(BaseModel):
    temp_uid: str
    name: str
    vekn_id: str | None = None
    email: str | None = None


class GoOnlineRequest(BaseModel):
    device_id: str
    tournament: dict  # Full tournament data from the offline device
    offline_players: list[OfflinePlayerData] = []
    offline_sanctions: list[dict] = []
    offline_decks: list[dict] = []
    force: bool = False


async def _resolve_or_create_offline_player(
    player_data: OfflinePlayerData,
    tournament_country: str | None,
    organizer_uid: str | None = None,
) -> tuple[str, User, bool]:
    """Resolve an offline player to a real user.

    Returns (temp_uid, real_user, created) — created=True only for a brand-new
    account (the go-online outcome summary tells the organizer how many real
    members were minted at the venue)."""
    if player_data.vekn_id and not player_data.vekn_id.startswith("TEMP-"):
        user = await get_user_by_vekn_id(player_data.vekn_id)
        if user:
            return player_data.temp_uid, user, False

    if player_data.email:
        auth_method = await get_auth_method_by_identifier("email", player_data.email)
        if auth_method:
            user = await get_user_by_uid(auth_method.user_uid)
            if user:
                if not user.vekn_id:
                    user.vekn_id = await allocate_next_vekn_id()
                    user.coopted_by = organizer_uid
                    user.coopted_at = datetime.now(UTC)
                    user.modified = datetime.now(UTC)
                    bd = await save_object_from_model(ObjectType.USER, user)
                    broadcast_precomputed(bd)
                return player_data.temp_uid, user, False

    now = datetime.now(UTC)
    vekn_id = await allocate_next_vekn_id()
    new_user = User(
        uid=str(uuid7()),
        modified=now,
        name=player_data.name,
        country=tournament_country,
        vekn_id=vekn_id,
        coopted_by=organizer_uid,
        coopted_at=now,
    )
    bd = await save_user(new_user)
    logger.info(
        f"Created user {new_user.uid} (VEKN {vekn_id}) for offline player '{player_data.name}'"
    )

    broadcast_precomputed(bd)

    if player_data.email:
        try:
            await send_invite_email(
                player_data.email.lower(), new_user.uid, new_user.name
            )
        except Exception:
            logger.warning(f"Failed to send invite email to {player_data.email}")

    return player_data.temp_uid, new_user, True


def _remap_uids_in_tournament(tournament_data: dict, uid_map: dict[str, str]) -> dict:
    """Whole-JSON byte replace of every temp_uid with its real UID — safe only
    because temp uids are full 36-char UUIDs, limiting substring collisions."""
    raw = msgspec.json.encode(tournament_data)
    for temp_uid, real_uid in uid_map.items():
        raw = raw.replace(temp_uid.encode(), real_uid.encode())
    return msgspec.json.decode(raw)


async def _gate_offline_created_insert(
    current_user: User, tournament_data: dict
) -> None:
    """Gates a tournament the server is inserting for the first time (created
    offline); shared by go_online and sync_offline."""
    if not permissions.can_create_tournament(current_user):
        raise HTTPException(
            status_code=403, detail="Only IC, NC, or Prince can create tournaments"
        )
    if current_user.uid not in (tournament_data.get("organizers_uids") or []):
        raise HTTPException(
            status_code=403,
            detail="Caller is not an organizer of the submitted tournament",
        )
    league_uid = tournament_data.get("league_uid")
    if league_uid:
        league = await get_league_by_uid(league_uid)
        if not league:
            raise HTTPException(status_code=400, detail="League not found")
        if not permissions.can_link_tournament_to_league(current_user, league):
            raise HTTPException(
                status_code=403,
                detail="You don't have permission to attach tournaments to this league",
            )
    # Run for the rejections, not the result.
    _engine_create_tournament(tournament_data, current_user)


@router.post("/{uid}/go-online")
async def go_online(
    uid: str,
    request: GoOnlineRequest,
    current_user: OptionalUser = None,
) -> Response:
    """Bring a tournament back online with full reconciliation."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Cheap, request-only check before any side effects.
    if request.tournament.get("uid") and request.tournament["uid"] != uid:
        raise HTTPException(status_code=400, detail="Tournament UID mismatch")
    request.tournament["uid"] = uid
    # Before the player loop below, not at the convert: a minted account copies
    # this value into its own permission-bearing country field.
    request.tournament["country"] = stored_country(request.tournament.get("country"))

    # Pre-lock gate: authorize before creating any users (save_user/allocate_next_vekn_id).
    # Re-checked authoritatively under the lock below; this unlocked read only fails fast.
    existing = await get_tournament_by_uid(uid)
    if existing:
        if not permissions.is_organizer(current_user, existing):
            raise HTTPException(
                status_code=403, detail="Only organizers can bring a tournament online"
            )
        if not existing.offline_mode:
            raise HTTPException(
                status_code=410,
                detail=(
                    "This tournament is no longer in offline mode — it was unlocked "
                    "by an admin or already brought online. Your offline changes "
                    "cannot be synced; reload to get the current state."
                ),
            )
        if (
            existing.offline_mode
            and existing.offline_device_id != request.device_id
            and not request.force
        ):
            raise HTTPException(
                status_code=409,
                detail="Tournament owned by another device. Use force to override.",
            )
    else:
        # Offline-CREATED tournament — the server first learns of it here, so
        # this insert is a creation.
        await _gate_offline_created_insert(current_user, request.tournament)

    # Resolved OUTSIDE the lock: each resolution may allocate a VEKN ID via its
    # own transaction. A rights-revoke race here only orphans an account (harmless).
    uid_map: dict[str, str] = {}  # temp player UID → resolved user UID
    vekn_remap: dict[
        str, str
    ] = {}  # offline TEMP- vekn → resolved real vekn (deck attribution)
    accounts_created = 0
    for player_data in request.offline_players:
        temp_uid, real_user, created = await _resolve_or_create_offline_player(
            player_data, request.tournament.get("country"), current_user.uid
        )
        uid_map[temp_uid] = real_user.uid
        accounts_created += created
        if (player_data.vekn_id or "").startswith("TEMP-") and real_user.vekn_id:
            vekn_remap[player_data.vekn_id] = real_user.vekn_id

    # Two temps (or a temp + existing player) resolving to the same person would
    # duplicate a participant — fail early rather than auto-merge them.
    final_player_uids = [
        uid_map.get(p.get("user_uid"), p.get("user_uid"))
        for p in request.tournament.get("players", [])
    ]
    dupes = {u for u in final_player_uids if u and final_player_uids.count(u) > 1}
    if dupes:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Offline sync would create {len(dupes)} duplicate participant(s) — "
                "the same person is registered both offline and already in the "
                "tournament. Remove the duplicate registration(s) before going online."
            ),
        )

    # SELECT FOR UPDATE serializes the device-lock check with the save; a missing
    # row upserts within the same tx. Holds only tx_conn — no per-player work.
    async with tournament_transaction(uid) as (tournament, tx_conn):
        # Re-verify authorization + device lock authoritatively under the lock.
        if tournament and not permissions.is_organizer(current_user, tournament):
            raise HTTPException(
                status_code=403, detail="Only organizers can bring a tournament online"
            )
        # No longer offline (force-unlocked, or already online elsewhere): refuse
        # to overwrite. 410 = discard+resync; 409 device-mismatch offers a force override.
        if tournament and not tournament.offline_mode:
            raise HTTPException(
                status_code=410,
                detail=(
                    "This tournament is no longer in offline mode — it was unlocked "
                    "by an admin or already brought online. Your offline changes "
                    "cannot be synced; reload to get the current state."
                ),
            )
        if tournament and tournament.offline_mode:
            if tournament.offline_device_id != request.device_id and not request.force:
                raise HTTPException(
                    status_code=409,
                    detail="Tournament owned by another device. Use force to override.",
                )

        # Preserve original organizers (prevent client from removing them)
        if tournament:
            original_organizers = tournament.organizers_uids or []
            client_organizers = request.tournament.get("organizers_uids", [])
            merged = list(dict.fromkeys(original_organizers + client_organizers))
            request.tournament["organizers_uids"] = merged

            for name in SERVER_OWNED_TOURNAMENT_FIELDS:
                request.tournament[name] = msgspec.to_builtins(
                    getattr(tournament, name)
                )

        tournament_data = request.tournament
        if uid_map:
            tournament_data = _remap_uids_in_tournament(tournament_data, uid_map)

        tournament_data["offline_mode"] = False
        tournament_data["offline_device_id"] = ""
        tournament_data["offline_user_uid"] = ""
        tournament_data["offline_since"] = None
        tournament_data["modified"] = datetime.now(UTC).isoformat()

        updated = msgspec.convert(tournament_data, Tournament)
        updated.modified = datetime.now(UTC)
        _normalize_wall_clock(updated)
        # Offline-issued DQs: assert player state server-side too (belt and braces)
        # — the offline client mirrors the flip, but state gates check-in/StartFinals.
        active_dq_uids = {
            uid_map.get(s.get("user_uid"), s.get("user_uid"))
            for s in request.offline_sanctions
            if s.get("level") == "disqualification"
            and not s.get("lifted_at")
            and not s.get("deleted_at")
        }
        if active_dq_uids:
            for player in updated.players:
                if player.user_uid in active_dq_uids:
                    player.state = PlayerState.DISQUALIFIED
        # A tournament finished offline arrives without a finish date (the
        # engine never stamps it) — use the sync time as the actual end time
        if updated.state == TournamentState.FINISHED and updated.finish is None:
            updated.finish = _wall_clock_now(updated.timezone)
        # Same vekn_results_stale compare as /action, against the locked pre-image —
        # the restore above only carries the flag over, not what the offline session changed.
        if (
            tournament
            and tournament.vekn_pushed_at
            and not updated.vekn_results_stale
            and (
                tournament.winner != updated.winner
                or encoder.encode(tournament.standings)
                != encoder.encode(updated.standings)
                or encoder.encode(tournament.finals) != encoder.encode(updated.finals)
                or encoder.encode(tournament.rounds) != encoder.encode(updated.rounds)
            )
        ):
            updated.vekn_results_stale = True
        # Mints rather than waiting: an offline-created event's VEKN push is the
        # hourly batch's, which stops running entirely at the decommission.
        if not updated.event_code:
            updated.event_code = await resolve_event_code(updated, tx_conn)
        tournament_bd = await save_object(
            ObjectType.TOURNAMENT,
            updated.uid,
            msgspec.to_builtins(updated),
            conn=tx_conn,
        )

        # Saved INSIDE the same transaction as the snapshot: a mid-push connection
        # drop must leave it still offline and retryable, never partially committed.
        pending_bds: list = []
        for sanction_data in request.offline_sanctions:
            sanction = msgspec.convert(sanction_data, Sanction)
            sanction.user_uid = uid_map.get(sanction.user_uid, sanction.user_uid)
            pending_bds.append(
                await save_object_from_model(
                    ObjectType.SANCTION, sanction, conn=tx_conn
                )
            )
        # Attribution is a vekn: a temp player's own-deck attribution is their
        # offline TEMP- vekn; repoint to the resolved real vekn, or drop if unresolved.
        for deck_data in request.offline_decks:
            deck_obj = msgspec.convert(deck_data, DeckObject)
            deck_obj.tournament_uid = uid
            deck_obj.user_uid = uid_map.get(deck_obj.user_uid, deck_obj.user_uid)
            if deck_obj.attribution and deck_obj.attribution.startswith("TEMP-"):
                deck_obj.attribution = vekn_remap.get(deck_obj.attribution)
            bd = await save_object_from_model(ObjectType.DECK, deck_obj, conn=tx_conn)
            bd.org_uids = updated.organizers_uids
            pending_bds.append(bd)

    # --- Transaction committed, row lock released ---
    logger.info(
        f"Tournament {uid} went back online (user={current_user.uid}, remapped={len(uid_map)} players)"
    )

    for bd in pending_bds:
        broadcast_precomputed(bd)

    if request.offline_sanctions:
        # One authoritative recompute over the now-saved sanctions, server-side
        # under the row lock (the offline client already recomputed via WASM).
        from .sanctions import _apply_sanction_to_tournament

        await _apply_sanction_to_tournament(uid)
        # Return the FRESH row: the HTTP response is the initiating device's sole
        # authority (its own SSE frames are suppressed during go-online).
        refreshed = await get_tournament_by_uid(uid)
        if refreshed is not None:
            updated = refreshed

    # Excludes the initiating device: it gets the reconciled tournament in the HTTP
    # response, and an echoed offline_mode=false would race ahead and trip its lost-lock warning.
    broadcast_precomputed(tournament_bd, exclude_device_id=request.device_id)

    _promo_recompute_diff(tournament, updated)

    # Otherwise an event finished offline waits for the next daily recompute
    # (~24h late) — mirror the action route and recompute immediately.
    if updated.state == TournamentState.FINISHED:
        try:
            from ..ratings import (
                rating_category_for_tournament,
                recompute_ratings_for_players,
                recompute_wins,
            )

            player_uids = {p.user_uid for p in updated.players if p.user_uid}
            category = rating_category_for_tournament(updated)
            results = await recompute_ratings_for_players(player_uids, category)
            results += await recompute_wins(player_uids)
            for _user, bd in results:
                broadcast_precomputed(bd)
        except Exception as e:
            logger.error(f"Error recomputing ratings for {uid}: {e}", exc_info=True)
        asyncio.create_task(maybe_submit_twda(updated))

    # Outcome summary closes the loop the go-offline modal opens: each created
    # account is a real coopted VEKN member the organizer should know about.
    summary = {
        "players_matched": len(request.offline_players) - accounts_created,
        "accounts_created": accounts_created,
        "decks_synced": len(request.offline_decks),
        "sanctions_synced": len(request.offline_sanctions),
    }
    return Response(
        content=encoder.encode({"tournament": updated, "summary": summary}),
        media_type="application/json",
    )


class ForceTakeoverRequest(BaseModel):
    device_id: str


@router.post("/{uid}/force-takeover")
async def force_takeover(
    uid: str,
    request: ForceTakeoverRequest,
    current_user: OptionalUser = None,
) -> Response:
    """Transfer offline lock to a new device (any organizer of this tournament)."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    # SELECT FOR UPDATE: serialize the offline-lock get-then-update (TOCTOU)
    async with tournament_transaction(uid) as (tournament, tx_conn):
        if not tournament:
            raise HTTPException(status_code=404, detail="Tournament not found")

        # Same gate as go_offline: the taken-over lock carries the same
        # member-creation power.
        if not permissions.can_take_tournament_offline(current_user, tournament):
            raise HTTPException(
                status_code=403,
                detail="You don't have permission to force-takeover this tournament",
            )

        if not tournament.offline_mode:
            raise HTTPException(
                status_code=400, detail="Tournament is not in offline mode"
            )

        old_device = tournament.offline_device_id
        tournament.offline_device_id = request.device_id
        tournament.offline_user_uid = current_user.uid
        tournament.modified = datetime.now(UTC)

        bd = await save_object(
            ObjectType.TOURNAMENT,
            tournament.uid,
            msgspec.to_builtins(tournament),
            conn=tx_conn,
        )

    logger.info(
        f"Tournament {uid} force-takeover: {old_device} → {request.device_id} by {current_user.uid}"
    )

    broadcast_precomputed(bd)

    return Response(content=encoder.encode(tournament), media_type="application/json")


class SyncOfflineRequest(BaseModel):
    device_id: str
    tournament: dict


@router.post("/{uid}/sync-offline")
async def sync_offline(
    uid: str,
    request: SyncOfflineRequest,
    current_user: OptionalUser = None,
) -> Response:
    """Background data backup for offline tournament. Saves snapshot without unlocking."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    # SELECT FOR UPDATE: serialize device-lock check with the snapshot write (TOCTOU)
    async with tournament_transaction(uid) as (tournament, tx_conn):
        if tournament:
            if not tournament.offline_mode:
                raise HTTPException(
                    status_code=400, detail="Tournament is not in offline mode"
                )

            # offline_device_id is member-visible, so the device-lock check alone
            # would let any member overwrite the snapshot — gate on organizer too.
            if not permissions.is_organizer(current_user, tournament):
                raise HTTPException(
                    status_code=403,
                    detail="Only organizers can sync an offline tournament",
                )

            if tournament.offline_device_id != request.device_id:
                raise HTTPException(
                    status_code=409, detail="Device does not hold the offline lock"
                )
        else:
            # Offline-CREATED tournament: insert rather than 404 — this backup
            # snapshot IS the crash insurance offline creation exists for.
            await _gate_offline_created_insert(current_user, request.tournament)

        # Pin the write to the locked row: the FOR UPDATE lock and device-lock
        # check are keyed on the URL uid, so the snapshot must save there too.
        if request.tournament.get("uid") and request.tournament["uid"] != uid:
            raise HTTPException(status_code=400, detail="Tournament UID mismatch")
        request.tournament["uid"] = uid

        tournament_data = request.tournament
        tournament_data["country"] = stored_country(tournament_data.get("country"))
        tournament_data["offline_mode"] = True
        if tournament:
            tournament_data["offline_device_id"] = tournament.offline_device_id
            tournament_data["offline_user_uid"] = tournament.offline_user_uid
            if tournament.offline_since:
                tournament_data["offline_since"] = tournament.offline_since.isoformat()
            # Server-only bookkeeping: keep the DB row authoritative during the
            # offline window (the snapshot never carries a fresher value).
            tournament_data["twda_status"] = (
                msgspec.to_builtins(tournament.twda_status)
                if tournament.twda_status
                else None
            )
        else:
            # Insert: no server-side lock fields to preserve — the snapshot stays
            # locked to the device that created it offline.
            tournament_data["offline_device_id"] = request.device_id
            tournament_data["offline_user_uid"] = current_user.uid
            if not tournament_data.get("offline_since"):
                tournament_data["offline_since"] = datetime.now(UTC).isoformat()
        tournament_data["modified"] = datetime.now(UTC).isoformat()

        updated = msgspec.convert(tournament_data, Tournament)
        updated.modified = datetime.now(UTC)
        _normalize_wall_clock(updated)
        await save_object(
            ObjectType.TOURNAMENT,
            updated.uid,
            msgspec.to_builtins(updated),
            conn=tx_conn,
        )

    now = datetime.now(UTC)
    logger.info(f"Tournament {uid} offline sync from device {request.device_id}")

    _promo_recompute_diff(tournament, updated)

    return Response(
        content=encoder.encode({"synced_at": now.isoformat()}),
        media_type="application/json",
    )


@router.post("/{uid}/force-unlock")
async def force_unlock(
    uid: str,
    request: Request,
    current_user: OptionalUser = None,
) -> Response:
    """IC-only emergency unlock. Clears offline mode entirely."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    # First-party IC sessions only — an OAuth token must not discard another
    # organizer's offline work; get_current_user stamps oauth_client_id to detect one.
    if getattr(request.state, "oauth_client_id", None):
        raise HTTPException(
            status_code=403, detail="OAuth tokens cannot force-unlock tournaments"
        )

    if not permissions.can_force_unlock_tournament(current_user):
        raise HTTPException(
            status_code=403, detail="Only IC can force-unlock tournaments"
        )

    # SELECT FOR UPDATE: serialize the offline-lock get-then-update (TOCTOU)
    async with tournament_transaction(uid) as (tournament, tx_conn):
        if not tournament:
            raise HTTPException(status_code=404, detail="Tournament not found")

        if not tournament.offline_mode:
            raise HTTPException(
                status_code=400, detail="Tournament is not in offline mode"
            )

        tournament.offline_mode = False
        tournament.offline_device_id = ""
        tournament.offline_user_uid = ""
        tournament.offline_since = None
        tournament.modified = datetime.now(UTC)

        bd = await save_object(
            ObjectType.TOURNAMENT,
            tournament.uid,
            msgspec.to_builtins(tournament),
            conn=tx_conn,
        )

    logger.info(f"Tournament {uid} force-unlocked by IC {current_user.uid}")

    broadcast_precomputed(bd)

    return Response(content=encoder.encode(tournament), media_type="application/json")
