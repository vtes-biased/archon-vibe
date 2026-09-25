"""Account surgery: merge (join), detach (split), and the reassignment helpers.

db.py cannot import broadcast (layering), so each function here returns the
BroadcastData for every synced row it changes and the calling route broadcasts it.
"""

from datetime import UTC, datetime
from uuid import uuid7

import msgspec

from .broadcast import deck_org_uids
from .db import (
    BroadcastData,
    clear_owner_columns,
    decode_json,
    delete_avatar,
    delete_transient_token,
    encode_json,
    get_agenda,
    get_calendar_token,
    get_connection,
    get_sanctions_for_user,
    get_user_by_uid,
    get_users_by_uids,
    remap_nda_user,
    save_object,
    save_object_from_model,
    save_sanction,
    save_user,
    soft_delete_user,
    tournament_transaction,
)
from .db_oauth import (
    delete_oauth_consent,
    get_oauth_consents_by_user,
    revoke_oauth_tokens_for_user_client,
)
from .models import (
    AuthMethod,
    DeckObject,
    ObjectType,
    SanctionLevel,
    Tournament,
    User,
)
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
            updated = msgspec.structs.replace(auth_method, user_uid=to_user_uid)
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
            """SELECT d."full"::text,
                      coalesce(t."full"->'organizers_uids', '[]'::jsonb),
                      t."full"->>'state'
            FROM objects d
            LEFT JOIN objects t
              ON t.type = 'tournament' AND t.uid = d."full"->>'tournament_uid'
            WHERE d.type = 'deck' AND d."full"->>'user_uid' = %s""",
            (from_user_uid,),
        )
        rows = await result.fetchall()
    broadcasts = []
    for row in rows:
        deck = msgspec.json.decode(row[0].encode(), type=DeckObject)
        bd = await save_object_from_model(
            ObjectType.DECK, msgspec.structs.replace(deck, user_uid=to_user_uid)
        )
        bd.org_uids = deck_org_uids(deck.private, row[2], row[1])
        broadcasts.append(bd)
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
    # chokepoint enforcing it for callers that don't guarantee it structurally.
    if delete_user_obj.vekn_id:
        raise ValueError(
            "Cannot merge an account that holds a VEKN ID — VEKN identities are "
            "immovable and are never merged away (keep the VEKN account as the survivor)"
        )
    if keep_user.anonymized_at:
        raise ValueError("Cannot merge into an anonymized member")

    # calendar_token lives outside "full", read explicitly; prefer the
    # claiming account's feed, like the contact fields below.
    merged_calendar_token = await get_calendar_token(
        delete_uid
    ) or await get_calendar_token(keep_uid)
    claimed_agenda = await get_agenda(delete_uid)
    merged_hidden, merged_added = (
        claimed_agenda if any(claimed_agenda) else await get_agenda(keep_uid)
    )

    if "coopted_by" in keep_user.local_modifications:
        sponsor_side = keep_user
    elif "coopted_by" in delete_user_obj.local_modifications:
        sponsor_side = delete_user_obj
    else:
        sponsor_side = keep_user if keep_user.coopted_by else delete_user_obj

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
        coopted_by=sponsor_side.coopted_by,
        coopted_at=sponsor_side.coopted_at,
        vekn_synced=keep_user.vekn_synced or delete_user_obj.vekn_synced,
        vekn_synced_at=keep_user.vekn_synced_at or delete_user_obj.vekn_synced_at,
        local_modifications=keep_user.local_modifications
        | delete_user_obj.local_modifications,
        vekn_prefix=keep_user.vekn_prefix or delete_user_obj.vekn_prefix,
        calendar_token=merged_calendar_token,
        agenda_hidden=merged_hidden,
        agenda_added=merged_added,
    )

    merged_bd = await save_user(merged)
    # auth_methods aren't synced (no SSE); the rest are — collect their
    # BroadcastData too.
    await reassign_auth_methods(delete_uid, keep_uid)
    await remap_nda_user(delete_uid, keep_uid)
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


UID_KEYED_FIELDS = frozenset(
    {
        "vekn_id",
        "roles",
        "coopted_by",
        "coopted_at",
        "vekn_synced",
        "vekn_synced_at",
        "vekn_prefix",
        "community_links",
        "promo_stock",
        "constructed_online",
        "constructed_offline",
        "limited_online",
        "limited_offline",
        "wins",
    }
)
PERSONAL_FIELDS = frozenset(
    {
        "nickname",
        "avatar_path",
        "contact_email",
        "contact_discord",
        "discord_id",
        "contact_phone",
        "phone_is_whatsapp",
        "github_login",
        "github_id",
    }
)


def _defaults(names: frozenset[str]) -> dict:
    return {
        f.name: (
            f.default_factory()
            if f.default_factory is not msgspec.NODEFAULT
            else f.default
        )
        for f in msgspec.structs.fields(User)
        if f.name in names
    }


async def detach_user_from_vekn(
    user_uid: str,
) -> tuple[User, User, list[BroadcastData]] | None:
    """Split into (personal_account, vekn_record, broadcasts), or None if not found.

    vekn_record keeps the uid and everything keyed to it.
    """
    user = await get_user_by_uid(user_uid)
    if not user:
        return None

    new_uid = str(uuid7())
    now = datetime.now(UTC)

    # calendar_token lives outside "full"; carry it to the personal account so the
    # existing .ics URL resolves, clearing the orphan's first so it's never duplicated.
    feed_token = await get_calendar_token(user_uid)
    agenda_hidden, agenda_added = await get_agenda(user_uid)
    await clear_owner_columns(user_uid)

    personal = msgspec.structs.replace(
        user,
        uid=new_uid,
        modified=now,
        calendar_token=feed_token,
        agenda_hidden=agenda_hidden,
        agenda_added=agenda_added,
        local_modifications=set(),
        **_defaults(UID_KEYED_FIELDS),
    )
    personal_bd = await save_user(personal)
    await reassign_auth_methods(user_uid, new_uid)
    # The NDA is the human's contract, not the VEKN record's — it walks away
    # with the personal account, like the login and the calendar feed.
    await remap_nda_user(user_uid, new_uid)

    # Sanctions/decks are NOT reassigned — they key on this stable uid.
    # The owner columns at None are a no-op via COALESCE (already cleared above).
    vekn_record = msgspec.structs.replace(
        user,
        modified=now,
        calendar_token=None,
        agenda_hidden=None,
        agenda_added=None,
        local_modifications=set(),
        **_defaults(PERSONAL_FIELDS),
    )
    vekn_bd = await save_user(vekn_record)

    return personal, vekn_record, [personal_bd, vekn_bd]


ANONYMIZED_NAME = "Anonymized member"
ANONYMIZED_FIELDS = PERSONAL_FIELDS | {
    "name",
    "city",
    "city_geoname_id",
    "state",
    "community_links",
}


def _scrub(tournament: Tournament, anonymized_uids: set[str]) -> bool:
    changed = False
    for player in tournament.players:
        if player.user_uid in anonymized_uids and player.display_name:
            player.display_name = None
            changed = True
    for announcement in tournament.announcements:
        if (
            announcement.author_uid in anonymized_uids
            and announcement.author_name != ANONYMIZED_NAME
        ):
            announcement.author_name = ANONYMIZED_NAME
            changed = True
    return changed


async def scrub_anonymized_copies(tournament: Tournament) -> None:
    uids = {p.user_uid for p in tournament.players if p.user_uid and p.display_name}
    uids |= {a.author_uid for a in tournament.announcements}
    if not uids:
        return
    users = await get_users_by_uids(uids)
    _scrub(tournament, {uid for uid, u in users.items() if u.anonymized_at})


async def _scrub_tournament_copies(user_uid: str) -> list[BroadcastData]:
    async with get_connection() as conn:
        result = await conn.execute(
            """SELECT uid FROM objects WHERE type = 'tournament' AND (
                "full"->'players' @> jsonb_build_array(jsonb_build_object('user_uid', %(u)s::text))
                OR "full"->'announcements'
                    @> jsonb_build_array(jsonb_build_object('author_uid', %(u)s::text))
            )""",
            {"u": user_uid},
        )
        uids = [row[0] for row in await result.fetchall()]
    broadcasts = []
    for uid in uids:
        async with tournament_transaction(uid) as (tournament, tx_conn):
            if tournament is None or not _scrub(tournament, {user_uid}):
                continue
            tournament.modified = datetime.now(UTC)
            broadcasts.append(
                await save_object(
                    ObjectType.TOURNAMENT,
                    tournament.uid,
                    msgspec.to_builtins(tournament),
                    conn=tx_conn,
                )
            )
    return broadcasts


async def anonymize_user(user: User, by_uid: str) -> tuple[User, list[BroadcastData]]:
    """The user row is saved last: until it carries anonymized_at
    nothing is marked done, so a failure midway is retried whole."""
    async with get_connection() as conn:
        async with conn.transaction():
            await conn.execute(
                "DELETE FROM auth_methods WHERE data->>'user_uid' = %s", (user.uid,)
            )
            await conn.execute(
                "DELETE FROM push_subscriptions WHERE user_uid = %s", (user.uid,)
            )
    for consent in await get_oauth_consents_by_user(user.uid):
        await revoke_oauth_tokens_for_user_client(user.uid, consent.client_id)
        await delete_oauth_consent(user.uid, consent.client_id)
    await delete_transient_token(f"discord_rc:{user.uid}")
    await delete_avatar(user.uid)
    await clear_owner_columns(user.uid)
    broadcasts = await _scrub_tournament_copies(user.uid)

    now = datetime.now(UTC)
    anonymized = msgspec.structs.replace(
        user,
        modified=now,
        anonymized_at=now,
        anonymized_by_uid=by_uid,
        local_modifications=user.local_modifications | ANONYMIZED_FIELDS,
        **(_defaults(ANONYMIZED_FIELDS) | {"name": ANONYMIZED_NAME}),
    )
    broadcasts.append(await save_user(anonymized))
    return anonymized, broadcasts
