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
`full` NOT NULL — plus `type`, `modified_at`, `deleted_at` and `calendar_token`.
Index `(type, modified_at, uid)`. The trade-off bought: a single schemaless table
(no migrations for schema changes), pre-computed projections (zero read-time
filtering), fast iteration.

Synced types: **User, Sanction, Tournament, DeckObject, League, Promo**. VtesCard
is static data loaded into IndexedDB. DeckObject is standalone, not embedded in
Tournament.

`calendar_token` is the one non-projected column — a per-user `.ics` feed secret
that must never be broadcast, and every projection is broadcast (`full` reaches
non-owners). It is a 1:1 column rather than a table to avoid a join on the hot
`get_user_by_uid` path; `save_object` COALESCEs it so token-less writes preserve
it, and `clear_calendar_token()` is the explicit drop path.

**Soft delete** sets `deleted_at = now()`; SSE broadcasts the deleted object so
clients — including ones offline during the delete — remove it from IndexedDB on
reconnect. A daily job hard-deletes after 30 days.

## Database access

psycopg3 async, no ORM. The pool is small (`max_size=20`, autocommit), sized for a
~2 GB VPS, so connections must cycle fast: check one out, run a query, release.
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

## Event system

**Business events** — domain actions like `Tournament.RoundStart`, processed by
the Rust engine. **All of them go through `POST /{uid}/action`**; there are no
per-event REST endpoints. The backend only deserializes the event JSON and calls
the engine, keeping the online (server) and offline (WASM) paths identical and the
engine the single source of truth for state transitions. Catalog:
[tournaments](tournaments.md#engine-event-catalog).

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

Tournament actions are optimistic via WASM:

1. WASM processes locally → `{tournament, deck_ops}` → IndexedDB updated → UI
   reacts immediately.
2. The server POST is sent async, serialized per tournament
   (`enqueueServerAction`).
3. On success, SSE delivers authoritative state and overwrites if different.
4. On rejection — no SSE follows and `modified_at` is unchanged — the client rolls
   back to the in-memory pre-action snapshot and surfaces the error.

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
| `tournament/mod.rs` | event processing, state machine, finals |
| `tournament/standings.rs` | standings, rating VP/GW, final placement |
| `tournament/sanctions.rs` | SA effective-round resolution (distinct from `sanctions.rs`) |
| `deck.rs` | deck parse/validate, TWDA export |
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
IndexedDB (`cards` store, keyed by card ID) and the Rust engine does lookup and
deck validation.

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
offline; text import is not.

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
([JG §5.2](domain/judging.md#event-organization-5)). The app does not check the
configured value against that floor today.

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

`RestoreRound` is excluded — it re-seats no one. Seating bodies resolve table-room
labels so a push says "Main Hall 3" exactly like the app and the wall signs, and a
re-seat push reuses the round's tag to replace the player's stale assignment
notification. The judge-call push carries `renotify: true` so a repeat call
re-alerts. Every send is fire-and-forget and fires **after** the tournament
transaction commits.

There is deliberately no unauthenticated rotate endpoint — an endpoint-only
rewrite would be a notification-hijack vector. The service worker's
`pushsubscriptionchange` handler re-subscribes locally only (it has no auth); the
app reconciles the new endpoint server-side on next open.

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

### Community links

Member-contributed links to external community resources, with moderator
oversight. `community_links` is a field on `User`, defaulting to `[]`.

`CommunityLink`: `type` (Discord, Telegram, WhatsApp, Forum, Facebook, Website,
Twitch, YouTube, Reddit, Instagram, Blog, Other), `url`, `label`, `languages`
(ISO 639-1, capped at 5; empty shows under every filter), and `moderation`
(`status` hidden|promoted, `by`, `at`, `scope` global (IC) | national (NC)). The
backend validates only the two-letter shape; the curated UI list lives in the
frontend.

Any user with a `vekn_id` may add, limit 5 (10 for IC/NC/Prince). On update,
existing moderation is re-applied by URL match. Moderation actions map to the
`moderate_link` / `promote_link_national` / `promote_link_global` capabilities —
officials pin their own links through the same country-scoped grant, not a
self-service exemption.

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

`GET /api/tournaments/{uid}/report` (organizer-only) yields text (standings and
results) or JSON (full data). Sharing produces a canvas-rendered PNG plus plain
text with deck info, from the finished-tournament views. The player-facing
copy-results action shares text plus the link only, with no image generation of
its own — the OG stub below already turns the shared link into the picture card.

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
proxy.

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
uid, which is then soft-deleted; ratings, wins, roles and `local_modifications` are
consolidated by union. The merge unions both accounts' roles without consulting
the appointment matrix. The route separately remaps `promo_ledger` holder
references onto the survivor and triggers a full promo stock recompute.

**Detach** splits one account in two: the VEKN record keeps its uid and all keyed
data, while a fresh uid walks away with auth methods and personal/contact PII
only. Callers are **self-abandon** (blocked while an active suspension or
probation is held — the sanction stays with the VEKN record; admin force-abandon
is exempt) and **admin displace**, which frees a VEKN ID before re-linking it, the
new owner then being merged into the freed record.

Reassigning object references during merge or detach must return `BroadcastData`
and broadcast, or other clients stay stale until the next snapshot resync.

### Archon Excel import

`GET /api/tournaments/archon-template` yields a blank template;
`POST /api/tournaments/{uid}/archon-import` uploads one. The importer extracts
rounds, tables, seating, scores and players, matching players by VEKN ID.

## Scheduled background tasks

| Job | Schedule | Module |
|---|---|---|
| VEKN sync (members, tournaments) | every 6h, configurable | `vekn_sync.py`, `vekn_tournament_sync.py` |
| TWDA sync (reconstruction + winner decks) | every 24h, configurable, own flag | `twda_import.py` |
| VEKN push batch | hourly, configurable | `vekn_push.py` |
| Legacy-archon merge | daily, systemd timer | `scripts/migrate_from_archon.py --merge` |
| Sanction cleanup | daily | `db.py` |
| Rating recompute | daily | `ratings.py` |
| Promo stock recompute | daily | `promo_stock.py` |
| OAuth cleanup | hourly | `db_oauth.py` |
| Snapshot generation | every 15 min | `snapshots.py` |
| Deleted-objects purge | daily | `db.py` |

The purge hard-deletes soft-deleted objects older than 30 days and also drops
orphaned `avatars` / `banners` / `push_subscriptions` side-table rows — there is no
FK cascade.
