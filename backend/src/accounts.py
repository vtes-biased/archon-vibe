"""Account surgery: merge (join), detach (split), and the reassignment helpers.

These operations move data between user accounts. They build on the plain CRUD in
db.py (one-way import — db.py never calls back here, so there is no cycle). Each
returns the BroadcastData for every synced row it changes so the calling route can
push the change to other clients' caches live; db.py can't import broadcast
(layering), so the route does the broadcasting.
"""

from datetime import UTC, datetime

import msgspec
from uuid6 import uuid7

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


async def reassign_auth_methods(from_user_uid: str, to_user_uid: str) -> int:
    """Reassign all auth methods from one user to another. Returns count updated."""
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
    """Reassign all sanctions from one user to another.

    Returns the BroadcastData for each moved sanction so the caller can push the
    new user_uid to other clients' caches live, not only on reconnect (pst #78).
    """
    sanctions = await get_sanctions_for_user(from_user_uid)
    broadcasts = []
    for sanction in sanctions:
        updated = msgspec.structs.replace(sanction, user_uid=to_user_uid)
        broadcasts.append(await save_sanction(updated))
    return broadcasts


async def reassign_decks(from_user_uid: str, to_user_uid: str) -> list[BroadcastData]:
    """Reassign all decks from one user to another.

    Returns the BroadcastData for each moved deck so the caller can push the new
    user_uid to other clients' caches live, not only on reconnect (pst #78).
    """
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
    """Repoint every user whose coopted_by references from_user_uid to to_user_uid.

    Returns the BroadcastData for each repointed user so the caller can push the
    change to other clients' caches live, not only on reconnect (pst #78).
    """
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
    """Merge two user accounts.

    Transfers all auth methods from delete_uid to keep_uid,
    merges user data (preferring non-empty values from keep_uid),
    reassigns sanctions and coopted_by references,
    then deletes the duplicate account.

    Returns (merged_user, broadcasts) or None if keep_uid doesn't exist.
    `broadcasts` are the BroadcastData for every synced row this changes — the
    survivor's update, the reassigned sanctions/decks/coopted-by users, and the
    dying account's soft-delete; the caller must `broadcast_precomputed` each so
    other clients update their cached copies live, not only on their next
    reconnect (db.py can't import broadcast — layering — so the route does it).
    pst #66 (survivor + soft-delete) / #78 (reassigned objects).
    """
    keep_user = await get_user_by_uid(keep_uid)
    delete_user_obj = await get_user_by_uid(delete_uid)

    if not keep_user:
        return None
    if keep_uid == delete_uid:
        return keep_user, []  # Same account — nothing to merge
    if not delete_user_obj:
        return keep_user, []  # Nothing to merge
    # #59 invariant: a uid carrying a vekn_id is immovable and is NEVER
    # soft-deleted. merge soft-deletes delete_uid, so the absorbed account must
    # not hold a VEKN ID — which also forbids merging two VEKN identities.
    # /claim and /link structurally guarantee delete has no vekn_id; admin and
    # discord-link do not, so this is the single chokepoint. A non-VEKN account
    # can't be a tournament participant/organizer (engine requires a VEKN ID),
    # so this guarantees the soft-deleted account leaves no orphaned tournament
    # refs — the reason the deeper cross-tournament remap is unnecessary (pst #77).
    if delete_user_obj.vekn_id:
        raise ValueError(
            "Cannot merge an account that holds a VEKN ID — VEKN identities are "
            "immovable and are never merged away (keep the VEKN account as the survivor)"
        )

    # calendar_token is stripped from "full", so read it from its column
    # (prefer the claiming/delete account's feed, like the contact fields below).
    merged_calendar_token = await get_calendar_token(
        delete_uid
    ) or await get_calendar_token(keep_uid)

    # Merge from keep_user as the base so every field survives by default
    # (identity, roles, ratings, wins, resync_after, and any future field) —
    # building User(...) from scratch silently dropped unlisted fields. Only the
    # fields with a real merge policy are overridden below: identity prefers
    # keep_user, contact info prefers delete_user (the claiming account),
    # roles/local_modifications union.
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
    # Everything keyed to the dying delete_uid must migrate to the survivor.
    # auth_methods aren't synced objects (no SSE); the rest are, so collect their
    # BroadcastData too (pst #78) — reassigned sanctions/decks/coopted-by users
    # otherwise stay stale on other clients until reconnect.
    await reassign_auth_methods(delete_uid, keep_uid)
    broadcasts = [merged_bd]
    broadcasts += await reassign_sanctions(delete_uid, keep_uid)
    broadcasts += await reassign_decks(delete_uid, keep_uid)
    broadcasts += await reassign_coopted_by_references(delete_uid, keep_uid)
    deleted = await soft_delete_user(delete_uid)
    if deleted:
        broadcasts.append(deleted[1])
    return merged, broadcasts


async def user_has_active_suspension(user_uid: str) -> bool:
    """True if the user holds an active suspension or probation.

    Active = not soft-deleted, not lifted, and either permanent (no expiry) or
    not yet expired. Used to block self-abandon of a VEKN ID (you can't abandon
    your way out of a suspension — see .pst/details/59-vekn-detach.md).
    """
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
    """Detach a person from their VEKN record (the strip/split operation).

    Splits one account into two. The original record is **immovable**: it keeps
    its uid and vekn_id plus everything keyed to that uid — roles, cooptation,
    prefix, ratings, wins, community_links, and (untouched, because they key on
    uid) sanctions, decks and tournament results. Only the human moves: a fresh
    uid carrying the login (auth methods) and personal/contact data.

    Used both to displace a holder before re-linking the VEKN ID to someone else
    (caller then merges the freed record into the new owner) and to abandon a
    VEKN ID (record left orphaned for a future claim). The two flows are
    identical here; their only difference (the re-merge) lives in the caller.
    See .pst/details/59-vekn-detach.md for the full rule.

    Returns (personal_account, vekn_record, broadcasts) or None if the user is
    not found. `broadcasts` are the BroadcastData for the new personal account
    and the nulled vekn_record; the caller must `broadcast_precomputed` each so
    other clients drop the moved-out PII (e.g. the orphan's now-nulled
    discord_id/contacts) live, not only on their next reconnect (db.py can't
    import broadcast — layering — so the route does it). pst #66.

    Adding a User field: only null it on `vekn_record` (and let it ride on
    `personal`) if it is genuinely personal/login data; otherwise leave it on
    `vekn_record` and null it on `personal` — the safe default is that VEKN
    history never follows the person.
    """
    user = await get_user_by_uid(user_uid)
    if not user:
        return None

    new_uid = str(uuid7())
    now = datetime.now(UTC)

    # The human's .ics feed follows the human: calendar_token lives in a dedicated
    # column (stripped from "full"), so read it explicitly and carry it to the new
    # personal account — their existing subscription URL keeps resolving. Same as
    # merge_users; clear it on the orphan first so the token is never duplicated.
    feed_token = await get_calendar_token(user_uid)
    await clear_calendar_token(user_uid)

    # The person walks away with login + personal data only — no VEKN identity,
    # roles, cooptation, official links, ratings or wins.
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
        calendar_token=feed_token,
        constructed_online=None,
        constructed_offline=None,
        limited_online=None,
        limited_offline=None,
        wins=[],
    )
    personal_bd = await save_user(personal)
    await reassign_auth_methods(user_uid, new_uid)

    # The VEKN record keeps everything; only the PII that moved out is wiped.
    # Sanctions and decks are NOT reassigned — they key on this stable uid.
    # (calendar_token already cleared above; the None here is a no-op via COALESCE.)
    vekn_record = msgspec.structs.replace(
        user,
        modified=now,
        nickname=None,
        avatar_path=None,
        contact_email=None,
        contact_discord=None,
        discord_id=None,
        contact_phone=None,
        phone_is_whatsapp=False,
        calendar_token=None,
        local_modifications=set(),
    )
    vekn_bd = await save_user(vekn_record)

    return personal, vekn_record, [personal_bd, vekn_bd]
