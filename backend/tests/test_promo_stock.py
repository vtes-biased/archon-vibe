"""Regression test for the server-computed promo stock aggregates.

`recompute_promo_stock` is the sole writer of `Promo.holdings` and
`User.promo_stock` — the authoritative "remaining" counts every client reads via
SSE (never derived client-side). The invariant it must hold: for each holder,
remaining = assignments in − outflow out (both ledger kinds) − tournament
attributions, and a holder that drops out of the recomputed set has its stale
denormalized key cleaned. A sign flip, a dropped term, or a missed cleanup would
show officials/organizers phantom or wrong physical-inventory counts — the whole
point of the feature.

One scenario drives every term through the shipped function against the real
`test_db` Postgres: an assignment in, a generic distribution out, a compensating
negative correction, a BCP/IC source going legitimately negative, a tournament
attribution to a stock source, and — after re-pointing that stock source — the
stale-key cleanup for the holder that no longer appears.
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

        # 10 assigned IC -> B; B gives away 3, then a -1 compensating correction.
        for e in (
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
        # B: 10 in − (3 − 1) out = 8. IC source: 0 − 10 = −10. C: 0 − 2 attributed.
        assert promo_after.holdings[org_b.uid].assigned == 10
        assert promo_after.holdings[org_b.uid].remaining == 8
        assert promo_after.holdings[ic.uid].remaining == -10
        assert promo_after.holdings[org_c.uid].remaining == -2
        assert (await db.get_user_by_uid(org_b.uid)).promo_stock[p] == 8
        assert (await db.get_user_by_uid(ic.uid)).promo_stock[p] == -10
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
