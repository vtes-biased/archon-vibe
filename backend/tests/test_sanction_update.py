"""Regression test for PUT /sanctions/{uid} expiry validation on level-only edits.

The bug (pst #365): `_validate_expiry` used to run only inside `if expires_at is
not None`, so editing *just the level* SUSPENSION->PROBATION skipped it and
persisted a PROBATION with expires_at=None. That is not cosmetic: a null-expiry
PROBATION reads as PERMANENTLY active in `user_has_active_suspension`
(accounts.py — `expires_at is None` -> active forever), permanently blocking the
member from abandoning their VEKN ID. The 18-month cap exists to bound exactly
this. The fix hoisted the validation to run on the resulting level+expires_at
pair unconditionally; this pins that at the HTTP interface.

Runs real: real Postgres, real route/auth, no tournament/engine (sanction has no
tournament_uid, so the DQ/SA recompute branches never fire). One user, one row.
"""

from datetime import UTC, datetime
from uuid import uuid7

import pytest
import src.db as db
from src.models import Role, Sanction, SanctionCategory, SanctionLevel, User

from tests.conftest import make_auth_header


@pytest.mark.asyncio
async def test_level_only_edit_to_probation_without_expiry_rejected(test_client):
    """SUSPENSION->PROBATION with no expires_at must 400 (not persist null expiry)."""
    ic = User(
        uid=str(uuid7()),
        modified=datetime.now(UTC),
        name="Ethics Officer",
        roles=[Role.IC],
    )
    await db.save_user(ic)

    sanction = Sanction(
        uid=str(uuid7()),
        modified=datetime.now(UTC),
        user_uid=ic.uid,
        issued_by_uid=ic.uid,
        level=SanctionLevel.SUSPENSION,  # suspension may have a null expiry
        category=SanctionCategory.UNSPORTSMANLIKE_CONDUCT,
        description="test",
        issued_at=datetime.now(UTC),
        expires_at=None,
    )
    try:
        await db.save_sanction(sanction)

        resp = await test_client.put(
            f"/sanctions/{sanction.uid}",
            json={"level": "probation"},  # no expires_at in the body
            headers=make_auth_header(ic.uid),
        )
        assert resp.status_code == 400
        assert "expir" in resp.json()["detail"].lower()

        # The rejected row is unchanged: still SUSPENSION, still null expiry.
        stored = await db.get_sanction_by_uid(sanction.uid)
        assert stored.level == SanctionLevel.SUSPENSION
        assert stored.expires_at is None
    finally:
        async with db.get_connection() as conn:
            await conn.execute("DELETE FROM objects WHERE type = 'sanction'")
