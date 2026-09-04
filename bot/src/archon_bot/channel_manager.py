import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass

import hikari

logger = logging.getLogger(__name__)

PLAYER_ALLOW = hikari.Permissions.CONNECT | hikari.Permissions.SPEAK
# A channel overwrite overrides the bot's server-level grant, so without its own
# CONNECT allow here the bot denies itself CONNECT — and Discord requires CONNECT
# to DELETE a voice channel, so /teardown 403s (50001) on its own tables.
BOT_ALLOW = hikari.Permissions.CONNECT | hikari.Permissions.SEND_MESSAGES

# @everyone must neither see nor join #judges; organizers win VIEW+CONNECT back.
JUDGE_DENY = hikari.Permissions.VIEW_CHANNEL | hikari.Permissions.CONNECT
JUDGE_ALLOW = hikari.Permissions.VIEW_CHANNEL | hikari.Permissions.CONNECT
JUDGES_BOT_ALLOW = JUDGE_ALLOW | hikari.Permissions.SEND_MESSAGES

# The legacy unprefixed "Table {m}" form is still matched so tournaments
# mid-flight when the round prefix shipped are discovered/cleaned correctly.
_TABLE_NAME_RE = re.compile(r"^(?:R\d+ - )?Table (\d+)$")


def _table_channel_name(table_num: int, round_number: int | None) -> str:
    if round_number is not None:
        return f"R{round_number} - Table {table_num}"
    return f"Table {table_num}"


@dataclass(frozen=True)
class DesiredChannel:
    """Matched/diffed by ``name``. ``member_uids`` is the CONNECT+SPEAK allow-set
    over the constant ``@everyone DENY CONNECT`` baseline."""

    name: str
    member_uids: frozenset[str]


def _seat_uids(seating: Iterable[dict]) -> frozenset[str]:
    return frozenset(s.get("player_uid", "") for s in seating) - {""}


def desired_channels(obj: dict) -> list[DesiredChannel]:
    """Reconcile's goal set. An empty return (not ``Playing``) means every
    matching Discord channel gets torn down; a seated finals table keeps its
    channel until then, whatever its own state."""
    if obj.get("state") != "Playing":
        return []
    organizer_uids = frozenset(obj.get("organizers_uids", []))
    finals = obj.get("finals") or {}
    finals_seating = finals.get("seating")
    if finals_seating:
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
    """Keyed on full member sets, NOT table count — a same-size seat swap must
    still flip it. Also keyed on the organizer set directly: #judges tracks it
    in every state, not just Playing."""
    return (
        frozenset(obj.get("organizers_uids", [])),
        tuple((dc.name, dc.member_uids) for dc in desired_channels(obj)),
    )


async def create_tournament_channels(
    bot: hikari.GatewayBot,
    guild_id: int,
    tournament_name: str,
    organizer_discord_id: int,
) -> dict:
    """``organizer_discord_id`` (the /setup runner) is granted on the private
    #judges channel; other organizers sync in on every reconcile."""
    logger.info("Creating tournament channels in guild=%s", guild_id)
    guild = await bot.rest.fetch_guild(guild_id)
    me = guild.get_my_member() or await bot.rest.fetch_my_member(guild_id)

    category = await bot.rest.create_guild_category(
        guild_id,
        name=f"Tournament: {tournament_name[:50]}",
    )
    logger.info("✓ created tournament category id=%s", category.id)

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

    lobby = await bot.rest.create_guild_text_channel(
        guild_id,
        name="lobby",
        category=category.id,
    )

    judges = await bot.rest.create_guild_voice_channel(
        guild_id,
        name="judges",
        category=category.id,
        permission_overwrites=[
            hikari.PermissionOverwrite(
                id=guild_id,  # @everyone
                type=hikari.PermissionOverwriteType.ROLE,
                deny=JUDGE_DENY,
            ),
            hikari.PermissionOverwrite(
                id=me.id,
                type=hikari.PermissionOverwriteType.MEMBER,
                allow=JUDGES_BOT_ALLOW,
            ),
            hikari.PermissionOverwrite(
                id=organizer_discord_id,
                type=hikari.PermissionOverwriteType.MEMBER,
                allow=JUDGE_ALLOW,
            ),
        ],
    )

    return {
        "category_id": str(category.id),
        "announcement_channel_id": str(announcement.id),
        "lobby_channel_id": str(lobby.id),
        "judges_channel_id": str(judges.id),
    }


def member_override_ids(channel: object) -> set[int]:
    overrides = getattr(channel, "permission_overwrites", None) or {}
    return {
        int(ov.id)
        for ov in overrides.values()
        if ov.type == hikari.PermissionOverwriteType.MEMBER
    }


async def sync_table_permissions(
    bot: hikari.GatewayBot,
    channel_id: int,
    member_uids: frozenset[str] | set[str],
    discord_id_map: dict[str, int],
    current_member_ids: set[int],
) -> None:
    desired_discord_ids = {
        discord_id_map[uid] for uid in member_uids if discord_id_map.get(uid)
    }
    await sync_member_overrides(
        bot, channel_id, desired_discord_ids, current_member_ids, PLAYER_ALLOW
    )


async def sync_member_overrides(
    bot: hikari.GatewayBot,
    channel_id: int,
    desired_discord_ids: set[int],
    current_member_ids: set[int],
    allow: hikari.Permissions,
) -> None:
    # Never remove the bot's own self-allow: its CONNECT is what lets teardown
    # delete the voice channel, so reconcile must not reap it.
    stale = current_member_ids - desired_discord_ids
    me = bot.get_me()
    if me is not None:
        stale.discard(int(me.id))
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

    missing = desired_discord_ids - current_member_ids
    for did in missing:
        try:
            await bot.rest.edit_permission_overwrite(
                channel_id,
                hikari.Snowflake(did),
                target_type=hikari.PermissionOverwriteType.MEMBER,
                allow=allow,
            )
        except Exception as e:
            logger.warning(
                "Failed to add override for %s on %s: %s", did, channel_id, e
            )


async def sync_judges_channel(
    bot: hikari.GatewayBot,
    guild_id: int,
    channel: object,
    desired_discord_ids: set[int],
) -> None:
    """Also retrofits pre-privacy judges channels missing the deny/allow
    overrides, on their next reconcile."""
    channel_id = int(channel.id)  # type: ignore[attr-defined]
    overrides = getattr(channel, "permission_overwrites", None) or {}

    everyone = overrides.get(guild_id)
    if (
        everyone is None
        or (getattr(everyone, "deny", hikari.Permissions.NONE) & JUDGE_DENY)
        != JUDGE_DENY
    ):
        await bot.rest.edit_permission_overwrite(
            channel_id,
            hikari.Snowflake(guild_id),
            target_type=hikari.PermissionOverwriteType.ROLE,
            deny=JUDGE_DENY,
        )

    me = bot.get_me()
    if me is not None:
        mine = overrides.get(int(me.id))
        if (
            mine is None
            or (getattr(mine, "allow", hikari.Permissions.NONE) & JUDGES_BOT_ALLOW)
            != JUDGES_BOT_ALLOW
        ):
            await bot.rest.edit_permission_overwrite(
                channel_id,
                hikari.Snowflake(me.id),
                target_type=hikari.PermissionOverwriteType.MEMBER,
                allow=JUDGES_BOT_ALLOW,
            )

    await sync_member_overrides(
        bot,
        channel_id,
        desired_discord_ids,
        member_override_ids(channel),
        JUDGE_ALLOW,
    )


async def create_round_voice_channel(
    bot: hikari.GatewayBot,
    guild_id: int,
    category_id: int,
    name: str,
    member_uids: frozenset[str] | set[str],
    discord_id_map: dict[str, int],
) -> int:
    logger.info("→ create_guild_voice_channel '%s' guild=%s", name, guild_id)
    overwrites = [
        hikari.PermissionOverwrite(
            id=guild_id,
            type=hikari.PermissionOverwriteType.ROLE,
            deny=hikari.Permissions.CONNECT,
        ),
    ]
    me = bot.get_me()
    if me is not None:
        overwrites.append(
            hikari.PermissionOverwrite(
                id=me.id,
                type=hikari.PermissionOverwriteType.MEMBER,
                allow=BOT_ALLOW,
            )
        )
    ch = await bot.rest.create_guild_voice_channel(
        guild_id,
        name=name,
        category=category_id,
        permission_overwrites=overwrites,
    )
    logger.info("✓ created '%s' id=%s", name, ch.id)
    # Freshly created: only the @everyone and bot overrides exist, so no fetch.
    await sync_table_permissions(
        bot, ch.id, member_uids, discord_id_map, current_member_ids=set()
    )
    return ch.id


def round_channels_by_name(
    channels: Iterable[object], category_id: int
) -> dict[str, object]:
    """Takes an already-fetched list so reconcile reads each survivor's
    ``permission_overwrites`` off the same payload it diffs."""
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
    """The category is deleted only once every child is gone: Discord un-parents
    a survivor to guild root rather than deleting it, so deleting the category
    early would scatter exactly the channels we couldn't remove."""
    under_category: list[int] = []
    try:
        channels = await bot.rest.fetch_guild_channels(guild_id)
        under_category = [
            int(ch.id)
            for ch in channels
            if getattr(ch, "parent_id", None) == category_id
        ]
    except Exception as e:
        logger.warning("Teardown: failed to list channels in guild=%s: %s", guild_id, e)

    failed: list[int] = []
    targets = dict.fromkeys(
        cid
        for cid in (*under_category, *map(int, extra_channel_ids))
        if cid != int(category_id)
    )
    for cid in targets:
        try:
            await bot.rest.delete_channel(cid)
        except hikari.NotFoundError:
            pass
        except Exception as e:
            logger.warning("Teardown: failed to delete channel %s: %s", cid, e)
            failed.append(cid)

    if failed:
        logger.warning(
            "Teardown left %d channel(s) undeleted; keeping category %s as their "
            "anchor: %s",
            len(failed),
            category_id,
            failed,
        )
        return failed

    try:
        await bot.rest.delete_channel(int(category_id))
    except hikari.NotFoundError:
        pass
    except Exception as e:
        logger.warning("Teardown: failed to delete category %s: %s", category_id, e)
        failed.append(int(category_id))
    else:
        logger.info("Teardown removed all channels for category=%s", category_id)
    return failed
