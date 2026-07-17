"""Access level projection functions for the new sync architecture.

Pre-computes public/member/full JSONB columns at write time.
All functions take a dict (full object data) and return a dict or None.
None means the object is not visible at that access level.
"""

import base64

from .models import ObjectType, Role

# Contact fields cloaked in the PUBLIC projection only (anonymous viewers).
# Reversible base64 keeps the plaintext — and any "@" — out of the public
# snapshot, so naive bulk harvesters of /sync/snapshot?level=public come up
# empty. The frontend decodes for display (deobfuscateContact in
# lib/contact.ts); member/full projections (authenticated viewers) stay
# plaintext. Mirror the prefix + scheme on both sides.
_OBFUSCATED_PREFIX = "#b64#"
_PUBLIC_OBFUSCATED_FIELDS = ("contact_email", "contact_phone")


def _obfuscate(value: str) -> str:
    if value.startswith(_OBFUSCATED_PREFIX):
        return value  # already cloaked — never double-encode
    return _OBFUSCATED_PREFIX + base64.b64encode(value.encode("utf-8")).decode("ascii")


def _obfuscate_public_contacts(proj: dict) -> dict:
    """In-place cloak the harvestable contact fields of a public projection."""
    for field in _PUBLIC_OBFUSCATED_FIELDS:
        value = proj.get(field)
        if isinstance(value, str) and value:
            proj[field] = _obfuscate(value)
    return proj


# ---------------------------------------------------------------------------
# User projections
# ---------------------------------------------------------------------------

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
# Minimal fields for anonymous link browsing (no name/personal info)
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
    # Discord snowflake (an opaque id, not contact info — owner: needs no
    # protecting): the bot's judges-channel sync maps organizers through it, and
    # organizers need no NC/Prince role, so it can't stay contact-set-only.
    | {"discord_id"}
    # Rating fields (embedded in user after merge)
    | {
        "constructed_online",
        "constructed_offline",
        "limited_online",
        "limited_offline",
        "wins",
    }
)


def _pick(d: dict, keys: set[str]) -> dict:
    """Return a new dict with only the specified keys (if present in d)."""
    return {k: v for k, v in d.items() if k in keys}


def compute_user_public(d: dict) -> dict | None:
    """Public projection for User.

    NC/Prince: public fields + contact info + community_links
    IC: public fields + community_links only (no contact info)
    Any user with community_links: minimal fields (country, roles, links) — no name
    Others: hidden
    """
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
    """Member projection for User.

    All users visible with identity + rating fields.
    NC/Prince: also get contact info + community_links.
    IC: also get community_links (no contact — IC contact is restricted).
    Any user with community_links: include them in member projection.
    """
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


def compute_user_full(d: dict) -> dict:
    """Full projection for User. Everything except calendar_token."""
    # Exclude calendar_token — private, only visible via /auth/me
    return {k: v for k, v in d.items() if k != "calendar_token"}


# ---------------------------------------------------------------------------
# Tournament projections
# ---------------------------------------------------------------------------

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
}

# Member gets everything EXCEPT checkin_code and the VEKN/TWDA push bookkeeping
_TOURNAMENT_MEMBER_EXCLUDE = {
    "checkin_code",
    "vekn_pushed_at",
    "vekn_results_stale",
    "twda_status",
}


def compute_tournament_public(d: dict) -> dict:
    """Public projection: minimal tournament info."""
    return _pick(d, _TOURNAMENT_PUBLIC_FIELDS)


def compute_tournament_member(d: dict) -> dict:
    """Member projection: everything except checkin_code and VEKN push bookkeeping.

    No per-viewer filtering — all members see all data.
    """
    return {k: v for k, v in d.items() if k not in _TOURNAMENT_MEMBER_EXCLUDE}


def compute_tournament_full(d: dict) -> dict:
    """Full projection: everything."""
    return dict(d)


# ---------------------------------------------------------------------------
# Sanction projections
# ---------------------------------------------------------------------------


def compute_sanction_public(d: dict) -> None:
    """Sanctions are not visible to non-members."""
    return None


# ---------------------------------------------------------------------------
# Deck projections
# ---------------------------------------------------------------------------


def compute_deck_public(d: dict) -> None:
    """Decks are never visible at public level."""
    return None


def compute_deck_member(d: dict) -> dict | None:
    """Member projection: visible if public flag is set.

    The engine sets public=True based on decklists_mode + tournament state
    + player status (winner/finalist/all). Own decks are always visible
    via personal overlay in SSE (obj_user_uid == viewer.uid).
    """
    if d.get("public"):
        return dict(d)
    return None


def compute_deck_full(d: dict) -> dict:
    """Full access always sees all decks."""
    return dict(d)


def compute_promo_public(d: dict) -> dict:
    """Catalog only — the server-written inventory aggregates are officials-only.

    Deliberately NOT gated on `active`: retired promos must keep resolving for
    historical distribution rows and raffle prizes; the gallery UI filters.
    """
    return {k: v for k, v in d.items() if k != "holdings"}


# ---------------------------------------------------------------------------
# Shared passthrough (identity projection)
# ---------------------------------------------------------------------------


def _identity(d: dict) -> dict:
    """Identity projection: object fully visible at this level (no filtering).

    Used where a type has no per-level field policy: leagues are fully public
    at every level, and sanctions are fully visible to any member.
    """
    return dict(d)


# ---------------------------------------------------------------------------
# Dispatch tables
# ---------------------------------------------------------------------------

_PUBLIC_DISPATCH = {
    ObjectType.USER: compute_user_public,
    ObjectType.TOURNAMENT: compute_tournament_public,
    ObjectType.SANCTION: compute_sanction_public,
    ObjectType.DECK: compute_deck_public,
    ObjectType.LEAGUE: _identity,
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

_FULL_DISPATCH = {
    ObjectType.USER: compute_user_full,
    ObjectType.TOURNAMENT: compute_tournament_full,
    ObjectType.SANCTION: _identity,
    ObjectType.DECK: compute_deck_full,
    ObjectType.LEAGUE: _identity,
    ObjectType.PROMO: _identity,
}


def compute_public(obj_type: str, full_dict: dict) -> dict | None:
    """Compute the public projection for an object."""
    fn = _PUBLIC_DISPATCH.get(obj_type)
    if fn is None:
        raise ValueError(f"Unknown object type: {obj_type}")
    return fn(full_dict)


def compute_member(obj_type: str, full_dict: dict) -> dict | None:
    """Compute the member projection for an object."""
    fn = _MEMBER_DISPATCH.get(obj_type)
    if fn is None:
        raise ValueError(f"Unknown object type: {obj_type}")
    return fn(full_dict)


def compute_full(obj_type: str, full_dict: dict) -> dict:
    """Compute the full projection for an object.

    This exists for consistency and to strip fields like calendar_token.
    """
    fn = _FULL_DISPATCH.get(obj_type)
    if fn is None:
        raise ValueError(f"Unknown object type: {obj_type}")
    result = fn(full_dict)
    if result is None:
        raise ValueError(f"Full projection must not return None for {obj_type}")
    return result
