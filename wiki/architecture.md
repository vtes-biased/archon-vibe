# Architecture

Offline-first PWA, client-server, with a shared Rust core providing identical
business logic on the frontend (WASM) and backend (PyO3). Works online or offline.

## Stack

- **Frontend** — Svelte 5 (runes) + SvelteKit with `adapter-static` (SPA), Vite,
  TypeScript, Tailwind v4, IndexedDB, PWA service workers. `idb`,
  `lucide-svelte`, `marked` + `dompurify`, Paraglide for i18n.
- **Backend** — FastAPI on Python 3.11+, PostgreSQL 17 with JSONB, psycopg3 async
  and no ORM, msgspec JSON. Tooling `uv` / `ruff` / `ty`.
- **Discord bot** — a separate process (`bot/`): hikari + lightbulb + miru +
  Pillow, SQLite for tokens and state, a pure OAuth client with no DB access and
  no business logic.
- **Shared core** — Rust compiled to WebAssembly (wasm-bindgen) and to a native
  library (PyO3/maturin).

## Data model

All objects extend `BaseObject`: `uid` (UUID v7, time-ordered, indexed),
`modified` (timestamp), `deleted_at` (nullable soft-delete). Everything else is
model-specific.

All synced objects live in one `objects` table with pre-computed access-level
columns — `public` / `member` / `full` JSONB, NULL when not visible at that level,
`full` NOT NULL — plus `api`, the third-party read API's projection, which no app
client is ever served ([sync](sync.md#access-levels)), plus `type`, `modified_at`,
`deleted_at` and `calendar_token`.
Index `(type, modified_at, uid)`. The trade-off bought: a single schemaless table
(no migrations for schema changes), pre-computed projections (zero read-time
filtering), fast iteration.

Synced types: **User, Sanction, Tournament, DeckObject, League, Promo**. VtesCard
is static data loaded into IndexedDB. DeckObject is standalone, not embedded in
Tournament.

`calendar_token` is the one non-projected column — a per-user `.ics` feed secret
that must reach nobody but its owner, and no projection is that narrow: the three
synced ones are broadcast (`full` reaches non-owners) and `api` is published. It
is a 1:1 column rather than a table to avoid a join on the hot
`get_user_by_uid` path; `save_object` COALESCEs it so token-less writes preserve
it, and `clear_calendar_token()` is the explicit drop path.

**Soft delete** sets `deleted_at = now()`; SSE broadcasts the deleted object so
clients — including ones offline during the delete — remove it from IndexedDB on
reconnect. A daily job hard-deletes after 30 days.

## Database access

psycopg3 async, no ORM. The pool is small and autocommit: `max_size` defaults to 20
in code, and production overrides it to **8** via `DB_POOL_MAX_SIZE`, sized for a
945 MB single-core VPS. Connections must cycle fast: check one out, run a query,
release.
Production holds 15k+ users and 7k+ tournaments on that box — never bulk-load a
whole table into memory, use targeted `WHERE id = ANY(...)` queries.

`tournament_transaction(uid)` is the unit of work for any tournament mutation —
the action handler and every offline-lifecycle endpoint. It `SELECT ... FOR
UPDATE`s the row, serializing concurrent writes to one tournament, and yields
`(tournament, tx_conn)` so the read-modify-write is atomic.

**Connection discipline.** A request must never check out a *second* pooled
connection while holding `tx_conn`: with 20 concurrent in-flight actions pinning
all connections via their locks, any further acquire blocks and deadlocks.

- **Reads** route through `_acquire` — explicit `conn=` → ambient `tx_conn`
  ContextVar → pool. Inside a transaction they transparently reuse `tx_conn`, so
  an action consumes exactly one connection start to finish.
- **Writes** route through `get_connection` and pool **independently** by default;
  they do not ride the ambient connection. This is deliberate: go-online creates
  users in a loop where each `save_user` must commit and be visible to the next
  `allocate_next_vekn_id`, which runs its own advisory-locked transaction. Folding
  those inserts into the outer transaction would hide them and reissue duplicate
  VEKN IDs. A write joins the transaction only when passed `conn=tx_conn`
  explicitly, keeping the boundary visible at the call site.
- **Never start a DB-touching `asyncio.create_task` or `gather` inside a
  transaction.** The child inherits the ContextVar and would interleave operations
  on the shared connection (one `await execute` yields mid-flight) or outlive the
  `with` block. `_acquire` records the owner task and **raises** if the ambient
  connection is reached from another task, so this fails loudly. Every spawned DB
  task — Discord role sync, VEKN sync, push sends — fires post-commit.
- The pool is `autocommit=True`, so a multi-statement write needing consistency
  must take an explicit `conn.transaction()`. `delete_object` / `purge` are the
  fixed exemplar (object plus `avatars`/`banners`/`push_subscriptions` side rows,
  since there is no FK cascade).

### Stored-value migrations

`objects` is schemaless, so there are no *schema* migrations — but a field's
meaning lives in the code that decodes it, and `msgspec` decodes strictly. When a
stored value's shape or vocabulary changes, every row written under the old
reading raises on decode, and it raises for the whole list rather than the row.

`backend/src/migrations.py` is the one place those rewrites live: an ordered
tuple of entries, each a guard query naming the rows that still hold the old
shape and a function mutating one `full` document. A guard may select more than
the uid, and the extra columns reach the function beside the document — that is
how a rewrite whose new value depends on *another* object gets it, since the
function sees one document and cannot read. The runner takes them in
order, locks each row `FOR UPDATE` in its **own** transaction and re-saves it
through `save_object`, which recomputes all four projections — hand-written
per-column SQL would restate `compute_public/member/api/full` and put one fact in
two places, and a single wrapping transaction would stamp every row with the same
`CURRENT_TIMESTAMP`, which a catch-up cursor's strict `modified_at > since` can
split across.

The lifespan runs it right after `init_db`, before the app serves — **not** from
`init_db` itself, which fourteen ops scripts call and which a report-only run
must never mutate through. A failure propagates and the process does not serve:
the rows an entry targets are exactly the ones the running code cannot read, so
serving half-migrated restores the outage the mechanism removes, unbounded and
quiet instead of bounded and loud. The remedy is to roll **forward**: entries are
self-guarding, so fixing one and restarting resumes at exactly the rows still
pending. Rolling the deploy back is clean only while no row has moved — the
per-row transactions commit as they go, and the previous build cannot decode a
row the run already rewrote. `python -m backend.src.migrations` runs the
same guards without the app, reporting by default and rewriting on `--apply`;
that is how an entry is rehearsed against a copy of production before it lands.

Nothing in the tree records that an entry has run, so its proof is a section in
[post-deploy](post-deploy.md) and the two die in one commit —
`just migration-pairing` ([dev](dev.md#lint-gates)) fails on either half
outliving the other. That death condition is what an entry is for and what keeps
the per-boot guard queries near zero. `_stamp_missing_event_codes`, which runs
beside it, is deliberately not an entry: it mints a missing value rather than
repairing an unreadable one, nothing breaks while a code is absent, and it has no
condition under which it would ever be deleted.

The mechanism is for **bounded** row counts — tens to low thousands. A pre-serve
migration extends deploy downtime by its own runtime, so a corpus-scale rewrite
stays a post-deploy script with a stated, accepted window; `reproject_public.py`
is the standing example.

## Event system

**Business events** — domain actions like `Tournament.RoundStart`, processed by
the Rust engine. **All of them go through `POST /{uid}/action`**; there are no
per-event REST endpoints. The backend only deserializes the event JSON and calls
the engine, keeping the online (server) and offline (WASM) paths identical and the
engine the single source of truth for state transitions. Catalog:
[tournaments](tournaments.md#engine-event-catalog).

**Creating a tournament is the same shape.** `create_tournament` is the sole
producer of a new Tournament object on every path: WASM for the offline create,
PyO3 for `POST /tournaments`, and PyO3 again as the gate on the offline-created
insert (`go-online`/`sync-offline`), where the result is discarded because the
device's own state is authoritative. Both callers pass the same actor — uid and
roles, which is all create reads. A new gate belongs in `validate_config_fields`,
the one validator create and `UpdateConfig` share; written into the
`create_tournament` body instead it binds creation only, and a config edit walks
around it afterwards. The rank-legality and date-ordering checks sit outside it
because `UpdateConfig` must pass the merged config-over-tournament view. The route
keeps what the engine cannot decide: the REST authorization layer, country
normalization, the league-link lookup and the `VEKN_PUSH` round bounds. The
editable set is `CONFIG_FIELDS`, which `UpdateConfig` applies and which
`test_tournament_field_contracts.py` pins against `TournamentConfig`,
`CreateTournamentRequest` and a real create through the engine — a field missing
from any of them is un-editable, un-creatable, or dropped at creation.

**Read-only rules** the UI must agree with — may a finals start, is this table
scorable, who places where — are engine exports too, called **synchronously**
through `getEngine()` and safe inside a `$derived`. A predicate reimplemented in
TypeScript drifts from the engine and the UI ends up offering what the engine
refuses.

**The root layout gates every route on `initEngine()`**, so no caller ever sees a
cold engine and `getEngine()` throws rather than answering. There is no degraded
mode: every fallback the gate replaced hid controls, blanked standings or reported
a table scorable, and a red banner over that is worse than a splash. Gating is
safe offline because the service worker precaches the wasm atomically with the
shell (`cache.addAll`), so a servable shell implies a servable engine; the wait is
the network, once, on a device's first visit. The error branch offers a reload,
never a retry button — `initEngine()` latches its failure and re-throws forever.

**CRUD events** — Create / Update / Delete, synchronizing DB state to clients. The
payload is the full object including `uid` and `modified`. Flow: DB change → CRUD
event → SSE → IndexedDB.

**Ephemeral SSE events** — real-time, never persisted, never written to
IndexedDB. Today that is `judge_call`. See [sync](sync.md#ephemeral-events).

## Online and offline

Online: action → backend Rust engine → PostgreSQL → CRUD event → SSE broadcast →
IndexedDB → reactive Svelte UI.

Offline uses **primary-device ownership**, which is why no CRUD log or conflict
resolution is needed:

1. An organizer holding `sponsor_member` takes the tournament offline (`go-offline`)
   and it locks to their device. Offline play mints real members at go-online, so
   it takes `sponsor_member` on top of `organize_tournament`. A tournament can also
   be *created* while offline through the same form (detect-and-adapt): the WASM
   engine creates it born device-locked, and the server first learns of it at
   go-online, via the insert path.
2. Other devices see an "offline" message and cannot mutate.
3. The WASM engine processes business events locally and writes IndexedDB
   directly.
4. Offline-created players get temp UIDs, remapped to real UIDs on sync.

Going back online, the primary device sends the full tournament state plus offline
data; the server overwrites, remaps temp UIDs and resumes SSE. Ownership can move
by **force-takeover** (another organizer holding `sponsor_member` claims the lock,
warned about losing the primary's unsaved data) or **force-unlock** (emergency,
no sync, first-party sessions only — OAuth tokens are rejected). The primary can
also background-sync without unlocking (`sync-offline`).

go-online resolves and creates offline players **before** taking the `FOR UPDATE`
lock: an unlocked pre-check gates side effects, then the lock only re-verifies
authoritatively, remaps temp UIDs and saves — so no per-player connection is held
while the row is locked. Benign race: if organizer rights are revoked between the
pre-check and the lock, the re-check 403s after the users were already created
(orphaned, harmless).

Lock lifecycle, self-echo suppression, the 410/409 guards and server-managed field
re-pull: [sync](sync.md#offline-lifecycle).

## Mutation pipeline

Tournament actions are optimistic via WASM **on a device that can own the
tournament** — the organizer console, which offline mode locks to one device
([online and offline](#online-and-offline)). A player's device can never hold that
lock and so can never mutate offline: for it the local engine is a pre-flight
check only, and the action awaits the server before the surface reports any
outcome. Optimism there would buy nothing and has twice sold a success the server
refused. The two paths differ in *when the outcome is declared*, not in which
engine decides.

The owning device's path:

1. WASM processes locally → `{tournament, deck_ops}` → IndexedDB updated → UI
   reacts immediately.
2. The action is written to a durable outbox, then the server POST is sent async,
   serialized per tournament (`enqueueServerAction`).
3. On success, SSE delivers authoritative state and overwrites if different.
4. On rejection — no SSE follows and `modified_at` is unchanged — the client rolls
   back to the pre-action snapshot and surfaces the error, then drops the entry.

**The owning device's queue is durable.** The outbox entry is the whole rollback
closure — the event, the pre-action tournament and decks, the optimistic
`modified` stamps — stored before the POST leaves and removed only after that
POST has been answered and any rollback has landed. A reload, a locked phone or
an app killed in that window therefore replays the action on the next launch
instead of dropping it with no request, no rollback and no frame that would ever
correct it.

The replay claims only the entries present at launch, by id: anything appended
later belongs to a POST some tab still has in flight. It waits for the first
catch-up, re-reads under a web lock the live POST also takes — an entry
surviving both has no live sender left — and runs only while the tournament's
stored `modified` still equals the entry's. Unchanged means the server never saw
the action, because the engine leaves `modified` alone and every server commit
bumps it. Entries are removed by id rather than position, since a replay and a
live POST settle different entries of one outbox.

Three cases drop an entry unreplayed. A `modified` mismatch is ambiguous from
the outside — this action committed as the tab died, or a co-judge moved the
tournament — so it is dropped rather than applied twice; `StartRound` is not
idempotent. A console tap before the first catch-up releases the replay, so an
action never queues behind a catch-up that a venue with no uplink may never
deliver. Both warn. An entry whose account is not the one signed in is dropped
silently, since logout clears the synced stores but not the outbox and the
action is not this user's to report. A drop leaves the optimistic write
standing, neither posted nor rolled back: with no confirmed server state there
is nothing to judge it against, and the next full resync is what corrects it.

An unload flush was rejected for the same reason the gate exists: a `keepalive`
POST on `pagehide` cannot tell an in-flight request from a committed one. A
server-side idempotency key would settle it outright, at the price of a field on
`TournamentActionRequest` — one of the enumerating sites
[hazards](hazards.md#fields-silently-dropped) names — to turn a rare ambiguous
drop into a rare ambiguous replay.

A player's device instead runs WASM as a pre-flight, awaits the POST on that same
queue and reports the server's answer, so there is nothing to roll back. It leaves
the tournament row to SSE and re-applies only the deck ops once the server has
granted, against a freshly read deck list — the frame carrying the server's deck
uid may already have landed during the round-trip, and the pre-flight's own uid
would replace it with one no later frame corrects. A pre-flight rejection is not
final: the action still goes to the server, whose reason is the one shown, because
a player's IndexedDB is the copy most likely to be stale. Past that POST the
reverse holds — the server has already answered, so a failure must reach the caller
instead of falling through to the server-only path and posting twice. The refusal
is rendered by the surface that fired the action, never as a toast: the tournament
page's banner sits above the console, out of view from where a player acts. The
split is `is_organizer` in the actor context, the same `organize_tournament`
capability that chooses the console view.

Rollback rather than "SSE will correct" is deliberate: a rejection produces no SSE
event for that object, so deferring would leave bad optimistic state in IndexedDB
indefinitely. Rollback also self-heals the ambiguous case — a network error *after*
the server committed — because there `modified_at` did advance, so the
authoritative frame overwrites the rollback. This relies on overwrite apply
semantics; a field-merge would preserve the stale optimistic fields forever.

Non-tournament mutations apply optimistically and have no rollback path; a
rejection surfaces as an error toast.

## The Rust engine

The engine defines the canonical object schemas and business logic. `just dev`
rebuilds both targets; build one directly with `wasm-pack` or `maturin develop`
(see `engine/README.md` for commands, bindings and entry-point signatures).

| Module | Owns |
|---|---|
| `lib.rs` | entry point, WASM and PyO3 bindings |
| `permissions.rs` | every authorization predicate — see [access](access.md) |
| `sanctions.rs` | the Judges Guide v2 penalty reference (categories, labels, baselines, escalation ladder); `sanction_reference_json` |
| `seating/` | simulated annealing + staggered seatings |
| `tournament/mod.rs` | event processing, state machine, finals, `table_label` |
| `tournament/standings.rs` | standings, rating VP/GW, final placement |
| `tournament/sanctions.rs` | SA effective-round resolution (distinct from `sanctions.rs`) |
| `deck.rs` | deck parse/validate, TWDA export, `library_type_order_json` |
| `ratings.rs` | rating points, `ranking_eligibility`, the two player counts |
| `league.rs` | league standings (RTP/Score/GP) |
| `cards.rs` | card database lookup and name normalization |
| `error.rs` | the error taxonomy |

`backend/src/models.py` derives `SUBCATEGORIES_BY_CATEGORY` and
`BASELINE_PENALTIES` from `sanctions.rs` at import; the frontend reads it via
`getSanctionReference()`; the Discord bot fetches it from the public
`GET /sanctions/reference`.

### Standings computation

`compute_preliminary_standings`, `compute_rating_vp_gw`, the prelim-only invariant
and final placement are specified on [tournaments](tournaments.md#standings); the
engine module is `tournament/standings.rs`.

**The display path computes nothing.** `displayStandings` hands back the ranked
sheet — cascade, DQ zeroing and placement included — and
`tournament-utils.ts`'s `computeStandings` only marshals it into the row shape the
components render, formatting the finals score. It is the sole producer of the
standings every tournament surface reads, so a round-less VEKN import, which no
recompute ever reaches, is ranked by the same rule as a live event.

### Error contract

`engine/src/error.rs` is the single taxonomy for every engine rejection: the
`EngineError` enum with stable `code()` strings (`"tournament.already_registered"`)
and `params()` for i18n interpolation. `Display` renders canonical English kept
byte-identical to the `err_*` values in `frontend/messages/en.json`.

New rejection sites must use an explicit variant. `From<&str>` / `From<String>`
exist only for genuine deserialization failures and internal `.ok_or(...)` notes —
they collapse to `Internal { detail }` and silently demote a domain rejection.

Wire shape per surface: WASM throws a JS string `{"code","params","message"}`
which `callEngine()` re-throws as a typed `EngineError`; PyO3 raises a `ValueError`
with the same JSON body, parsed by `EngineRejection.from_engine()`; HTTP 400 is
`{"detail":"<English>","code","params"}` with `detail` kept a string for the
Discord bot and legacy clients.

Frontend fallback order (`toUserMessage`, which also localizes `apiRequest`
toasts): a `code` resolves through `errorCodeToMessage(code, params)` to the
paraglide `err_*` key in five locales; else the server `detail` in English; else
`"Request failed: <statusText>"`. An `internal` code yields a generic localized
message plus a `console.error` of the raw detail, so parse and invariant noise is
never shown; an unknown future code from version skew falls through to `detail`.
App-level checks mirroring engine rules reuse the engine codes so the same
condition localizes identically on every path.

## API conventions

- **Request bodies** are Pydantic `BaseModel` — FastAPI parses them
  automatically. Not `msgspec.Struct` over raw `bytes`: an unbound `body: bytes`
  won't read the request body.
- **Responses** use msgspec (`msgspec.json.Encoder`), faster than Pydantic. Python
  models are `msgspec.Struct`, mirrored by TypeScript interfaces.
- **Date-only fields** (expiry, event dates) accept `YYYY-MM-DD` and store UTC
  midnight. Full tz-aware datetimes are reserved for precise timestamps
  (`issued_at`, `modified`).
- **Scheduled times** (`Tournament.start`/`finish`) are stored **naive**, paired
  with the separate `Tournament.timezone` — never tz-aware. Readers anchor the
  wall clock in that zone, so a stored instant would get shifted by the venue's
  offset a second time. Every writer must follow: the create and config routes,
  the VEKN import, the legacy merge, and the server-side `finish` stamp.

## Cards and decks

**Build-time card database.** `scripts/update_cards.py` sources canonical card
data via `krcg.loader.load_online` and writes `engine/data/cards.json`. Refresh is
build-time, not boot: a daily workflow commits and tags `cards-<date>`, and the
file ships bundled in the wheel and the frontend build. At runtime it loads into
IndexedDB (`cards` store, keyed by card ID), and is handed to the engine once —
`loadCards` / `load_cards`, which parses it into the map the engine holds — so a
deck call passes a deck alone. The frontend memoizes that hand-off on the card
map's identity and rebuilds the map only when the served ETag differs from the one
it stored, so a session re-hands the catalog only when the catalog itself changed.

**Deck validation** is `validate_deck` in `engine/src/deck.rs`: unknown cards,
the banned list and a library over 90 are errors whatever the format. Storyline
never reaches it: the format has no decks at all rather than lax ones, the engine
refusing the upload ([tournaments](tournaments.md#configuration)). The rest of
the construction rules — crypt of at least 12, library of at least 60, one group
or two consecutive ones ([the game](domain/vtes.md#deck-structure)) — apply under
Standard and V5 only, Limited having no group rule and minimums that depend on the
booster count the app does not record. Under V5, a card outside that set is a
warning.

**Three name forms**, all four fields being engine parser lookup keys:
`printed_name` (bare, frontend display), `unique_name` (minimal group/advanced
disambiguator, used for text decklist export), `full_name` (always group/advanced
suffixed), plus `name_variants` (aliases, ordinals, accents). `normalize_name`
folds Latin accents to ASCII on both the index and the query, so an accent-free
spelling still resolves. The frontend renders `printed_name` with separate badges
— a circled group number (group `"any"` gets none) and an advanced glyph — rather
than a suffixed name string.

**DeckObject** fields: `tournament_uid`, `user_uid`, `round`, `name`, `author`,
`comments`, `cards` (card_id → count), `attribution`, `public`. The engine sets
`public` from `decklists_mode` plus tournament state (Winner / Finalists / All).
Deduplication keys on `(tournament_uid, user_uid, round)` on both sides of the
stack.

**Import** — raw-text paste parses locally through the WASM engine
(offline-capable). URL import (VDB / VTESDecks / Amaranth) and QR go through the
backend `GET /fetch-deck` proxy, which uses krcg providers to fetch and resolve
provider-native card ids — notably Amaranth's own — to VEKN ids against krcg's own
bundled card DB, independent of our `cards.json`. URL and QR import are disabled
offline; text import is not. Both ride `apiRequest`, so they inherit the
refresh-and-retry every other authenticated call has, and the proxy codes its
refusals (`deck_fetch.bad_link`, `deck_fetch.provider_unavailable`) so a dead
session, an unreadable link and a provider outage each read differently.

**Library type ordering** is `LIBRARY_TYPE_ORDER` in `engine/src/deck.rs`, exported
as `libraryTypeOrder` and read through `getLibraryTypeOrder()`. The engine's own
TWDA export and every frontend decklist rendering — the deck view, the event text
record — group by it.

Decks are not bundled into the tournament SSE event: the tournament page listens
for `type === "deck"` events and re-queries the grouped decks.

## Subsystems

### Leagues

Aggregate tournaments into leagues with standings; synced like tournaments and
users, stored in IndexedDB `leagues`. Fields: `name`, `kind` (League /
Meta-League, two levels maximum), `standings_mode` (RTP / Score / GP), `format`,
`country`, `start`/`finish`, `description`, `organizers_uids`, `parent_uid`, and
`open_to_country_princes` — a country-league-only flag letting same-country
Princes attach their own tournaments without becoming organizers (attach-only,
inert on a worldwide league).

Standings are computed at read time through the engine on both sides; the league
SSE payload is **config only**, with standings derived client-side from IndexedDB
tournaments. GP and RTP modes use `compute_final_standings` to derive placement.

*GP (Grand Prix)* is an established league-scoring convention — not part of the
hard VEKN tournament rules, and not a "house rule" either: winner 25; finalists
(2nd–5th) 15; then 10, 9, 8, 7, 6 for 6th–10th; 3 for 11th and beyond. Ties take
best-position points with a competition skip — two tied for 6th each get 10 and
the next is 8th — never averaged. Position is **final** placement, not prelim
array order.

League RTP points use prelim-only standings VP/GW, while the global rating uses
totals including finals. The two RTP consumers legitimately diverge.

### Promo catalog

An IC-managed catalog of promotional items (BCP promo cards and packs, alt-art or
unreleased, with no krcg link) distributed at events. Synced via SSE, stored in
IndexedDB `promos`.

Fields: `name`, `kind` (card/pack/other), `description`, `release_date`, `active`
(retirement flag — a promo referenced by a tournament report is refused a
hard-delete and retired instead, never soft-deleted, so historical references keep
resolving), `allowed_ranks` / `league_uids` (distribution-picker gating, UX-only
with no engine or access-control enforcement; empty means unrestricted, both set
means AND), `image_path`, and `holdings` (`holder_uid → {assigned, remaining}`, a
server-written aggregate, full projection only).

CRUD is plain REST, not the engine event pipeline: `POST/PUT/DELETE /api/promos`,
IC-only, with delete returning 409 while a tournament still references the uid.

**Distribution reporting.** `Tournament.promos_distributed` (`{promo_uid, qty}[]`)
plus `promo_stock_source_uid` (multi-organizer stock attribution, defaulting to
the reporting organizer) are written by the `ReportPromos` engine event. Unlike
the VEKN and TWDA bookkeeping fields both are member-visible, and neither is ever
touched server-side. `ReportPromos` skips the post-finish rating recompute.

**Inventory ledger.** `promo_ledger` is a non-synced side table, append-mostly and
the source of truth for holder inventory. Kinds: `intake` (a print batch received
from BCP, credited to the receiving holder in `from_uid`, no `to_uid`),
`assignment` (stock moves holder→holder) and `distribution` (a non-tournament
exit, no `to_uid`). Corrections are compensating negative-`qty` rows, never edits.
A holder with no recorded intake is the old fallback: stock can still go negative
from assignments and distributions alone, and the UI hides the negative source.

`POST/GET /api/promos/ledger` — POST is self-sourced except for IC, who may record
for another holder; `intake` is additionally officials-only, with NC able to
intake into their own pool and IC into any holder's, and plain members not at all.
`assignment` rejects `from_uid == to_uid` with a 400: it credits and debits the
same holder, a no-op in the recompute — use `intake`. GET returns the whole
role-scoped ledger with no pagination (IC and NC see every row, everyone else only
rows they are party to).

`recompute_promo_stock()` re-derives, per affected promo, the full per-holder
`Promo.holdings` from every ledger row plus live tournaments' `promos_distributed`
attributed to each report's stock source, and merges the matching keys into each
holder's `User.promo_stock`, dropping stale keys for holders who fall out. Both
are full-projection fields, so remaining stock always streams through the normal
SSE pipeline instead of being derived client-side. Triggers: every ledger POST, a
catalog PUT (self-heal against a concurrent overlap), any tournament save whose
`promos_distributed` set changes, `users/merge` (remapping ledger holder uids
first), and a daily self-healing pass. It is fire-and-forget so route handlers
never block. **Hard invariant**: the recompute only reads and attributes
`promos_distributed`, never writes it — the offline device stays sole authority
over that field.

A `RaffleDraw`'s optional `prize_promo_uid` is display-only and never written to
`promos_distributed`, so a raffled promo cannot double-count; the distribution
editor surfaces unreported raffled promos as a dismissible pre-fill hint, and
warns — never blocks — when a submitted report drives the submitter's own stock
negative.

Promo images are the one **unauthenticated** blob endpoint, so the service worker
can cache them cache-first for offline raffle and picker display; the catalog sync
prefetches every active promo's image on save, since the SW cache only populates
lazily on fetch and a device may go offline having never viewed the promo.

### Shared timer

Online-only, and **entirely optional** — `round_time = 0` means no timer, and
offline venues and async pods run on the wall clock. Timer state lives on the
`Tournament` object and syncs via the normal SSE CRUD-on-save; clients compute the
countdown locally, so there are no per-second broadcasts. The countdown anchors on
`Date.now()` against the server-written timer state, deliberately not
`performance.now()`: the wall clock survives sleep and hibernation and gives every
viewer the same single server-clock reference, so devices converge on one
remaining time; the monotonic clock serves only as a divergence watchdog.

The rules put a **two-hour floor** on a round
([§3.1.1](domain/tournament-rules.md#round-structure)), and a round shorter than
that unsanctions the event if any table ends on time being called
([JG §5.2](domain/judging.md#event-organization-5)). The floor is enforced by
construction, not validated: the round and finals pickers offer only *no timer*
and 2h–3h in quarter-hour steps, so a sub-floor value is unreachable from the UI.
It is a hard block rather than a warning because a called time on a short round
unsanctions the event outright — that is not a trade-off left to the organizer.

`TimerState` is `started_at` (UTC, when started or resumed),
`elapsed_before_pause` (seconds) and `paused`. The tournament carries
`timer: TimerState` plus `table_extra_time` (table index → extra seconds); config
carries `round_time` (seconds, 0 = no timer) and `finals_time` (0 = use
`round_time`). Endpoints `POST /{uid}/timer/{start|pause|reset|add-time}` are
organizer-only, online-only, Playing-state, and save-and-broadcast; extra time
caps at 600s total.

**Per-round lifecycle is backend, not engine.** Every round and finals lifecycle
event resets the timer to a fresh full **paused** state and clears extra time.
Starting a round never launches the clock — players need time to get seated, so
the organizer starts it explicitly. `AddTable` is excluded so a mid-round table
add never resets a running clock. A single global timer is meaningless with
parallel rounds (each self-organized pod is its own round), so the frontend and
the bot deactivate it whenever more than one round is live.

### Announcements

Organizer-initiated, online-only, on the `Tournament` object, syncing via normal
CRUD-on-save — the same carve-out as the timer, not processed by the engine.

`Announcement` is `id` (uuid7 hex, the client dedup and dismissal key), `body`,
`created_at`, `author_uid` and the denormalized `author_name`. The list is capped
to the most recent 20 with a 280-character body limit. `POST /{uid}/announce` and
`DELETE /{uid}/announce/{id}` are organizer-only and online-only, returning 423
while offline. Member-projected automatically, since the member projection is a
denylist. Banners are dismissible per-device via localStorage.

### Call for judge

`POST /{uid}/call-judge {table}` — the caller must be authenticated and seated at
that table in the current round, with the tournament in Playing state and not
offline. It emits the ephemeral `judge_call` SSE event to the tournament's
explicit organizers only — they are the ones on premises.

### Web Push

Opt-in browser notifications, degrading gracefully when VAPID keys are absent, and
gated on iOS behind Add-to-Home-Screen (PWA standalone mode).

`push_subscriptions` (endpoint PK, `user_uid`, `p256dh`, `auth`, `ua`,
`created_at`, `last_seen_at`) is a side table, **not** projected — these are send
credentials, never display data. Pruned on owner hard-delete and lazily on a
send-time 404/410.

Three env vars: `VAPID_PRIVATE_KEY` (raw base64url scalar), `VAPID_PUBLIC_KEY`,
`VAPID_SUBJECT`; generate with `just vapid-keys`. **The public key is delivered at
runtime** (`GET /api/push/vapid-key`), not baked into the frontend build — the
frontend ships as one release artifact across environments, and a baked key would
force beta and prod to share a keypair.

Send path: pure builders return locale-independent *specs*, and `render_payload`
localizes per subscription in that row's stored locale — a user may carry a French
phone and an English laptop. Delivery is native async over a single shared
`aiohttp.ClientSession` per fan-out, whose connector pools keep-alive connections
per push host (most Chrome subscriptions share `fcm.googleapis.com`), so a fan-out
reuses connections instead of a fresh TLS handshake per push. `pywebpush` owns the
RFC 8291 payload encryption and RFC 8292 VAPID signing; we own only the transport.

| Trigger | Who receives |
|---|---|
| `StartRound` / `SelfOrganizeRound` / `StartFinals` | each player newly seated in the last round or the finals |
| `AlterSeating` / `SwapSeats` / `SeatPlayer` / `UnseatPlayer` | only players whose table or seat changed, landing on a still-live table of a Playing tournament — corrections to finished tables page no one, and unseated players get nothing |
| `POST /{uid}/announce` | checked-in, playing and completed participants except the poster; registered players too before round 1, since check-in-window announcements must reach the unchecked |
| `POST /{uid}/call-judge` | the tournament's organizers except the caller |

`RestoreRound` is excluded — it re-seats no one. Seating and judge-call bodies
resolve table-room labels so a push says "Main Hall 3" exactly like the app and
the wall signs, each locale carrying its own "Table N" for an unroomed table, and a
re-seat push reuses the round's tag to replace the player's stale assignment
notification. The judge-call push carries `renotify: true` so a repeat call
re-alerts. Every send is fire-and-forget and fires **after** the tournament
transaction commits.

There is deliberately no unauthenticated rotate endpoint — an endpoint-only
rewrite would be a notification-hijack vector. The service worker's
`pushsubscriptionchange` handler re-subscribes locally only (it has no auth); the
app reconciles the new endpoint server-side on next open.

### What's new

A dismissible modal on first load after an upgrade, listing the `CHANGELOG.md`
entries this device has not seen. Entirely client-side — no version endpoint is
involved, and none is wanted ([dev](dev.md#deployment)).

`CHANGELOG.md` is imported raw from the repository root by
`frontend/src/lib/changelog.ts` and parsed at load. An entry is a
`## vX.Y.Z — YYYY-MM-DD` heading plus the markdown beneath it; `## Unreleased`
matches nothing, so notes written before their tag is cut never reach a user. The
newest version this device has seen lives in `localStorage.changelog-seen`, and
everything above it is pending.

**A first-ever visit shows nothing.** An absent marker baselines to the newest
entry rather than dumping the whole history — which is also what an existing user
gets on the release that introduces the modal. `unseenEntries()` does that write
itself on an absent marker, so it is a query with a storage side effect; the modal
only writes again on dismissal.

The e2e image copies `CHANGELOG.md` in separately (`frontend/Dockerfile.test`),
since the import reaches above the frontend directory the container holds.

Entries stay English inside a translated shell ([i18n](i18n.md#the-changelog)).

The upgrade itself needs no hook. The service worker already auto-applies a waiting
worker at boot and reloads, so a newer bundle simply arrives carrying entries the
device has not seen; the notes reach the build they describe because `just release`
stamps them into the commit it tags ([dev](dev.md#the-release-order)).

### Binary assets

Binary image blobs live in dedicated side tables — `avatars`, `banners`,
`promo_images` — never in `objects`, whose rows are projected and streamed to
every client's IndexedDB. Each side table uses the owning object's uid as PK plus
`data BYTEA` and `content_type`.

A small **path string** on the synced object points at the served URL. On upload a
fresh versioned URL is written to the object and saved, so the resulting SSE
broadcast propagates it to all clients. Versioned URLs are served
`Cache-Control: public, max-age=31536000, immutable`; an unversioned request gets
a short TTL. No client-side cache-busting is needed.

| Asset | Table | Path field | Level | Endpoints |
|---|---|---|---|---|
| User avatar | `avatars` | `avatar_path` | member | `POST/GET/DELETE /api/users/{uid}/avatar` |
| Tournament banner | `banners` | `banner_path` | public | `POST/GET/DELETE /api/tournaments/{uid}/banner` |
| Promo image | `promo_images` | `image_path` | public, **unauthenticated** GET | `POST/GET/DELETE /api/promos/{uid}/image` |

URL shape `/api/{users|tournaments|promos}/{uid}/{avatar|banner|image}?v=<epoch-ms>`.
`banner_path` is public so it can serve as the `og:image` for share links.

Avatars are cropped client-side and compressed server-side. Banner upload is
organizer-gated, 1 MB, webp/png/jpeg, and blocked while offline so `banner_path`
cannot diverge from the device snapshot and get overwritten at go-online. Promo
image upload is IC-gated with the same limits and needs no offline guard, catalog
edits being online-only already.

The service worker routes same-origin `/api/promos/*/image` requests to a
cache-first handler — a deliberate exception to its default rule that every other
same-origin GET passes through untouched, so authenticated responses never land in
Cache Storage.

### NDA records

The playtest enrollment workflow: a PTC (or IC, `manage_nda` in
[access](access.md#capabilities)) requests a signature, the member click-signs
the BCP NDA in-app, and the resulting record gates PT grants
([access](access.md#capabilities), Appointments).

Records live in the `nda_records` side table — one row per request or upload,
never in `objects`, never projected or synced ([sync](sync.md#access-levels)):
the sealed file and the signer's PII are served only by gated REST reads with
`Cache-Control: private, no-store`. Endpoints, all under
`/api/users/{uid}/nda`: `GET` (status + records; PTC/IC or self), `POST
/request` (PTC/IC; one open request per member, enforced by a partial unique
index), `GET /document` (the agreement text, prefilled with the member's name
and the current date), `POST /sign` (self-only; requires the pending request),
`POST /upload` (PTC/IC; paper-scan fallback, PDF or image, 8 MB), `GET
/{record_uid}/pdf` (the sealed file).

Every read endpoint is *self or PTC/IC*, so the member sees their own evidence:
the profile's Account tab lists their signed and uploaded records with the
signature date and a re-download of each sealed file, and `/nda` shows that same
standing state instead of the no-pending-request dead end once the flow is over.
The status read is the profile page's one silent per-visit online check —
records are never synced, so nothing else can surface them.

The document is a versioned constant in `backend/src/nda.py` (`NDA_VERSION`,
sha256 over the template): each signature pins the exact (version, hash) it was
shown, so BCP wording changes never orphan old evidence. Signing renders a
sealed PDF — the filled agreement plus an audit page carrying the typed name,
email, address, phone, member uid, VEKN id, requester, UTC timestamp, record id,
version and hash — stores it in the row, and emails the signer a copy
best-effort (the record stands even when SMTP fails). The PDF embeds DejaVu, so
the evidence fields render Latin, Greek and Cyrillic; characters outside that
coverage (CJK among them) drop from the rendered PDF with only an fpdf warning,
though the typed name is stored verbatim in the row either way. The paper template's BCP
countersignature question (pre-embedded image vs offer/acceptance wording) is
BCP's call and still open; the audit page names Black Chantry's signatory as the
paper template does.

Lifecycle: the record **persists after PT is revoked** (it is the evidence, not
the role), dies with the member's hard delete (`delete_object` and the 30-day
purge clean the side table), and follows the *person* through account surgery —
merge re-homes it on the survivor, detach takes it to the personal account, like
`calendar_token` (pinned by `test_surgery_moves_nda_record_with_the_person`).
Existing PT holders from before this workflow keep the role and surface as
missing-NDA on the member page for the PTC to backfill via the scan upload; an
upload also resolves any open signature request in the same write.

### Community links

Member-contributed links to external community resources, with moderator
oversight. `community_links` is a field on `User`, defaulting to `[]`.

`CommunityLink`: `type`, `url`, `label`, `languages` (ISO 639-1, capped at 5),
`country`, and `moderation` — **one value, not a record**: `hidden`, `national`
(NC) or `global` (IC), null when no moderator has acted. Who moderated and when
is logged, never stored: nothing read it back, and an audit field on a synced
object is one every projection then has to withhold. The backend validates only
the two-letter shape of a language code.

The curated list of content languages lives in `languages.ts`, labelled by
endonym. It is a **separate and wider vocabulary than the five interface
locales** ([i18n](i18n.md)) — a member writes in the language they speak — but
deliberately curated rather than the whole of ISO 639-1: the shortlist is what
the pool's filter has to stay legible against, and a missing language is one
line.

`engine/src/community.rs` owns the type table: one row per platform giving its
**placement** — `channel` (a group venue) or `content` — and, for content, its
**media** kind (video, podcast, text, social). Python builds
`CONTENT_LINK_TYPES` from it at import and raises if the enum has drifted; the
frontend reads it through `getCommunityLinkReference()`. Adding a platform is a
row there plus a label, colour and icon in `CommunityLinkPills.svelte`.

**A link carries its own country**, defaulting to the owner's at creation and
owner-settable — the Brazilian Discord run from Portugal. Every moderation
decision keys off the link's country, never its owner's. It is **required**: a
national pin files a link under a country, so one without a country would be
pinned into a card nobody can reach. The editor's country field has no empty
choice, so a member with no country of their own picks one there rather than
being turned away.

**Placement follows the pins, not the platform**, because platform does not
determine function: an NC's Instagram is an announcements channel and a player's
is content. A global pin puts a link in the Global card and a national pin in its
country's card whatever its platform; only an unpinned link falls back to its
placement, a channel into its country's card and content into the pool. The page
shows the Global card, the reader's country, a country search that materializes
one further card, and the content pool filtered by a language multiselect —
seeded once from the reader's locale, never re-asserted — and a media facet.
Officials sit inside their country's card, behind sign-in, the NCs open and the
Princes folded behind their count — a visitor came for the coordinator, and a
country with a dozen Princes buries them. A card with nothing
pinned and no groups says so to whoever can pin there, since getting each NC to
pin a few links is what actually launches the page. `?sponsor=1` hides every link
section and narrows the cards to the visitor's country, falling back to every
country with a reachable official.

A content link must declare a language, since the pool filters on one. A
language-less link predating that rule may be resubmitted unchanged — the whole
array goes over the wire, so one legacy entry would otherwise block every later
edit — and shows under every filter until rewritten.

Any user with a `vekn_id` may add, limit 5 (10 for IC/NC/Prince). One editor
modal serves both the community page and the profile, sending the whole array
through `PATCH /auth/me`. On update, existing moderation is re-applied by URL
match, so a rewritten URL drops its pin and the editor warns before saving.
Hidden and the two pins are mutually exclusive, so a link carries **one
four-valued state** — `none` (stored null) / `hidden` / `national` / `global` —
and both editors set it through `community_links.py`, which gates each value on
the capability it needs: `moderate_link` for none and hidden, `promote_link_national`,
`promote_link_global`. Officials curate their own links through that same
country-scoped grant, not a self-service exemption, which is what lets the editor
carry the state itself: an NC files their country's Discord already pinned rather
than saving it and hunting for an icon. An absent `state` leaves moderation
alone, so an ordinary resubmission never clears someone else's decision.

A card shows a link and, for anyone who may change it, one edit button — the
whole surface, no inline moderation icons. `PATCH /auth/me` carries the owner's
own edits; `PATCH /api/users/{uid}/community-link-moderation` carries a
moderator's, and may change **every field except the URL**. The URL is the
identity moderation is keyed on, and rewriting it would let a moderator point a
member's link somewhere else.

`GET /auth/me/link-title` reads the target's `og:title`, else its `<title>`, to
seed an editable label. It is the only place the server fetches an address a
member typed, and `link_preview.py` holds the guards
([hazards](hazards.md#outbound-fetches)).

### Calendar

`GET /api/calendar/tournaments.ics` serves iCal for client subscriptions. Feeds:
**personal** (`?token=<calendar_token>`, agenda-matched), **country**
(`?country=XX`) and **global** (no params); `?online=false` excludes online events
from any feed.

`calendar_token` is nullable on User, generated on demand, stripped from SSE, only
visible via `/auth/me`, and backed by a partial index.

Agenda matching: the user organizes the event (any state), participates in it (any
state), or — non-finished only — it is in their country, online, or an NC-level
championship on their continent.

Personal feeds keep recently-finished own events for 90 days keyed on `finish`:
subscribed calendars reconcile on every poll, so an event leaving the feed is
*deleted* from the subscriber's calendar, and history must not vanish at finish.
Country, global and league feeds stay upcoming-only.

**Anonymous feeds render venue and address into LOCATION**, which takes no special
casing — both are public-projection fields. That is consistent with the `.ics`
being an advertising artifact mirroring vekn.net's public event calendar, where
full addresses show anonymously; venue granularity is the organizer's data-entry
choice. `venue_url` is the exception, withheld on an online event because there it
is the join link rather than a venue website.

### Reports and social sharing

**The event's text record is produced client-side**, by `generateResultsText`
(`social-text.ts`) from the tournament, its player info and the winner's deck —
all of which the device already holds offline. `copy-results.ts` takes that one
render to either destination: the clipboard, or a `.txt` download named by the
event code. There is no report endpoint; the server has no input the device
lacks, and a download navigation cannot carry the bearer token anyway. Sharing
also produces a canvas-rendered PNG, from the finished-tournament views. The
player-facing copy-results action shares text plus the link only, with no image
generation of its own — the OG stub below already turns the shared link into the
picture card.

### The short event code

`Tournament.event_code` is the event's permanent public handle, public projection,
resolved at `/t/{code}`. A `uid` is 36 characters and unsayable, and the identifier
that has served that role — the VEKN event id, which names the TWDA file, the forum
post and the vekn.net URL — dies with the
[decommission](vekn-decommission.md).

**It is the identifier the outside world already uses**, by a precedence evaluated
**once**: `external_ids['vekn']`, then `external_ids['twda']` — the archive's own
key, a slug like `2010czechecq` on all but 14 reconstructions, and the name of the
file the TWDA publishes — then a minted 6-character Crockford base32 code, never
all digits so it cannot read as a vekn id. So the numbers and slugs already cited
by 4538 archive entries keep resolving against us.

**Never rewritten.** An event that mints its own code and later gains a vekn id
keeps the minted one: rewriting would move a published TWDA branch and break every
link already shared. Any path that rebuilds a tournament row must carry it over
explicitly, exactly like `checkin_code` — the VEKN sync's rebuild does.

Assignment waits on the VEKN calendar push that `POST /api/tournaments` already
fires, since a successful push is what supplies the vekn id the event should carry
(`_maybe_push_vekn_event`). Every other ingress knows its answer at insert and
stamps inline, go-online included — an event created offline has only the hourly
batch push ahead of it, and that push stops entirely at the decommission, so it
mints rather than waits. A row that reaches neither — a restart in between — is swept at
startup, capped at 100, over which it names `backfill_event_codes.py` rather than
minting a corpus before the app answers. Uniqueness is a unique index on
`lower(event_code)` spanning soft-deleted rows, so a code is never reissued and a
mint collision is simply retried.

Resolution is case-insensitive and falls back to `external_ids['vekn']` on a miss,
which covers an event whose vekn id arrived after its code was minted. The fallback
can never shadow a code, since a hit on the code ends the lookup.

`/t/{code}` redirects to `/tournaments/{uid}`: the uid route reads `params.uid`
throughout, and the uid form can never be retired anyway — it is in the TWDA, in
push notifications, in every link shared to date, and it is the only form an
offline-created event has before it syncs. Every link meant to leave the app emits
the short form when there is one and the uid form otherwise, never a wait: the
share and copy-results paths, both OG stubs, the `.ics` feed, the deck header
submitted to the TWDA, and the Discord bot's announcements. In-app deep links —
push notification targets — stay on the uid the router already navigates.

**Open Graph stubs.** Social link-preview crawlers don't run JavaScript, so they
would always see the static SPA shell with the site-wide `og:image`. nginx
UA-splits `/tournaments/{uid}`: humans get the static SPA (SW-cacheable,
offline-first unaffected), social bots are proxied to a FastAPI route that renders
a minimal HTML stub from the public projection. With a `banner_path` the stub uses
`twitter:card=summary_large_image` (1200×630), otherwise the 512×512 site icon
with `summary`. Unknown or deleted uids fall back gracefully — crawlers never get
a 404.

Search engines are deliberately excluded from the UA list: they render JS and
should index the real SPA route. The UA list lives in the nginx template that beta
and prod both render. An unlisted crawler gets the generic site-wide card.

`/tournaments/{uid}` is **not** in the proxied-prefix allowlist — it is served
statically for humans and reaches FastAPI only through the named-location bot
proxy. `/t/{code}` works the same way, and both stubs canonicalise on the short
form where the event has one, so the two URLs do not read as two pages.

### Account surgery

**Deceased members.** `User.deceased_at` is an in-memoriam flag with a date, plus
`deceased_by_uid` for audit (full-only). This is **not** a soft-delete: tournament
history, ratings and rankings are preserved and the record stays active. Set and
cleared via `PATCH /api/users/{uid}/deceased`, requires a `vekn_id`, never pushed
to VEKN, and tracked in `local_modifications` to block a VEKN-sync overwrite.

**Delete member.** `DELETE /api/users/{uid}`, IC-only, soft-deletes a
VEKN-**less** account — the mirror of deceased, which targets VEKN-bearing ones.

**Immovable-uid invariant**: a uid carrying a `vekn_id` is never re-keyed and
never soft-deleted. Everything keyed to it — sanctions, decks, tournament results,
ratings, wins, cooptation — stays attached. Only the account *without* the
`vekn_id` ever moves.

**Merge** (`POST /admin/users/merge`, IC only): the VEKN-bearing uid is always the
survivor. Auth methods, sanctions, decks and `coopted_by` migrate from the dying
uid, which is then soft-deleted; roles and `local_modifications` are consolidated
by union, without consulting the appointment matrix. Ratings and wins are derived,
not merged: the survivor's Hall of Fame count is recomputed on the spot, because a
reassigned deck can complete a win they already held, while their rating waits for
the nightly pass — no result changed hands, only ownership. The route separately remaps `promo_ledger` holder
references onto the survivor and triggers a full promo stock recompute.

**Detach** splits one account in two: the VEKN record keeps its uid and all keyed
data — community links and promo stock among them, both earned by the VEKN
identity and keyed to its uid — while a fresh uid walks away with auth methods
and personal/contact PII only. Callers are **self-abandon** (blocked while an
active suspension or probation is held — the sanction stays with the VEKN record;
admin force-abandon is exempt) and **admin displace**, which frees a VEKN ID
before re-linking it, the new owner then being merged into the freed record.

Reassigning object references during merge or detach must return `BroadcastData`
and broadcast, or other clients stay stale until the next snapshot resync.

### Archon Excel import

`GET /api/tournaments/archon-template` yields a blank template;
`POST /api/tournaments/{uid}/archon-import` uploads one. The importer extracts
rounds, tables, seating, scores and players, matching players by VEKN ID.

## Scheduled background tasks

| Job | Schedule | Module |
|---|---|---|
| VEKN sync (members, tournaments) | at startup, then every `VEKN_SYNC_INTERVAL_HOURS` | `vekn_sync.py`, `vekn_tournament_sync.py` |
| Snapshot rebuild, only if the corpus moved | at startup, then checked every 15 min | `snapshots.py` |
| OAuth cleanup | hourly | `db_oauth.py` |
| VEKN push batch | hourly, configurable | `vekn_push.py` |
| Sanction cleanup | daily, 01:00 UTC | `db.py` |
| Deleted-objects purge | daily, 01:30 UTC | `db.py` |
| Promo stock recompute | daily, 02:00 UTC | `promo_stock.py` |
| Rating recompute (ratings, then Hall of Fame wins) | daily, 02:30 UTC | `ratings.py` |
| TWDA sync (reconstruction + winner decks) | daily, 05:00 UTC, own flag | `twda_import.py` |

**Every daily job is a `CronTrigger` at a pinned UTC hour, never an interval** —
an interval job of a day or more can never fire here
([hazards](hazards.md#deploy)). Both deployed environments set
`VEKN_SYNC_INTERVAL_HOURS` to 24, so the VEKN chain's own timer is likewise
unreachable and its daily cadence is really its startup kick; the kick is the
mechanism, the interval is the ceiling.

The tournament sync and the TWDA sync hold one lock between them, so neither
reads the corpus as lacking an event the other is halfway through creating. That
is all it buys: **the two are not ordered, and the two orders are not
symmetric.** A reconstruction landing first heals, because `_adopt_same_event`
adopts a vekn-less same-day copy and carves out a reconstruction's winner-only
roster explicitly. The vekn copy landing first does not: the archive sync matches
only its own `twda` external id, so a decisions file that still reads `create`
mints a second row, and the adoption's `taken` guard then refuses a copy already
holding a vekn id. Regenerating the decisions file against the current corpus is
what prevents that — never the schedule. The lock is also in-process only:
`scripts/backfill_twda.py` and the legacy-archon merge write the same corpus from
outside it.

The purge hard-deletes soft-deleted objects older than 30 days and also drops
orphaned `avatars` / `banners` / `push_subscriptions` side-table rows — there is no
FK cascade.
