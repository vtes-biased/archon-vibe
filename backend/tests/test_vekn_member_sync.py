"""VEKN member sync role seeding (vekn_sync.sync_player): CREATE seeds derived
roles (Prince/NC/IC); UPDATE never writes roles, so app-managed roles survive
re-sync — the contract restored after 364a7ec's removal of it. Its coopted_by
inference skips a sponsor an official pinned. Runs end-to-end against the real
DB, no mocks.
"""

import pytest
from src.data.vekn_roster import ADMINS
from src.geonames import city_index
from src.models import Role
from src.vekn_sync import VEKNSyncService


@pytest.mark.asyncio
async def test_create_seeds_derived_roles(test_db):
    # A static-roster admin, so create must derive Prince (princeid), NC
    # (coordinatorid) and IC (ADMINS) together. Judge ranks are not seeded —
    # app-managed, no vekn.net field.
    roster_id = next(iter(ADMINS))

    user, action = await VEKNSyncService().sync_player(
        {
            "veknid": int(roster_id),
            "firstname": "Seed",
            "lastname": "Member",
            "princeid": "PR1",
            "coordinatorid": "CO1",
        },
        city_index(),
    )

    assert action == "created"
    assert set(user.roles) == {Role.PRINCE, Role.NC, Role.IC}


@pytest.mark.asyncio
async def test_update_never_writes_roles(test_db):
    # Seed a user the way the app would: a single app-granted role, no Prince/NC.
    created, action = await VEKNSyncService().sync_player(
        {"veknid": 1000777, "firstname": "App", "lastname": "User"}, city_index()
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
        },
        city_index(),
    )
    assert action == "updated"  # identity-adjacent field (vekn_prefix) changed

    after = await get_user_by_uid(created.uid)
    assert after.roles == [Role.IC], "app-granted role survives a sync re-derive"


@pytest.mark.asyncio
async def test_inference_respects_a_cleared_sponsor_pin(test_db):
    import msgspec
    from src.db import get_user_by_uid, save_user

    async def seed(vekn_id: int, **fields):
        user, _ = await VEKNSyncService().sync_player(
            {"veknid": vekn_id, "firstname": "M", "lastname": str(vekn_id)},
            city_index(),
        )
        user = msgspec.structs.replace(user, country="FR", **fields)
        await save_user(user)
        return user

    nc = await seed(1000800, vekn_prefix="10008", roles=[Role.NC])
    pinned = await seed(1000801, coopted_by=None, local_modifications={"coopted_by"})
    free = await seed(1000802, coopted_by=None)

    await VEKNSyncService()._infer_coopted_by()
    await VEKNSyncService()._infer_coopted_by_city()

    assert (await get_user_by_uid(free.uid)).coopted_by == nc.uid
    assert (await get_user_by_uid(pinned.uid)).coopted_by is None
