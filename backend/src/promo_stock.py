"""Server-computed promo stock aggregates: denormalizes promo_ledger and
tournament distribution reports into Promo.holdings and User.promo_stock.
Idempotent — recomputing from source data always converges.
"""

import asyncio
import logging
from datetime import UTC, datetime

import msgspec

from .broadcast import broadcast_precomputed
from .db import (
    get_all_promos,
    get_promo_by_uid,
    get_promo_ledger_for_promos,
    get_tournament_promo_attributions,
    get_user_by_uid,
    get_users_with_promo_stock_keys,
    save_promo,
    save_user,
)
from .models import PromoHolding, PromoLedgerKind

logger = logging.getLogger(__name__)

# Serializes recomputes: without this, interleaved runs could finish out of
# order and leave stale aggregates written last.
_recompute_lock = asyncio.Lock()


def schedule_recompute(promo_uids: list[str] | None = None) -> None:
    """Fire-and-forget recompute (route hooks must not block the response)."""

    async def _run() -> None:
        try:
            await recompute_promo_stock(promo_uids)
        except Exception:
            logger.exception("Promo stock recompute failed")

    asyncio.create_task(_run())


async def recompute_promo_stock(promo_uids: list[str] | None = None) -> None:
    """Recompute per-holder aggregates for the given promos (None = all)."""
    async with _recompute_lock:
        await _recompute(promo_uids)


async def _recompute(promo_uids: list[str] | None) -> None:
    promos = await get_all_promos()
    if promo_uids is not None:
        wanted = set(promo_uids)
        promos = [p for p in promos if p.uid in wanted]
    if not promos:
        return
    target_uids = {p.uid for p in promos}

    entries = await get_promo_ledger_for_promos(list(target_uids))
    attributions = await get_tournament_promo_attributions(target_uids)

    # promo_uid -> holder_uid -> aggregate. Remaining = assignments + intakes in
    # - assignments out - generic distributions - tournament attributions.
    holdings: dict[str, dict[str, PromoHolding]] = {u: {} for u in target_uids}

    def hold(promo_uid: str, holder_uid: str) -> PromoHolding:
        return holdings[promo_uid].setdefault(holder_uid, PromoHolding())

    for e in entries:
        if e.kind == PromoLedgerKind.INTAKE:
            # Credits from_uid; no debit — external origin, outside the ledger.
            h = hold(e.promo_uid, e.from_uid)
            h.assigned += e.qty
            h.remaining += e.qty
            continue
        if e.kind == PromoLedgerKind.ASSIGNMENT and e.to_uid:
            h = hold(e.promo_uid, e.to_uid)
            h.assigned += e.qty
            h.remaining += e.qty
        # Sources with no recorded intake go negative (the UI hides them).
        h = hold(e.promo_uid, e.from_uid)
        h.remaining -= e.qty

    for promo_uid, holder_uid, qty in attributions:
        h = hold(promo_uid, holder_uid)
        h.remaining -= qty

    # Re-read right before saving so a concurrent catalog edit isn't clobbered;
    # catalog PUT re-triggers a recompute, closing the reverse race.
    for stale in promos:
        new_holdings = holdings[stale.uid]
        if msgspec.to_builtins(stale.holdings) == msgspec.to_builtins(new_holdings):
            continue
        promo = await get_promo_by_uid(stale.uid)
        if promo is None:
            continue
        promo.holdings = new_holdings
        promo.modified = datetime.now(UTC)
        bd = await save_promo(promo)
        broadcast_precomputed(bd)

    # Drop stale per-user keys for holders who fall out (e.g. a changed stock
    # source).
    user_stocks: dict[str, dict[str, int]] = {}
    for promo_uid, per_holder in holdings.items():
        for holder_uid, h in per_holder.items():
            user_stocks.setdefault(holder_uid, {})[promo_uid] = h.remaining
    for uid in await get_users_with_promo_stock_keys(list(target_uids)):
        user_stocks.setdefault(uid, {})

    for user_uid, stocks in user_stocks.items():
        user = await get_user_by_uid(user_uid)
        if user is None:
            continue
        merged = dict(user.promo_stock)
        for promo_uid in target_uids:
            if promo_uid in stocks:
                merged[promo_uid] = stocks[promo_uid]
            else:
                merged.pop(promo_uid, None)
        if merged == user.promo_stock:
            continue
        user.promo_stock = merged
        user.modified = datetime.now(UTC)
        bd = await save_user(user)
        broadcast_precomputed(bd)
