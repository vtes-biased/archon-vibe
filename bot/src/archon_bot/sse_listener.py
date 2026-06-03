"""SSE subscription per organizer for real-time tournament state changes."""

import asyncio
import json
import logging
from collections import defaultdict

import aiohttp

from . import config
from .channel_manager import (
    create_table_channels,
    delete_channels,
    sync_table_permissions,
)
from .token_store import TokenStore

logger = logging.getLogger(__name__)

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

            try:
                headers = {"Authorization": f"Bearer {tokens['access_token']}"}
                async with session.get(
                    f"{config.ARCHON_URL}/stream",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=None, sock_read=300),
                ) as resp:
                    if resp.status == 401:
                        refreshed = await api.refresh_tokens(organizer_discord_id)
                        if not refreshed:
                            logger.error("Token refresh failed for SSE, stopping")
                            return
                        continue

                    if resp.status != 200:
                        logger.error("SSE connection failed: %s", resp.status)
                        await asyncio.sleep(retry_delay)
                        retry_delay = min(retry_delay * 2, 60)
                        continue

                    retry_delay = 1
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
                                # Server wants a clean re-sync. Reconnect for a
                                # fresh catch-up (the bot sends no `since`, so a
                                # reconnect always replays full current state).
                                logger.info(
                                    "Resync requested, reconnecting SSE for %s", key
                                )
                                break

                            synced = await _dispatch_event(
                                bot, store, guild_id, tournament_uid, data, synced
                            )
                        # `:`-comment lines (": connected", ": keepalive") ignored

            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.error("SSE error: %s", e)
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

    if msg_type == "sync_complete":
        return True
    if msg_type == "judge_call":
        await _handle_judge_call(
            bot, store, guild_id, tournament_uid, data.get("data") or {}
        )
        return synced

    events = _normalize_events(data)

    if not synced:
        # Catch-up / overlay: seed tournament state, post nothing.
        _handle_snapshot(_task_key(guild_id, tournament_uid), tournament_uid, events)
        return synced

    for ev in events:
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


def _format_standings(standings: list, standings_mode: str, players: list) -> str:
    """Format standings respecting the tournament's standings_mode setting.

    - Private: no standings shown
    - Cutoff: only the 5th-place score threshold (no names)
    - Top 10: top 10 players with scores
    - Public: all players with scores
    """
    if standings_mode == "Private" or not standings:
        return ""

    if standings_mode == "Cutoff":
        if len(standings) < 5:
            return "\n**Top 5 cutoff:** Not enough players yet."
        s = standings[4]
        gw = s.get("gw", 0)
        vp = s.get("vp", 0)
        return f"\n**Top 5 cutoff score:** {gw}GW {vp}VP"

    limit = {"Top 10": 10, "Public": len(standings)}.get(standings_mode, 0)
    if limit == 0:
        return ""

    label = "Top 10" if standings_mode == "Top 10" else "Standings"
    lines = [f"\n**{label}:**"]
    for i, s in enumerate(standings[:limit]):
        display = _player_display(s.get("user_uid", ""), players)
        gw = s.get("gw", 0)
        vp = s.get("vp", 0)
        tp = s.get("tp", 0)
        lines.append(f"{i + 1}. {display} — {gw}GW {vp}VP {tp}TP")
    return "\n".join(lines)


async def _post(bot, channel_id: int, content: str) -> None:
    """Post a message to a channel, logging failures."""
    try:
        await bot.rest.create_message(channel_id, content)
    except Exception as e:
        logger.warning("Failed to post to channel %s: %s", channel_id, e)


def _player_display(puid: str, players: list) -> str:
    """Get display name for a player UID."""
    p = next((p for p in players if p.get("user_uid") == puid), None)
    if p:
        return p.get("display_name") or puid[:8]
    return puid[:8]


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
    names = [_player_display(uid, players) for uid in unlinked]
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
        lines.append(_format_standings(standings, standings_mode, players))
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
        current_round = rounds[-1]
        tables_data: list[list[str]] = []

        lines = [f"**Round {round_count} — Seating**\n"]
        for ti, table in enumerate(current_round):
            seating = table.get("seating", [])
            player_uids = [s.get("player_uid", "") for s in seating]
            tables_data.append(player_uids)
            seat_names = [_player_display(uid, players) for uid in player_uids]
            lines.append(f"**Table {ti + 1}**: {' → '.join(seat_names)}")

        lines.append(
            "\nJoin your table's voice channel and use `/report` when the round ends."
        )
        await _post(bot, announcement_id, "\n".join(lines))

        # Build discord_id_map for all players + organizers
        all_player_uids = {uid for table in tables_data for uid in table}
        discord_id_map = await _build_discord_id_map(
            store, all_player_uids | organizer_uids
        )

        # Create table voice channels with permissions
        try:
            channel_ids = await create_table_channels(
                bot,
                int(guild_id),
                category_id,
                tables_data,
                discord_id_map=discord_id_map,
                organizer_uids=organizer_uids,
            )
            _table_channels[key] = channel_ids
        except Exception as e:
            logger.warning("Failed to create table channels: %s", e)

        # Track seating for mid-round change detection
        _last_seating[key] = [set(t) for t in tables_data]

        # Warn about unlinked players
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

    # ── Finals started ──
    finals = obj.get("finals")
    if finals and state == "Playing" and prev_state != "Playing":
        seating = finals.get("seating", [])
        seed_order = finals.get("seed_order", [])

        lines = [f"**Finals — {name}**\n"]
        lines.append("Seating order (prey → predator):")
        for i, s in enumerate(seating):
            uid = s.get("player_uid", "")
            display = _player_display(uid, players)
            seed = seed_order.index(uid) + 1 if uid in seed_order else "?"
            lines.append(f"  {i + 1}. {display} (seed #{seed})")

        lines.append("\nJoin the Finals voice channel. Good luck!")
        await _post(bot, announcement_id, "\n".join(lines))

        finalists = [[s.get("player_uid", "") for s in seating]]
        finalist_uids = {s.get("player_uid", "") for s in seating}

        # Build discord_id_map for finalists + organizers
        discord_id_map = await _build_discord_id_map(
            store, finalist_uids | organizer_uids
        )

        try:
            ch_ids = await create_table_channels(
                bot,
                int(guild_id),
                category_id,
                finalists,
                discord_id_map=discord_id_map,
                organizer_uids=organizer_uids,
                is_finals=True,
            )
            _table_channels[key].extend(ch_ids)
        except Exception as e:
            logger.warning("Failed to create finals channel: %s", e)

        # Warn about unlinked finalists
        await _warn_unlinked_players(
            bot, judges_id, finalist_uids, discord_id_map, players
        )

        await _post(
            bot,
            judges_id,
            f"**{name}** — Finals started ({len(seating)} finalists).\n{webapp_url}",
        )

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
                    _player_display(s.get("player_uid", ""), players)
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
            winner_name = _player_display(winner, players)
            lines.append(f"Congratulations to the winner: **{winner_name}**!")

        lines.append(_format_standings(standings, standings_mode, players))
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


_SANCTION_LEVEL_LABELS = {
    "caution": "Caution",
    "warning": "Warning",
    "standings_adjustment": "Standings Adjustment",
    "disqualification": "Disqualification",
}

_SANCTION_LEVEL_EMOJI = {
    "caution": "\u26a0\ufe0f",  # ⚠️
    "warning": "\U0001f7e0",  # 🟠
    "standings_adjustment": "\U0001f7e3",  # 🟣
    "disqualification": "\U0001f534",  # 🔴
}


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

    level_label = _SANCTION_LEVEL_LABELS.get(level, level)
    level_emoji = _SANCTION_LEVEL_EMOJI.get(level, "")

    # Try to find the player's Discord mention
    player_discord_id = await store.get_discord_id_by_archon_uid(user_uid)
    player_mention = f"<@{player_discord_id}>" if player_discord_id else user_uid[:8]

    round_info = f" (Round {round_number + 1})" if round_number is not None else ""
    subcategory_info = f" — {subcategory.replace('_', ' ')}" if subcategory else ""

    judges_msg = (
        f"{level_emoji} **{level_label}** issued to {player_mention}{round_info}\n"
        f"Category: {category}{subcategory_info}\n"
        f"_{description}_"
    )

    # Post to judges channel
    try:
        await bot.rest.create_message(judges_id, judges_msg)
    except Exception as e:
        logger.warning("Failed to post sanction to judges: %s", e)

    # Notify the player in the appropriate channel:
    # - If there are active table channels (ongoing round), post to the table
    # - Otherwise, post to lobby
    key = _task_key(guild_id, tournament_uid)
    table_chs = _table_channels.get(key, [])
    player_msg = (
        f"{level_emoji} {player_mention} received a **{level_label}**{round_info}\n"
        f"_{description}_"
    )

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
        await bot.rest.create_message(
            judges_id,
            f"**Judge call!** {table_label} — {player_name} needs a judge",
        )
    except Exception as e:
        logger.warning("Failed to post judge call: %s", e)
