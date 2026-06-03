"""Discord channel creation and permission management."""

import logging

import hikari

logger = logging.getLogger(__name__)

PLAYER_ALLOW = hikari.Permissions.CONNECT | hikari.Permissions.SPEAK


async def create_tournament_channels(
    bot: hikari.GatewayBot,
    guild_id: int,
    tournament_name: str,
) -> dict:
    """Create tournament channels (category, announcement, lobby, judges).

    Returns dict with channel IDs.
    """
    guild = await bot.rest.fetch_guild(guild_id)
    me = guild.get_my_member() or await bot.rest.fetch_my_member(guild_id)

    # Create category
    category = await bot.rest.create_guild_category(
        guild_id,
        name=f"Tournament: {tournament_name[:50]}",
    )

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
            called right after channel creation with known-empty overrides).
    """
    allowed_uids = player_uids | organizer_uids
    desired_discord_ids: set[int] = set()
    for uid in allowed_uids:
        did = discord_id_map.get(uid)
        if did:
            desired_discord_ids.add(did)

    if current_member_ids is None:
        # Fetch current overrides
        channel = await bot.rest.fetch_channel(channel_id)
        current_overrides = getattr(channel, "permission_overwrites", {})
        # Find current member overrides (skip role overrides like @everyone)
        current_member_ids = set()
        for ov in current_overrides.values():
            if ov.type == hikari.PermissionOverwriteType.MEMBER:
                current_member_ids.add(int(ov.id))

    # Remove stale overrides
    stale = current_member_ids - desired_discord_ids
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


async def create_table_channels(
    bot: hikari.GatewayBot,
    guild_id: int,
    category_id: int,
    tables: list[list[str]],
    discord_id_map: dict[str, int],
    organizer_uids: set[str] | None = None,
    is_finals: bool = False,
    start_index: int = 0,
) -> list[int]:
    """Create voice channels for tournament tables, then sync permissions.

    Args:
        tables: List of tables, each containing player archon UIDs
        discord_id_map: Mapping from archon_uid to Discord user ID (int)
        organizer_uids: Set of organizer archon UIDs (get access to all tables)
        is_finals: If True, create a single "Finals" channel
        start_index: Table numbering offset (for adding new tables mid-round)

    Returns list of created channel IDs.
    """
    org_uids = organizer_uids or set()
    channel_ids = []

    if is_finals:
        # Single finals channel with @everyone DENY
        ch = await bot.rest.create_guild_voice_channel(
            guild_id,
            name="Finals",
            category=category_id,
            permission_overwrites=[
                hikari.PermissionOverwrite(
                    id=guild_id,
                    type=hikari.PermissionOverwriteType.ROLE,
                    deny=hikari.Permissions.CONNECT,
                ),
            ],
        )
        channel_ids.append(ch.id)
        # All finalists across all tables
        all_players = {uid for table in tables for uid in table}
        # Freshly created: only @everyone role override, no member overrides
        await sync_table_permissions(
            bot,
            guild_id,
            ch.id,
            all_players,
            org_uids,
            discord_id_map,
            current_member_ids=set(),
        )
    else:
        for i, table in enumerate(tables):
            table_num = start_index + i + 1
            ch = await bot.rest.create_guild_voice_channel(
                guild_id,
                name=f"Table {table_num}",
                category=category_id,
                permission_overwrites=[
                    hikari.PermissionOverwrite(
                        id=guild_id,
                        type=hikari.PermissionOverwriteType.ROLE,
                        deny=hikari.Permissions.CONNECT,
                    ),
                ],
            )
            channel_ids.append(ch.id)
            # Freshly created: only @everyone role override, no member overrides
            await sync_table_permissions(
                bot,
                guild_id,
                ch.id,
                set(table),
                org_uids,
                discord_id_map,
                current_member_ids=set(),
            )

    return channel_ids


async def delete_channels(
    bot: hikari.GatewayBot,
    channel_ids: list[int],
) -> None:
    """Delete a list of channels, ignoring already-deleted ones."""
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
) -> None:
    """Delete all channels in a tournament category, then the category itself."""
    try:
        channels = await bot.rest.fetch_guild_channels(guild_id)
        for ch in channels:
            if getattr(ch, "parent_id", None) == category_id:
                try:
                    await bot.rest.delete_channel(ch.id)
                except Exception as e:
                    logger.warning("Failed to delete channel %s: %s", ch.id, e)
        await bot.rest.delete_channel(category_id)
    except hikari.NotFoundError:
        pass
    except Exception as e:
        logger.warning("Failed to teardown category %s: %s", category_id, e)
