"""Regression test for `recompute_promo_stock`, the sole writer of
`Promo.holdings`/`User.promo_stock` — the authoritative counts every client
reads via SSE. Drives every term (intake, assignment, distribution, correction,
negative source, tournament attribution, stale-key cleanup) through the shipped
function against the real `test_db` Postgres.
"""

from datetime import UTC, datetime
from uuid import uuid7

import pytest
import src.db as db
from src.models import (
    Promo,
    PromoDistribution,
    PromoLedgerEntry,
    PromoLedgerKind,
    Tournament,
    User,
)
from src.promo_stock import recompute_promo_stock

from tests.conftest import seed_tournament


def _user(name: str) -> User:
    return User(uid=str(uuid7()), modified=datetime.now(UTC), name=name)


def _entry(kind: PromoLedgerKind, promo_uid: str, qty: int, frm: str, to: str | None):
    now = datetime.now(UTC)
    return PromoLedgerEntry(
        uid=str(uuid7()),
        kind=kind,
        promo_uid=promo_uid,
        qty=qty,
        from_uid=frm,
        to_uid=to,
        happened_at=now,
        created_by=frm,
        created_at=now,
    )


@pytest.mark.asyncio
async def test_recompute_nets_ledger_and_attributions_and_cleans_stale_holders(test_db):
    try:
        promo = Promo(uid=str(uuid7()), modified=datetime.now(UTC), name="Alt-art Foo")
        await db.save_promo(promo)
        p = promo.uid

        ic = _user("BCP")  # supply source, allowed to go negative
        org_b = _user("Organizer B")
        org_c = _user("Organizer C")
        for u in (ic, org_b, org_c):
            await db.save_user(u)

        # IC intakes 4, assigns 10 to B (net −6, exercising the unbounded-source
        # path); B distributes 3, then a −1 correction.
        for e in (
            _entry(PromoLedgerKind.INTAKE, p, 4, ic.uid, None),
            _entry(PromoLedgerKind.ASSIGNMENT, p, 10, ic.uid, org_b.uid),
            _entry(PromoLedgerKind.DISTRIBUTION, p, 3, org_b.uid, None),
            _entry(PromoLedgerKind.DISTRIBUTION, p, -1, org_b.uid, None),
        ):
            await db.insert_promo_ledger_entry(e)

        # A tournament reports 2 distributed, sourced from C's stock.
        t = Tournament(
            uid=str(uuid7()),
            modified=datetime.now(UTC),
            name="Promo Event",
            promos_distributed=[PromoDistribution(promo_uid=p, qty=2)],
            promo_stock_source_uid=org_c.uid,
        )
        await seed_tournament(t)

        await recompute_promo_stock([p])

        promo_after = await db.get_promo_by_uid(p)
        # B: 10 in − (3 − 1) out = 8. IC: 4 intaken − 10 out = −6 (intake debits
        # nobody). C: 0 − 2 attributed.
        assert promo_after.holdings[org_b.uid].assigned == 10
        assert promo_after.holdings[org_b.uid].remaining == 8
        assert promo_after.holdings[ic.uid].assigned == 4
        assert promo_after.holdings[ic.uid].remaining == -6
        assert promo_after.holdings[org_c.uid].remaining == -2
        assert (await db.get_user_by_uid(org_b.uid)).promo_stock[p] == 8
        assert (await db.get_user_by_uid(ic.uid)).promo_stock[p] == -6
        assert (await db.get_user_by_uid(org_c.uid)).promo_stock[p] == -2

        # Re-point the report's stock source B<-C: the attribution moves to B and
        # C drops out of the recomputed set entirely.
        t.promo_stock_source_uid = org_b.uid
        t.modified = datetime.now(UTC)
        await seed_tournament(t)

        await recompute_promo_stock([p])

        promo_final = await db.get_promo_by_uid(p)
        # B now also carries the 2 attributed: 8 − 2 = 6.
        assert promo_final.holdings[org_b.uid].remaining == 6
        assert (await db.get_user_by_uid(org_b.uid)).promo_stock[p] == 6
        # C no longer appears — its stale holdings entry AND promo_stock key are gone.
        assert org_c.uid not in promo_final.holdings
        assert p not in (await db.get_user_by_uid(org_c.uid)).promo_stock
    finally:
        async with db.get_connection() as conn:
            await conn.execute(
                "DELETE FROM objects WHERE type IN ('promo', 'tournament')"
            )
            await conn.execute("DELETE FROM promo_ledger")
