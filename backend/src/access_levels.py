"""Access level projection functions for the new sync architecture.

Pre-computes public/member/full JSONB columns at write time.
All functions take a dict (full object data) and return a dict or None.
None means the object is not visible at that access level.
"""

from .models import Role


# ---------------------------------------------------------------------------
# User projections
# ---------------------------------------------------------------------------

_USER_PUBLIC_FIELDS = {"uid", "modified", "deleted_at", "name", "country", "roles", "vekn_prefix"}
_USER_PUBLIC_CONTACT = {"contact_email", "contact_discord", "contact_phone"}
_USER_MEMBER_FIELDS = (
    _USER_PUBLIC_FIELDS
    | {"vekn_id", "city", "state", "nickname", "avatar_path"}
    # Rating fields (embedded in user after merge)
    | {
        "constructed_online",
        "constructed_offline",
        "limited_online",
        "limited_offline",
        "wins",
    }
)
_USER_FULL_EXTRA = (
    _USER_PUBLIC_CONTACT
    | {
        "coopted_by",
        "coopted_at",
        "vekn_synced",
        "vekn_synced_at",
        "local_modifications",
        "vekn_prefix",
        "resync_after",
    }
)


def _pick(d: dict, keys: set[str]) -> dict:
    """Return a new dict with only the specified keys (if present in d)."""
    return {k: v for k, v in d.items() if k in keys}


def compute_user_public(d: dict) -> dict | None:
    """Public projection for User.

    Only NC/Prince users get a public representation.
    Includes contact info for NC/Prince so non-members can reach organizers.
    """
    roles = d.get("roles", [])
    if Role.NC not in roles and Role.PRINCE not in roles:
        return None
    result = _pick(d, _USER_PUBLIC_FIELDS | _USER_PUBLIC_CONTACT)
    return result


def compute_user_member(d: dict) -> dict:
    """Member projection for User. All users visible, no contact info."""
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
}

# Member gets everything EXCEPT checkin_code, vekn_pushed_at
_TOURNAMENT_MEMBER_EXCLUDE = {"checkin_code", "vekn_pushed_at"}


def compute_tournament_public(d: dict) -> dict:
    """Public projection: minimal tournament info."""
    return _pick(d, _TOURNAMENT_PUBLIC_FIELDS)


def compute_tournament_member(d: dict) -> dict:
    """Member projection: everything except checkin_code and vekn_pushed_at.

    No per-viewer filtering (my_tables removed, standings/deck visibility
    is no longer gated at this level — all members see all data).
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


def compute_sanction_member(d: dict) -> dict:
    """Members see full sanction data."""
    return dict(d)


def compute_sanction_full(d: dict) -> dict:
    """Full sanction data (same as member)."""
    return dict(d)


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


# ---------------------------------------------------------------------------
# League projections
# ---------------------------------------------------------------------------


def compute_league_public(d: dict) -> dict:
    """Leagues are fully public."""
    return dict(d)


def compute_league_member(d: dict) -> dict:
    """Leagues are fully public."""
    return dict(d)


def compute_league_full(d: dict) -> dict:
    """Leagues are fully public."""
    return dict(d)


# ---------------------------------------------------------------------------
# Dispatch tables
# ---------------------------------------------------------------------------

_PUBLIC_DISPATCH = {
    "user": compute_user_public,
    "tournament": compute_tournament_public,
    "sanction": compute_sanction_public,
    "deck": compute_deck_public,
    "league": compute_league_public,
}

_MEMBER_DISPATCH = {
    "user": compute_user_member,
    "tournament": compute_tournament_member,
    "sanction": compute_sanction_member,
    "deck": compute_deck_member,
    "league": compute_league_member,
}

_FULL_DISPATCH = {
    "user": compute_user_full,
    "tournament": compute_tournament_full,
    "sanction": compute_sanction_full,
    "deck": compute_deck_full,
    "league": compute_league_full,
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
