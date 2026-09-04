import asyncio
import base64
import binascii
import json
import logging
import time
from collections import defaultdict
from contextlib import aclosing
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
    format_table_seating,
    format_time_extension,
    format_timer_reminder,
    format_timer_start,
    player_display,
)
from .channel_manager import (
    create_round_voice_channel,
    delete_channels,
    desired_channels,
    member_override_ids,
    round_channels_by_name,
    structure_signature,
    sync_judges_channel,
    sync_table_permissions,
)
from .command_mentions import command_mention
from .scheduled_events import ensure_scheduled_event, event_signature
from .token_store import TokenStore

logger = logging.getLogger(__name__)

# A handler stuck on an un-timed-out await freezes stream consumption silently —
# sock_read never fires while stuck in a handler, so no error, no reconnect.
_DISPATCH_TIMEOUT = 90


def _access_token_expired(token: str, *, skew_seconds: int = 60) -> bool:
    """Decodes the UNVERIFIED JWT payload — the bot holds no signing secret."""
    try:
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)  # restore base64 padding
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return float(payload["exp"]) - time.time() <= skew_seconds
    except (IndexError, KeyError, ValueError, binascii.Error, json.JSONDecodeError):
        return True


# All keyed by guild_id:tournament_uid (_task_key). Written by reconcile_channels,
# read by the announcement layer to route sanctions/scores.
_sse_tasks: dict[str, asyncio.Task] = {}
_table_channels: dict[str, list[int]] = defaultdict(list)

# The previous tournament snapshot: announcements diff against it and the
# reconcile guard hashes it. Seeded silently at catch-up, popped in stop_sse.
_last_tournament: dict[str, dict] = {}

# NOT popped in stop_sse: popping mid-hold would hand a waiter a fresh lock, and
# a torn-down link makes every holder no-op after its re-read anyway.
_structural_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

# Participant identities (uid → {"name", "nickname", "discord_id"}), seeded from
# `user` SSE events, for players/organizers with no Discord link. Popped in stop_sse.
_user_names: dict[str, dict[str, dict]] = defaultdict(dict)

# Organizer uids already flagged in #judges as having no known Discord account,
# so the notice fires once per listener lifetime. Popped in stop_sse.
_warned_unlinked_organizers: dict[str, set[str]] = defaultdict(set)

# Pending timer-reminder tasks; cancelled and rebuilt on every timer-signature
# change and after a reconnect's catch-up. Cleared in stop_sse.
_timer_tasks: dict[str, list[asyncio.Task]] = defaultdict(list)

# Reminder tokens (round_tag, table_index, threshold) already posted, so a
# reschedule never double-fires. The check-then-add in _fire_timer_reminder is
# unlocked: it relies on SSE dispatch being serial. Cleared in stop_sse.
_timer_fired: dict[str, set] = defaultdict(set)

# The round_tag _timer_fired currently belongs to; a change resets the set.
_timer_round_tag: dict[str, str] = {}


def _cache_user_identity(key: str, user_obj: dict) -> None:
    uid = user_obj.get("uid")
    if uid:
        _user_names[key][uid] = {
            "name": user_obj.get("name"),
            "nickname": user_obj.get("nickname"),
            "discord_id": user_obj.get("discord_id"),
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
    key = _task_key(guild_id, tournament_uid)
    tournament = _last_tournament.get(key)
    if not tournament:
        return None

    if tournament.get("state", "") != "Playing":
        return None
    rounds = tournament.get("rounds", [])
    # Finals first: a finalist is still seated in the last preliminary round.
    finals = tournament.get("finals") or {}
    if finals.get("seating"):
        if any(s.get("player_uid") == player_uid for s in finals["seating"]):
            return (len(rounds), 0)
        return None
    if not rounds:
        return None
    round_idx = len(rounds) - 1
    for ti, table in enumerate(rounds[round_idx]):
        if any(s.get("player_uid") == player_uid for s in table.get("seating", [])):
            return (round_idx, ti)
    return None


async def start_sse(
    bot,
    api,
    store: TokenStore,
    guild_id: str,
    tournament_uid: str,
    organizer_discord_id: str,
) -> None:
    key = _task_key(guild_id, tournament_uid)
    if key in _sse_tasks and not _sse_tasks[key].done():
        return

    task = asyncio.create_task(
        _sse_loop(bot, api, store, guild_id, tournament_uid, organizer_discord_id)
    )
    _sse_tasks[key] = task


def tracked_table_channels(guild_id: str, tournament_uid: str) -> list[int]:
    """Call BEFORE ``stop_sse``, which clears the map this reads."""
    return [
        c for c in _table_channels.get(_task_key(guild_id, tournament_uid), []) if c
    ]


async def stop_sse(guild_id: str, tournament_uid: str) -> None:
    key = _task_key(guild_id, tournament_uid)
    task = _sse_tasks.pop(key, None)
    if task and not task.done():
        task.cancel()
    _table_channels.pop(key, None)
    _last_tournament.pop(key, None)
    _user_names.pop(key, None)
    _warned_unlinked_organizers.pop(key, None)
    _cancel_timer_tasks(key)
    _timer_tasks.pop(key, None)
    _timer_fired.pop(key, None)
    _timer_round_tag.pop(key, None)
    # _structural_locks intentionally NOT popped — see structural_lock.


async def probe_tournament(
    api,
    store: TokenStore,
    organizer_discord_id: str,
    tournament_uid: str,
) -> dict | None:
    """The backend answers 200 and just omits the tournament frame when the uid
    is unknown/unreadable, so absence before ``sync_complete`` means "no access"."""
    tokens = await store.get_tokens(organizer_discord_id, tournament_uid)
    if not tokens:
        return None
    if _access_token_expired(tokens["access_token"]):
        refreshed = await api.refresh_tokens(
            organizer_discord_id,
            tournament_uid,
            stale_access_token=tokens["access_token"],
        )
        if not refreshed:
            return None
        tokens = refreshed
    try:
        async with aiohttp.ClientSession() as session:
            for attempt in range(2):
                async with session.get(
                    f"{config.ARCHON_URL}/stream",
                    params={"tournament": tournament_uid},
                    headers={"Authorization": f"Bearer {tokens['access_token']}"},
                    # Bounds the whole probe incl. the body read — the scoped
                    # catch-up is small and the tournament frame comes first.
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status == 401 and attempt == 0:
                        refreshed = await api.refresh_tokens(
                            organizer_discord_id,
                            tournament_uid,
                            stale_access_token=tokens["access_token"],
                        )
                        if not refreshed:
                            return None
                        tokens = refreshed
                        continue
                    if resp.status != 200:
                        return None
                    async with aclosing(_sse_frames(resp)) as frames:
                        async for data in frames:
                            if data.get("type") == "sync_complete":
                                return None
                            for ev in _normalize_events(data):
                                if ev.get("type") == "tournament":
                                    return ev.get("data") or {}
                    return None
    except (aiohttp.ClientError, TimeoutError):
        return None
    return None


async def _sse_frames(resp):
    """Yields each frame's JSON payload. No ``event:`` field is sent; consumers
    dispatch on the payload ``type``."""
    data_lines: list[str] = []
    async for line_bytes in resp.content:
        line = line_bytes.decode("utf-8").rstrip("\n\r")
        if line.startswith("data:"):
            data_lines.append(line[5:].strip())
        elif line == "" and data_lines:
            data_str = "\n".join(data_lines)
            data_lines = []
            try:
                yield json.loads(data_str)
            except json.JSONDecodeError:
                logger.warning("Unparseable SSE data: %s", data_str[:200])


async def _sse_loop(
    bot,
    api,
    store: TokenStore,
    guild_id: str,
    tournament_uid: str,
    organizer_discord_id: str,
) -> None:
    key = _task_key(guild_id, tournament_uid)
    retry_delay = 1

    async with aiohttp.ClientSession() as session:
        while True:
            tokens = await store.get_tokens(organizer_discord_id, tournament_uid)
            if not tokens:
                logger.warning(
                    "No tokens for organizer %s on %s, stopping SSE",
                    organizer_discord_id,
                    tournament_uid,
                )
                return

            # Refresh up front if the stored token expired while we were down, so
            # the first connect doesn't 401.
            if _access_token_expired(tokens["access_token"]):
                refreshed = await api.refresh_tokens(
                    organizer_discord_id,
                    tournament_uid,
                    stale_access_token=tokens["access_token"],
                )
                if refreshed:
                    tokens = refreshed
                # else fall through: the 401 handler below refreshes.

            try:
                headers = {"Authorization": f"Bearer {tokens['access_token']}"}
                async with session.get(
                    f"{config.ARCHON_URL}/stream",
                    # Scoped: the whole corpus overflowed aiohttp's 512KB line limit.
                    params={"tournament": tournament_uid},
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=None, sock_read=300),
                ) as resp:
                    if resp.status == 401:
                        refreshed = await api.refresh_tokens(
                            organizer_discord_id,
                            tournament_uid,
                            stale_access_token=tokens["access_token"],
                        )
                        if refreshed:
                            # Token renewal is one-shot, not a failure to back off from.
                            continue
                        if not await store.get_tokens(
                            organizer_discord_id, tournament_uid
                        ):
                            # Invalid grant, pair removed; a fresh /register respawns this.
                            logger.error("Refresh token rejected for SSE, stopping")
                            return
                        logger.warning(
                            "Transient token refresh failure for SSE %s; will retry",
                            key,
                        )

                    if resp.status != 200:
                        logger.error("SSE connection failed: %s", resp.status)
                    else:
                        logger.info(
                            "SSE connected for guild=%s tournament=%s",
                            guild_id,
                            tournament_uid,
                        )

                        synced = False
                        async with aclosing(_sse_frames(resp)) as frames:
                            async for data in frames:
                                if data.get("type") == "resync":
                                    logger.info(
                                        "Resync requested, reconnecting SSE for %s", key
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
                                    logger.error(
                                        "Timed out (%ds) handling SSE %s for %s; "
                                        "skipping to keep the stream flowing",
                                        _DISPATCH_TIMEOUT,
                                        data.get("type"),
                                        key,
                                    )
                                # Bounded separately so a slow reconcile can't unset
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
                                                bot, store, guild_id, tournament_uid
                                            ),
                                            timeout=_DISPATCH_TIMEOUT,
                                        )
                                    except TimeoutError:
                                        logger.error("Reconcile timed out for %s", key)
                                    except Exception as e:
                                        logger.error("Reconcile failed: %s", e)
                                # Reset only on a *healthy* sync, not right after the
                                # 200, so a mid-read failure keeps backing off instead
                                # of hammering /stream once per second.
                                if synced:
                                    retry_delay = 1

            except asyncio.CancelledError:
                logger.info("SSE listener cancelled for %s; stopping", key)
                return
            except Exception as e:
                logger.error("SSE error for %s: %s", key, e)

            # This line is the single observable proof the listener is still
            # alive and will reconnect — if it stops appearing, it's wedged.
            logger.info(
                "SSE disconnected for %s; reconnecting in %ds", key, retry_delay
            )
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 60)


def _normalize_events(data: dict) -> list[dict]:
    """Catch-up sends plural arrays (``{"type":"tournaments","data":[...]}``);
    live sends singular objects. Normalizes both to singular-typed events."""
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
    msg_type = data.get("type", "")
    key = _task_key(guild_id, tournament_uid)

    if msg_type == "sync_complete":
        return True
    if msg_type == "heartbeat":
        return synced
    if msg_type == "judge_call":
        logger.info("SSE recv judge_call for %s", key)
        await _handle_judge_call(
            bot, store, guild_id, tournament_uid, data.get("data") or {}
        )
        return synced

    events = _normalize_events(data)

    if not synced:
        logger.info("SSE catch-up: seeding %d object(s) for %s", len(events), key)
        _handle_snapshot(key, events)
        return synced

    for ev in events:
        logger.info("SSE recv live %s for %s", ev.get("type"), key)
        await _handle_update(bot, store, guild_id, tournament_uid, ev)
    return synced


def _handle_snapshot(key: str, events: list[dict]) -> None:
    for ev in events:
        obj = ev.get("data") or {}
        if ev.get("type") == "user":
            _cache_user_identity(key, obj)
            continue
        if ev.get("type") != "tournament":
            continue
        _last_tournament[key] = obj
        logger.info(
            "Snapshot: state=%s rounds=%d for %s",
            obj.get("state", ""),
            len(obj.get("rounds", [])),
            key,
        )


async def _post(bot, channel_id: int, content: str) -> bool:
    """Logs before AND after the Discord call: a "→" with no matching "✓" pins a
    hung/slow REST call to the exact channel — the bot has no CI, we debug from logs."""
    logger.info("→ create_message channel=%s (%d chars)", channel_id, len(content))
    try:
        await bot.rest.create_message(channel_id, content)
    except Exception as e:
        logger.warning("Failed to post to channel %s: %s", channel_id, e)
        return False
    logger.info("✓ create_message channel=%s", channel_id)
    return True


def _seat_uids(table: dict) -> list[str]:
    return [s.get("player_uid", "") for s in table.get("seating", [])]


def _extract_round_seating(tournament: dict) -> list[list[str]] | None:
    rounds = tournament.get("rounds", [])
    if not rounds:
        return None
    return [_seat_uids(table) for table in rounds[-1]]


def _seat_results(table: dict) -> dict[str, tuple]:
    out: dict[str, tuple] = {}
    for s in table.get("seating", []):
        r = s.get("result") or {}
        out[s.get("player_uid", "")] = (r.get("gw", 0), r.get("vp", 0), r.get("tp", 0))
    return out


def _active_tables(obj: dict) -> tuple[str, list[dict]]:
    """The returned tag (``finals`` / ``round<N>``) lets a round-change or
    prelim→finals transition be told apart from a score being reported."""
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
    """Announces a table only when its seating is unchanged but a reported score
    differs from the previous snapshot — a tag mismatch (round/finals change)
    or seating swap is skipped, handled by their own announcements instead."""
    cur_tag, cur_tables = _active_tables(cur_obj)
    prev_tag, prev_tables = _active_tables(prev_obj)
    if not cur_tag or cur_tag != prev_tag:
        return []
    is_finals = cur_tag == "finals"
    out: list[tuple[int, str]] = []
    # cur_tables[i] ↔ table_chs[i]: the engine never reorders existing tables
    # within a round, a mid-round add only appends, and a remove shrinks the tail.
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


def compute_seating_echoes(
    prev_obj: dict | None, cur_obj: dict, table_chs: list[int]
) -> list[tuple[int, int]]:
    """``(channel_id, table_index)`` for every table whose chat should get its
    seating: all of them on a round or finals start, only the changed ones on a
    mid-round update. ``[]`` on a None ``prev_obj`` — no replay on reconnect."""
    if prev_obj is None:
        return []
    cur_tag, cur_tables = _active_tables(cur_obj)
    if not cur_tag:
        return []
    prev_tag, prev_tables = _active_tables(prev_obj)
    out: list[tuple[int, int]] = []
    for i, table in enumerate(cur_tables):
        if i >= len(table_chs) or not table_chs[i]:
            continue
        if (
            cur_tag == prev_tag
            and i < len(prev_tables)
            and _seat_uids(table) == _seat_uids(prev_tables[i])
        ):
            continue
        out.append((table_chs[i], i))
    return out


def compute_announcement_posts(
    prev_obj: dict | None, cur_obj: dict
) -> list[tuple[str, str]]:
    """Diffs the append-only ``announcements`` list by ``id``. Returns ``[]`` on a
    None ``prev_obj`` — catch-up seeds it silently, so a reconnect never re-posts
    the backlog."""
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


# No top-level ``result`` field on a table (only per-seat ``result``), so
# state + override is the only completion signal.
_TABLE_DONE_STATES = {"Finished", "Invalid", "Cancelled"}


def _table_pending(table: dict) -> bool:
    return table.get("state") not in _TABLE_DONE_STATES and not table.get("override")


def _live_round_count(obj: dict) -> int:
    return sum(1 for r in obj.get("rounds", []) if any(_table_pending(t) for t in r))


# Reminders fire at these many seconds of remaining time, per table.
_TIMER_THRESHOLDS = (900, 300, 60, 0)


@dataclass(frozen=True)
class TimerReminder:
    channel_id: int
    token: tuple
    delay: float  # wall-clock seconds from `now`; ≤0 means the threshold has passed
    message: str


@dataclass(frozen=True)
class ClockTable:
    index: int
    channel_id: int
    label: str
    total: int  # the round or finals time plus this table's extra time, seconds


def _parse_started_at_epoch(started_at: str | None) -> float | None:
    if not started_at:
        return None
    try:
        dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.timestamp() if dt.tzinfo else dt.replace(tzinfo=UTC).timestamp()


def clock_tables(obj: dict, table_chs: list[int]) -> tuple[str, list[ClockTable]]:
    """The pending tables the shared round clock governs, with their chat channel
    and full allotment; empty whenever the frontend hides the timer."""
    if obj.get("state", "") != "Playing":
        return "", []
    tag, tables = _active_tables(obj)
    if not tag:
        return "", []
    is_finals = tag == "finals"
    # One shared clock is meaningless once >1 prelim round is live; mirrors the
    # frontend, which hides the timer in the same case.
    if not is_finals and _live_round_count(obj) > 1:
        return "", []
    total = (
        (obj.get("finals_time") or obj.get("round_time") or 0)
        if is_finals
        else (obj.get("round_time") or 0)
    )
    if total <= 0:
        return "", []

    extra_map = obj.get("table_extra_time") or {}
    out: list[ClockTable] = []
    for i, table in enumerate(tables):
        if i >= len(table_chs) or not table_chs[i]:  # skip 0 sentinel / missing
            continue
        if not _table_pending(table):
            # A finished finals (seating still populated) would otherwise keep a
            # stale "Time!" scheduled until the tournament is formally finalized.
            continue
        out.append(
            ClockTable(
                index=i,
                channel_id=table_chs[i],
                label="Finals" if is_finals else f"Table {i + 1}",
                total=total + extra_map.get(str(i), 0),
            )
        )
    return tag, out


def _clock_running(obj: dict) -> bool:
    timer = obj.get("timer") or {}
    return bool(timer.get("started_at")) and not timer.get("paused")


def compute_timer_reminders(
    obj: dict, table_chs: list[int], now: float
) -> list[TimerReminder]:
    """Mirrors the frontend countdown formula exactly (TimerDisplay.svelte):
    ``remaining = total - (elapsed_before_pause + (now - started_at)) + extra``.
    The two must change together or the bot's reminders drift from the display."""
    timer = obj.get("timer") or {}
    if timer.get("paused"):
        return []
    started_epoch = _parse_started_at_epoch(timer.get("started_at"))
    if started_epoch is None:
        return []
    elapsed_before = float(timer.get("elapsed_before_pause") or 0.0)
    tag, tables = clock_tables(obj, table_chs)
    out: list[TimerReminder] = []
    for ct in tables:
        deadline = started_epoch + ct.total - elapsed_before
        for thr in _TIMER_THRESHOLDS:
            out.append(
                TimerReminder(
                    channel_id=ct.channel_id,
                    token=(tag, ct.index, thr),
                    delay=(deadline - thr) - now,
                    message=format_timer_reminder(ct.label, thr),
                )
            )
    return out


def compute_timer_start_posts(
    prev_obj: dict | None, cur_obj: dict, table_chs: list[int]
) -> list[tuple[int, str]]:
    """A first start carries ``elapsed_before_pause`` 0; a resume carries the
    elapsed time the pause banked, so it posts nothing."""
    if prev_obj is None or _clock_running(prev_obj) or not _clock_running(cur_obj):
        return []
    if float((cur_obj.get("timer") or {}).get("elapsed_before_pause") or 0.0) > 0:
        return []
    _tag, tables = clock_tables(cur_obj, table_chs)
    return [(ct.channel_id, format_timer_start(ct.label, ct.total)) for ct in tables]


def compute_time_extension_posts(
    prev_obj: dict | None, cur_obj: dict, table_chs: list[int]
) -> list[tuple[int, str]]:
    """Every round transition resets ``table_extra_time`` to ``{}``, so live
    diffs only ever grow and a shrink is a round boundary with nothing to say."""
    if prev_obj is None:
        return []
    prev_extra = prev_obj.get("table_extra_time") or {}
    cur_extra = cur_obj.get("table_extra_time") or {}
    _tag, tables = clock_tables(cur_obj, table_chs)
    out: list[tuple[int, str]] = []
    for ct in tables:
        total_extra = cur_extra.get(str(ct.index), 0)
        granted = total_extra - prev_extra.get(str(ct.index), 0)
        if granted > 0:
            out.append(
                (ct.channel_id, format_time_extension(ct.label, granted, total_extra))
            )
    return out


def _timer_signature(obj: dict) -> tuple:
    """Equal between two snapshots means the schedule still holds — skips
    score/sanction churn that doesn't touch any table's deadline."""
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
    for t in _timer_tasks.get(key, []):
        if not t.done():
            t.cancel()
    _timer_tasks[key] = []


async def _fire_timer_reminder(bot, key: str, reminder: TimerReminder) -> None:
    """The fired set guards the narrow window where this posts just as a
    reschedule recomputes."""
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
    """The single authority for the schedule: a passed threshold is marked fired
    WITHOUT posting, suppressing stale reminders on reconnect/restart. Never
    raises — a schedule miss is repaired by the next signature change."""
    key = _task_key(guild_id, tournament_uid)
    try:
        _cancel_timer_tasks(key)
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
                fired.add(reminder.token)
                continue
            _timer_tasks[key].append(
                asyncio.create_task(_fire_timer_reminder(bot, key, reminder))
            )
        logger.info(
            "Timer reschedule %s: %d pending (tag=%s)", key, len(_timer_tasks[key]), tag
        )
    except Exception as e:
        logger.error("Timer reschedule failed for %s: %s", key, e)


async def _build_discord_id_map(
    store: TokenStore, archon_uids: set[str]
) -> dict[str, int]:
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
        f"Ask them to run {command_mention('checkin')} in the lobby.",
    )


async def _warn_unlinked_organizers(
    bot, key: str, judges_id: int, unlinked_uids: set[str], players: list
) -> None:
    """Fires once per organizer per listener lifetime."""
    new = unlinked_uids - _warned_unlinked_organizers[key]
    if not new:
        return
    _warned_unlinked_organizers[key] |= new
    names = [player_display(uid, players, user_names=_user_names[key]) for uid in new]
    await _post(
        bot,
        judges_id,
        f"**Warning:** {len(new)} organizer{'s have' if len(new) != 1 else ' has'} "
        f"no linked Discord account and cannot see this channel: "
        f"{', '.join(names)}. Ask them to run {command_mention('register')} here once, or link "
        f"Discord on the webapp.",
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
    """Callers MUST hold ``structural_lock``. Reconciles only the volatile
    round/finals channels, never category/text — aborts and warns #judges if
    the category itself is gone rather than recreate an unparented mess."""
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
            f"can't place voice channels. Recreate it, or run {command_mention('teardown')} then "
            f"{command_mention('setup')} again.",
        )
        return ReconcileSummary(aborted=True)

    current = round_channels_by_name(channels, category_id)
    desired_by_name = {dc.name: dc for dc in desired}

    all_member_uids: set[str] = set()
    for dc in desired:
        all_member_uids |= dc.member_uids
    discord_id_map = await _build_discord_id_map(store, all_member_uids)

    summary = ReconcileSummary()

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
                    int(ch.id),
                    dc.member_uids,
                    discord_id_map,
                    current_member_ids=member_override_ids(ch),
                )
                summary.synced.append(dc.name)
            except Exception as e:
                logger.warning("Reconcile %s: sync '%s' failed: %s", key, dc.name, e)
            name_to_id[dc.name] = int(ch.id)

    judges_ch = next((ch for ch in channels if int(ch.id) == judges_id), None)
    if judges_ch is None:
        logger.warning(
            "Reconcile %s: judges channel %s not found; skipping judges sync",
            key,
            judges_id,
        )
    else:
        organizer_uids = set(obj.get("organizers_uids", []))
        judge_map = await _build_discord_id_map(store, organizer_uids)
        for uid in organizer_uids - set(judge_map):
            did = (_user_names[key].get(uid) or {}).get("discord_id")
            if did:
                judge_map[uid] = int(did)
        desired_judges = set(judge_map.values()) | {int(link["organizer_discord_id"])}
        try:
            await sync_judges_channel(bot, int(guild_id), judges_ch, desired_judges)
        except Exception as e:
            logger.warning("Reconcile %s: judges sync failed: %s", key, e)
        # A uid with no cached user frame yet is likely a live add still in
        # flight; only warn once its identity is cached and confirmed unlinked.
        known_unlinked = {
            uid
            for uid in organizer_uids - set(judge_map)
            if _user_names[key].get(uid) is not None
        }
        await _warn_unlinked_organizers(
            bot, key, judges_id, known_unlinked, obj.get("players", [])
        )

    # index i ↔ desired table i, the contract the announcement layer indexes
    # into. A failed create leaves a 0 sentinel so later tables keep their index.
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
    """Returns ``None`` if no tournament state is cached yet (still connecting)."""
    key = _task_key(guild_id, tournament_uid)
    async with structural_lock(guild_id, tournament_uid):
        obj = _last_tournament.get(key)
        if obj is None:
            return None
        summary = await reconcile_channels(bot, store, guild_id, tournament_uid, obj)
    await _reschedule_timers(bot, guild_id, tournament_uid, obj)
    return summary


async def _handle_update(
    bot,
    store: TokenStore,
    guild_id: str,
    tournament_uid: str,
    data: dict,
) -> None:
    """A tournament event splits in two: the STRUCTURAL half is reconciled only
    when ``structure_signature`` changes; the ANNOUNCEMENT half is edge-triggered."""
    obj_type = data.get("type")

    if obj_type == "sanction":
        await _handle_sanction_update(bot, store, guild_id, tournament_uid, data)
        return

    if obj_type == "user":
        key = _task_key(guild_id, tournament_uid)
        user_obj = data.get("data") or {}
        uid = user_obj.get("uid")
        had_discord = bool((_user_names[key].get(uid) or {}).get("discord_id"))
        _cache_user_identity(key, user_obj)
        # Live-path ordering: a tournament frame reconciles BEFORE its
        # participant frames, so a late-arriving identity re-triggers the sync.
        obj = _last_tournament.get(key)
        if (
            uid
            and user_obj.get("discord_id")
            and not had_discord
            and obj
            and uid in (obj.get("organizers_uids") or [])
        ):
            _warned_unlinked_organizers[key].discard(uid)
            try:
                await sync_now(bot, store, guild_id, tournament_uid)
            except Exception as e:
                logger.error("Organizer re-grant reconcile failed for %s: %s", key, e)
        return

    if obj_type != "tournament":
        if obj_type:
            logger.debug("Ignoring SSE update of unknown type: %s", obj_type)
        return

    obj = data.get("data") or {}
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

    structure_changed = structure_signature(prev_obj or {}) != structure_signature(obj)
    if structure_changed:
        async with structural_lock(guild_id, tournament_uid):
            try:
                await reconcile_channels(bot, store, guild_id, tournament_uid, obj)
            except Exception as e:
                logger.error("Reconcile failed for %s: %s", key, e)

    try:
        await _emit_announcements(
            bot, store, guild_id, tournament_uid, prev_obj, obj, link
        )
    except Exception as e:
        logger.error("Announcement emit failed for %s: %s", key, e)

    # Same structural lock so a concurrent reconcile can't race the stored event id.
    if event_signature(prev_obj or {}) != event_signature(obj):
        async with structural_lock(guild_id, tournament_uid):
            try:
                await ensure_scheduled_event(
                    bot, store, guild_id, tournament_uid, obj, prev_obj
                )
            except Exception as e:
                logger.error("Scheduled-event ensure failed for %s: %s", key, e)

    # No structural lock: only touches in-process tasks, never Discord channels.
    # Runs after any structural reconcile above so _table_channels is current.
    if structure_changed or _timer_signature(prev_obj or {}) != _timer_signature(obj):
        await _reschedule_timers(bot, guild_id, tournament_uid, obj)

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
    """Deliberately NOT idempotent — each fires once on its transition;
    re-posting seating would be spam."""
    key = _task_key(guild_id, tournament_uid)
    announcement_id = int(link["announcement_channel_id"])
    lobby_id = int(link["lobby_channel_id"])
    judges_id = int(link["judges_channel_id"])

    prev = prev_obj or {}
    prev_state = prev.get("state", "")
    prev_round_count = len(prev.get("rounds", []))

    state = obj.get("state", "")
    name = obj.get("name", "Tournament")
    webapp_url = config.event_url(obj, tournament_uid)
    rounds = obj.get("rounds", [])
    players = obj.get("players", [])
    round_count = len(rounds)

    if state == "Registration" and prev_state != "Registration":
        await _post(
            bot,
            announcement_id,
            f"**Registration is open for {name}!**\n"
            f"Use {command_mention('register')} in <#{lobby_id}> to sign up.",
        )
        await _post(
            bot,
            lobby_id,
            f"Registration is open! Use {command_mention('register')} to sign up for **{name}**.",
        )
        await _post(
            bot,
            judges_id,
            f"**{name}** — Registration opened.\nManage tournament: {webapp_url}",
        )

    if state == "Waiting" and prev_state == "Registration":
        registered = len(players)
        decklist_note = ""
        if obj.get("decklist_required"):
            decklist_note = (
                f"\nThis tournament requires a decklist — if you haven't uploaded "
                f"yours yet, do it on the webapp before the round starts: {webapp_url}"
            )

        await _post(
            bot,
            announcement_id,
            f"**Check-in is open for {name}!**\n"
            f"{registered} player{'s' if registered != 1 else ''} registered. "
            f"Use {command_mention('checkin')} in <#{lobby_id}> to check in.{decklist_note}",
        )
        await _post(
            bot,
            lobby_id,
            f"Check-in is now open! Use {command_mention('checkin')} to check in for "
            f"**{name}**.{decklist_note}",
        )
        await _post(
            bot,
            judges_id,
            f"**{name}** — Check-in opened ({registered} registered).\n"
            f"Close check-in and start Round 1 from the webapp when ready.\n{webapp_url}",
        )

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
            f"\nCheck-in for the next round is open — use {command_mention('checkin')} in <#{lobby_id}>."
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

    if state == "Playing" and round_count > prev_round_count and rounds:
        await _announce_round_seating(bot, store, guild_id, tournament_uid, obj, link)

    if obj.get("finals") and state == "Playing" and prev_state != "Playing":
        await _announce_finals(bot, store, guild_id, tournament_uid, obj, link)

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

    echoes = compute_seating_echoes(prev_obj, obj, _table_channels.get(key, []))
    if echoes:
        tag, tables = _active_tables(obj)
        seated = {uid for _ch, i in echoes for uid in _seat_uids(tables[i])}
        discord_id_map = await _build_discord_id_map(store, seated)
        for ch_id, i in echoes:
            await _post(
                bot,
                ch_id,
                format_table_seating(
                    i,
                    tables[i],
                    players,
                    is_finals=tag == "finals",
                    seed_order=(obj.get("finals") or {}).get("seed_order", []),
                    discord_id_map=discord_id_map,
                    user_names=_user_names[key],
                ),
            )

    # A pure score report makes no structural change, so _table_channels still
    # maps the live tables (reconcile was skipped).
    if state == "Playing" and prev_obj is not None:
        for ch_id, msg in compute_result_announcements(
            prev_obj, obj, _table_channels.get(key, []), players, _user_names[key]
        ):
            await _post(bot, ch_id, msg)

    for ch_id, msg in compute_timer_start_posts(
        prev_obj, obj, _table_channels.get(key, [])
    ):
        await _post(bot, ch_id, msg)
    for ch_id, msg in compute_time_extension_posts(
        prev_obj, obj, _table_channels.get(key, [])
    ):
        await _post(bot, ch_id, msg)

    # Not state-gated — an organizer can broadcast at any phase.
    for _aid, msg in compute_announcement_posts(prev_obj, obj):
        await _post(bot, announcement_id, msg)

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
            f"Use {command_mention('teardown')} when you're ready to remove the tournament channels.\n{webapp_url}",
        )


async def _announce_round_seating(
    bot,
    store: TokenStore,
    guild_id: str,
    tournament_uid: str,
    obj: dict,
    link: dict,
) -> None:
    key = _task_key(guild_id, tournament_uid)
    announcement_id = int(link["announcement_channel_id"])
    judges_id = int(link["judges_channel_id"])
    name = obj.get("name", "Tournament")
    webapp_url = config.event_url(obj, tournament_uid)
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
        f"Use {command_mention('sanction')} on a player to issue sanctions.\n{webapp_url}",
    )


async def _announce_finals(
    bot,
    store: TokenStore,
    guild_id: str,
    tournament_uid: str,
    obj: dict,
    link: dict,
) -> None:
    key = _task_key(guild_id, tournament_uid)
    announcement_id = int(link["announcement_channel_id"])
    judges_id = int(link["judges_channel_id"])
    name = obj.get("name", "Tournament")
    webapp_url = config.event_url(obj, tournament_uid)
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
    """STRUCTURAL ONLY by design: a seating announcement missed during the
    disconnect is not replayed; the voice channels are always restored."""
    key = _task_key(guild_id, tournament_uid)
    obj = _last_tournament.get(key)
    state = obj.get("state", "") if obj else "(none)"
    logger.info("Reconciling %s after (re)connect (state=%s)", key, state)
    if not obj:
        # A tournament soft-deleted while the bot was DOWN never reappears here
        # (catch-up filters deleted_at); /teardown is the authority for its cleanup.
        return
    async with structural_lock(guild_id, tournament_uid):
        await reconcile_channels(bot, store, guild_id, tournament_uid, obj)
        try:
            await ensure_scheduled_event(bot, store, guild_id, tournament_uid, obj)
        except Exception as e:
            logger.error("Scheduled-event ensure failed for %s: %s", key, e)
    await _reschedule_timers(bot, guild_id, tournament_uid, obj)


def sanction_table_channel(
    tournament: dict | None, round_number: int, user_uid: str, table_chs: list[int]
) -> int | None:
    """``table_chs`` maps the LIVE context only, so a past round's same-index
    table (which would seat strangers) falls back to the lobby instead."""
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
    obj = data.get("data") or {}
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

    player_discord_id = await store.get_discord_id_by_archon_uid(user_uid)
    player_mention = f"<@{player_discord_id}>" if player_discord_id else user_uid[:8]

    judges_msg, player_msg = format_sanction(
        level, category, subcategory, description, round_number, player_mention
    )

    key = _task_key(guild_id, tournament_uid)
    logger.info(
        "SSE recv sanction (level=%s round=%s) for %s", level, round_number, key
    )
    await _post(bot, judges_id, judges_msg)

    posted_to_table = False
    if round_number is not None:
        target = sanction_table_channel(
            _last_tournament.get(key),
            round_number,
            user_uid,
            _table_channels.get(key, []),
        )
        if target:
            posted_to_table = await _post(bot, target, player_msg)
    if not posted_to_table:
        await _post(bot, lobby_id, player_msg)


async def _handle_judge_call(
    bot,
    store: TokenStore,
    guild_id: str,
    tournament_uid: str,
    data: dict,
) -> None:
    link = await store.get_tournament_link(guild_id, tournament_uid)
    if not link:
        return
    table = data.get("table", 0)
    table_label = data.get("table_label") or f"Table {table + 1}"
    player_name = data.get("player_name", "Unknown")
    await _post(
        bot,
        int(link["judges_channel_id"]),
        f"**Judge call!** {table_label} — {player_name} needs a judge",
    )
