"""Bulk-register (CSV import) invariants.

One test over the endpoint's whole contract: VEKN-ID and email matching,
engine registration + Paid payment status, and the never-silently-create
rule — unmatched rows and VEKN-less members come back for the desk flow.
"""

from datetime import UTC, datetime
from uuid import uuid7

import pytest
import src.db as db
from src.models import (
    AuthMethod,
    AuthMethodType,
    Role,
    Tournament,
    TournamentState,
    User,
)

from tests.conftest import make_auth_header


@pytest.mark.asyncio
async def test_bulk_register_matches_and_reports(test_client):
    org = User(
        uid=str(uuid7()),
        modified=datetime.now(UTC),
        name="Org",
        roles=[Role.PRINCE],
        vekn_id="1000001",
    )
    by_vekn = User(
        uid=str(uuid7()),
        modified=datetime.now(UTC),
        name="Vekn Match",
        vekn_id="1000002",
    )
    by_email = User(
        uid=str(uuid7()),
        modified=datetime.now(UTC),
        name="Email Match",
        vekn_id="1000003",
    )
    no_vekn = User(uid=str(uuid7()), modified=datetime.now(UTC), name="No Vekn")
    for u in (org, by_vekn, by_email, no_vekn):
        await db.save_user(u)
    await db.insert_auth_method(
        AuthMethod(
            uid=str(uuid7()),
            modified=datetime.now(UTC),
            user_uid=by_email.uid,
            method_type=AuthMethodType.EMAIL,
            identifier="email.match@example.com",
            credential_hash="hash",
            verified=True,
        )
    )
    await db.insert_auth_method(
        AuthMethod(
            uid=str(uuid7()),
            modified=datetime.now(UTC),
            user_uid=no_vekn.uid,
            method_type=AuthMethodType.EMAIL,
            identifier="no.vekn@example.com",
            credential_hash="hash",
            verified=True,
        )
    )

    tournament = Tournament(
        uid=str(uuid7()),
        modified=datetime.now(UTC),
        name="CSV Import",
        state=TournamentState.REGISTRATION,
        organizers_uids=[org.uid],
    )
    try:
        async with db.get_connection() as conn:
            await db.save_tournament(tournament, conn=conn)

        resp = await test_client.post(
            f"/api/tournaments/{tournament.uid}/bulk-register",
            json={
                "rows": [
                    {"vekn_id": "1000002", "name": "Vekn Match"},
                    {"email": "email.match@example.com", "paid": False},
                    {"email": "no.vekn@example.com", "name": "No Vekn"},
                    {"email": "stranger@example.com", "name": "Stranger"},
                ],
                "default_paid": True,
            },
            headers=make_auth_header(org.uid),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert sorted(body["registered"]) == ["Email Match", "Vekn Match"]
        reasons = {u["name"]: u["reason"] for u in body["unmatched"]}
        assert reasons == {"No Vekn": "no_vekn_id", "Stranger": "not_found"}
        assert body["failed"] == []

        saved = await db.get_tournament_by_uid(tournament.uid)
        by_uid = {p.user_uid: p for p in saved.players}
        assert set(by_uid) == {by_vekn.uid, by_email.uid}
        # default_paid applies to rows without a paid column; explicit false wins
        assert by_uid[by_vekn.uid].payment_status == "Paid"
        assert by_uid[by_email.uid].payment_status == "Pending"
    finally:
        async with db.get_connection() as conn:
            await conn.execute("DELETE FROM objects WHERE uid = %s", (tournament.uid,))
