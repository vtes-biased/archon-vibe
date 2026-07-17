# 492 — Promotional material tracking (BCP promos)

Stakeholder ask: organizers report promo cards distributed at events; BCP (=IC) gets
traceability from assignment to distribution. Reworked from the original spec: the
hand-entered per-tournament "remaining" field is dropped (inventory snapshot masquerading
as an event fact); remaining is **computed** from a ledger.

## Decisions (settled with owner, 2026-07-17)

- **Scope split**: event-scoped distribution reporting + IC/NC inventory ledger.
  No hand-entered "remaining" anywhere: remaining = assignments in − (assignments out
  + distributions) per holder.
- **Chain**: IC (=BCP) → NC → organizer, or IC → organizer. Transfers between holders are
  assignments. Non-tournament channels (demos, store events, league-end prizes) are
  recorded as generic ledger distributions — no league admin component needed.
- **Catalog**: `PromoItem`, new synced ObjectType. IC-only minting. **No krcg link** —
  identity and images are Archon-owned (promos are alt-art printings or unreleased cards;
  krcg's grain is the card, not the printing). Fields: name, kind (card/pack/other),
  description?, release date?, active flag, restrictions (below), versioned `image_path`.
- **Images**: IC-uploaded, blob side table (avatars/banners pattern, ≤1MB), cached
  locally so offline tournaments can display them (raffle winner display).
- **Restrictions** (picker gating, soft — edge cases handled manually by BCP/NCs):
  two optional axes: `allowed_ranks` (NC-plus = {NC, CC}; existing enum suffices) and
  `league_uids` (GP-only: **GP-ness is league membership in this app, NOT a rank** — do
  not add a GP rank; VEKN event type 15 stays mapped to BASIC). Empty = unrestricted;
  both set = AND.
- **Distribution reporting**: embedded `Tournament.promos_distributed` list
  `{promo_uid, qty}` (SYNC.md embed rule); organizer-entered, optional, gentle
  finish-flow prompt; online-only plain backend route (announce/banner pattern — no
  Rust engine); member-level visibility (event-linked, not organizer-linked).
- **Raffle link**: optional prize on `RaffleDraw` (promo_uid or free label); display-only
  (does NOT auto-write distribution rows); player-side winner display shows promo image.
- **IA**: Community "Promos" tab is the single hub — public gallery (player-facing
  catalog), IC inline mint/edit/retire, IC/NC inventory ledger + assignments + CSV
  reporting in the same tab (role-gated progressive disclosure, like community
  moderation). Tournament page keeps only the entry form + raffle display. Inventory
  management is online-only.
- **Access**: IC = BCP, no new role. PromoItem public. Ledger full-level, scoped to
  involved parties + officials.
- **Volumes**: ~150 organizers, ~300 events/yr, ~20 active promos, ≤10 lines/event →
  CSV-first reporting, no analytics dashboard.
- **Write path** (settled 3rd round): distribution rows ride the engine event pipeline
  (`UpdateConfig`-style event; serde field on the Rust Tournament struct, no logic) —
  offline entry at the venue, optimistic sync, no new route. Side routes stay reserved
  for blobs/ephemera/integrations.
- **Assignment model** (settled 3rd round): Model O — holders are always users
  (IC→NC→organizer); assignments recorded when stock moves hands; leftovers implicitly
  stay in organizer stock; return-to-NC = reverse assignment; gifting = an assignment;
  per-event kits = timed assignments. Multi-organizer events: "stock source" selector on
  the report, defaulting to submitter, choosable among organizers_uids. Permissions: IC
  assignments need no prior stock (BCP supply inflow); NC/organizer assignments draw on
  own stock, warn-not-block on negatives; no country scoping. Organizers see own stock
  and record their own generic giveaways (demos); raffle totals pre-fill the report as
  a hint.

## Codebase anchors

- Organizer console: `frontend/src/routes/tournaments/[uid]/+page.svelte` — tabbed
  (players/rounds/finals/config); `ConfigTab.svelte` foldable-section pattern
  (`TableRoomsEditor`) or a finished-state section next to `FinishedResults`.
- New object type checklist: SYNC.md:319-330; embed-vs-new-type rule: SYNC.md:296-305.
- Blob uploads: avatars (`routes/users.py:338`, `schema.sql:39-44`), banners
  (`routes/tournaments.py:720`, `schema.sql:49-54`) — versioned path rides the object.
- Picker UI shape: `CardSearch.svelte` + `searchCards` (`cards.ts:94`) — reuse over
  PromoItems (not VtesCards).
- Raffle model: `RaffleDraw {label, pool, winners}` (`models.py:544`); engine mirror in
  `engine/src/tournament/mod.rs` — prize is a serde-only additive field, no logic.
- Reporting dimensions already on Tournament: country, organizers_uids, format, rank,
  league_uid, start/finish.

## Engineering decisions (principal-engineer review, 2026-07-17)

- **Ledger storage**: dedicated `promo_ledger` side table + REST — the OAuth-tables
  precedent (BaseObject-shaped data deliberately absent from `ObjectType`,
  `models.py:614-658`, `schema.sql:57-112`). One table, `kind` enum
  {assignment, distribution}, append-mostly, corrections as compensating rows (no
  mutations). Rejected: full synced type (forces online-only data into every IDB; needs
  a two-user-ref personal-overlay on the hot reconnect path) and partial integration
  (fights `list(ObjectType)` auto-inclusion in `main.py:699`/`snapshots.py:22`).
  **No server-side pagination** (owner directive, now a CLAUDE.md convention): the GET
  returns the whole role-scoped ledger (officials = all rows, organizers = their
  involved-party rows; scoping is access control and stays server-side); filtering/
  pagination client-side; growth escape hatch = a date-range filter param, still not
  pagination. This is the app's **first read-via-API UI**: document the carve-out in
  SYNC.md — online-only + officials-only + back-office + small role-scoped dataset
  shipped whole.
- **Remaining is server-computed and streamed, never client-derived** (owner revision,
  4th round): clients must never disagree on totals because of local sync state —
  stale-but-consistent beats fresh-but-divergent for stock counts. The ledger table
  stays the source of truth; the server denormalizes aggregates into synced objects:
  `Promo.holdings` (per-holder assigned/remaining; full projection → officials) and
  `User.promo_stock` (own-profile full → organizer own-stock view, offline-readable,
  zero new entitlement logic). Recompute: incremental on ledger writes and on ANY
  tournament save where the promos_distributed set changes — online ReportPromos,
  offline full-state push, finish, reopen/re-edit, soft-delete (affected promos =
  union of old+new row uids) — plus a daily full self-healing pass (ratings
  precedent). Post-finish corrections are first-class: ReportPromos has no state gate
  and replace-the-whole-list semantics, so fixing a submitted count is re-submitting
  the table. Recompute does targeted field updates only — never clobbers concurrent IC catalog
  edits, never writes `Tournament.promos_distributed`. Consequences: Promo projections
  are no longer `_identity` (public/member strip holdings), and `entitled_level` gains
  one branch: NC → full for promo objects regardless of country (chain is not
  country-scoped; Princes/organizers stay member). CSV stays client-side. The common
  read path (remaining in the Promos tab) is thereby offline-first again; REST remains
  only for entry writes + the audit/history listing.
- **`promos_distributed`**: dedicated `ReportPromos` engine event (require_organizer,
  field set, no logic) — NOT folded into `UpdateConfig` (validation-heavy config
  whitelist; folding pollutes its audit meaning and hits the create/update whitelist
  asymmetry). Member-visible via denylist absence (stock_source uid leaks nothing —
  organizers_uids is member-visible today). NOT in the server-managed re-pull block:
  the offline device is authoritative, so **nothing server-side may ever mutate
  `promos_distributed`** — the ledger only reads/attributes it.
- **PromoItem retirement**: `active=false`, never a tombstone (universal soft-delete
  hard-deletes client-side, SYNC.md:246-255 — would dangle historical rows). Refuse
  hard-delete while referenced. Public projection does NOT gate on `active`; the
  gallery UI filters. Gating fields ship in the public projection (UX-only gating, not
  access control — consistent with authz-in-Rust philosophy, no engine enforcement).
- **Images**: avatars/banners do NOT work offline today (`service-worker.ts:34-48`
  cache-serves only precached ASSETS/navigations) — offline promo images are NEW
  capability: public unauthenticated versioned GET (auth-bearing responses are
  deliberately never cached), cache-first path-prefix allowlist in the SW fetch
  handler, and proactive prefetch of active promo images on catalog sync. SW cache
  over IDB blobs (immutable URLs make cache-first trivially correct; less code).
- **Raffle prize is not purely additive serde**: the draw is a `json::object` literal
  (`mod.rs:2427-2431`) — the prize threads through the RaffleDraw event into that
  literal + msgspec struct + TS type.

## Open wrinkles

Owner-level discussion complete; engineering forks settled by PE review above.
Remaining implementation minutiae: CSV columns; Community tab order/naming;
finish-prompt UX; i18n.

## Children (filed 2026-07-17, dependency order — ALL LANDED 2026-07-17)

1. #493 Promo object type — commit 1f5bff9
2. #495 Tournament distribution reporting (ReportPromos + editor UI) — 62f83d3
3. #494 Promo images + SW offline caching — 2008efd
4. #496 Raffle prize link — 988eea0
5. #497 Inventory ledger + server-computed stock + carve-out doc — 3f0f8eb
6. #498 Community Promos tab — final commit of the epic

Post-epic notes: ledger POST has a VEKN-membership floor; member-to-member
assignments are allowed by design (indistinguishable from legitimate promo
gifting; audited via created_by/from_uid, correctable via compensating rows).
Recomputes are serialized behind a module lock; the daily pass remains the
hard convergence backstop.
