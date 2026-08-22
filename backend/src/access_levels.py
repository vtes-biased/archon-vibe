import base64

from .models import ObjectType, Role

# Reversible, not security — a harvester speed-bump only. Mirror the prefix +
# scheme in the frontend's deobfuscateContact (lib/contact.ts).
_OBFUSCATED_PREFIX = "#b64#"
_PUBLIC_OBFUSCATED_FIELDS = ("contact_email", "contact_phone")


def _obfuscate(value: str) -> str:
    if value.startswith(_OBFUSCATED_PREFIX):
        return value  # already cloaked — never double-encode
    return _OBFUSCATED_PREFIX + base64.b64encode(value.encode("utf-8")).decode("ascii")


def _obfuscate_public_contacts(proj: dict) -> dict:
    for field in _PUBLIC_OBFUSCATED_FIELDS:
        value = proj.get(field)
        if isinstance(value, str) and value:
            proj[field] = _obfuscate(value)
    return proj


_USER_PUBLIC_FIELDS = {
    "uid",
    "modified",
    "deleted_at",
    "name",
    "country",
    "roles",
    "vekn_prefix",
}
_USER_CONTACT_FIELDS = {
    "contact_email",
    "contact_discord",
    "discord_id",
    "contact_phone",
    "phone_is_whatsapp",
}
_USER_COMMUNITY_LINKS = {"community_links"}
_USER_LINKS_ONLY_FIELDS = {
    "uid",
    "modified",
    "deleted_at",
    "country",
    "roles",
    "community_links",
}
_USER_MEMBER_FIELDS = (
    _USER_PUBLIC_FIELDS
    | {"vekn_id", "city", "city_geoname_id", "state", "nickname", "avatar_path"}
    # In-memoriam marker — members see the flag/date (not deceased_by_uid, which
    # is administrative and stays full-only).
    | {"deceased_at"}
    # Not contact info: the bot's judges-channel sync maps organizers through
    # this id, and organizers need no NC/Prince role.
    | {"discord_id"}
    | {
        "constructed_online",
        "constructed_offline",
        "limited_online",
        "limited_offline",
        "wins",
    }
)


API_SYNC_FIELDS = {"modified", "deleted_at"}

USER_API_FIELDS = {
    "uid",
    "vekn_id",
    "country",
    "roles",
    "community_links",
    "constructed_online",
    "constructed_offline",
    "limited_online",
    "limited_offline",
    "wins",
}


def _pick(d: dict, keys: set[str]) -> dict:
    """Return a new dict with only the specified keys (if present in d)."""
    return {k: v for k, v in d.items() if k in keys}


def compute_user_public(d: dict) -> dict | None:
    roles = d.get("roles", [])
    if Role.NC in roles or Role.PRINCE in roles:
        return _obfuscate_public_contacts(
            _pick(d, _USER_PUBLIC_FIELDS | _USER_CONTACT_FIELDS | _USER_COMMUNITY_LINKS)
        )
    if Role.IC in roles:
        return _pick(d, _USER_PUBLIC_FIELDS | _USER_COMMUNITY_LINKS)
    if d.get("community_links"):
        return _pick(d, _USER_LINKS_ONLY_FIELDS)
    return None


def compute_user_member(d: dict) -> dict:
    roles = d.get("roles", [])
    if Role.NC in roles or Role.PRINCE in roles:
        return _pick(
            d, _USER_MEMBER_FIELDS | _USER_CONTACT_FIELDS | _USER_COMMUNITY_LINKS
        )
    if Role.IC in roles:
        return _pick(d, _USER_MEMBER_FIELDS | _USER_COMMUNITY_LINKS)
    if d.get("community_links"):
        return _pick(d, _USER_MEMBER_FIELDS | _USER_COMMUNITY_LINKS)
    return _pick(d, _USER_MEMBER_FIELDS)


def compute_user_api(d: dict) -> dict | None:
    # Matches idx_objects_user_vekn_id, which treats "" as no id.
    if not d.get("vekn_id"):
        return None
    return _pick(d, USER_API_FIELDS)


def compute_user_full(d: dict) -> dict:
    # calendar_token is private, only ever surfaced via /auth/me.
    return {k: v for k, v in d.items() if k != "calendar_token"}


# A missing bool reads as False after JSON — never omit one to withhold it.
_TOURNAMENT_PUBLIC_FIELDS = {
    "uid",
    "modified",
    "deleted_at",
    "name",
    "format",
    "rank",
    "online",
    "start",
    "finish",
    "timezone",
    "country",
    "league_uid",
    "state",
    "banner_path",  # public hero / og:image — visible pre-login
    "venue",
    "venue_url",
    "address",
    "map_url",
    "description",
    "external_ids",  # public ids only (vekn event, legacy archon uid)
    "event_code",  # an anonymous visitor following a short URL must resolve it
    "proxies",
    "multideck",
    "decklist_required",
    "max_rounds",
    "max_players",
    "open_rounds",  # rankedStatus reads it first — else "unranked" can't be shown
    "self_organized_rounds",
}

_TOURNAMENT_MEMBER_EXCLUDE = {
    "checkin_code",
    "vekn_pushed_at",
    "vekn_results_stale",
    "twda_status",
}


TOURNAMENT_API_EXCLUDE = (
    _TOURNAMENT_MEMBER_EXCLUDE
    | API_SYNC_FIELDS
    | {
        "announcements",
        "raffles",
        "promos_distributed",
        "promo_stock_source_uid",
        "offline_device_id",
    }
)
PLAYER_API_EXCLUDE = {"display_name", "payment_status"}


def compute_tournament_public(d: dict) -> dict:
    proj = _pick(d, _TOURNAMENT_PUBLIC_FIELDS)
    # Online event: venue_url is the join link, not a website — withheld same
    # as calendar.py's rendering.
    if d.get("online"):
        proj.pop("venue_url", None)
    return proj


def compute_tournament_member(d: dict) -> dict:
    return {k: v for k, v in d.items() if k not in _TOURNAMENT_MEMBER_EXCLUDE}


def compute_tournament_api(d: dict) -> dict:
    proj = {k: v for k, v in d.items() if k not in TOURNAMENT_API_EXCLUDE}
    # Rebuilt, never popped in place: the nested player dicts are the same
    # objects the member and full projections of this save hand out.
    proj["players"] = [
        {k: v for k, v in player.items() if k not in PLAYER_API_EXCLUDE}
        for player in d["players"]
    ]
    return proj


def compute_tournament_full(d: dict) -> dict:
    return dict(d)


DECK_API_EXCLUDE = API_SYNC_FIELDS | {"author"}


def compute_deck_member(d: dict) -> dict | None:
    if d.get("public"):
        return dict(d)
    return None


def compute_deck_api(d: dict) -> dict | None:
    if d.get("public"):
        return {k: v for k, v in d.items() if k not in DECK_API_EXCLUDE}
    return None


def compute_deck_full(d: dict) -> dict:
    return dict(d)


def compute_league_public(d: dict) -> dict:
    return {k: v for k, v in d.items() if k != "organizers_uids"}


def compute_promo_public(d: dict) -> dict:
    # Not gated on `active` — retired promos must keep resolving for history
    # and raffles; the gallery UI filters client-side.
    return {k: v for k, v in d.items() if k != "holdings"}


def compute_league_api(d: dict) -> dict:
    return {k: v for k, v in d.items() if k not in API_SYNC_FIELDS}


def _identity(d: dict) -> dict:
    return dict(d)


def _invisible(d: dict) -> None:
    return None


_PUBLIC_DISPATCH = {
    ObjectType.USER: compute_user_public,
    ObjectType.TOURNAMENT: compute_tournament_public,
    ObjectType.SANCTION: _invisible,
    ObjectType.DECK: _invisible,
    ObjectType.LEAGUE: compute_league_public,
    ObjectType.PROMO: compute_promo_public,
}

_MEMBER_DISPATCH = {
    ObjectType.USER: compute_user_member,
    ObjectType.TOURNAMENT: compute_tournament_member,
    ObjectType.SANCTION: _identity,
    ObjectType.DECK: compute_deck_member,
    ObjectType.LEAGUE: _identity,
    ObjectType.PROMO: compute_promo_public,
}

_API_DISPATCH = {
    ObjectType.USER: compute_user_api,
    ObjectType.TOURNAMENT: compute_tournament_api,
    ObjectType.SANCTION: _invisible,
    ObjectType.DECK: compute_deck_api,
    ObjectType.LEAGUE: compute_league_api,
    ObjectType.PROMO: _invisible,
}

_FULL_DISPATCH = {
    ObjectType.USER: compute_user_full,
    ObjectType.TOURNAMENT: compute_tournament_full,
    ObjectType.SANCTION: _identity,
    ObjectType.DECK: compute_deck_full,
    ObjectType.LEAGUE: _identity,
    ObjectType.PROMO: _identity,
}


def compute_public(obj_type: str, full_dict: dict) -> dict | None:
    fn = _PUBLIC_DISPATCH.get(obj_type)
    if fn is None:
        raise ValueError(f"Unknown object type: {obj_type}")
    return fn(full_dict)


def compute_member(obj_type: str, full_dict: dict) -> dict | None:
    fn = _MEMBER_DISPATCH.get(obj_type)
    if fn is None:
        raise ValueError(f"Unknown object type: {obj_type}")
    return fn(full_dict)


def compute_api(obj_type: str, full_dict: dict) -> dict | None:
    fn = _API_DISPATCH.get(obj_type)
    if fn is None:
        raise ValueError(f"Unknown object type: {obj_type}")
    return fn(full_dict)


def compute_full(obj_type: str, full_dict: dict) -> dict:
    fn = _FULL_DISPATCH.get(obj_type)
    if fn is None:
        raise ValueError(f"Unknown object type: {obj_type}")
    result = fn(full_dict)
    if result is None:
        raise ValueError(f"Full projection must not return None for {obj_type}")
    return result
