"""Server-computed promo stock aggregates.

The promo_ledger table and the tournaments' distribution reports are the
source of truth; this module denormalizes them into `Promo.holdings` and
`User.promo_stock` so every client reads the same authoritative remaining
counts (streamed via SSE, never derived client-side — sync-state differences
must not show different totals to different viewers).

Triggered on ledger writes, promo catalog updates (self-heal after a potential
read-modify-write overlap), any tournament save changing promos_distributed
(ReportPromos action, offline push, soft-delete), and a daily full pass.
Idempotent: recomputing from source data always converges.
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

# Serializes recomputes: interleaved runs could otherwise finish out of order
# and write stale aggregates last (each trigger commits its source row BEFORE
# scheduling, so a serialized later run always reads — and writes — later
# state, making convergence immediate instead of waiting on the daily pass).
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
            # Print batch received from BCP: credits the holder (from_uid),
            # debits nobody — the external origin is outside the ledger.
            h = hold(e.promo_uid, e.from_uid)
            h.assigned += e.qty
            h.remaining += e.qty
            continue
        if e.kind == PromoLedgerKind.ASSIGNMENT and e.to_uid:
            h = hold(e.promo_uid, e.to_uid)
            h.assigned += e.qty
            h.remaining += e.qty
        # Outflow from the source holder (assignment + distribution). Sources
        # with no recorded intake go negative — unbounded fallback; UI hides
        # pure supply sources.
        h = hold(e.promo_uid, e.from_uid)
        h.remaining -= e.qty

    for promo_uid, holder_uid, qty in attributions:
        h = hold(promo_uid, holder_uid)
        h.remaining -= qty

    # Write changed Promo.holdings. Re-read right before saving so a catalog
    # edit committed meanwhile isn't clobbered (and catalog PUT re-triggers a
    # recompute, closing the reverse window).
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

    # Merge per-user stock for the target promos: set computed keys, drop
    # stale ones (holders that no longer appear, e.g. a changed stock source).
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
