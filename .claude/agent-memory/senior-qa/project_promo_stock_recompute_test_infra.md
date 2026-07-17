---
name: promo-stock-recompute-test-infra
description: How to test promo_stock.recompute_promo_stock (server-computed Promo.holdings / User.promo_stock); non-obvious seeding + teardown facts and the invariant pinned by test_promo_stock.py
metadata:
  type: project
---

`backend/src/promo_stock.py::recompute_promo_stock` is the sole writer of the
authoritative "remaining" counts streamed via SSE: `Promo.holdings`
(officials, full projection) and `User.promo_stock` (own-profile full). Ledger
(`promo_ledger` side table) + tournament distribution reports are the source of
truth; clients never derive remaining locally. Pinned by
`backend/tests/test_promo_stock.py` (one test).

**Invariant pinned:** per holder, remaining = assignments in − outflow out (both
ledger kinds) − tournament attributions; a holder that drops out of the
recomputed set gets its stale `holdings` entry AND `promo_stock` key cleaned.
Consequence of a regression: officials/organizers see phantom or wrong physical
inventory — the feature's whole point. Mutation-verified against two mutations
(attribution sign flip; disabling the stale-key backfill).

**Non-obvious test-writing facts:**
- Call `recompute_promo_stock([uid])` **directly (awaited)** — NOT
  `schedule_recompute` (fire-and-forget `asyncio.create_task`, untestable timing).
- Recompute reads tournaments via **raw SQL** on `full->promos_distributed` /
  `full->>promo_stock_source_uid` (`get_tournament_promo_attributions`), so a
  minimal saved `Tournament` with just those two fields set is enough — no
  engine, no rounds/standings. Attribution is charged to `promo_stock_source_uid`;
  re-pointing it moves the attribution AND makes the old source drop out (the
  stale-key branch: `get_users_with_promo_stock_keys` + `merged.pop`).
- IC/BCP supply source is allowed to go **negative** (assignment out with no
  prior stock) — that's correct, not a bug; UI hides it. Assert it explicitly.
- `PromoLedgerEntry` requires `happened_at`, `created_at`, `created_by`; kind is
  `PromoLedgerKind` (assignment needs `to_uid`, distribution forbids it — that's
  a route-level guard, not enforced by recompute). Insert via
  `db.insert_promo_ledger_entry`.
- Teardown: `test_db` only wipes `type='user'`. Explicitly
  `DELETE FROM objects WHERE type IN ('promo','tournament')` and
  `DELETE FROM promo_ledger` in a `finally` (account-surgery pattern).
- `broadcast_precomputed` inside recompute is a no-op without SSE subscribers —
  safe in tests.

The route guards (`POST /api/promos/ledger`: qty≠0, assignment-needs-to_uid,
distribution-forbids-to_uid, self-sourced-unless-IC) are thin one-line checks —
deliberately NOT tested (would re-assert the implementation). See
[[project_report_promos_no_state_gate]] for the engine-side ReportPromos event
(different surface — that's the offline-authoritative field the ledger only reads).
