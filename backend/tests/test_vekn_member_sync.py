"""Tests for VEKN member sync role seeding (vekn_sync.sync_player).

Invariant pair (one test each), the contract restored after the outright
removal in 364a7ec — guarding against an *accidental* re-swing of role handling
in this access-control-sensitive path:

* CREATE seeds derived roles. A vekn.net Prince/NC/admin/judge that this sync
  imports for the first time gets the corresponding role written. Regression
  guarded: dropping the seed again strands environments populated by this sync
  alone (dev-reset, post-decommission rebuild) with zero roles and a locked-out
  role-edit API (it needs an IC caller).
* UPDATE never writes roles. A re-sync of an existing user leaves the user's
  app-managed roles intact even when the incoming vekn data would derive a
  different set. Regression guarded: re-introducing role derivation on the
  update path flips access control daily (an IC's app-granted roles wiped, or
  a revoked Prince silently re-granted, on every sync run).

Both run sync_player end-to-end against the real DB (real save_user /
get_user_by_vekn_id / _derive_role_seeds) — the shipped interface, no mocks.
A static-roster admin/judge id (ADMINS/JUDGES in data/vekn_roster.py) is
imported so the assertion tracks the shipped roster rather than a hand-copied id.
"""

import pytest
from src.data.vekn_roster import ADMINS, JUDGES
from src.models import Role
from src.vekn_sync import VEKNSyncService


@pytest.mark.asyncio
async def test_create_seeds_derived_roles(test_db):
    # One id that is both a static-roster admin and judge, so the create seed
    # must cover Prince (princeid), NC (coordinatorid), IC (ADMINS) and the
    # judge-tier role (JUDGES) in a single pass.
    roster_id = next(iter(ADMINS & JUDGES.keys()))

    user, action = await VEKNSyncService().sync_player(
        {
            "veknid": int(roster_id),
            "firstname": "Seed",
            "lastname": "Member",
            "princeid": "PR1",
            "coordinatorid": "CO1",
        }
    )

    assert action == "created"
    assert set(user.roles) == {Role.PRINCE, Role.NC, Role.IC, JUDGES[roster_id]}


@pytest.mark.asyncio
async def test_update_never_writes_roles(test_db):
    # Seed a user the way the app would: a single app-granted role, no Prince/NC.
    created, action = await VEKNSyncService().sync_player(
        {"veknid": 1000777, "firstname": "App", "lastname": "User"}
    )
    assert action == "created"
    assert created.roles == []

    from src.db import get_user_by_uid, save_user

    created.roles = [Role.IC]
    await save_user(created)

    # Re-sync with data that WOULD derive Prince+NC if the update path seeded.
    _, action = await VEKNSyncService().sync_player(
        {
            "veknid": 1000777,
            "firstname": "App",
            "lastname": "User",
            "princeid": "PR9",
            "coordinatorid": "CO9",
        }
    )
    assert action == "updated"  # identity-adjacent field (vekn_prefix) changed

    after = await get_user_by_uid(created.uid)
    assert after.roles == [Role.IC], "app-granted role survives a sync re-derive"
