"""SSE subscription per organizer for real-time tournament state changes."""

import asyncio
import base64
import binascii
import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime

import aiohttp

from . import config
from .announcements import (
    format_announcement,
    format_finals,
    format_round_seating,
    format_sanction,
    format_standings,
    format_table_result,
    format_timer_reminder,
    player_display,
)
from .channel_manager import (
    create_round_voice_channel,
    delete_channels,
    desired_channels,
    member_override_ids,
    round_channels_by_name,
    structure_signature,
    sync_table_permissions,
)
from .scheduled_events import ensure_scheduled_event, event_signature
from .token_store import TokenStore

logger = logging.getLogger(__name__)

# Hard cap on how long a single SSE event may take to handle. Handlers do
# blocking Discord REST work (posting messages, creating voice channels); if one
# stalls on an un-timed-out await, processing events INLINE in the read loop
# would freeze stream consumption indefinitely (the listener goes silent — no
# error, no reconnect, since sock_read never fires while stuck in a handler).
# Bounding each dispatch turns a permanent wedge into a logged, recoverable skip;
# any side-effect missed on a skip is repaired by reconcile on the next sync.
_DISPATCH_TIMEOUT = 90


def _access_token_expired(token: str, *, skew_seconds: int = 60) -> bool:
    """Decode the UNVERIFIED JWT payload (the bot holds no signing secret) to read
    ``exp``. True if it expires within ``skew_seconds`` or can't be parsed, so the
    caller refreshes before connecting rather than after a 401.
    """
    try:
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)  # restore base64 padding
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return float(payload["exp"]) - time.time() <= skew_seconds
    except (IndexError, KeyError, ValueError, binascii.Error, json.JSONDecodeError):
        return True


# Track active SSE tasks: guild_id+tournament_uid → asyncio.Task
_sse_tasks: dict[str, asyncio.Task] = {}

# key → table/finals voice channel ids in desired order. Written by
# reconcile_channels; read by the announcement layer to route sanctions/scores.
_table_channels: dict[str, list[int]] = defaultdict(list)

# key → the previous tournament snapshot: announcements diff against it and the
# reconcile guard hashes it. Seeded silently at catch-up, popped in stop_sse.
_last_tournament: dict[str, dict] = {}

# key → lock serializing all structural mutation (live/reconnect reconcile, /sync,
# /teardown). NOT popped in stop_sse: popping mid-hold would hand a waiter a fresh
# lock, and a torn-down link makes every holder no-op after its re-read anyway.
_structural_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

# Cache participant identities (uid → {"name", "nickname"}) per tournament,
# seeded from `user` SSE events (the scoped stream now pushes the tournament's
# participants alongside the tournament object). Lets seating/standings resolve a
# name for players not linked to Discord. Popped in stop_sse.
_user_names: dict[str, dict[str, dict]] = defaultdict(dict)


# key → pending asyncio.Task for scheduled round-timer reminders. Cancelled and
# rebuilt whenever the timer signature changes (start/pause/resume/extra-time/round
# change) and after a reconnect's catch-up. Cleared in stop_sse.
_timer_tasks: dict[str, list[asyncio.Task]] = defaultdict(list)

# key → reminder tokens (round_tag, table_index, threshold) already posted, so a
# reschedule (re-broadcast, added extra time, reconnect) never double-fires. Reset
# when the round_tag changes (a new round has fresh thresholds). Cleared in stop_sse.
# The check-then-add in _fire_timer_reminder is unlocked: it relies on SSE dispatch
# being serial (one event handled at a time) — parallelizing handlers would need a lock.
_timer_fired: dict[str, set] = defaultdict(set)

# key → the round_tag _timer_fired currently belongs to; a change resets the set.
_timer_round_tag: dict[str, str] = {}


def _cache_user_identity(key: str, user_obj: dict) -> None:
    """Record a participant's display identity from a `user` SSE event."""
    uid = user_obj.get("uid")
    if uid:
        _user_names[key][uid] = {
            "name": user_obj.get("name"),
            "nickname": user_obj.get("nickname"),
        }


def _task_key(guild_id: str, tournament_uid: str) -> str:
    return f"{guild_id}:{tournament_uid}"


def structural_lock(guild_id: str, tournament_uid: str) -> asyncio.Lock:
    """Per-tournament lock every structural-mutation path holds (reconcile from a
    live event or reconnect, /sync, /teardown) so they never interleave."""
    return _structural_locks[_task_key(guild_id, tournament_uid)]


def find_player_table(
    guild_id: str, tournament_uid: str, player_uid: str
) -> tuple[int, int] | None:
    """Find a player's (round_index, table_index) from cached tournament data.

    Returns None if not found or no active round.
    """
    key = _task_key(guild_id, tournament_uid)
    tournament = _last_tournament.get(key)
    if not tournament:
        return None

    state = tournament.get("state", "")
    if state != "Playing":
        return None

    rounds = tournament.get("rounds", [])
    if not rounds:
        return None

    # Check latest round first
    round_idx = len(rounds) - 1
    for ti, table in enumerate(rounds[round_idx]):
        seating = table.get("seating", [])
        if any(s.get("player_uid") == player_uid for s in seating):
            return (round_idx, ti)

    # Check finals (round index = len(rounds))
    finals = tournament.get("finals")
    if finals and not finals.get("result"):
        seating = finals.get("seating", [])
        if any(s.get("player_uid") == player_uid for s in seating):
            return (len(rounds), 0)

    return None


async def start_sse(
    bot,
    api,  # shared ArchonAPI instance
    store: TokenStore,
    guild_id: str,
    tournament_uid: str,
    organizer_discord_id: str,
) -> None:
    """Start an SSE listener for a tournament using the organizer's token."""
    key = _task_key(guild_id, tournament_uid)
    if key in _sse_tasks and not _sse_tasks[key].done():
        return  # Already listening

    task = asyncio.create_task(
        _sse_loop(bot, api, store, guild_id, tournament_uid, organizer_discord_id)
    )
    _sse_tasks[key] = task


def tracked_table_channels(guild_id: str, tournament_uid: str) -> list[int]:
    """Snapshot the table/finals voice channels currently tracked for a tournament.

    ``/teardown`` passes these to ``teardown_tournament`` so it also deletes
    channels that have drifted out of the category (which the category scan would
    miss). Returns a copy; call it BEFORE ``stop_sse``, which clears the map.
    """
    return [
        c for c in _table_channels.get(_task_key(guild_id, tournament_uid), []) if c
    ]


async def stop_sse(guild_id: str, tournament_uid: str) -> None:
    """Stop SSE listener for a tournament and clean up all cached state."""
    key = _task_key(guild_id, tournament_uid)
    task = _sse_tasks.pop(key, None)
    if task and not task.done():
        task.cancel()
    _table_channels.pop(key, None)
    _last_tournament.pop(key, None)
    _user_names.pop(key, None)
    _cancel_timer_tasks(key)
    _timer_tasks.pop(key, None)
    _timer_fired.pop(key, None)
    _timer_round_tag.pop(key, None)
    # _structural_locks intentionally NOT popped — see structural_lock.


async def _sse_loop(
    bot,
    api,  # shared ArchonAPI instance
    store: TokenStore,
    guild_id: str,
    tournament_uid: str,
    organizer_discord_id: str,
) -> None:
    """Long-running SSE connection that reacts to tournament state changes.

    Uses a single aiohttp session for the lifetime of the loop, reused across
    all reconnections. The session is scoped to this task.
    """
    key = _task_key(guild_id, tournament_uid)
    retry_delay = 1

    async with aiohttp.ClientSession() as session:
        while True:
            tokens = await store.get_tokens(organizer_discord_id)
            if not tokens:
                logger.warning(
                    "No tokens for organizer %s, stopping SSE", organizer_discord_id
                )
                return

            # Refresh up front if the stored token expired while we were down, so
            # the first connect doesn't 401.
            if _access_token_expired(tokens["access_token"]):
                refreshed = await api.refresh_tokens(
                    organizer_discord_id,
                    stale_access_token=tokens["access_token"],
                )
                if refreshed:
                    tokens = refreshed
                # else fall through: the 401 handler below refreshes.

            try:
                headers = {"Authorization": f"Bearer {tokens['access_token']}"}
                async with session.get(
                    f"{config.ARCHON_URL}/stream",
                    # Tournament-scoped: the backend streams only this
                    # tournament + its sanctions + judge calls, not the whole
                    # corpus (which overflowed aiohttp's 512KB line limit).
                    params={"tournament": tournament_uid},
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=None, sock_read=300),
                ) as resp:
                    if resp.status == 401:
                        refreshed = await api.refresh_tokens(
                            organizer_discord_id,
                            stale_access_token=tokens["access_token"],
                        )
                        if not refreshed:
                            logger.error("Token refresh failed for SSE, stopping")
                            return
                        # Fresh token: retry at once (token renewal is one-shot,
                        # not a failure to back off from).
                        continue

                    if resp.status != 200:
                        logger.error("SSE connection failed: %s", resp.status)
                    else:
                        logger.info(
                            "SSE connected for guild=%s tournament=%s",
                            guild_id,
                            tournament_uid,
                        )

                        # The backend sends no `event:` field — every message is a
                        # single `data: {"type":...}` line, so we dispatch on the
                        # payload `type`, never on an SSE event name. `synced` flips
                        # at `sync_complete`; before that we only seed state (no
                        # announcements) so the catch-up replay doesn't spam.
                        synced = False
                        data_lines: list[str] = []

                        async for line_bytes in resp.content:
                            line = line_bytes.decode("utf-8").rstrip("\n\r")

                            if line.startswith("data:"):
                                data_lines.append(line[5:].strip())
                            elif line == "":
                                if not data_lines:
                                    continue
                                data_str = "\n".join(data_lines)
                                data_lines = []
                                try:
                                    data = json.loads(data_str)
                                except json.JSONDecodeError:
                                    logger.warning(
                                        "Unparseable SSE data: %s", data_str[:200]
                                    )
                                    continue

                                if data.get("type") == "resync":
                                    # Server wants a clean re-sync. Reconnect for
                                    # a fresh scoped catch-up (the bot sends no
                                    # `since`, so a reconnect always replays the
                                    # tournament's full current state).
                                    logger.info(
                                        "Resync requested, reconnecting SSE for %s",
                                        key,
                                    )
                                    break

                                was_synced = synced
                                try:
                                    synced = await asyncio.wait_for(
                                        _dispatch_event(
                                            bot,
                                            store,
                                            guild_id,
                                            tournament_uid,
                                            data,
                                            synced,
                                        ),
                                        timeout=_DISPATCH_TIMEOUT,
                                    )
                                except TimeoutError:
                                    # The connection is fine — only the handler
                                    # stalled. Log and keep reading so one slow
                                    # Discord call can't wedge the whole stream;
                                    # reconcile repairs any missed side-effect.
                                    logger.error(
                                        "Timed out (%ds) handling SSE %s for %s; "
                                        "skipping to keep the stream flowing",
                                        _DISPATCH_TIMEOUT,
                                        data.get("type"),
                                        key,
                                    )
                                # Catch-up just completed: reconcile Discord to the
                                # current tournament state (create round channels
                                # missed while we were disconnected). Bounded
                                # separately so a slow reconcile can't unset
                                # `synced` and silence live announcements.
                                if synced and not was_synced:
                                    logger.info(
                                        "SSE catch-up complete for %s; now live, "
                                        "reconciling Discord state",
                                        key,
                                    )
                                    try:
                                        await asyncio.wait_for(
                                            _reconcile(
                                                bot,
                                                store,
                                                guild_id,
                                                tournament_uid,
                                            ),
                                            timeout=_DISPATCH_TIMEOUT,
                                        )
                                    except TimeoutError:
                                        logger.error("Reconcile timed out for %s", key)
                                    except Exception as e:
                                        logger.error("Reconcile failed: %s", e)
                                # A completed catch-up proves the connection
                                # works, so reset backoff for a prompt reconnect.
                                # Reset only on a *healthy* sync — NOT right after
                                # the 200 — so a connection that fails mid-read
                                # (e.g. an oversized catch-up frame) keeps backing
                                # off instead of hammering /stream once per second.
                                if synced:
                                    retry_delay = 1
                            # `:`-comment lines (": connected"/": keepalive") ignored

            except asyncio.CancelledError:
                logger.info("SSE listener cancelled for %s; stopping", key)
                return
            except Exception as e:
                logger.error("SSE error for %s: %s", key, e)

            # Back off before every reconnect (clean EOF, non-200, resync, or
            # error). Reset to 1 above only after a healthy sync. This line is
            # the single observable proof the listener is still alive and will
            # reconnect — if it stops appearing, the loop is wedged.
            logger.info(
                "SSE disconnected for %s; reconnecting in %ds", key, retry_delay
            )
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 60)


def _normalize_events(data: dict) -> list[dict]:
    """Flatten one SSE message into a list of singular ``{type, data}`` events.

    Catch-up and personal-overlay phases send plural arrays
    (``{"type":"tournaments","data":[...]}``); the live phase sends singular
    objects (``{"type":"tournament","data":{...}}``). Returns singular-typed
    events uniformly either way (``users``→``user``, ``sanctions``→``sanction``).
    """
    msg_type = data.get("type", "")
    payload = data.get("data")
    if isinstance(payload, list):
        singular = msg_type[:-1] if msg_type.endswith("s") else msg_type
        return [{"type": singular, "data": obj} for obj in payload]
    return [{"type": msg_type, "data": payload}]


async def _dispatch_event(
    bot,
    store: TokenStore,
    guild_id: str,
    tournament_uid: str,
    data: dict,
    synced: bool,
) -> bool:
    """Route one parsed SSE message; return the updated ``synced`` flag.

    Until ``sync_complete`` arrives we only seed state (no announcements) so a
    (re)connect's catch-up replay doesn't spam every past transition into the
    channels. After it, tournament/sanction objects drive live announcements.
    """
    msg_type = data.get("type", "")
    key = _task_key(guild_id, tournament_uid)

    if msg_type == "sync_complete":
        return True
    if msg_type == "judge_call":
        logger.info("SSE recv judge_call for %s", key)
        await _handle_judge_call(
            bot, store, guild_id, tournament_uid, data.get("data") or {}
        )
        return synced

    events = _normalize_events(data)

    if not synced:
        # Catch-up / overlay: seed tournament state, post nothing.
        logger.info("SSE catch-up: seeding %d object(s) for %s", len(events), key)
        _handle_snapshot(key, tournament_uid, events)
        return synced

    for ev in events:
        logger.info("SSE recv live %s for %s", ev.get("type"), key)
        await _handle_update(bot, store, guild_id, tournament_uid, ev)
    return synced


def _handle_snapshot(key: str, tournament_uid: str, data: dict | list) -> None:
    """Seed the previous-state snapshot from catch-up without posting anything.

    Catch-up replays the tournament's full current state; recording it silently
    means the next live event diffs against where we actually are (no spam), and a
    reconnect's reconcile reads it to repair channels.
    """
    items = data if isinstance(data, list) else [data]
    for item in items:
        obj = item.get("data", item)
        if item.get("type") == "user":
            _cache_user_identity(key, obj)
            continue
        if item.get("type") != "tournament" or obj.get("uid") != tournament_uid:
            continue
        _last_tournament[key] = obj
        logger.info(
            "Snapshot: state=%s rounds=%d for %s",
            obj.get("state", ""),
            len(obj.get("rounds", [])),
            key,
        )


async def _post(bot, channel_id: int, content: str) -> None:
    """Post a message to a channel, logging failures.

    Logs before AND after the Discord call: a "→ create_message" with no
    matching "✓" pins a hung/slow REST call (the listener-wedge failure mode) to the exact
    channel, since the bot has no CI and we debug from logs.
    """
    logger.info("→ create_message channel=%s (%d chars)", channel_id, len(content))
    try:
        await bot.rest.create_message(channel_id, content)
        logger.info("✓ create_message channel=%s", channel_id)
    except Exception as e:
        logger.warning("Failed to post to channel %s: %s", channel_id, e)


def _extract_round_seating(tournament: dict) -> list[set[str]] | None:
    """Extract current round seating as list of player UID sets per table.

    Returns None if no active round.
    """
    rounds = tournament.get("rounds", [])
    if not rounds:
        return None
    current_round = rounds[-1]
    result = []
    for table in current_round:
        seating = table.get("seating", [])
        result.append({s.get("player_uid", "") for s in seating})
    return result


def _seat_results(table: dict) -> dict[str, tuple]:
    """Map each seated player UID → its (gw, vp, tp) score tuple for diffing."""
    out: dict[str, tuple] = {}
    for s in table.get("seating", []):
        r = s.get("result") or {}
        out[s.get("player_uid", "")] = (r.get("gw", 0), r.get("vp", 0), r.get("tp", 0))
    return out


def _active_tables(obj: dict) -> tuple[str, list[dict]]:
    """The tables whose voice channels are currently live in ``_table_channels``:
    finals if seated, otherwise the latest round. The returned tag identifies the
    context (``finals`` / ``round<N>``) so a round-change or prelim→finals
    transition is never mistaken for a score being reported.
    """
    finals = obj.get("finals") or {}
    if finals.get("seating"):
        return "finals", [finals]
    rounds = obj.get("rounds", [])
    if rounds:
        return f"round{len(rounds)}", rounds[-1]
    return "", []


def compute_result_announcements(
    prev_obj: dict,
    cur_obj: dict,
    table_chs: list[int],
    players: list,
    user_names: dict | None = None,
) -> list[tuple[int, str]]:
    """Pure: which table channels to notify of a reported score, and with what.

    A table is announced when its seating is unchanged (same players) but a
    reported score differs from the previous tournament snapshot — i.e. someone
    entered or edited VPs. Skips:
      - context changes (new round / finals start): tag mismatch — those have
        their own seating announcement;
      - seating swaps (different players at a position): handled elsewhere;
      - no-op pushes (sanctions, check-ins, …) that left scores untouched.
    Returns ``[(channel_id, message), …]`` index-aligned to ``table_chs``.
    """
    cur_tag, cur_tables = _active_tables(cur_obj)
    prev_tag, prev_tables = _active_tables(prev_obj)
    if not cur_tag or cur_tag != prev_tag:
        return []
    is_finals = cur_tag == "finals"
    out: list[tuple[int, str]] = []
    # Positional alignment: cur_tables[i] ↔ table_chs[i]. Safe because the engine
    # never reorders existing tables within a round; a mid-round table ADD only
    # appends (i ≥ len(prev_tables) is clamped out — a fresh table has no prior
    # score to diff), and a remove shrinks both lists from the tail.
    for i, table in enumerate(cur_tables):
        # `not table_chs[i]` skips a 0 sentinel left by a failed reconcile create.
        if i >= len(table_chs) or i >= len(prev_tables) or not table_chs[i]:
            continue
        cur_res = _seat_results(table)
        prev_res = _seat_results(prev_tables[i])
        if set(cur_res) != set(prev_res) or cur_res == prev_res:
            continue
        out.append(
            (
                table_chs[i],
                format_table_result(
                    i, table, players, is_finals=is_finals, user_names=user_names
                ),
            )
        )
    return out


def compute_announcement_posts(
    prev_obj: dict | None, cur_obj: dict
) -> list[tuple[str, str]]:
    """Pure: organizer in-app announcements to mirror to Discord, in list order.

    Diffs the tournament's append-only ``announcements`` list (newest last, capped
    at 20) by ``id``: any id present in cur but not prev is new. Returns
    ``[(id, message), …]``. Returns ``[]`` when ``prev_obj`` is None — catch-up
    seeds the snapshot silently, so a (re)connect never re-posts the backlog (the
    idempotency-across-restart guard the ticket calls for).
    """
    if prev_obj is None:
        return []
    prev_ids = {a.get("id") for a in (prev_obj.get("announcements") or [])}
    out: list[tuple[str, str]] = []
    for a in cur_obj.get("announcements") or []:
        aid = a.get("id")
        if not aid or aid in prev_ids:
            continue
        body = (a.get("body") or "").strip()
        if body:
            out.append((aid, format_announcement(body)))
    return out


# Terminal table states: play has stopped (result reported, voided, or finalized).
# There is no top-level ``result`` field on a table (only per-seat ``result``), so
# state + override is the only completion signal.
_TABLE_DONE_STATES = {"Finished", "Invalid", "Cancelled"}


def _table_pending(table: dict) -> bool:
    """A table still being played — the only kind that wants a timer reminder.

    Anything with a reported/voided/judge-finalized result (``Finished`` /
    ``Invalid`` / ``Cancelled`` or an ``override``) has stopped play, so a
    "15 minutes left" or "Time!" post would just be noise. An unset state
    defaults to pending.
    """
    return table.get("state") not in _TABLE_DONE_STATES and not table.get("override")


def _live_round_count(obj: dict) -> int:
    """Prelim rounds with at least one table still in play — the parallel-round gauge."""
    return sum(1 for r in obj.get("rounds", []) if any(_table_pending(t) for t in r))


# Reminders fire at these many seconds of remaining time, per table: 15-minute and
# 5-minute warnings, then the time-up post. Ordered longest-first for readability.
_TIMER_THRESHOLDS = (900, 300, 0)


@dataclass(frozen=True)
class TimerReminder:
    """One scheduled timer post: where, the dedup token, the delay, the text."""

    channel_id: int
    token: tuple
    delay: float  # wall-clock seconds from `now`; ≤0 means the threshold has passed
    message: str


def _parse_started_at_epoch(started_at: str | None) -> float | None:
    """Parse the timer's ISO ``started_at`` to a UTC epoch (seconds), or None.

    msgspec serializes ``datetime.now(UTC)`` as an offset-aware ISO string; a bare
    ``Z`` and naive strings are handled defensively (naive ⇒ assume UTC).
    """
    if not started_at:
        return None
    try:
        dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.timestamp() if dt.tzinfo else dt.replace(tzinfo=UTC).timestamp()


def compute_timer_reminders(
    obj: dict, table_chs: list[int], now: float
) -> list[TimerReminder]:
    """Pure: the per-table timer reminders to schedule, given ``now`` (UTC epoch).

    Mirrors the frontend countdown exactly (TimerDisplay.svelte): per table,
    ``remaining = total - (elapsed_before_pause + (now - started_at)) + extra``,
    where ``total`` is ``finals_time or round_time`` for finals else ``round_time``.
    A reminder's ``delay`` is when that table hits the threshold, in wall-clock
    seconds from ``now``; the caller suppresses any ``delay ≤ 0`` (already passed)
    so a reconnect/restart never posts a stale reminder.

    Returns ``[]`` when no clock is running: not Playing, no ``round_time`` set,
    paused, or no ``started_at`` — i.e. nothing to count down to.
    """
    if obj.get("state", "") != "Playing":
        return []
    timer = obj.get("timer") or {}
    if timer.get("paused"):
        return []
    started_epoch = _parse_started_at_epoch(timer.get("started_at"))
    if started_epoch is None:
        return []

    tag, tables = _active_tables(obj)
    if not tag:
        return []
    is_finals = tag == "finals"
    # Deactivate the timer during parallel rounds: it tracks one shared clock, which
    # is meaningless once >1 prelim round is live (self-organized pods each push their
    # own round). Mirrors the frontend, which hides the timer in the same case.
    if not is_finals and _live_round_count(obj) > 1:
        return []
    total = (
        (obj.get("finals_time") or obj.get("round_time") or 0)
        if is_finals
        else (obj.get("round_time") or 0)
    )
    if total <= 0:
        return []

    elapsed_before = float(timer.get("elapsed_before_pause") or 0.0)
    extra_map = obj.get("table_extra_time") or {}
    out: list[TimerReminder] = []
    for i, table in enumerate(tables):
        if i >= len(table_chs) or not table_chs[i]:  # skip 0 sentinel / missing
            continue
        if not _table_pending(table):
            # Only tables still in play want a reminder. A table with a reported,
            # voided, or judge-finalized result has stopped — and a finished finals
            # (seating still populated) would otherwise keep a stale "Time!"
            # scheduled until the tournament is formally finalized.
            continue
        extra = extra_map.get(str(i), 0)
        deadline = started_epoch + total + extra - elapsed_before
        label = "Finals" if is_finals else f"Table {i + 1}"
        for thr in _TIMER_THRESHOLDS:
            out.append(
                TimerReminder(
                    channel_id=table_chs[i],
                    token=(tag, i, thr),
                    delay=(deadline - thr) - now,
                    message=format_timer_reminder(label, thr),
                )
            )
    return out


def _timer_signature(obj: dict) -> tuple:
    """Cheap digest of the timer-affecting fields — the reschedule guard.

    Equal between two snapshots ⇒ the schedule still holds (skips score/sanction
    churn). The active-tables ``tag`` flips on a round change or prelim→finals; the
    per-table pending flags flip when a table finishes early (so its reminder is
    cancelled); the extra-time map flips when an extension pushes a deadline out.
    """
    timer = obj.get("timer") or {}
    tag, tables = _active_tables(obj)
    return (
        obj.get("state"),
        obj.get("round_time") or 0,
        obj.get("finals_time") or 0,
        tag,
        _live_round_count(obj),  # flips the schedule on/off across a parallel boundary
        tuple(_table_pending(t) for t in tables),
        timer.get("started_at"),
        bool(timer.get("paused")),
        timer.get("elapsed_before_pause"),
        tuple(sorted((obj.get("table_extra_time") or {}).items())),
    )


def _cancel_timer_tasks(key: str) -> None:
    """Cancel and drop all pending timer reminders for a tournament."""
    for t in _timer_tasks.get(key, []):
        if not t.done():
            t.cancel()
    _timer_tasks[key] = []


async def _fire_timer_reminder(bot, key: str, reminder: TimerReminder) -> None:
    """Sleep until a reminder's threshold, then post it once.

    Cancellation (a reschedule supersedes this one) returns silently. The fired
    set guards the narrow window where this posts just as a reschedule recomputes.
    """
    try:
        await asyncio.sleep(reminder.delay)
    except asyncio.CancelledError:
        return
    if reminder.token in _timer_fired[key]:
        return
    _timer_fired[key].add(reminder.token)
    await _post(bot, reminder.channel_id, reminder.message)


async def _reschedule_timers(
    bot, guild_id: str, tournament_uid: str, obj: dict
) -> None:
    """Rebuild a tournament's timer reminders from the current snapshot.

    Idempotent and the single authority for the schedule: cancels everything
    pending, then re-schedules each future threshold not already fired. A passed
    threshold (``delay ≤ 0``) is marked fired WITHOUT posting — that suppresses
    stale reminders on reconnect/restart. Reads the live table voice channels from
    ``_table_channels`` (populated by reconcile), so reminders land in the same
    per-table chats as score posts.
    """
    key = _task_key(guild_id, tournament_uid)
    _cancel_timer_tasks(key)

    # A new round/finals has fresh thresholds — drop the prior round's fired set.
    tag, _ = _active_tables(obj)
    if _timer_round_tag.get(key) != tag:
        _timer_round_tag[key] = tag
        _timer_fired[key] = set()

    fired = _timer_fired[key]
    for reminder in compute_timer_reminders(
        obj, _table_channels.get(key, []), time.time()
    ):
        if reminder.token in fired:
            continue
        if reminder.delay <= 0:
            fired.add(reminder.token)  # already passed → suppress, don't post late
            continue
        _timer_tasks[key].append(
            asyncio.create_task(_fire_timer_reminder(bot, key, reminder))
        )
    logger.info(
        "Timer reschedule %s: %d pending (tag=%s)", key, len(_timer_tasks[key]), tag
    )


async def _build_discord_id_map(
    store: TokenStore, archon_uids: set[str]
) -> dict[str, int]:
    """Batch-lookup discord IDs and cast to int."""
    raw = await store.get_discord_ids_by_archon_uids(list(archon_uids))
    return {uid: int(did) for uid, did in raw.items()}


async def _warn_unlinked_players(
    bot,
    judges_id: int,
    player_uids: set[str],
    discord_id_map: dict[str, int],
    players: list,
    user_names: dict | None = None,
) -> None:
    """Post a warning to #judges about seated players without a Discord link."""
    unlinked = player_uids - set(discord_id_map.keys())
    if not unlinked:
        return
    # Unlinked by definition → no mention possible; show the best known name.
    names = [player_display(uid, players, user_names=user_names) for uid in unlinked]
    await _post(
        bot,
        judges_id,
        f"**Warning:** {len(unlinked)} seated player{'s have' if len(unlinked) != 1 else ' has'} "
        f"not linked their Discord account and cannot join voice: {', '.join(names)}. "
        f"Ask them to run `/checkin` in the lobby.",
    )


@dataclass
class ReconcileSummary:
    """What a ``reconcile_channels`` run changed — surfaced by ``/sync``."""

    created: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    synced: list[str] = field(default_factory=list)
    aborted: bool = False


async def reconcile_channels(
    bot,
    store: TokenStore,
    guild_id: str,
    tournament_uid: str,
    obj: dict,
) -> ReconcileSummary:
    """The single idempotent authority for a tournament's round/finals voice channels.

    Drives Discord to ``desired_channels(obj)`` from ONE ``fetch_guild_channels``
    call, diffing by channel NAME (so a timed-out partial create converges without
    duplicates): create the missing, delete the no-longer-desired, perm-sync the
    survivors — threading each survivor's overrides off the payload so
    ``sync_table_permissions`` never re-fetches per channel. Writes
    ``_table_channels`` in desired order for the announcement layer.

    An empty desired set (non-Playing, or a finished finals) deletes everything —
    that IS round-close cleanup.

    Callers MUST hold ``structural_lock``; the link is re-read here (teardown may
    have removed it while we waited) and a missing link no-ops. v1 reconciles only
    the volatile round/finals channels — never the category/text channels — but
    aborts and warns #judges if the category itself is gone, rather than recreate
    an unparented mess.
    """
    key = _task_key(guild_id, tournament_uid)
    link = await store.get_tournament_link(guild_id, tournament_uid)
    if not link:
        return ReconcileSummary()

    category_id = int(link["category_id"])
    judges_id = int(link["judges_channel_id"])

    desired = desired_channels(obj)
    channels = await bot.rest.fetch_guild_channels(int(guild_id))

    if not any(int(ch.id) == category_id for ch in channels):
        logger.error(
            "Reconcile %s: category %s is gone — aborting (won't recreate)",
            key,
            category_id,
        )
        await _post(
            bot,
            judges_id,
            "**Channel sync aborted:** the tournament category was deleted, so I "
            "can't place voice channels. Recreate it, or run `/teardown` then "
            "`/setup` again.",
        )
        return ReconcileSummary(aborted=True)

    current = round_channels_by_name(channels, category_id)
    desired_by_name = {dc.name: dc for dc in desired}

    all_member_uids: set[str] = set()
    for dc in desired:
        all_member_uids |= dc.member_uids
    discord_id_map = await _build_discord_id_map(store, all_member_uids)

    summary = ReconcileSummary()

    # No longer desired: closed round, prelim tables under finals, stale round prefix.
    extra = [ch for name, ch in current.items() if name not in desired_by_name]
    if extra:
        await delete_channels(bot, [int(ch.id) for ch in extra])
        summary.deleted = [ch.name for ch in extra]

    name_to_id: dict[str, int] = {}
    for dc in desired:
        ch = current.get(dc.name)
        if ch is None:
            try:
                name_to_id[dc.name] = await create_round_voice_channel(
                    bot,
                    int(guild_id),
                    category_id,
                    dc.name,
                    dc.member_uids,
                    discord_id_map,
                )
                summary.created.append(dc.name)
            except Exception as e:
                logger.warning("Reconcile %s: create '%s' failed: %s", key, dc.name, e)
        else:
            try:
                await sync_table_permissions(
                    bot,
                    int(guild_id),
                    int(ch.id),
                    set(dc.member_uids),
                    set(),
                    discord_id_map,
                    current_member_ids=member_override_ids(ch),
                )
                summary.synced.append(dc.name)
            except Exception as e:
                logger.warning("Reconcile %s: sync '%s' failed: %s", key, dc.name, e)
            name_to_id[dc.name] = int(ch.id)

    # Positional: index i ↔ desired table i, the contract the announcement layer
    # (score + sanction routing) indexes into. A failed create leaves a 0 sentinel
    # so later tables keep their index instead of shifting; consumers skip 0.
    _table_channels[key] = [name_to_id.get(dc.name, 0) for dc in desired]
    logger.info(
        "Reconcile %s: +%d -%d ~%d (state=%s, %d channels)",
        key,
        len(summary.created),
        len(summary.deleted),
        len(summary.synced),
        obj.get("state", ""),
        len(_table_channels[key]),
    )
    return summary


async def sync_now(
    bot,
    store: TokenStore,
    guild_id: str,
    tournament_uid: str,
) -> ReconcileSummary | None:
    """Reconcile against the cached tournament object, under the structural lock.

    Backs the ``/sync`` command. Returns ``None`` if no tournament state is cached
    yet (the listener is still connecting), else the reconcile summary.
    """
    async with structural_lock(guild_id, tournament_uid):
        obj = _last_tournament.get(_task_key(guild_id, tournament_uid))
        if obj is None:
            return None
        return await reconcile_channels(bot, store, guild_id, tournament_uid, obj)


async def _handle_update(
    bot,
    store: TokenStore,
    guild_id: str,
    tournament_uid: str,
    data: dict,
) -> None:
    """Handle one live SSE update (tournament, sanction, or participant user).

    A tournament event splits in two: the STRUCTURAL half (channels+perms) is
    reconciled only when ``structure_signature`` changes (skipping score-report
    churn); the ANNOUNCEMENT half is edge-triggered off the prev→cur diff.
    """
    obj_type = data.get("type")

    if obj_type == "sanction":
        await _handle_sanction_update(bot, store, guild_id, tournament_uid, data)
        return

    if obj_type == "user":
        # Participant identity pushed alongside the tournament — cache it for name
        # resolution; never announced directly.
        _cache_user_identity(
            _task_key(guild_id, tournament_uid), data.get("data") or {}
        )
        return

    if obj_type != "tournament":
        if obj_type:
            logger.debug("Ignoring SSE update of unknown type: %s", obj_type)
        return

    obj = data.get("data", data)
    if obj.get("uid") != tournament_uid:
        return

    key = _task_key(guild_id, tournament_uid)
    link = await store.get_tournament_link(guild_id, tournament_uid)
    if not link:
        _last_tournament[key] = obj
        return

    prev_obj = _last_tournament.get(key)
    state = obj.get("state", "")
    round_count = len(obj.get("rounds", []))
    logger.info(
        "Tournament update %s: state %s→%s, rounds %d→%d, %d players",
        key,
        (prev_obj or {}).get("state", "(none)"),
        state,
        len((prev_obj or {}).get("rounds", [])),
        round_count,
        len(obj.get("players", [])),
    )

    # Structural half — only when the structure changed (skips score-report churn).
    if structure_signature(prev_obj or {}) != structure_signature(obj):
        async with structural_lock(guild_id, tournament_uid):
            try:
                await reconcile_channels(bot, store, guild_id, tournament_uid, obj)
            except Exception as e:
                logger.error("Reconcile failed for %s: %s", key, e)

    # Announcement half — edge-triggered.
    try:
        await _emit_announcements(
            bot, store, guild_id, tournament_uid, prev_obj, obj, link
        )
    except Exception as e:
        logger.error("Announcement emit failed for %s: %s", key, e)

    # Scheduled-event half — driven off the public-field signature (name/start/
    # finish/banner/state), independent of channel structure. Same structural lock so
    # a concurrent reconcile can't race the stored event id.
    if event_signature(prev_obj or {}) != event_signature(obj):
        async with structural_lock(guild_id, tournament_uid):
            try:
                await ensure_scheduled_event(
                    bot, store, guild_id, tournament_uid, obj, prev_obj
                )
            except Exception as e:
                logger.error("Scheduled-event ensure failed for %s: %s", key, e)

    # Timer half — reschedule per-table round-timer reminders when the timer state
    # changed (start/pause/resume, added extra time, new round). No structural lock:
    # it only touches in-process reminder tasks, never Discord channels. Runs after
    # any structural reconcile above so _table_channels is current.
    if _timer_signature(prev_obj or {}) != _timer_signature(obj):
        try:
            await _reschedule_timers(bot, guild_id, tournament_uid, obj)
        except Exception as e:
            logger.error("Timer reschedule failed for %s: %s", key, e)

    # Snapshot LAST: the diffs above need the previous object; a crash retries next event.
    _last_tournament[key] = obj


async def _emit_announcements(
    bot,
    store: TokenStore,
    guild_id: str,
    tournament_uid: str,
    prev_obj: dict | None,
    obj: dict,
    link: dict,
) -> None:
    """The ANNOUNCEMENT half: edge-triggered posts on the prev→cur diff.

    Deliberately NOT idempotent — each fires once on its transition (re-posting
    seating would be spam). Channel structure/perms are ``reconcile_channels``'s job.
    """
    key = _task_key(guild_id, tournament_uid)
    announcement_id = int(link["announcement_channel_id"])
    lobby_id = int(link["lobby_channel_id"])
    judges_id = int(link["judges_channel_id"])

    prev = prev_obj or {}
    prev_state = prev.get("state", "")
    prev_round_count = len(prev.get("rounds", []))

    state = obj.get("state", "")
    name = obj.get("name", "Tournament")
    webapp_url = f"{config.ARCHON_FRONTEND_URL}/tournaments/{tournament_uid}"
    rounds = obj.get("rounds", [])
    players = obj.get("players", [])
    round_count = len(rounds)

    # ── Registration opened (Planned → Registration) ──
    if state == "Registration" and prev_state != "Registration":
        await _post(
            bot,
            announcement_id,
            f"**Registration is open for {name}!**\n"
            f"Use `/register` in <#{lobby_id}> to sign up.",
        )
        await _post(
            bot,
            lobby_id,
            f"Registration is open! Use `/register` to sign up for **{name}**.",
        )
        await _post(
            bot,
            judges_id,
            f"**{name}** — Registration opened.\nManage tournament: {webapp_url}",
        )

    # ── Check-in opened (Registration → Waiting) ──
    if state == "Waiting" and prev_state == "Registration":
        registered = len(players)
        decklist_note = ""
        if obj.get("decklist_required"):
            decklist_note = (
                f"\nThis tournament requires a decklist — upload yours on the "
                f"webapp: {webapp_url}"
            )

        await _post(
            bot,
            announcement_id,
            f"**Check-in is open for {name}!**\n"
            f"{registered} player{'s' if registered != 1 else ''} registered. "
            f"Use `/checkin` in <#{lobby_id}> to check in.{decklist_note}",
        )
        await _post(
            bot,
            lobby_id,
            f"Check-in is now open! Use `/checkin` to check in for "
            f"**{name}**.{decklist_note}",
        )
        await _post(
            bot,
            judges_id,
            f"**{name}** — Check-in opened ({registered} registered).\n"
            f"Close check-in and start Round 1 from the webapp when ready.\n{webapp_url}",
        )

    # ── Round finished → back to Waiting (channel cleanup is reconcile's job) ──
    if state == "Waiting" and prev_state == "Playing":
        standings = obj.get("standings", [])
        standings_mode = obj.get("standings_mode", "Private")

        lines = [f"**Round {round_count} complete!**"]
        lines.append(
            format_standings(
                standings, standings_mode, players, user_names=_user_names[key]
            )
        )
        lines.append(
            f"\nCheck-in for the next round is open — use `/checkin` in <#{lobby_id}>."
        )
        await _post(bot, announcement_id, "\n".join(lines))

        checked_in = sum(1 for p in players if p.get("state") == "Checked-in")
        await _post(
            bot,
            judges_id,
            f"**{name}** — Round {round_count} finished. "
            f"{checked_in} player{'s' if checked_in != 1 else ''} checked in for next round.\n"
            f"Start next round or finals from the webapp.\n{webapp_url}",
        )

    # ── New round started ──
    if state == "Playing" and round_count > prev_round_count and rounds:
        await _announce_round_seating(bot, store, guild_id, tournament_uid, obj, link)

    # ── Finals started ──
    if obj.get("finals") and state == "Playing" and prev_state != "Playing":
        await _announce_finals(bot, store, guild_id, tournament_uid, obj, link)

    # ── Mid-round seating change (SwapSeats, AlterSeating, AddTable, …) ──
    if (
        state == "Playing"
        and round_count == prev_round_count
        and round_count > 0
        and prev_obj is not None
    ):
        cur_seating = _extract_round_seating(obj)
        prev_seating = _extract_round_seating(prev_obj)
        if (
            cur_seating is not None
            and prev_seating is not None
            and cur_seating != prev_seating
        ):
            await _announce_seating_update(
                bot, store, guild_id, tournament_uid, obj, link
            )

    # ── Score reported at a table (open reporting = anti-cheat visibility) ──
    # A pure score report makes no structural change, so reconcile was skipped and
    # _table_channels still maps the live tables. Gated on Playing — Finished has none.
    if state == "Playing" and prev_obj is not None:
        for ch_id, msg in compute_result_announcements(
            prev_obj, obj, _table_channels.get(key, []), players, _user_names[key]
        ):
            await _post(bot, ch_id, msg)

    # ── Organizer in-app announcements mirrored to the Discord announcement channel ──
    # Diffed by id against the prev snapshot (catch-up seeds it silently, so a
    # reconnect doesn't re-post the backlog). Not state-gated — an organizer can
    # broadcast at any phase.
    for _aid, msg in compute_announcement_posts(prev_obj, obj):
        await _post(bot, announcement_id, msg)

    # ── Tournament finished (channel cleanup is reconcile's job) ──
    if state == "Finished" and prev_state != "Finished":
        standings = obj.get("standings", [])
        winner = obj.get("winner", "")
        standings_mode = obj.get("standings_mode", "Private")

        lines = [f"**{name} is finished!**"]
        if winner:
            winner_name = player_display(winner, players, user_names=_user_names[key])
            lines.append(f"Congratulations to the winner: **{winner_name}**!")

        lines.append(
            format_standings(
                standings, standings_mode, players, user_names=_user_names[key]
            )
        )
        lines.append(f"\nFull results: {webapp_url}")
        lines.append("Thank you all for playing!")
        await _post(bot, announcement_id, "\n".join(lines))

        await _post(
            bot,
            judges_id,
            f"**{name}** — Tournament finished.\n"
            f"Results and VEKN push available on the webapp.\n"
            f"Use `/teardown` when you're ready to remove the tournament channels.\n{webapp_url}",
        )


async def _announce_round_seating(
    bot,
    store: TokenStore,
    guild_id: str,
    tournament_uid: str,
    obj: dict,
    link: dict,
) -> None:
    """Post a new round's seating to #announcement + #judges; warn unlinked players."""
    key = _task_key(guild_id, tournament_uid)
    announcement_id = int(link["announcement_channel_id"])
    judges_id = int(link["judges_channel_id"])
    name = obj.get("name", "Tournament")
    webapp_url = f"{config.ARCHON_FRONTEND_URL}/tournaments/{tournament_uid}"
    players = obj.get("players", [])
    organizer_uids = set(obj.get("organizers_uids", []))
    rounds = obj.get("rounds", [])
    round_count = len(rounds)
    tables_data = [
        [s.get("player_uid", "") for s in table.get("seating", [])]
        for table in rounds[-1]
    ]
    all_player_uids = {uid for table in tables_data for uid in table}
    discord_id_map = await _build_discord_id_map(
        store, all_player_uids | organizer_uids
    )

    await _post(
        bot,
        announcement_id,
        format_round_seating(
            round_count,
            tables_data,
            players,
            discord_id_map=discord_id_map,
            user_names=_user_names[key],
        ),
    )
    await _warn_unlinked_players(
        bot, judges_id, all_player_uids, discord_id_map, players, _user_names[key]
    )
    await _post(
        bot,
        judges_id,
        f"**{name}** — Round {round_count} started ({len(tables_data)} tables, "
        f"{sum(len(t) for t in tables_data)} players).\n"
        f"Use `/sanction @player` to issue sanctions.\n{webapp_url}",
    )


async def _announce_finals(
    bot,
    store: TokenStore,
    guild_id: str,
    tournament_uid: str,
    obj: dict,
    link: dict,
) -> None:
    """Post the finalists to #announcement + #judges; warn unlinked finalists."""
    key = _task_key(guild_id, tournament_uid)
    announcement_id = int(link["announcement_channel_id"])
    judges_id = int(link["judges_channel_id"])
    name = obj.get("name", "Tournament")
    webapp_url = f"{config.ARCHON_FRONTEND_URL}/tournaments/{tournament_uid}"
    players = obj.get("players", [])
    organizer_uids = set(obj.get("organizers_uids", []))
    finals = obj.get("finals") or {}
    seating = finals.get("seating", [])
    if not seating:
        return
    seed_order = finals.get("seed_order", [])
    finalist_uids = {s.get("player_uid", "") for s in seating}
    discord_id_map = await _build_discord_id_map(store, finalist_uids | organizer_uids)

    await _post(
        bot,
        announcement_id,
        format_finals(
            name,
            seating,
            seed_order,
            players,
            discord_id_map=discord_id_map,
            user_names=_user_names[key],
        ),
    )
    await _warn_unlinked_players(
        bot, judges_id, finalist_uids, discord_id_map, players, _user_names[key]
    )
    await _post(
        bot,
        judges_id,
        f"**{name}** — Finals started ({len(seating)} finalists).\n{webapp_url}",
    )


async def _announce_seating_update(
    bot,
    store: TokenStore,
    guild_id: str,
    tournament_uid: str,
    obj: dict,
    link: dict,
) -> None:
    """Post updated mid-round seating to #announcement; warn newly unlinked players."""
    key = _task_key(guild_id, tournament_uid)
    announcement_id = int(link["announcement_channel_id"])
    judges_id = int(link["judges_channel_id"])
    players = obj.get("players", [])
    organizer_uids = set(obj.get("organizers_uids", []))
    rounds = obj.get("rounds", [])
    round_count = len(rounds)
    current_round = rounds[-1]
    all_player_uids = {
        s.get("player_uid", "")
        for table in current_round
        for s in table.get("seating", [])
    }
    discord_id_map = await _build_discord_id_map(
        store, all_player_uids | organizer_uids
    )

    lines = [f"**Seating updated — Round {round_count}**\n"]
    for ti, table in enumerate(current_round):
        seat_names = [
            player_display(
                s.get("player_uid", ""),
                players,
                discord_id_map=discord_id_map,
                user_names=_user_names[key],
                mention=True,
            )
            for s in table.get("seating", [])
        ]
        lines.append(f"**Table {ti + 1}**: {' → '.join(seat_names)}")
    await _post(bot, announcement_id, "\n".join(lines))
    await _warn_unlinked_players(
        bot, judges_id, all_player_uids, discord_id_map, players, _user_names[key]
    )


async def _reconcile(
    bot,
    store: TokenStore,
    guild_id: str,
    tournament_uid: str,
) -> None:
    """Repair channels to the seeded state after a (re)connect's silent catch-up.

    reconcile_channels makes Discord match current state (create missing, delete a
    closed round's, re-adopt existing), so a normal reconnect is silent. STRUCTURAL
    ONLY by design: a seating announcement missed during the disconnect is not
    replayed (it can't be edge-derived without re-spamming every reconnect); the
    voice channels — what players need — are always restored.
    """
    key = _task_key(guild_id, tournament_uid)
    obj = _last_tournament.get(key)
    state = obj.get("state", "") if obj else "(none)"
    logger.info("Reconciling %s after (re)connect (state=%s)", key, state)
    if not obj:
        # Catch-up filters deleted_at IS NULL, so a tournament soft-deleted while the
        # bot was DOWN never reappears here — no ensure runs, and any scheduled event
        # is left for /teardown to remove (the authority for a deleted tournament's
        # Discord cleanup). Narrow window: tournament delete is PLANNED-state only.
        return
    async with structural_lock(guild_id, tournament_uid):
        await reconcile_channels(bot, store, guild_id, tournament_uid, obj)
        # Initial create + restart idempotency: the stored event id survives in
        # SQLite, so ensure no-ops (edits) rather than double-creating.
        try:
            await ensure_scheduled_event(bot, store, guild_id, tournament_uid, obj)
        except Exception as e:
            logger.error("Scheduled-event ensure failed for %s: %s", key, e)

    # Re-arm timer reminders from the seeded snapshot (channels now reconciled): a
    # restart mid-round rebuilds the schedule — passed thresholds are suppressed,
    # still-future ones re-scheduled. No persisted cron; this is the recompute.
    try:
        await _reschedule_timers(bot, guild_id, tournament_uid, obj)
    except Exception as e:
        logger.error("Timer reschedule failed for %s: %s", key, e)


def sanction_table_channel(
    tournament: dict | None, round_number: int, user_uid: str, table_chs: list[int]
) -> int | None:
    """Pure: the table voice channel to notify of a sanction, or None (→ lobby).

    ``table_chs`` maps the LIVE context's channels (reconcile's contract), so a
    sanction routes to a table only when its round IS that context — a past
    round's same-index table would seat strangers, and a live finals replaces
    the prelim channels. Everything else falls back to the lobby.
    """
    if not tournament or not table_chs:
        return None
    tag, live_tables = _active_tables(tournament)
    if tag != f"round{round_number + 1}":
        return None
    for ti, table in enumerate(live_tables):
        if any(s.get("player_uid") == user_uid for s in table.get("seating", [])):
            if ti < len(table_chs) and table_chs[ti]:  # skip 0 sentinel
                return table_chs[ti]
            return None
    return None


async def _handle_sanction_update(
    bot,
    store: TokenStore,
    guild_id: str,
    tournament_uid: str,
    data: dict,
) -> None:
    """Handle a sanction SSE event.

    - Always posts to #judges channel
    - If the sanction targets the live round and the player's table channel
      exists: posts to that table channel
    - Otherwise: posts to #lobby
    """
    obj = data.get("data", data)

    # Only handle sanctions for this tournament
    if obj.get("tournament_uid") != tournament_uid:
        return

    # Skip lifted/deleted sanctions
    if obj.get("lifted_at") or obj.get("deleted_at"):
        return

    link = await store.get_tournament_link(guild_id, tournament_uid)
    if not link:
        return

    judges_id = int(link["judges_channel_id"])
    lobby_id = int(link["lobby_channel_id"])

    level = obj.get("level", "")
    category = obj.get("category", "").replace("_", " ")
    subcategory = obj.get("subcategory", "")
    description = obj.get("description", "")
    round_number = obj.get("round_number")
    user_uid = obj.get("user_uid", "")

    # Try to find the player's Discord mention
    player_discord_id = await store.get_discord_id_by_archon_uid(user_uid)
    player_mention = f"<@{player_discord_id}>" if player_discord_id else user_uid[:8]

    judges_msg, player_msg = format_sanction(
        level, category, subcategory, description, round_number, player_mention
    )

    logger.info(
        "SSE recv sanction (level=%s round=%s) for %s",
        level,
        round_number,
        _task_key(guild_id, tournament_uid),
    )

    # Post to judges channel
    try:
        logger.info("→ create_message sanction→judges channel=%s", judges_id)
        await bot.rest.create_message(judges_id, judges_msg)
    except Exception as e:
        logger.warning("Failed to post sanction to judges: %s", e)

    # Notify the player in the appropriate channel:
    # - If the sanction targets the live round, post to the player's table
    # - Otherwise, post to lobby
    key = _task_key(guild_id, tournament_uid)

    posted_to_table = False
    if round_number is not None:
        target = sanction_table_channel(
            _last_tournament.get(key),
            round_number,
            user_uid,
            _table_channels.get(key, []),
        )
        if target:
            try:
                logger.info("→ create_message sanction→table channel=%s", target)
                await bot.rest.create_message(target, player_msg)
                posted_to_table = True
            except Exception as e:
                logger.warning("Failed to post sanction to table %s: %s", target, e)

    if not posted_to_table:
        # Past-round correction, no live tables, or player not seated — post to lobby
        try:
            logger.info("→ create_message sanction→lobby channel=%s", lobby_id)
            await bot.rest.create_message(lobby_id, player_msg)
        except Exception as e:
            logger.warning("Failed to post sanction to lobby: %s", e)


async def _handle_judge_call(
    bot,
    store: TokenStore,
    guild_id: str,
    tournament_uid: str,
    data: dict,
) -> None:
    """Handle a judge_call ephemeral event.

    ``data`` is the inner payload (``{tournament_uid, table, table_label,
    player_name}``). One organizer token streams judge calls for all their
    tournaments, so filter to this listener's tournament.
    """
    if data.get("tournament_uid") != tournament_uid:
        return

    link = await store.get_tournament_link(guild_id, tournament_uid)
    if not link:
        return

    judges_id = int(link["judges_channel_id"])
    table = data.get("table", "?")
    table_label = data.get("table_label", f"Table {table}")
    player_name = data.get("player_name", "Unknown")

    try:
        logger.info("→ create_message judge_call→judges channel=%s", judges_id)
        await bot.rest.create_message(
            judges_id,
            f"**Judge call!** {table_label} — {player_name} needs a judge",
        )
    except Exception as e:
        logger.warning("Failed to post judge call: %s", e)
