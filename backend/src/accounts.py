"""Account surgery: merge (join), detach (split), and the reassignment helpers.

db.py cannot import broadcast (layering), so each function here returns the
BroadcastData for every synced row it changes and the calling route broadcasts it.
"""

from datetime import UTC, datetime
from uuid import uuid7

import msgspec

from .db import (
    BroadcastData,
    clear_calendar_token,
    decode_json,
    encode_json,
    get_calendar_token,
    get_connection,
    get_sanctions_for_user,
    get_user_by_uid,
    save_object_from_model,
    save_sanction,
    save_user,
    soft_delete_user,
)
from .models import AuthMethod, DeckObject, ObjectType, SanctionLevel, User
from .ratings import recompute_wins


async def reassign_auth_methods(from_user_uid: str, to_user_uid: str) -> int:
    async with get_connection() as conn:
        result = await conn.execute(
            "SELECT data FROM auth_methods WHERE data->>'user_uid' = %s",
            (from_user_uid,),
        )
        rows = await result.fetchall()

        count = 0
        for row in rows:
            auth_method = decode_json(row[0], AuthMethod)
            updated = AuthMethod(
                uid=auth_method.uid,
                modified=auth_method.modified,
                user_uid=to_user_uid,
                method_type=auth_method.method_type,
                identifier=auth_method.identifier,
                credential_hash=auth_method.credential_hash,
                verified=auth_method.verified,
                created_at=auth_method.created_at,
                last_used_at=auth_method.last_used_at,
            )
            await conn.execute(
                "UPDATE auth_methods SET data = %s WHERE uid = %s",
                (encode_json(updated), auth_method.uid),
            )
            count += 1

        return count


async def reassign_sanctions(
    from_user_uid: str, to_user_uid: str
) -> list[BroadcastData]:
    sanctions = await get_sanctions_for_user(from_user_uid)
    broadcasts = []
    for sanction in sanctions:
        updated = msgspec.structs.replace(sanction, user_uid=to_user_uid)
        broadcasts.append(await save_sanction(updated))
    return broadcasts


async def reassign_decks(from_user_uid: str, to_user_uid: str) -> list[BroadcastData]:
    async with get_connection() as conn:
        result = await conn.execute(
            """SELECT "full"::text FROM objects
            WHERE type = 'deck' AND "full"->>'user_uid' = %s""",
            (from_user_uid,),
        )
        rows = await result.fetchall()
    broadcasts = []
    for row in rows:
        deck = msgspec.json.decode(row[0].encode(), type=DeckObject)
        broadcasts.append(
            await save_object_from_model(
                ObjectType.DECK, msgspec.structs.replace(deck, user_uid=to_user_uid)
            )
        )
    return broadcasts


async def reassign_coopted_by_references(
    from_user_uid: str, to_user_uid: str
) -> list[BroadcastData]:
    async with get_connection() as conn:
        result = await conn.execute(
            """SELECT "full" FROM objects
            WHERE type = 'user' AND "full"->>'coopted_by' = %s""",
            (from_user_uid,),
        )
        rows = await result.fetchall()

    broadcasts = []
    for row in rows:
        user = decode_json(row[0], User)
        user.coopted_by = to_user_uid
        broadcasts.append(await save_user(user))

    return broadcasts


async def merge_users(
    keep_uid: str, delete_uid: str
) -> tuple[User, list[BroadcastData]] | None:
    """Returns (merged_user, broadcasts), or None if keep_uid doesn't exist."""
    keep_user = await get_user_by_uid(keep_uid)
    delete_user_obj = await get_user_by_uid(delete_uid)

    if not keep_user:
        return None
    if keep_uid == delete_uid:
        return keep_user, []
    if not delete_user_obj:
        return keep_user, []
    # A uid holding a vekn_id is immovable and never soft-deleted — this is the one
    # chokepoint enforcing it for callers (admin, discord-link) that don't guarantee it structurally.
    if delete_user_obj.vekn_id:
        raise ValueError(
            "Cannot merge an account that holds a VEKN ID — VEKN identities are "
            "immovable and are never merged away (keep the VEKN account as the survivor)"
        )

    # calendar_token lives outside "full", read explicitly; prefer the
    # claiming account's feed, like the contact fields below.
    merged_calendar_token = await get_calendar_token(
        delete_uid
    ) or await get_calendar_token(keep_uid)

    # msgspec.structs.replace keeps every unlisted field; only fields with a
    # real merge policy are overridden below.
    merged = msgspec.structs.replace(
        keep_user,
        name=keep_user.name or delete_user_obj.name,
        country=keep_user.country or delete_user_obj.country,
        vekn_id=keep_user.vekn_id or delete_user_obj.vekn_id,
        city=keep_user.city or delete_user_obj.city,
        city_geoname_id=keep_user.city_geoname_id or delete_user_obj.city_geoname_id,
        state=keep_user.state or delete_user_obj.state,
        nickname=delete_user_obj.nickname or keep_user.nickname,
        roles=list(set(keep_user.roles) | set(delete_user_obj.roles)),
        avatar_path=delete_user_obj.avatar_path or keep_user.avatar_path,
        contact_email=delete_user_obj.contact_email or keep_user.contact_email,
        contact_discord=delete_user_obj.contact_discord or keep_user.contact_discord,
        discord_id=delete_user_obj.discord_id or keep_user.discord_id,
        contact_phone=delete_user_obj.contact_phone or keep_user.contact_phone,
        phone_is_whatsapp=delete_user_obj.phone_is_whatsapp
        or keep_user.phone_is_whatsapp,
        community_links=keep_user.community_links or delete_user_obj.community_links,
        coopted_by=keep_user.coopted_by or delete_user_obj.coopted_by,
        coopted_at=keep_user.coopted_at or delete_user_obj.coopted_at,
        vekn_synced=keep_user.vekn_synced or delete_user_obj.vekn_synced,
        vekn_synced_at=keep_user.vekn_synced_at or delete_user_obj.vekn_synced_at,
        local_modifications=keep_user.local_modifications
        | delete_user_obj.local_modifications,
        vekn_prefix=keep_user.vekn_prefix or delete_user_obj.vekn_prefix,
        calendar_token=merged_calendar_token,
    )

    merged_bd = await save_user(merged)
    # auth_methods aren't synced (no SSE); the rest are — collect their
    # BroadcastData too.
    await reassign_auth_methods(delete_uid, keep_uid)
    broadcasts = [merged_bd]
    broadcasts += await reassign_sanctions(delete_uid, keep_uid)
    broadcasts += await reassign_decks(delete_uid, keep_uid)
    # A reassigned deck can carry a Hall of Fame place, so the derived win count
    # follows it. Rebind `merged`, or the route answers the pre-recompute list.
    for recomputed, bd in await recompute_wins({keep_uid}):
        merged = recomputed
        broadcasts.append(bd)
    broadcasts += await reassign_coopted_by_references(delete_uid, keep_uid)
    deleted = await soft_delete_user(delete_uid)
    if deleted:
        broadcasts.append(deleted[1])
    return merged, broadcasts


async def user_has_active_suspension(user_uid: str) -> bool:
    """True if the user holds an active (non-lifted, unexpired) suspension or
    probation — blocks self-abandon of a VEKN ID."""
    now = datetime.now(UTC)
    for s in await get_sanctions_for_user(user_uid):
        if s.deleted_at is not None or s.lifted_at is not None:
            continue
        if s.level not in (SanctionLevel.SUSPENSION, SanctionLevel.PROBATION):
            continue
        if s.expires_at is None or s.expires_at > now:
            return True
    return False


async def detach_user_from_vekn(
    user_uid: str,
) -> tuple[User, User, list[BroadcastData]] | None:
    """Split into (personal_account, vekn_record, broadcasts), or None if not found.

    vekn_record keeps the uid and everything keyed to it. A new personal/login
    field must be added to the null-list on vekn_record below, or it leaks onto
    the record for the next claimant; a new field keyed to the uid must be added
    to the clear-list on personal, or the split copies it onto an account that
    holds none of it.
    """
    user = await get_user_by_uid(user_uid)
    if not user:
        return None

    new_uid = str(uuid7())
    now = datetime.now(UTC)

    # calendar_token lives outside "full"; carry it to the personal account so the
    # existing .ics URL resolves, clearing the orphan's first so it's never duplicated.
    feed_token = await get_calendar_token(user_uid)
    await clear_calendar_token(user_uid)

    personal = msgspec.structs.replace(
        user,
        uid=new_uid,
        modified=now,
        vekn_id=None,
        roles=[],
        coopted_by=None,
        coopted_at=None,
        vekn_synced=False,
        vekn_synced_at=None,
        local_modifications=set(),
        vekn_prefix=None,
        community_links=[],
        promo_stock={},
        calendar_token=feed_token,
        constructed_online=None,
        constructed_offline=None,
        limited_online=None,
        limited_offline=None,
        wins=[],
    )
    personal_bd = await save_user(personal)
    await reassign_auth_methods(user_uid, new_uid)

    # Sanctions/decks are NOT reassigned — they key on this stable uid.
    # calendar_token=None here is a no-op via COALESCE (already cleared above).
    vekn_record = msgspec.structs.replace(
        user,
        modified=now,
        nickname=None,
        avatar_path=None,
        contact_email=None,
        contact_discord=None,
        discord_id=None,
        github_login=None,
        github_id=None,
        contact_phone=None,
        phone_is_whatsapp=False,
        calendar_token=None,
        local_modifications=set(),
    )
    vekn_bd = await save_user(vekn_record)

    return personal, vekn_record, [personal_bd, vekn_bd]
