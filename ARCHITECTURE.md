# Architecture

## Overview

Offline-first PWA, client-server, with a shared Rust core providing identical business logic on the frontend (WASM) and backend (PyO3). Works whether online or offline.

## Technology Stack

- **Frontend**: Svelte + Vite + TypeScript; IndexedDB local storage; PWA service workers.
- **Backend**: FastAPI (Python 3.11+); PostgreSQL (JSONB); psycopg3 async, no ORM; msgspec JSON; tooling `uv` / `ruff` / `ty`.
- **Discord bot**: separate process; hikari + lightbulb + miru + Pillow; SQLite token/state; pure OAuth client (no DB, no business logic).
- **Shared core**: Rust → WebAssembly (frontend) + native library via PyO3 (backend).

## Data Model

### Object Structure

All objects extend `BaseObject`: `uid` (UUID v7, time-ordered, indexed), `modified` (timestamp), `deleted_at` (nullable soft-delete). Other fields are model-specific.

### Database Schema

All synced objects live in one `objects` table with pre-computed access-level columns — `public` / `member` / `full` JSONB (NULL when not visible at that level; `full` is NOT NULL) — plus `type`, `modified_at`, `deleted_at`, and `calendar_token`. Index: `(type, modified_at, uid)`.

`access_levels.py` computes the three projections at **write time**; SSE reads the matching column directly, with no per-request filtering. The trade-off: a single schemaless table (no migrations for schema changes), pre-computed projections (zero read-time filtering), and fast iteration. (Levels and field visibility: SYNC.md.)

`calendar_token` is the one non-projected column — a per-user `.ics` feed secret that must never be broadcast (every projection is, and `full` reaches non-owners). It's a 1:1 column rather than a table to avoid a join on the hot `get_user_by_uid` path; `save_object` COALESCEs it so token-less writes preserve it, and `clear_calendar_token()` is the explicit drop path.

### Database Access & Connection Model

psycopg3 async, no ORM. The pool is small (`max_size=20`, autocommit), sized for a ~2GB VPS, so connections must cycle fast: check one out, run a query, release. Production holds 15k+ users and 7k+ tournaments on this box, so avoid bulk-loading whole tables into memory — use targeted/filtered queries (`WHERE id = ANY(...)`).

**`tournament_transaction(uid)`** is the unit of work for any tournament mutation (the action handler and every offline-lifecycle endpoint). It `SELECT ... FOR UPDATE`s the row — serializing concurrent writes to one tournament — and yields `(tournament, tx_conn)` so the read-modify-write is atomic.

**Connection discipline** — a request must never check out a *second* pooled connection while holding `tx_conn`: with 20 concurrent in-flight actions pinning all connections via their locks, any further acquire blocks and deadlocks.

- **Reads** route through `_acquire` (explicit `conn=` → ambient `tx_conn` ContextVar → pool). Inside a transaction they transparently reuse `tx_conn`, so an action consumes exactly one connection start-to-finish — no need to thread `conn` by hand.
- **Writes** route through `get_connection` and pool **independently** by default — they do *not* ride the ambient connection. This is deliberate: go-online creates users in a loop where each `save_user` must commit and be visible to the next `allocate_next_vekn_id` (which runs its own advisory-locked transaction); folding those inserts into the outer transaction would hide them and reissue duplicate VEKN IDs. A write joins the transaction only when passed `conn=tx_conn` explicitly, keeping the read/write boundary visible at the call site.
- **Invariant**: never start a DB-touching `asyncio.create_task` / `gather` inside a transaction — the child inherits the ContextVar and would interleave operations on the shared connection (one `await execute` yields mid-flight) or outlive the `with` block. `_acquire` records the owner task and **raises** if the ambient connection is reached from another task, so this fails loudly. All spawned DB tasks (Discord role sync, VEKN sync) fire post-commit.

## Event System

Three event kinds:

1. **Business events** — domain actions (e.g. `Tournament.RoundStart`), processed by the shared Rust engine, which transforms objects per business rules. **ALL business events go through `POST /{uid}/action`** — there are no per-event REST endpoints. The backend only deserializes the event JSON and calls the engine, keeping online (server) and offline (WASM) processing identical and the engine the single source of truth for state transitions. (Full catalog: TOURNAMENTS.md.)
2. **CRUD events** — Create / Update / Delete, synchronizing DB state to clients; payload is the full object including `uid` and `modified`. Flow: DB change → CRUD event → SSE → IndexedDB.
3. **Ephemeral SSE events** — real-time, not persisted, not written to IndexedDB. `judge_call`: a player requests judge assistance; broadcast to organizers + IC only; payload `{tournament_uid, table, table_label, player_name}`; auto-dismissed after 120s with an audio chime; online-only. (See SYNC.md.)

## Online Mode

```
┌───────────┐         SSE        ┌────────────┐
│  Svelte   │◄───────────────────│  FastAPI   │              ┌───────────────┐
│    PWA    │                    │  Backend   │ Rust Engine  │ Object/Event  │
│           │  Business Events   │            │─────────────►│    Logic      │
│           ├───────────────────►│            │              └───────────────┘
└─────┬─────┘                    └──────┬─────┘
      │                                 │
 ┌────▼─────┐                      ┌───▼─────┐
 │ IndexedDB│                      │ Postgres│
 │ (Local)  │                      │   DB    │
 └──────────┘                      └─────────┘
```

Action → backend Rust engine → PostgreSQL → CRUD event → SSE broadcast → IndexedDB → reactive Svelte UI.

## Offline Mode

### Device-Lock Model

Primary-device ownership — no CRUD log or conflict resolution needed:

1. Organizer takes the tournament offline (`go-offline`) → locked to their device.
2. Other devices see an "offline" message — no mutations.
3. The WASM Rust engine processes business events locally → writes IndexedDB directly.
4. Offline-created players get temp UIDs (remapped to real UIDs on sync).

### Going Back Online

The primary device sends the full tournament state + offline data; the server overwrites, remaps temp UIDs, and resumes SSE.

go-online resolves/creates offline players (`save_user` / `allocate_next_vekn_id`) **before** taking the `FOR UPDATE` lock: an unlocked pre-check gates side effects (organizer + device lock), then the lock only re-verifies authoritatively, remaps temp UIDs, and saves — so no per-player connection is held while the row is locked. Benign race: if organizer rights are revoked between the pre-check and the lock, the re-check 403s after the users were already created (orphaned, harmless).

### Ownership & Transfer

- **Primary device** is authoritative — the server accepts its full state on go-online.
- **Force-takeover**: another organizer can claim the lock (warned about losing the primary's unsaved data).
- **Opportunistic sync**: the primary can background-sync without unlocking (`sync-offline`).
- **IC force-unlock**: emergency unlock without syncing offline data (first-party IC sessions only — OAuth tokens rejected).
- **Lock-loss reconciliation**: when a force-unlock or takeover reaches the previously isolated device via SSE/snapshot, it clears local offline state and warns the user their unsynced changes are discarded. `go-online` returns 410 (no longer offline) or 409 (another device took over) so a stale snapshot can't clobber authoritative state, and the server self-excludes the initiating device from its own go-online broadcast so a normal online transition doesn't self-trip that warning. (Full mechanics: SYNC.md.)

## Mutation Pipeline

Tournament actions are optimistic via WASM:

1. WASM processes locally → `{tournament, deck_ops}` → IndexedDB updated → UI reacts immediately.
2. Server POST sent async → on success SSE delivers authoritative state (overwrites if different).
3. On rejection (no SSE follows, `modified_at` unchanged) → roll back to the in-memory pre-action snapshot + surface the error. (Cursor `since`/`ts` over `modified_at`, and queue-overflow stream-close behavior: SYNC.md.)

### StartRound Seating Forwarding

Seating is seeded and value-stable: `seating::seed_for_round(tournament_uid, round_index)` feeds a `ChaCha8Rng`, so WASM (offline), PyO3 (backend/bot), and the browser all compute byte-identical seating for the same tournament + round. `StartRound` accepts an optional `seating: Vec<Vec<String>>` (table → ordered player UIDs); when provided the engine validates and uses it directly. `tournamentAction()` (`api.ts`) extracts the WASM-computed seating after processing `StartRound` and injects it into the server POST — a safety net guaranteeing agreement even if engine builds drift, not a correctness requirement. Engine validation (`tournament/mod.rs`): each table 4–5 players, every checked-in player exactly once, no duplicate UIDs across tables.

## Card/Deck System

- **Card database**: VTES card data loaded from JSON into IndexedDB (`cards` store, keyed by card ID); the Rust engine does lookup and deck validation (crypt/library counts, banned cards, multideck rules).
- **DeckObject**: a standalone synced object (not embedded in Tournament). Fields: `tournament_uid`, `user_uid`, `round`, `name`, `author`, `comments`, `cards` (card_id → count), `attribution`, `public`. The `public` flag is set by the engine from `decklists_mode` + tournament state (Winner/Finalists/All).
- No REST endpoints for decks — all mutations via `POST /{uid}/action` → engine `deck_ops` (`upsert` / `delete` / `set_public`). The client fetches deck URLs directly; the backend offers a CORS proxy fallback.
- **SSE reactivity**: the tournament page listens for `type === "deck"` sync events → re-queries `getDecksByTournamentGrouped()` → updates `decksByUser` state (passed as a prop to PlayersTab / PlayerView / DecksTab). Decks are not bundled into the tournament SSE event.

## League System

Aggregates tournaments into leagues with standings. Synced via SSE like tournaments/users; stored in IndexedDB `leagues` (indexes `by-country`, `by-start`). Fields: `name`, `kind` (League/Meta-League), `standings_mode` (RTP/Score/GP), `format`, `online`, `country`, `start`/`finish`, `description`, `organizers_uids`, `parent_uid`, `allow_no_finals`. GP and RTP modes use `compute_final_standings` to derive final placement (winner=1, other finalists=2).

## Serialization & Rust Integration

msgspec is used throughout for high-performance JSON: responses encode via `msgspec.json.Encoder`; Python models are `msgspec.Struct`, mirrored by TypeScript interfaces.

The Rust core defines the canonical object schemas and business logic, compiled to a native library (PyO3) and to WebAssembly (wasm-bindgen) so logic is identical across client and server. Engine at `engine/src/`; build with `just build-engine` (see engine/README.md for bindings and entry-point signatures).

**Key modules**:
- `lib.rs` — entry point, WASM/PyO3 bindings.
- `permissions.rs` — single source for all authorization predicates (below).
- `seating/` — seating algorithm (simulated annealing + staggered seatings).
- `tournament.rs` / `tournament/mod.rs` — event processing (state machine, scoring, finals).
- `tournament/standings.rs` — `compute_preliminary_standings` (GW/VP/TP/toss sort). GW and TP are **recomputed** per table from raw VPs + current sanctions (`sanctions::table_sa_adjustments` → `compute_gw`/`compute_tp`), so an SA issued *after* a round was scored re-decides GW and re-ranks/re-averages TP — the frozen seat `result.gw`/`result.tp` would otherwise go stale. VP sums raw per-seat VP then subtracts the full SA penalty (`-1` per SA via `sa_vp_penalty`), which may go negative; per-seat `result.vp` stays raw for display. Both `table_sa_adjustments` and `sa_vp_penalty` consume `sanctions::resolve_sa_effective_rounds` (same file) so GW/TP and VP always agree on which round each SA targets. DQ'd players (state `Disqualified` or active DQ sanction) have their VP/GW/TP zeroed and are sorted last; opponents keep all earned scores. Non-competing (proxy) players (`non_competing == true`) are also sorted last with rank "—" but their VP/GW/TP are kept (not zeroed). `compute_rating_vp_gw` (single source for the backend rating/VEKN-push paths) applies the same rule and additionally includes finals VP/GW; returns `(0, 0)` early for DQ'd or non-competing players. `compute_final_standings`: winner = rank 1, other finalists share rank 2 (VEKN §3.7.5), non-finalists competition-ranked from finalist_count+1; whether a final happened is read from the per-player `finalist` flag, not from finals seating data.
- `deck.rs` — deck parse/validate/enrich, TWDA export.
- `ratings.rs` — rating points computation; skips DQ'd players entirely (no RTP entry); `_player_count` stays inclusive of DQ'd players (tournament-rules A.2).
- `league.rs` — league standings (RTP/Score/GP); GP/RTP delegate to `compute_final_standings`.
- `cards.rs` — card database (lookup by ID/name, normalization).

**Engine error contract**: `engine/src/error.rs` is the single taxonomy for all engine rejections — the `EngineError` enum (~70 variants) with stable `code()` strings (e.g. `"tournament.already_registered"`) and `params()` for i18n interpolation. `Display` renders canonical English kept byte-identical to `frontend/messages/en.json` `err_*` values. New sites must use an explicit variant; `From<&str>`/`From<String>` exist only for genuine deserialization failures and `.ok_or("x required")?` internal notes — they collapse to `Internal { detail }`.

Wire shapes per surface: WASM throws a JS string `{"code","params","message"}` (`callEngine()` in `engine.ts` re-throws it as a typed `EngineError`); PyO3 raises a `ValueError` with the same JSON body (`EngineRejection.from_engine()` parses it); HTTP 400 is `{"detail":"<English>","code","params"}` — `detail` stays a string for the Discord bot and legacy clients.

Frontend fallback order (`toUserMessage` in `errors.ts`; the same mapping localizes `apiRequest` toasts): `code` present → `errorCodeToMessage(code, params)` → paraglide `err_*` key (5 locales); else server `detail` (English); else `"Request failed: <statusText>"`. An `internal` code yields a generic localized message + `console.error` of the raw detail (parse/invariant noise never shown); an unknown future code (version skew) falls through to `detail`. App-level checks that mirror engine rules reuse the engine codes so the same condition localizes identically on every path — the backend `_check_player_barred` raises `EngineRejection` and its frontend twin `checkPlayerBarred` (tournament-actions.ts) throws a coded `EngineError`, keeping the offline path localized.

**Authorization (single source of truth)**: all role/country/uid/ownership predicates live in `engine/src/permissions.rs`, consumed by both stacks — backend via PyO3 (`backend/src/permissions.py` is a thin marshalling adapter with no logic; each route keeps its own `HTTPException(403, ...)` detail), frontend via WASM (`isOrganizer()`, `canEditLeague()`, `canMarkDeceased()` in `engine.ts` are UX-only and fail closed to `false` until WASM loads). The backend remains the authoritative enforcement point.

## API & Data Conventions

- **Request bodies**: Pydantic `BaseModel` (FastAPI parses automatically) — not `msgspec.Struct` over raw `bytes` (an unbound `body: bytes` won't read the request body).
- **Responses**: msgspec (`msgspec.json.Encoder`) — faster than Pydantic.
- **Date-only fields** (expiry/event dates): accept `YYYY-MM-DD`, store as UTC midnight; reserve full tz-aware datetimes for precise timestamps (`issued_at`, `modified`).
- **Soft delete**: set `deleted_at = now()`; SSE broadcasts the deleted object so clients (including those offline during the delete) remove it from IndexedDB on reconnect; a daily job hard-deletes after 30 days.

## Shared Timer

Online-only. Timer state lives on the `Tournament` object and syncs via the normal SSE CRUD-on-save; clients compute the countdown locally — no per-second server broadcasts.

- `TimerState`: `started_at` (UTC, when started/resumed), `elapsed_before_pause` (seconds), `paused`.
- Tournament fields: `timer: TimerState` (global), `table_extra_time: dict[str,int]` (table_idx → extra seconds). Config: `round_time` (seconds, 0 = no timer), `finals_time` (0 = use round_time).
- Endpoints (organizer-only, online-only, Playing state; all save-and-broadcast): `POST /{uid}/timer/{start|pause|reset|add-time}` — start/resume, pause, reset + clear extensions, add per-table seconds (max 600s total).
- **Per-round lifecycle** (backend, not Rust engine): on round-start events (StartRound, SelfOrganizeRound, StartFinals, RestoreRound) the timer auto-starts fresh (`started_at=now`, `paused=False`, `table_extra_time` cleared) when that is the only round in progress; a parallel-round guard prevents clobbering a still-running clock. On round-end events (FinishRound, CancelRound, FinishTournament, CancelFinals) the timer and `table_extra_time` are cleared once no round remains running.
- Frontend: `TimerDisplay.svelte` (countdown, <5 min warning, expired, organizer controls); `JudgeCallBanner.svelte` (stacks dismissible `judge_call` alerts with chime).

## Announcements

Organizer-initiated, online-only. Announcement state lives on the `Tournament` object and syncs via the normal SSE CRUD-on-save — same carve-out as the timer (not processed by the Rust engine).

- `Announcement`: `id` (uuid7 hex, client dedup/dismissal key), `body`, `created_at`, `author_uid`, `author_name` (denormalized).
- Tournament field: `announcements: list[Announcement]` — capped to the most recent 20; 280-char per-body limit.
- Endpoints (organizer-only, online-only, offline_mode → 423): `POST /{uid}/announce`, `DELETE /{uid}/announce/{id}`.
- Member-projected automatically (not in `_TOURNAMENT_MEMBER_EXCLUDE` denylist in `access_levels.py`); no `DATA_SCHEMA_VERSION` bump needed.
- Frontend: `AnnouncementComposer.svelte` (organizer compose/delete), `AnnouncementBanner.svelte` (dismissible per-device via localStorage; arrival toast).
- The Discord bot mirrors each new announcement to the tournament's #announcement channel (`sse_listener.compute_announcement_posts`, diffed by `id`) — see Discord Tournament Bot below.

## Call for Judge

Player-initiated, online-only: `POST /{uid}/call-judge` `{table}` — the caller must be authenticated and seated at that table in the current round, the tournament in Playing state and not offline. Emits the ephemeral `judge_call` SSE event to organizers + IC only (see Event System).

## VEKN Sync

Bidirectional integration with vekn.net, gated by feature flags (`VEKN_PUSH` backend, `VITE_VEKN_PUSH` frontend). Outbound push creates a VEKN calendar entry on tournament create and uploads archondata on finish, plus member sync; inbound pull imports members and historical tournaments. All push is fire-and-forget with an hourly batch retry; imported/merged tournaments are stamped `vekn_pushed_at` so results are never re-uploaded (the importer folds finals into standings while archondata is prelim-only, so a re-push would send wrong numbers). Full mechanics — flags, archondata format, push constraints, outage resilience, member/tournament/error handling: **VEKN_SYNC.md**. Key files: `vekn_push.py`, `vekn_api.py`, `vekn_sync.py`, `vekn_tournament_sync.py`.

## Authentication

Multiple methods, all issuing JWT access/refresh token pairs.

| Method | Notes | Key files |
|--------|-------|-----------|
| Email + Password | register or login | `routes/auth.py` |
| Magic Link | signup, password reset, invite; link valid until the password is actually set (not just verified); landing at `/verify-email` | `email_service.py` |
| WebAuthn / Passkeys | FIDO2; four endpoints — `register/{options,verify}` (authenticated, add to existing account) and `create/{options,verify}` (unauthenticated, create new user) | `passkeys.svelte.ts` |
| Discord OAuth | `GET /auth/discord/authorize` (`mode=login\|link`) → `/callback`; login matches by Discord ID or creates a user, link attaches the Discord ID to the authenticated user | `routes/auth.py` |

JWT: short-lived access, longer-lived refresh; OAuth tokens are a separate `oauth_access` type with scope restrictions.

### Discord Linked Roles

Pushes VEKN role metadata (organization/judge/playtest levels) to Discord so server admins can gate roles on Archon standing. Requires the **target user's own** OAuth token (`role_connections.write` scope) — the backend cannot push for a user who has never logged in via Discord, so metadata is only pushed when a stored `discord_rc:{user_uid}` token exists. Fire-and-forget on Discord login/link, role changes, VEKN-ID changes, and periodic sync. Registered at startup (`register_metadata()`, idempotent PUT, needs `DISCORD_BOT_TOKEN`). Full field schema, portal setup, env vars, and alternatives: **DISCORD.md**. Key file: `roles_hook/__init__.py`.

## OAuth2 Provider

Full RFC 6749 / RFC 7636 (PKCE) implementation for third-party API access. Endpoints `/oauth/{authorize,token,userinfo}`; client CRUD + secret regeneration under `/oauth/clients` (DEV role); `GET /oauth/consents` (list authorized apps, first-party session only — rejects OAuth tokens with 403), `DELETE /oauth/consents/{client_id}` (revoke consent + immediately revoke live tokens for that client). Scopes: `profile:read` (limited to `/oauth/*`), `user:impersonate` (full API). Security: PKCE S256 required, Argon2-hashed client secrets, refresh-token rotation with a revocation chain, single-use auth codes, consent persistence; `revoked` flag on access tokens honored by auth middleware. Frontend: `/consent` page, `DeveloperSection.svelte` (developer-facing); `AuthorizedApps.svelte` (member-facing profile section). Files: `routes/oauth.py`, `db_oauth.py`, `models.py`, `middleware/auth.py`.

## Discord Tournament Bot

Standalone process (`bot/`) managing online VTES tournaments inside Discord servers — a pure OAuth client to the backend (no DB access, no business logic); all mutations go through `POST /{uid}/action` using `user:impersonate` tokens on behalf of real users. Single process only (module-level state in `sse_listener.py`). **Pre-production — not live and not yet tested**, but in scope for prod prep.

**Commands**: `/setup <url>` (link tournament; create category + announcement/lobby/judges channels — NC/Prince/IC only), `/teardown`, `/announce`, `/sync` (reconcile voice channels — repair tool), `/register`, `/checkin`, `/report <vp>` (→ `SetScore`), `/judge` (→ `judge_call`), `/sanction` (multi-step).

**Modules**: `token_store.py` (SQLite: `tokens`, `guild_tournaments` (+ `scheduled_event_id`), `pending_oauth` 15-min TTL); `archon_api.py` (REST client using stored OAuth tokens); `sse_listener.py` (per-(guild, tournament) SSE subscription driving channel/announcement/scheduled-event updates); `channel_manager.py` (voice channels with per-player CONNECT+SPEAK perms); `scheduled_events.py` (Guild Scheduled Event lifecycle); `oauth_callback.py` (local PKCE redirect server); `commands/{setup,player,judge}.py`.

**SSE listener** — subscribes to a **tournament-scoped** stream (`/stream?tournament=<uid>`) with the organizer's `user:impersonate` token, one connection per active (guild, tournament) pair, delivering only that tournament + its sanctions + judge calls:
- `reconcile_channels(...)` is the sole idempotent authority that creates/deletes voice channels and sets per-member CONNECT+SPEAK permissions; called on every relevant state change (round start/end, finals, reconnect, `/sync`). `channel_manager.desired_channels(obj)` (pure) computes the target set; `structure_signature(obj)` is a change-guard hash so reconcile is skipped when structure is unchanged. A per-tournament `asyncio.Lock` serializes structural mutations so concurrent events, reconnects, and `/sync` never interleave.
- `_emit_announcements` is a separate edge-triggered layer posting seating/standings/score to #announcement, after structural reconcile, suppressed during silent catch-up. It also mirrors organizer in-app announcements (`compute_announcement_posts` diffs the `announcements` list by `id`, new entries only; the silently-seeded snapshot means a reconnect never replays the backlog).
- **Round-timer reminders** — `compute_timer_reminders` (pure) mirrors the frontend countdown to schedule 15-min + 5-min warnings and a time-up `asyncio` task per table, posting into each table's voice text chat. `_reschedule_timers` is the single authority: cancel+rebuild on every `_timer_signature` change (timer start/pause/resume, per-table extra-time, round change, a table finishing) and after a reconnect's catch-up — no persisted cron, the schedule is recomputed from the snapshot. Passed thresholds are suppressed without posting and a per-key fired-set prevents double-fire, so a restart never re-posts; only pending tables get reminders (`_table_pending` — anything `Finished`/`Invalid`/`Cancelled`/`override` has stopped play).
- **Catch-up on (re)connect**: the bot sends no `since` cursor → the backend replays full current state; events seed state silently until `sync_complete` flips `synced`, so a restart/reconnect never re-posts past announcements. A `resync` message triggers a fresh reconnect. A shared `aiohttp` session spans reconnects; module-level state is cleaned up on `stop_sse` and teardown.

**Channel permissions**: #announcement — @everyone DENY SEND_MESSAGES, bot allowed; table voice — @everyone DENY CONNECT, per-player + organizers ALLOW CONNECT+SPEAK (organizers may join any table to judge); synced idempotently.

**Scheduled events**: `scheduled_events.py` (`ensure_scheduled_event`) creates/edits/deletes a Discord EXTERNAL Guild Scheduled Event per linked online tournament — driven off the SSE snapshot (no setup-time create path): on catch-up reconnect (initial + restart-idempotent via the persisted `scheduled_event_id`) and every relevant state change (name/start/finish/banner); deleted on finish or `/teardown`. Cover image: tournament banner transcoded webp→PNG via Pillow. Requires **MANAGE_EVENTS** bot permission; graceful if absent (logged + one-time hint to #judges).

**OAuth flow**: `/setup` initiates PKCE → user authorizes `user:impersonate` → redirect to the local callback server → token stored in SQLite for all API calls and SSE subscriptions.

**Misc**: Register / AddPlayer / CheckIn accept an optional `display_name` (Discord nickname) stored on `Player`, shown in `playerInfo`/`seatDisplay`. `/auth?login_hint=discord` auto-redirects bot-generated links to Discord OAuth. Only NC/Prince/IC can `/setup`; the bot never holds privileged backend credentials. Key directory: `bot/src/`.

## Community Links

Member-contributed links to external community resources, with moderator oversight. `community_links: list[CommunityLink]` is a field on `User` (default `[]`).

- **CommunityLink**: `type` (Discord/Telegram/WhatsApp/Forum/Facebook/Website/Twitch/YouTube/Reddit/Instagram/Blog/Other), `url`, `label`, `languages` (ISO 639-1, cap 5; empty = shows under every filter), `moderation` (`LinkModeration`: `status` hidden|promoted, `by`, `at`, `scope` global(IC)|national(NC)). The backend validates only the two-letter shape; the curated UI list is `frontend/src/lib/data/languages.ts`.
- **Add**: any user with `vekn_id`; limit 5 (10 for IC/NC/Prince). On update, existing moderation is re-applied by URL match.
- **Moderation** (`PATCH /api/users/{uid}/community-link-moderation` `{url, action}`): IC may hide/clear/promote_national/promote_global; NC (same country) hide/clear/promote_national; Prince (same country) hide/clear. Self-moderation allowed (officials pin their own links).
- **Projection**: public — NC/Prince and IC included (IC without contact), others hidden; member — NC/Prince/IC and any user with non-empty links; full — always. (`compute_user_public` / `compute_user_member`.)
- **Frontend** (`CommunityTab.svelte`): Global Resources (scope=global pins), Communities (social links grouped by country, pins first), Content (language filter defaulting to All, sorted global pin → national pin → promoted → officials → rest), Officials Directory (NC/Prince/IC contacts). `CommunityModerationActions.svelte` provides inline moderator controls.

## Calendar System

`GET /api/calendar/tournaments.ics` serves iCal for client subscriptions. Feeds: **Personal** (`?token=<calendar_token>`, agenda-matched), **Country** (`?country=XX`), **Global** (no params); `?online=false` excludes online events from any feed.

- `calendar_token` (User, nullable, generated on demand via `POST /auth/me/calendar-token`); stripped from SSE, only visible via `/auth/me`; partial DB index (WHERE NOT NULL).
- Agenda matching (`_matches_agenda()`): the user organizes (any state), participates (any state), or — non-finished only — same country / online / NC-CC on the user's continent.
- Frontend: `getAgendaTournaments()` / `getFilteredTournaments()` (db.ts, IndexedDB mirrors of the agenda logic), `generateCalendarToken()` (auth.svelte.ts), `getContinent()` / `getCountriesOnContinent()` (geonames.ts). The tournament list uses a "My Agenda" toggle (logged-in) plus an "Include online" toggle.

## Internationalization (i18n)

Paraglide JS (inlang), client-only (no SSR for the SPA). Locales `en` (default), `fr`, `es`, `pt`, `it` in `frontend/messages/*.json`; a Vite plugin compiles them to TypeScript (`$lib/paraglide/messages`). Browser auto-detection (`preferredLanguage`) + cookie persistence; manual `LocaleSwitcher.svelte` in the desktop sidebar.

## Web Push Notifications

Opt-in browser push notifications for tournament events. Degrades gracefully when VAPID keys are absent (`is_configured()` → no-op); gated on iOS behind Add-to-Home-Screen (PWA standalone mode).

### Side Table

`push_subscriptions(endpoint PK, user_uid, p256dh, auth, ua, created_at, last_seen_at)` — **not** in the synced `objects` table and not projected (send credentials, never display data; same pattern as `avatars`/`banners`/`oauth_*`). Indexed on `user_uid`. Pruned on owner hard-delete (`delete_object` + `purge_deleted_objects` in `db.py`) and lazily on send-time 404/410.

### VAPID Config

Three env vars: `VAPID_PRIVATE_KEY` (raw base64url scalar, loaded via `Vapid01.from_raw`), `VAPID_PUBLIC_KEY`, `VAPID_SUBJECT`. Keygen: `just vapid-keys` → `backend/scripts/gen_vapid_keys.py`. Private key + subject are ansible-vault secrets; `.env.example` has the blank vars.

**VAPID public key is delivered at runtime** (`GET /api/push/vapid-key`), not baked into the frontend build — the frontend ships as one release artifact across all envs; a baked key would force beta and prod to share a keypair.

### Backend Send Path (`backend/src/push_service.py`)

Pure builders `build_seating_specs` / `build_announcement_spec` / `build_judge_call_spec` return locale-independent *specs*; `render_payload(spec, locale)` localizes them into the wire notification. `send_to_users` looks up the target users' subscriptions (one `WHERE user_uid = ANY` query) and renders **per subscription** in that row's stored `locale` (a user may carry a FR phone and an EN laptop). Delivery is native async via `pywebpush.webpush_async` over a single shared `aiohttp.ClientSession` per fan-out: the `TCPConnector` pools keep-alive connections **per push host** (most Chrome subs share `fcm.googleapis.com`), so a fan-out reuses connections instead of a fresh TLS handshake per push, bounded by `limit` / `limit_per_host`. pywebpush owns the RFC 8291 `aes128gcm` payload encryption + RFC 8292 VAPID signing (`Vapid02`) — the crypto we deliberately don't hand-roll; we own only the transport. (aiohttp is HTTP/1.1; HTTP/2 multiplexing to FCM would mean an httpx transport — deferred, only worth it at thousands-of-subs scale.) Dead subs are pruned on a `WebPushException` with `.response.status` 404/410. Sends fire as `asyncio.create_task` and, for the tournament-action triggers, **after** `tournament_transaction` commits — a DB-touching task must never run inside the lock (see DB invariant in Connection discipline above). The templated bodies (seating, judge call) are localized via the `_PUSH_MESSAGES` table (5 locales, en source, `{placeholder}` format strings); the announcement body is organizer free text, rendered as typed.

### Triggers

| Event | Who receives | Where fired |
|-------|-------------|-------------|
| `StartRound` / `SelfOrganizeRound` / `StartFinals` | Each player newly seated in `rounds[-1]` or `finals.seating` | `_maybe_push_seating` in `routes/tournaments.py` |
| `POST /{uid}/announce` | All checked-in participants except the poster | `_maybe_push_announcement` in `routes/tournaments.py` |
| `POST /{uid}/call-judge` | The tournament's organizers except the caller (same audience as the ephemeral `judge_call` SSE) | `_maybe_push_judge_call` in `routes/tournaments.py` |

`RestoreRound` is excluded (re-seats no one). The judge-call push fires alongside `broadcast_judge_call` (no transaction — it's an ephemeral event) and carries `renotify: true` so a repeat call at a table re-alerts. Each send is fire-and-forget; delivery failure never delays the action response.

### Routes (`backend/src/routes/push.py`)

- `GET /api/push/vapid-key` — public key (503 when not configured)
- `POST /api/push/subscribe` — authed upsert; covers initial subscribe + lazy reconcile after `pushsubscriptionchange`
- `POST /api/push/unsubscribe` — authed drop

No unauthenticated rotate endpoint (an endpoint-only rewrite would be a notification-hijack vector); stale rows are pruned on 404/410 at send time.

### Frontend

- SW handlers in `service-worker.ts`: `push` → `showNotification`; `notificationclick` → focus/open deep-link; `pushsubscriptionchange` → local re-subscribe (the SW has no auth; the updated endpoint is reconciled server-side on next app-open via `reconcilePush()`).
- Store: `lib/stores/push.svelte.ts` — subscribe/unsubscribe/lazy-reconcile, permission + iOS/standalone detection.
- API client fns: `lib/api.ts`.
- Profile toggle: `profile/AppSettings.svelte`.
- Per-tournament opt-in + iOS A2HS nudge: `tournaments/[uid]/PushOptIn.svelte` (shown to checked-in participants of a live tournament).
- Lazy reconcile on app open: `+layout.svelte`.

## Binary Asset System

Binary image blobs are stored in dedicated side tables (`avatars`, `banners`) — **not** in the unified `objects` table. The `objects` table rows are projected into public/member/full JSONB and streamed via SSE to every client's IndexedDB; blobs must stay off that path. Each side table uses the owning object's uid as PK plus `data BYTEA` + `content_type`.

A small **path string** on the synced object points to the served URL (`avatar_path` on User, `banner_path` on Tournament). When a new image is uploaded, a fresh versioned URL is written to the object and saved — the resulting SSE broadcast propagates the new URL to all clients. Each versioned URL is served `Cache-Control: public, max-age=31536000, immutable`; an unversioned request gets a short TTL. This removes any need for client-side cache-busting.

| Asset | Side table | Path field | Access level | Endpoints |
|-------|-----------|------------|--------------|-----------|
| User avatar | `avatars` | `avatar_path` (member+) | member | `POST/GET/DELETE /api/users/{uid}/avatar` |
| Tournament banner | `banners` | `banner_path` (public) | public | `POST/GET/DELETE /api/tournaments/{uid}/banner` |

**URL shape**: `/api/{users\|tournaments}/{uid}/{avatar\|banner}?v=<epoch-ms>`. The `?v=` parameter is the version key — a re-upload yields a new epoch-ms, making the URL unique and thus immutable-cacheable.

`banner_path` is public so it serves as the `og:image` for social share links (see Social Sharing below).

Avatar upload: client-side cropping (`AvatarCropper.svelte`), server-side compression. Banner upload: organizer-gated, 1 MB, webp/png/jpeg; blocked while offline (so `banner_path` can't diverge from the device snapshot and get overwritten on go-online).

## TWDA

### Outbound (Export)

On the transition into `Finished` (if the winner has a deck), `twda.py` opens or updates a GitHub PR against the [TWDA repo](https://github.com/GiottoVerducci/TWD) — idempotent (branch `archon/{vekn_event_id}` + file `decks/{id}.txt`, create-or-update). It re-fires when the winner's deck is upserted on an already-finished tournament (organizer-only; players are deck-locked post-finish), so late uploads and post-event edits reach the archive. Files: `backend/src/twda.py`, `engine/src/deck.rs` (`export_twda`).

Designer credit: the winner's name is always in the header; a separate optional `Created by: <name>` line is emitted only when the deck is attributed to someone else (or historical `twda` backfill) — omitted for self-designed or anonymous decks. Names only, never VEKN IDs.

### Inbound (Import)

`twda_import.py` pulls winner decklists from [static.krcg.org/data/twda.json](https://static.krcg.org/data/twda.json) and creates `DeckObject`s for matched tournaments — runs inside `run_vekn_sync()` (after tournament sync, before rating recompute); manual `POST /admin/sync-twda-decks`. Matches recent entries by numeric `id` = `external_ids["vekn"]`, older entries by VEKN ID in `event_link`. Creates a deck only if the winner has none for that tournament; `attribution="twda"`, `public=True`. ETag cache is in-memory only; the ~12MB JSON is released after parsing.

## Legacy-Archon Sync

`backend/scripts/migrate_from_archon.py` — two modes sharing the mapping code: **insert-only ETL** (default; `--truncate` wipes first; for beta rebuilds and disaster fallback) and **idempotent `--merge`** (daily during the parallel-run period, old archon a read-only second upstream until decommission; cutover = freeze + final merge + vhost swap). Runner: a systemd timer (not an in-app job); env `OLD_DATABASE_URL` / `NEW_DATABASE_URL`.

**Single writer per field** (prevents daily flip-flop between syncs):

| Data | Writer |
|------|--------|
| identity (name/country/city/state) | VEKN sync |
| contact / nickname / discord / coopted_by / community links | archon sync |
| roles | nobody — seeded once by ETL, app-managed thereafter |
| sanctions, leagues | archon sync (upsert by source uid) |
| rich play data (rounds/seatings/decks/finals) | archon sync |
| `local_modifications` fields | nobody — local edits trump both syncs |

**Tournament matching** (merge mode, ≤1 live tournament per vekn event id): by uid → idempotent update; else by `external_ids.archon` / `external_ids.vekn` → merge rich data INTO the vekn-created copy (its uid survives; a round-less incoming copy never overwrites a rich original); else insert under the old-archon uid. Both-rich conflict (one-app-per-event violation) → logged loudly, skipped. Other invariants: deterministic deck uids (uuid5 of tournament+user+round); a pre-run `pg_dump` for recovery; merge writes are NOT live-broadcast over SSE (clients catch up on next reconnect); `vekn_pushed_at` stamped on merged finished tournaments so `batch_push` never re-uploads them.

## Archon Import (Excel)

Import legacy Archon Excel results: `GET /api/tournaments/archon-template` (blank template), `POST /api/tournaments/{uid}/archon-import` (upload). `archon_import.py` extracts rounds, tables, seating, scores, and players, matching players by VEKN ID.

## Tournament Reports & Social Sharing

- **Reports**: `GET /api/tournaments/{uid}/report` (organizer-only) — Text (standings + results) or JSON (full data).
- **Social sharing**: canvas-rendered PNG (`social-card.ts`) + plain text with deck info (`social-text.ts`); Share buttons on `FinishedResults.svelte` (organizer action bar) for finished tournaments.

### Open Graph Share Image

Social link-preview crawlers (Discord, Facebook, Reddit, WhatsApp, Telegram, …) don't run JavaScript, so they always see the static SPA shell with the site-wide `og:image`. To serve per-tournament banners, nginx UA-splits `/tournaments/{uid}`:

- **Humans** → `try_files … /200.html` (static SPA, SW-cacheable, offline-first unaffected).
- **Social bots** → `@og_stub` named location → FastAPI `GET /tournaments/{uid}`.

The FastAPI route (`main.py`) calls `get_tournament_public_projection(uid)` (type-filtered, unauthenticated — public level only) and passes the dict to `og.render_og_html()` (`backend/src/og.py`), which renders a minimal HTML stub with `og:title/description/image/…` and `twitter:card`. If the tournament has a `banner_path`, the stub uses `twitter:card=summary_large_image` (1200×630); otherwise it falls back to the 512×512 site icon with `summary`. Unknown/deleted uids fall back gracefully — no 404 to crawlers.

`/tournaments/{uid}` is **not** in the `_backend_paths` proxied-prefix list. It is served statically for humans and reaches FastAPI only via the named-location bot proxy — the offline-first SPA is unaffected.

Search engines (Googlebot, Bingbot) are deliberately excluded from the UA list — they render JS and should index the real SPA route. The UA list lives in `frontend/nginx.conf` (Docker/local) and `ansible/roles/static_site/templates/https.conf.j2` (prod) so beta and prod stay in sync. An unlisted crawler gets the generic site-wide card (today's pre-existing behavior), never an error.

## User Account Surgery

### Deceased Members

`User.deceased_at` (in-memoriam flag + date) and `deceased_by_uid` (audit, full-only). This is **not** a soft-delete — tournament history, ratings, and rankings are preserved and the record stays active. Set/cleared (reversible) via `PATCH /api/users/{uid}/deceased`. Permission: IC (any country) or NC (same country only); Prince excluded; **requires `vekn_id`**. Engine `can_mark_deceased` / WASM `canMarkDeceased`. Never pushed to VEKN; `deceased_at` tracked in `local_modifications` to block VEKN-sync overwrite. Access: `deceased_at` member+, `deceased_by_uid` full-only.

### Delete Member

`DELETE /api/users/{uid}` — IC-only; soft-deletes a VEKN-**less** account, the mirror of deceased (which targets VEKN-bearing accounts). Engine `can_delete_member` / WASM `canDeleteMember`; standard soft-delete + SSE broadcast path.

**Immovable-uid invariant**: a uid that carries a `vekn_id` is never re-keyed and never soft-deleted — everything keyed to it (sanctions, decks, tournament results, ratings, wins, cooptation) stays attached. Only the account *without* the `vekn_id` ever moves.

### Merge / Detach

- **Merge** (`POST /admin/users/merge`; IC/NC/Prince, same-country): the VEKN-bearing uid is always the survivor (`keep_uid`). Migrates auth methods, sanctions, decks, and `coopted_by` from the dying uid, then soft-deletes it; consolidates ratings, wins, roles, and `local_modifications` (union). `accounts.merge_users()`.
- **Detach** (`detach_user_from_vekn`): splits one account in two — the VEKN record keeps its uid and all keyed data; a fresh uid walks away with auth methods + personal/contact PII only. Callers: **self-abandon** (`POST /vekn/me/abandon`, blocked while an active suspension or probation is held — the sanction stays with the VEKN record; admin force-abandon is exempt) and **admin displace** (inside `POST /vekn/link`, frees a VEKN ID before re-linking it; the new owner is then merged into the freed record).

## Scheduled Background Tasks

| Job | Schedule | Module | Description |
|-----|----------|--------|-------------|
| VEKN sync | Every 6h (configurable) | `vekn_sync.py`, `vekn_tournament_sync.py`, `twda_import.py` | Pull members + historical tournaments from VEKN; import TWDA winner decks |
| Legacy-archon merge | Daily (systemd timer) | `scripts/migrate_from_archon.py --merge` | Idempotent daily merge from the old archon DB during the parallel-run period (decommissioned at cutover; see Legacy-Archon Sync) |
| VEKN push | Every 1h (configurable) | `vekn_push.py` | Batch push missed tournament events/results/members |
| Sanction cleanup | Daily | `db.py` | Soft-delete expired (>18mo), hard-delete soft-deleted (>30d) |
| Rating recompute | Daily | `ratings.py` | Full recompute of all player ratings and wins |
| OAuth cleanup | Hourly | `db_oauth.py` | Clean expired authorization codes and revoked tokens |
| Snapshot generation | Every 15 min | `snapshots.py` | Regenerate gzip snapshots (public/member/full) for initial sync |
| Deleted objects purge | Daily | `db.py` | Hard-delete soft-deleted objects older than 30 days; also drops orphaned `avatars`/`banners`/`push_subscriptions` side-table rows (no FK cascade; push rows also pruned on-send on 404/410) |
