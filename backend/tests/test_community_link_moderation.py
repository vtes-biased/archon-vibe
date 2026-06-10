"""Tests for PATCH /api/users/{uid}/community-link-moderation — the
moderation permission matrix.

This guards an access-control boundary with no other coverage: who may
hide/clear/promote a community link, and on whom. A widened branch (e.g. a
Prince gaining promote rights, an NC promoting cross-country or
internationally, a non-official slipping through) would silently push
unauthorized content into the public projection seen by the whole community.
The matrix below pins each authorized/forbidden cell at the HTTP interface,
so a behavior-preserving refactor of the route's `match` block stays green
while any loosening of the policy turns it red.
"""

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from src import db
from src.models import CommunityLink, Role, User
from uuid6 import uuid7

from tests.conftest import make_auth_header

LINK_URL = "https://discord.gg/vtes"


async def _insert_user(roles: list[Role], country: str = "FR", **kwargs) -> User:
    user = User(
        uid=str(uuid7()),
        modified=datetime.now(UTC),
        name="Test User",
        country=country,
        roles=roles,
        community_links=[CommunityLink(type="discord", url=LINK_URL, label="VTES")],
        **kwargs,
    )
    await db.save_user(user)
    return user


# (moderator_roles, action, target_country, expected_status)
# moderator is always FR; target_country flips the same-country dimension.
MATRIX = [
    # --- non-official is locked out of every action ---
    ([], "hide", "FR", 403),
    ([Role.JUDGE], "hide", "FR", 403),
    # --- hide/clear: IC anywhere, NC/Prince same-country only ---
    ([Role.IC], "hide", "FR", 200),
    ([Role.IC], "hide", "US", 200),
    ([Role.NC], "hide", "FR", 200),
    ([Role.NC], "hide", "US", 403),
    ([Role.PRINCE], "clear", "FR", 200),
    ([Role.PRINCE], "clear", "US", 403),
    # --- promote_national: IC anywhere, NC same-country; NOT Prince ---
    ([Role.IC], "promote_national", "US", 200),
    ([Role.NC], "promote_national", "FR", 200),
    ([Role.NC], "promote_national", "US", 403),
    ([Role.PRINCE], "promote_national", "FR", 403),
    # --- promote_global: IC only ---
    ([Role.IC], "promote_global", "FR", 200),
    ([Role.NC], "promote_global", "FR", 403),
    ([Role.PRINCE], "promote_global", "FR", 403),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("roles,action,target_country,expected", MATRIX)
async def test_moderation_permission_matrix(
    test_client: AsyncClient, test_db, roles, action, target_country, expected
):
    moderator = await _insert_user(roles=roles, country="FR", vekn_id=None)
    target = await _insert_user(roles=[], country=target_country)

    response = await test_client.patch(
        f"/api/users/{target.uid}/community-link-moderation",
        json={"url": LINK_URL, "action": action},
        headers=make_auth_header(moderator.uid),
    )
    assert response.status_code == expected


@pytest.mark.asyncio
async def test_promote_persists_scope(test_client: AsyncClient, test_db):
    """A successful promote stamps the moderation status and the scope that the
    frontend filter consumes — national for the country's NC, global for IC."""
    nc = await _insert_user(roles=[Role.NC], country="FR")
    ic = await _insert_user(roles=[Role.IC], country="FR")
    target_nat = await _insert_user(roles=[], country="FR")
    target_intl = await _insert_user(roles=[], country="FR")

    r1 = await test_client.patch(
        f"/api/users/{target_nat.uid}/community-link-moderation",
        json={"url": LINK_URL, "action": "promote_national"},
        headers=make_auth_header(nc.uid),
    )
    assert r1.status_code == 200
    stored = await db.get_user_by_uid(target_nat.uid)
    assert stored.community_links[0].moderation.status == "promoted"
    assert stored.community_links[0].moderation.scope == "national"

    r2 = await test_client.patch(
        f"/api/users/{target_intl.uid}/community-link-moderation",
        json={"url": LINK_URL, "action": "promote_global"},
        headers=make_auth_header(ic.uid),
    )
    assert r2.status_code == 200
    stored = await db.get_user_by_uid(target_intl.uid)
    assert stored.community_links[0].moderation.scope == "global"


@pytest.mark.asyncio
async def test_self_moderation_allowed(test_client: AsyncClient, test_db):
    """Self-moderation is allowed (was 403 before): an official pins their own
    link. Re-introducing the self-target block would silently break this."""
    ic = await _insert_user(roles=[Role.IC], country="FR")
    response = await test_client.patch(
        f"/api/users/{ic.uid}/community-link-moderation",
        json={"url": LINK_URL, "action": "promote_global"},
        headers=make_auth_header(ic.uid),
    )
    assert response.status_code == 200
    stored = await db.get_user_by_uid(ic.uid)
    assert stored.community_links[0].moderation.scope == "global"
