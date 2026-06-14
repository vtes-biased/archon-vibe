"""SSE subscription per organizer for real-time tournament state changes."""

import asyncio
import base64
import binascii
import json
import logging
import time
from collections import defaultdict

import aiohttp

from . import config
from .announcements import (
    format_finals,
    format_round_seating,
    format_sanction,
    format_standings,
    player_display,
)
from .channel_manager import (
    create_table_channels,
    delete_channels,
    fetch_round_channel_ids,
    sync_table_permissions,
)
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

# Track table voice channel IDs per round: key → list of channel IDs
_table_channels: dict[str, list[int]] = defaultdict(list)

# Track last known state per tournament to detect transitions (prevents spam)
_last_state: dict[str, str] = {}

# Track last known round count to detect new rounds
_last_round_count: dict[str, int] = {}

# Cache last tournament data for table lookups (needed for sanction → table mapping)
_last_tournament: dict[str, dict] = {}

# Track last known seating per round for mid-round change detection
_last_seating: dict[str, list[set[str]]] = {}


def _task_key(guild_id: str, tournament_uid: str) -> str:
    return f"{guild_id}:{tournament_uid}"


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


async def stop_sse(guild_id: str, tournament_uid: str) -> None:
    """Stop SSE listener for a tournament and clean up all cached state."""
    key = _task_key(guild_id, tournament_uid)
    task = _sse_tasks.pop(key, None)
    if task and not task.done():
        task.cancel()
    _last_state.pop(key, None)
    _last_round_count.pop(key, None)
    _last_seating.pop(key, None)
    _table_channels.pop(key, None)
    _last_tournament.pop(key, None)


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
    """Initialize state tracking from snapshot without posting announcements."""
    items = data if isinstance(data, list) else [data]
    for item in items:
        obj = item.get("data", item)
        if item.get("type") != "tournament" or obj.get("uid") != tournament_uid:
            continue
        _last_state[key] = obj.get("state", "")
        _last_round_count[key] = len(obj.get("rounds", []))
        _last_seating[key] = _extract_round_seating(obj) or []
        _last_tournament[key] = obj
        logger.info(
            "Snapshot: state=%s rounds=%d for %s",
            _last_state[key],
            _last_round_count[key],
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


def _collect_all_player_uids(seating: list[set[str]]) -> set[str]:
    """Collect all player UIDs from seating."""
    result: set[str] = set()
    for table in seating:
        result |= table
    return result


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
) -> None:
    """Post a warning to #judges about seated players without a Discord link."""
    unlinked = player_uids - set(discord_id_map.keys())
    if not unlinked:
        return
    names = [player_display(uid, players) for uid in unlinked]
    await _post(
        bot,
        judges_id,
        f"**Warning:** {len(unlinked)} seated player{'s have' if len(unlinked) != 1 else ' has'} "
        f"not linked their Discord account and cannot join voice: {', '.join(names)}. "
        f"Ask them to run `/checkin` in the lobby.",
    )


async def _handle_update(
    bot,
    store: TokenStore,
    guild_id: str,
    tournament_uid: str,
    data: dict,
) -> None:
    """Handle an SSE update event (tournament or sanction)."""
    obj_type = data.get("type")

    if obj_type == "sanction":
        await _handle_sanction_update(bot, store, guild_id, tournament_uid, data)
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

    announcement_id = int(link["announcement_channel_id"])
    lobby_id = int(link["lobby_channel_id"])
    category_id = int(link["category_id"])
    judges_id = int(link["judges_channel_id"])

    state = obj.get("state", "")
    name = obj.get("name", "Tournament")
    webapp_url = f"{config.ARCHON_FRONTEND_URL}/tournaments/{tournament_uid}"

    prev_state = _last_state.get(key)
    prev_round_count = _last_round_count.get(key, 0)

    rounds = obj.get("rounds", [])
    players = obj.get("players", [])
    round_count = len(rounds)

    # The key debug line for transition bugs: every tournament update logs the
    # state machine delta the handlers below branch on.
    logger.info(
        "Tournament update %s: state %s→%s, rounds %d→%d, %d players",
        key,
        prev_state,
        state,
        prev_round_count,
        round_count,
        len(players),
    )

    organizer_uids = set(obj.get("organizers_uids", []))

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
        checked_in = sum(1 for p in players if p.get("state") == "Checked-in")
        registered = len(players)
        decklist_note = ""
        if obj.get("decklist_required"):
            decklist_note = f"\nThis tournament requires a decklist — upload yours on the webapp: {webapp_url}"

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
            f"Check-in is now open! Use `/checkin` to check in for **{name}**.{decklist_note}",
        )
        await _post(
            bot,
            judges_id,
            f"**{name}** — Check-in opened ({registered} registered).\n"
            f"Close check-in and start Round 1 from the webapp when ready.\n{webapp_url}",
        )

    # ── Round finished → back to Waiting ──
    if state == "Waiting" and prev_state == "Playing":
        standings = obj.get("standings", [])
        standings_mode = obj.get("standings_mode", "Private")

        lines = [f"**Round {round_count} complete!**"]
        lines.append(format_standings(standings, standings_mode, players))
        lines.append(
            f"\nCheck-in for the next round is open — use `/checkin` in <#{lobby_id}>."
        )
        await _post(bot, announcement_id, "\n".join(lines))

        # Clean up table channels
        if key in _table_channels:
            await delete_channels(bot, _table_channels.pop(key))
        _last_seating.pop(key, None)

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
        await _setup_round(
            bot, store, guild_id, tournament_uid, obj, announce=True, new_round=True
        )

    # ── Finals started ──
    finals = obj.get("finals")
    if finals and state == "Playing" and prev_state != "Playing":
        await _setup_finals(bot, store, guild_id, tournament_uid, obj, announce=True)

    # ── Mid-round seating changes (SwapSeats, AlterSeating, etc.) ──
    if (
        state == "Playing"
        and round_count == prev_round_count
        and round_count > 0
        and key in _last_seating
    ):
        current_seating = _extract_round_seating(obj)
        prev_seating = _last_seating.get(key)

        if (
            current_seating is not None
            and prev_seating is not None
            and current_seating != prev_seating
        ):
            all_player_uids = _collect_all_player_uids(current_seating)
            discord_id_map = await _build_discord_id_map(
                store, all_player_uids | organizer_uids
            )

            table_chs = _table_channels.get(key, [])
            prev_count = len(prev_seating)
            new_count = len(current_seating)

            # Handle table count changes
            if new_count > prev_count:
                # New tables added — create channels with correct numbering
                new_tables = [
                    list(current_seating[i]) for i in range(prev_count, new_count)
                ]
                try:
                    new_ch_ids = await create_table_channels(
                        bot,
                        int(guild_id),
                        category_id,
                        new_tables,
                        discord_id_map=discord_id_map,
                        organizer_uids=organizer_uids,
                        start_index=prev_count,
                    )
                    table_chs.extend(new_ch_ids)
                except Exception as e:
                    logger.warning("Failed to create new table channels: %s", e)

            if new_count < prev_count:
                # Tables removed — delete orphaned channels, update dict immediately
                orphaned = table_chs[new_count:]
                await delete_channels(bot, orphaned)
                table_chs = table_chs[:new_count]
                _table_channels[key] = table_chs

            # Sync permissions on existing tables that changed
            for i in range(min(new_count, len(table_chs))):
                if i < len(prev_seating) and i < len(current_seating):
                    if current_seating[i] != prev_seating[i]:
                        try:
                            await sync_table_permissions(
                                bot,
                                int(guild_id),
                                table_chs[i],
                                current_seating[i],
                                organizer_uids,
                                discord_id_map,
                            )
                        except Exception as e:
                            logger.warning(
                                "Failed to sync table %d permissions: %s", i + 1, e
                            )

            _table_channels[key] = table_chs
            _last_seating[key] = current_seating

            # Post updated seating
            current_round = rounds[-1]
            lines = [f"**Seating updated — Round {round_count}**\n"]
            for ti, table in enumerate(current_round):
                seat_names = [
                    player_display(s.get("player_uid", ""), players)
                    for s in table.get("seating", [])
                ]
                lines.append(f"**Table {ti + 1}**: {' → '.join(seat_names)}")
            await _post(bot, announcement_id, "\n".join(lines))

            # Warn about newly unlinked players
            await _warn_unlinked_players(
                bot, judges_id, all_player_uids, discord_id_map, players
            )

    # ── Tournament finished ──
    if state == "Finished" and prev_state != "Finished":
        standings = obj.get("standings", [])
        winner = obj.get("winner", "")
        standings_mode = obj.get("standings_mode", "Private")

        lines = [f"**{name} is finished!**"]
        if winner:
            winner_name = player_display(winner, players)
            lines.append(f"Congratulations to the winner: **{winner_name}**!")

        lines.append(format_standings(standings, standings_mode, players))
        lines.append(f"\nFull results: {webapp_url}")
        lines.append("Thank you all for playing!")
        await _post(bot, announcement_id, "\n".join(lines))

        # Clean up table channels
        if key in _table_channels:
            await delete_channels(bot, _table_channels.pop(key))
        _last_seating.pop(key, None)

        await _post(
            bot,
            judges_id,
            f"**{name}** — Tournament finished.\n"
            f"Results and VEKN push available on the webapp.\n"
            f"Use `/teardown` when you're ready to remove the tournament channels.\n{webapp_url}",
        )

    # Update state tracking LAST so comparisons above see previous state.
    # If handler crashes mid-way, next SSE event retries the transition.
    _last_state[key] = state
    _last_round_count[key] = round_count
    _last_tournament[key] = obj


async def _setup_round(
    bot,
    store: TokenStore,
    guild_id: str,
    tournament_uid: str,
    obj: dict,
    *,
    announce: bool,
    new_round: bool = False,
) -> None:
    """Set up the current round's table voice channels + (optionally) announce.

    Two modes, both safe to call repeatedly:

    - ``new_round=True`` (a genuine transition: ``round_count`` increased): any
      ``Table N`` channels under the category are STALE — leftovers from a prior
      round whose cleanup we missed, or a partial set from a timed-out attempt —
      so delete them all, then create this round's tables fresh and announce.
      Delete-then-create is what makes a timed-out retry idempotent (no duplicate
      channels) without adopting the wrong round's channels by count.
    - ``new_round=False`` (reconnect/reconcile): reuse channels that already
      cover the round (silent — re-adopt the map and re-sync permissions to the
      current seating); otherwise treat it as a missed round and set it up.
    """
    key = _task_key(guild_id, tournament_uid)
    link = await store.get_tournament_link(guild_id, tournament_uid)
    if not link:
        return
    rounds = obj.get("rounds", [])
    if not rounds:
        return

    category_id = int(link["category_id"])
    announcement_id = int(link["announcement_channel_id"])
    judges_id = int(link["judges_channel_id"])
    name = obj.get("name", "Tournament")
    webapp_url = f"{config.ARCHON_FRONTEND_URL}/tournaments/{tournament_uid}"
    players = obj.get("players", [])
    organizer_uids = set(obj.get("organizers_uids", []))
    round_count = len(rounds)
    tables_data: list[list[str]] = [
        [s.get("player_uid", "") for s in table.get("seating", [])]
        for table in rounds[-1]
    ]

    existing, _finals_id = await fetch_round_channel_ids(
        bot, int(guild_id), category_id
    )

    if new_round and existing:
        # Stale channels (missed prior cleanup, or a timed-out partial create).
        await delete_channels(bot, existing)
        existing = []

    # A true new round always (re)creates; reconcile adopts channels that already
    # cover the round and only creates when they're missing.
    do_create = new_round or len(existing) < len(tables_data)
    do_announce = announce and do_create
    logger.info(
        "Setup round %d for %s: %d tables, new_round=%s, existing=%d → %s",
        round_count,
        key,
        len(tables_data),
        new_round,
        len(existing),
        "create+announce" if do_announce else ("create" if do_create else "adopt"),
    )

    all_player_uids = {uid for table in tables_data for uid in table}
    discord_id_map = await _build_discord_id_map(
        store, all_player_uids | organizer_uids
    )

    if do_announce:
        await _post(
            bot,
            announcement_id,
            format_round_seating(round_count, tables_data, players),
        )

    if do_create:
        # Create only the not-yet-existing tables, numbered after the existing.
        try:
            new_ids = await create_table_channels(
                bot,
                int(guild_id),
                category_id,
                tables_data[len(existing) :],
                discord_id_map=discord_id_map,
                organizer_uids=organizer_uids,
                start_index=len(existing),
            )
            _table_channels[key] = existing + new_ids
        except Exception as e:
            logger.warning("Failed to create table channels: %s", e)
            _table_channels[key] = existing
    else:
        # Channels already present (reconnect): adopt them, reconcile perms.
        _table_channels[key] = existing[: len(tables_data)]
        for i, table in enumerate(tables_data):
            if i < len(_table_channels[key]):
                try:
                    await sync_table_permissions(
                        bot,
                        int(guild_id),
                        _table_channels[key][i],
                        set(table),
                        organizer_uids,
                        discord_id_map,
                    )
                except Exception as e:
                    logger.warning("Failed to sync table %d permissions: %s", i + 1, e)

    _last_seating[key] = [set(t) for t in tables_data]

    if do_announce:
        await _warn_unlinked_players(
            bot, judges_id, all_player_uids, discord_id_map, players
        )
        await _post(
            bot,
            judges_id,
            f"**{name}** — Round {round_count} started ({len(tables_data)} tables, "
            f"{sum(len(t) for t in tables_data)} players).\n"
            f"Use `/sanction @player` to issue sanctions.\n{webapp_url}",
        )


async def _setup_finals(
    bot,
    store: TokenStore,
    guild_id: str,
    tournament_uid: str,
    obj: dict,
    *,
    announce: bool,
) -> None:
    """Idempotently set up the finals voice channel + announce the finalists.

    Reuses an existing ``Finals`` channel under the category (reconnect/restart
    safe); only announces + creates when none exists yet.
    """
    key = _task_key(guild_id, tournament_uid)
    link = await store.get_tournament_link(guild_id, tournament_uid)
    if not link:
        return
    finals = obj.get("finals") or {}
    seating = finals.get("seating", [])
    if not seating:
        return

    category_id = int(link["category_id"])
    announcement_id = int(link["announcement_channel_id"])
    judges_id = int(link["judges_channel_id"])
    name = obj.get("name", "Tournament")
    webapp_url = f"{config.ARCHON_FRONTEND_URL}/tournaments/{tournament_uid}"
    players = obj.get("players", [])
    organizer_uids = set(obj.get("organizers_uids", []))
    seed_order = finals.get("seed_order", [])
    finalists = [s.get("player_uid", "") for s in seating]
    finalist_uids = set(finalists)

    # Ignore any prelim `Table N` channels: during finals sanctions route to the
    # single finals table, and teardown deletes whatever is in _table_channels —
    # so the map must hold ONLY the finals channel, never stale prelim tables.
    _existing_tables, finals_id = await fetch_round_channel_ids(
        bot, int(guild_id), category_id
    )
    fresh = finals_id is None
    logger.info(
        "Setup finals for %s: %d finalists, existing_finals=%s → %s",
        key,
        len(seating),
        finals_id,
        "create+announce" if (announce and fresh) else "adopt",
    )

    discord_id_map = await _build_discord_id_map(store, finalist_uids | organizer_uids)

    if announce and fresh:
        await _post(
            bot, announcement_id, format_finals(name, seating, seed_order, players)
        )

    if fresh:
        try:
            ch_ids = await create_table_channels(
                bot,
                int(guild_id),
                category_id,
                [finalists],
                discord_id_map=discord_id_map,
                organizer_uids=organizer_uids,
                is_finals=True,
            )
            finals_id = ch_ids[0] if ch_ids else None
        except Exception as e:
            logger.warning("Failed to create finals channel: %s", e)

    if finals_id is not None:
        _table_channels[key] = [finals_id]

    if announce and fresh:
        await _warn_unlinked_players(
            bot, judges_id, finalist_uids, discord_id_map, players
        )
        await _post(
            bot,
            judges_id,
            f"**{name}** — Finals started ({len(seating)} finalists).\n{webapp_url}",
        )


async def _reconcile(
    bot,
    store: TokenStore,
    guild_id: str,
    tournament_uid: str,
) -> None:
    """Repair Discord to match current state after a (re)connect's catch-up.

    Catch-up only SEEDS state silently (``_handle_snapshot``), so a round or
    finals that started while the bot was disconnected — or before a restart —
    would otherwise have no voice channels and no seating announcement. This
    recreates them. ``_setup_round``/``_setup_finals`` reuse existing channels,
    so a normal reconnect (channels already present) is silent.
    """
    key = _task_key(guild_id, tournament_uid)
    obj = _last_tournament.get(key)
    state = obj.get("state", "") if obj else "(none)"
    logger.info("Reconciling %s after (re)connect (state=%s)", key, state)
    if not obj or state != "Playing":
        return
    finals = obj.get("finals") or {}
    if finals.get("seating") and not finals.get("result"):
        await _setup_finals(bot, store, guild_id, tournament_uid, obj, announce=True)
    elif obj.get("rounds"):
        await _setup_round(bot, store, guild_id, tournament_uid, obj, announce=True)


async def _handle_sanction_update(
    bot,
    store: TokenStore,
    guild_id: str,
    tournament_uid: str,
    data: dict,
) -> None:
    """Handle a sanction SSE event.

    - Always posts to #judges channel
    - If round_number set and table channels exist: posts to the player's table channel
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
    # - If there are active table channels (ongoing round), post to the table
    # - Otherwise, post to lobby
    key = _task_key(guild_id, tournament_uid)
    table_chs = _table_channels.get(key, [])

    # Find the player's table channel if round is active
    posted_to_table = False
    if round_number is not None and table_chs:
        # Look up which table the player is at using cached tournament data
        tournament_data = _last_tournament.get(key)
        if tournament_data:
            rounds = tournament_data.get("rounds", [])
            if round_number < len(rounds):
                current_round = rounds[round_number]
                for ti, table in enumerate(current_round):
                    seating = table.get("seating", [])
                    if any(s.get("player_uid") == user_uid for s in seating):
                        if ti < len(table_chs):
                            try:
                                logger.info(
                                    "→ create_message sanction→table %d channel=%s",
                                    ti + 1,
                                    table_chs[ti],
                                )
                                await bot.rest.create_message(table_chs[ti], player_msg)
                                posted_to_table = True
                            except Exception as e:
                                logger.warning(
                                    "Failed to post sanction to table %d: %s", ti, e
                                )
                        break

    if not posted_to_table:
        # No active round, no table channels, or player not found at a table — post to lobby
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
