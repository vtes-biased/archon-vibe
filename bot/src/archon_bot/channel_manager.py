"""Discord channel creation and permission management."""

import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass

import hikari

logger = logging.getLogger(__name__)

PLAYER_ALLOW = hikari.Permissions.CONNECT | hikari.Permissions.SPEAK

# Table voice-channel name: round-prefixed "R{n} - Table {m}". The optional
# legacy "Table {m}" form (no prefix) is still matched so tournaments mid-flight
# when this shipped are discovered/cleaned correctly.
_TABLE_NAME_RE = re.compile(r"^(?:R\d+ - )?Table (\d+)$")


def _table_channel_name(table_num: int, round_number: int | None) -> str:
    """Voice-channel name for a prelim table — round-prefixed when known."""
    if round_number is not None:
        return f"R{round_number} - Table {table_num}"
    return f"Table {table_num}"


@dataclass(frozen=True)
class DesiredChannel:
    """A voice channel the tournament state requires, matched/diffed by ``name``.

    ``member_uids`` (seated players ∪ organizers) is the CONNECT+SPEAK allow-set
    over the constant ``@everyone DENY CONNECT`` baseline.
    """

    name: str
    member_uids: frozenset[str]


def _seat_uids(seating: Iterable[dict]) -> frozenset[str]:
    return frozenset(s.get("player_uid", "") for s in seating) - {""}


def desired_channels(obj: dict) -> list[DesiredChannel]:
    """The target round/finals voice-channel set for a state — reconcile's goal.

    Empty unless ``Playing``. With finals seated and no result yet: a single
    ``Finals`` for all finalists ∪ organizers (a finished finals → nothing, so the
    channel is torn down). Otherwise the current round: one ``R{n} - Table {m}`` per
    table, scoped to that table's seated players ∪ organizers.
    """
    if obj.get("state") != "Playing":
        return []
    organizer_uids = frozenset(obj.get("organizers_uids", []))
    finals = obj.get("finals") or {}
    finals_seating = finals.get("seating")
    if finals_seating:
        if finals.get("result"):
            return []
        return [DesiredChannel("Finals", _seat_uids(finals_seating) | organizer_uids)]
    rounds = obj.get("rounds", [])
    if not rounds:
        return []
    round_number = len(rounds)
    return [
        DesiredChannel(
            _table_channel_name(i + 1, round_number),
            _seat_uids(table.get("seating", [])) | organizer_uids,
        )
        for i, table in enumerate(rounds[-1])
    ]


def structure_signature(obj: dict) -> tuple:
    """Hashable digest of the structure-affecting fields — the cheap reconcile guard.

    Keyed on each desired channel's name and full member set (per-table membership,
    organizers, finals/prelim mode), NOT on table count: a same-size seat swap must
    still flip it. Equal between two snapshots ⇒ no reconcile needed.
    """
    return tuple((dc.name, dc.member_uids) for dc in desired_channels(obj))


async def create_tournament_channels(
    bot: hikari.GatewayBot,
    guild_id: int,
    tournament_name: str,
) -> dict:
    """Create tournament channels (category, announcement, lobby, judges).

    Returns dict with channel IDs.
    """
    logger.info("Creating tournament channels in guild=%s", guild_id)
    guild = await bot.rest.fetch_guild(guild_id)
    me = guild.get_my_member() or await bot.rest.fetch_my_member(guild_id)

    # Create category
    category = await bot.rest.create_guild_category(
        guild_id,
        name=f"Tournament: {tournament_name[:50]}",
    )
    logger.info("✓ created tournament category id=%s", category.id)

    # #announcement — read-only for @everyone
    announcement = await bot.rest.create_guild_text_channel(
        guild_id,
        name="announcement",
        category=category.id,
        permission_overwrites=[
            hikari.PermissionOverwrite(
                id=guild_id,  # @everyone
                type=hikari.PermissionOverwriteType.ROLE,
                deny=hikari.Permissions.SEND_MESSAGES,
            ),
            hikari.PermissionOverwrite(
                id=me.id,
                type=hikari.PermissionOverwriteType.MEMBER,
                allow=hikari.Permissions.SEND_MESSAGES,
            ),
        ],
    )

    # #lobby — writable by everyone
    lobby = await bot.rest.create_guild_text_channel(
        guild_id,
        name="lobby",
        category=category.id,
    )

    # #judges — voice channel for judges/organizers
    judges = await bot.rest.create_guild_voice_channel(
        guild_id,
        name="judges",
        category=category.id,
    )

    return {
        "category_id": str(category.id),
        "announcement_channel_id": str(announcement.id),
        "lobby_channel_id": str(lobby.id),
        "judges_channel_id": str(judges.id),
    }


def member_override_ids(channel: object) -> set[int]:
    """Member ids holding an override on an already-fetched channel payload.

    Lets reconcile pass current members to ``sync_table_permissions`` off the
    ``fetch_guild_channels`` payload instead of re-fetching per channel. Role
    overrides (@everyone) are skipped.
    """
    overrides = getattr(channel, "permission_overwrites", None) or {}
    return {
        int(ov.id)
        for ov in overrides.values()
        if ov.type == hikari.PermissionOverwriteType.MEMBER
    }


async def sync_table_permissions(
    bot: hikari.GatewayBot,
    guild_id: int,
    channel_id: int,
    player_uids: set[str],
    organizer_uids: set[str],
    discord_id_map: dict[str, int],
    current_member_ids: set[int] | None = None,
) -> None:
    """Idempotently sync voice channel permissions for a table.

    Sets CONNECT+SPEAK for each player and organizer found in discord_id_map.
    Removes stale member overrides for users no longer at this table.
    Leaves @everyone DENY CONNECT untouched.

    Args:
        current_member_ids: If provided, skip the fetch_channel call (e.g., when
            called right after channel creation with known-empty overrides, or with
            the overwrites already on a ``fetch_guild_channels`` payload).
    """
    allowed_uids = player_uids | organizer_uids
    desired_discord_ids: set[int] = set()
    for uid in allowed_uids:
        did = discord_id_map.get(uid)
        if did:
            desired_discord_ids.add(did)

    if current_member_ids is None:
        channel = await bot.rest.fetch_channel(channel_id)
        current_member_ids = member_override_ids(channel)

    # Remove stale overrides
    stale = current_member_ids - desired_discord_ids
    missing_preview = desired_discord_ids - current_member_ids
    logger.info(
        "Syncing perms channel=%s: +%d -%d members",
        channel_id,
        len(missing_preview),
        len(stale),
    )
    for did in stale:
        try:
            await bot.rest.delete_permission_overwrite(
                channel_id, hikari.Snowflake(did)
            )
        except hikari.NotFoundError:
            pass
        except Exception as e:
            logger.warning(
                "Failed to remove override for %s on %s: %s", did, channel_id, e
            )

    # Add missing overrides
    missing = desired_discord_ids - current_member_ids
    for did in missing:
        try:
            await bot.rest.edit_permission_overwrite(
                channel_id,
                hikari.Snowflake(did),
                target_type=hikari.PermissionOverwriteType.MEMBER,
                allow=PLAYER_ALLOW,
            )
        except Exception as e:
            logger.warning(
                "Failed to add override for %s on %s: %s", did, channel_id, e
            )


async def create_round_voice_channel(
    bot: hikari.GatewayBot,
    guild_id: int,
    category_id: int,
    name: str,
    member_uids: frozenset[str] | set[str],
    discord_id_map: dict[str, int],
) -> int:
    """Create one table/finals voice channel (``@everyone DENY CONNECT`` baseline)
    and grant CONNECT+SPEAK to its members. Returns the new channel id."""
    logger.info("→ create_guild_voice_channel '%s' guild=%s", name, guild_id)
    ch = await bot.rest.create_guild_voice_channel(
        guild_id,
        name=name,
        category=category_id,
        permission_overwrites=[
            hikari.PermissionOverwrite(
                id=guild_id,
                type=hikari.PermissionOverwriteType.ROLE,
                deny=hikari.Permissions.CONNECT,
            ),
        ],
    )
    logger.info("✓ created '%s' id=%s", name, ch.id)
    # Freshly created → only the @everyone override exists, so no fetch needed.
    await sync_table_permissions(
        bot,
        guild_id,
        ch.id,
        set(member_uids),
        set(),
        discord_id_map,
        current_member_ids=set(),
    )
    return ch.id


def round_channels_by_name(
    channels: Iterable[object], category_id: int
) -> dict[str, object]:
    """The volatile round/finals VOICE channels under ``category_id``, keyed by name
    — exactly what reconcile owns (``R{n} - Table {m}``, legacy ``Table {m}``,
    ``Finals``); #judges, text, and foreign-category channels are excluded.

    Takes an already-fetched list so reconcile reads each survivor's
    ``permission_overwrites`` off the same payload it diffs.
    """
    out: dict[str, object] = {}
    for ch in channels:
        if getattr(ch, "parent_id", None) != category_id:
            continue
        if ch.type != hikari.ChannelType.GUILD_VOICE:
            continue
        name = ch.name or ""
        if name == "Finals" or _TABLE_NAME_RE.match(name):
            out[name] = ch
    return out


async def delete_channels(
    bot: hikari.GatewayBot,
    channel_ids: list[int],
) -> None:
    """Delete a list of channels, ignoring already-deleted ones."""
    if channel_ids:
        logger.info("→ deleting %d channel(s): %s", len(channel_ids), channel_ids)
    for cid in channel_ids:
        try:
            await bot.rest.delete_channel(cid)
        except hikari.NotFoundError:
            pass
        except Exception as e:
            logger.warning("Failed to delete channel %s: %s", cid, e)


async def teardown_tournament(
    bot: hikari.GatewayBot,
    guild_id: int,
    category_id: int,
    extra_channel_ids: Iterable[int] = (),
) -> list[int]:
    """Delete a tournament's channels reliably, then the category itself.

    Deletes (by explicit id, deduped) the union of:
      - every channel currently under ``category_id`` — the restart-safe catch-all
        that finds table/finals channels we may have lost track of in memory; and
      - ``extra_channel_ids`` — channels we know belong to this tournament but that
        may have drifted *out* of the category and so are invisible to the scan.
        A child whose delete failed during an earlier teardown is left top-level
        when the category is then removed (Discord un-parents children rather than
        deleting them); the scan, keyed on the now-gone category, can never see it
        again. The caller passes the link's announcement/lobby/judges plus any
        tracked table/finals ids so a re-run still cleans those orphans up.

    The category is deleted LAST so an early category delete never orphans a child
    we were about to remove. Returns the channel ids that could not be deleted
    (excluding ones already gone) so the caller can flag a partial teardown for
    manual cleanup instead of falsely reporting success.
    """
    under_category: list[int] = []
    try:
        channels = await bot.rest.fetch_guild_channels(guild_id)
        under_category = [
            int(ch.id)
            for ch in channels
            if getattr(ch, "parent_id", None) == category_id
        ]
    except Exception as e:
        # Listing failed — still delete the explicitly-known ids below.
        logger.warning("Teardown: failed to list channels in guild=%s: %s", guild_id, e)

    failed: list[int] = []
    # Children + known orphans first; the category itself is handled last.
    targets = dict.fromkeys(
        cid
        for cid in (*under_category, *map(int, extra_channel_ids))
        if cid != int(category_id)
    )
    for cid in (*targets, int(category_id)):
        try:
            await bot.rest.delete_channel(cid)
        except hikari.NotFoundError:
            pass
        except Exception as e:
            logger.warning("Teardown: failed to delete channel %s: %s", cid, e)
            failed.append(cid)

    if failed:
        logger.warning("Teardown left %d channel(s) undeleted: %s", len(failed), failed)
    else:
        logger.info("Teardown removed all channels for category=%s", category_id)
    return failed
