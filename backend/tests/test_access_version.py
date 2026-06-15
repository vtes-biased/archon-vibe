"""Tests for the connect-time entitlement fingerprint (access-version handshake).

The fingerprint must change exactly when WHAT a viewer is entitled to changes — base
level, overlay-granting role, the country scoping an official's overlay, or the set of
tournaments they organize — and stay STABLE otherwise (so a quiet system never loops on
a spurious resync). Non-overlay roles and a plain member's cosmetic fields must NOT move it.
"""

from datetime import UTC, datetime

import pytest
from src import db
from src.db import compute_access_version, save_tournament, save_user
from src.models import Role, Tournament, User

NOW = datetime.now(UTC)


def _member(uid="m1", roles=None, country=None) -> User:
    return User(
        uid=uid,
        modified=NOW,
        name="M",
        vekn_id="9999",
        roles=roles or [],
        country=country,
    )


@pytest.mark.asyncio
async def test_av_is_deterministic_and_level_sensitive(test_db):
    """Same entitlement → same fp (no quiet-system loop); a base-level change moves it."""
    anon = await compute_access_version(None)
    assert anon == await compute_access_version(None)
    ic = await compute_access_version(_member("ic", roles=[Role.IC]))  # full level
    assert ic != anon


@pytest.mark.asyncio
async def test_av_ignores_nonoverlay_roles(test_db):
    """A non-overlay role (Judge/PT/…) doesn't branch in access projection, so adding it
    must NOT change the fp — else every such grant would force a needless resync."""
    plain = await compute_access_version(_member())
    judge = await compute_access_version(_member(roles=[Role.JUDGE, Role.PT]))
    assert plain == judge


@pytest.mark.asyncio
async def test_av_country_counts_only_for_officials(test_db):
    """Country scopes the NC/Prince overlay, so it enters the fp ONLY for officials —
    a plain member's country edit is cosmetic and must not resync."""
    assert await compute_access_version(
        _member(country="France")
    ) == await compute_access_version(_member(country="Germany"))
    nc_fr = await compute_access_version(
        _member("nc", roles=[Role.NC], country="France")
    )
    nc_de = await compute_access_version(
        _member("nc", roles=[Role.NC], country="Germany")
    )
    assert nc_fr != nc_de


@pytest.mark.asyncio
async def test_av_tracks_the_organizer_set(test_db):
    """Becoming an organizer changes which objects the member is entitled to at full, so
    the org-set must enter the fp — this is what makes an OFFLINE organizer change resync."""
    member = _member("org-member")
    await save_user(member)
    before = await compute_access_version(member)

    t = Tournament(uid="av-trn-1", modified=NOW, name="T", organizers_uids=[member.uid])
    await save_tournament(t)
    try:
        after = await compute_access_version(member)
        assert after != before  # gained an organized tournament → fp moves
        # Idempotent: recomputing with the same org-set is stable (no spurious resync).
        assert after == await compute_access_version(member)
    finally:
        async with db.get_connection() as conn:
            await conn.execute("DELETE FROM objects WHERE uid = 'av-trn-1'")
