# Testing

The policy — few tests, at boundaries, no mocks, each traceable to a wiki claim —
is [dogmas](dogmas.md#testing). This page is the layers, how to run them, and the
traps that have bitten.

## Layers

| Layer | Location | What it validates |
|---|---|---|
| Rust engine | inline `#[cfg(test)]` in `engine/src/` | the authoritative logic suite — seating, deck parse and validate, tournament lifecycle, ratings, permissions, league scoring |
| Backend | `backend/tests/test_*.py` | SSE filtering, access-level projections across role permutations, organizer access, the profile-update security boundary, ratings helpers, account surgery, the TWDA designer credit, the public API's read-only gate and schema drift |
| Frontend E2E | `frontend/tests/e2e/*.spec.ts` | full user arcs through the real UI |
| Bot | `bot/` | validated fakes over a nonexistent backend and Discord, guarded against hikari's real signatures |

There is **no frontend unit-test framework** — Playwright E2E only.

## Running them

**Backend** — `just test-backend` is canonical: it builds the PyO3 engine into the
venv, brings the `db` container up if needed, runs pytest, then stops the DB.
`conftest.py` points at a separate `archon_test` database on `:5433` and
**auto-creates it**, so no manual setup is needed beyond a running `db` container
and a built engine. Override the target with `TEST_DATABASE_URL`. Pure-unit suites
— SSE filters, organizer access, access levels — need no DB at all.

**Rust** — `cd engine && cargo test --lib`. `cargo` may not be on the default PATH.

**Frontend type check** — `npx svelte-check --tsconfig ./tsconfig.json`.

**E2E** — `just test-e2e` spins up a **fully isolated** stack on the compose `test`
profile and tears it down, never touching the dev `db`, `backend` or the
`postgres_data` volume: a throwaway Postgres whose data lives in tmpfs, a backend
bound to it with VEKN sync off, a seed job, and a frontend container that builds
the WASM engine, serves Vite, runs Playwright and writes the report.

> The seed script opens with `DELETE FROM objects` and `DELETE FROM auth_methods`.
> **Never point it at a database you care about.** It refuses a non-empty DB unless
> `E2E_FORCE=1`.

> `docker compose down -v` is **project-scoped, not profile-scoped** — it removes
> every named volume in the file regardless of `--profile`, so an ad-hoc teardown
> can wipe the dev `postgres_data`. `just test-e2e` is safe because its data is
> tmpfs, but a hand-run stack must get its own project name (`docker compose -p
> archon-vibe-e2e …`) so `down -v` can only touch test volumes — and must be
> stopped with `docker compose -p <proj> down`, never by killing the CLI child,
> which lets the parent recipe fire its `down -v` exit trap.

For a manual run, point everything at a throwaway database: create it, run a
backend against it on a separate port with `VEKN_SYNC_ENABLED=false`, seed it and
write the seed file Playwright reads, run a Vite dev server against that backend,
and run the suite with `BASE_URL` set. `playwright.config.ts` skips its own
`webServer` when `BASE_URL` is set.

### From a fresh worktree

A fresh worktree has empty venvs, no `node_modules` and no generated artifacts.

- **Backend**: build the engine with `uv run maturin develop --manifest-path
  engine/Cargo.toml`, then `uv run python -m pytest backend/tests/` against
  Postgres on `:5433`. **Do not use `just test-backend` from a worktree** — its
  compose-project check won't match and it tries to bring up `db` on a clashing
  port.
- **Bot**: needs `DISCORD_BOT_TOKEN`, `OAUTH_CLIENT_ID` and `OAUTH_CLIENT_SECRET`
  set at import; run pytest from `bot/`.
- **Frontend**: `npm ci`, `npx svelte-kit sync`, then compile paraglide — skipping
  that yields ~75 phantom errors. The only expected remaining `svelte-check` errors
  are the missing generated artifacts. Prettier is not project tooling.

## E2E infrastructure

`global-setup.ts` runs before all tests and does **not** seed or clean the database
— seeding is the compose job, or your manual run. It health-checks the backend,
reads the seed file, logs the organizer in for real JWT tokens, and warms the Vite
dev server so parallel workers don't each pay compilation. `global-teardown.ts`
removes the token file; DB cleanup is unnecessary against a tmpfs database.

The seed creates one organizer (IC + Ethics, VEKN ID `9999901`) and ten players
(`9990010`–`9990019`), truncating first to avoid syncing the full VEKN dataset, and
regenerates snapshots so SSE sync is fresh. `--cleanup` removes test objects by
VEKN ID prefix and by the `E2E ` name prefix.

Two auth helpers: one used **after** `page.goto()`, which clears the sync cursor to
force a full-level resync, and one used **before** the first navigation via
`addInitScript`, so the first sync already uses full-level data. Sync helpers wait
on the `[data-sync-state="synced"]` indicator and on the first rendered row.

Coverage: `users.spec.ts` (app load, SSE streaming, user list, profile page,
sanction modal); `tournament.spec.ts` (the full nominal arc — create, register 8
players, check in, upload and replace a decklist, score 2 rounds through the UI
with a seating change and an in-event caution, random toss, finals, winner banner,
rating points on the rankings page); `leagues.spec.ts` (creation, detail, list).

**Everything goes through the real UI — no direct API calls.** The suite drives the
organizer console throughout, so its mutations are optimistic, and server POSTs are
serialized per tournament, making chained UI steps ordering-safe. A player's device
awaits the server instead ([architecture](architecture.md#mutation-pipeline)); no
test drives one. Tables are scored by giving the first seat all VPs, since a sweep is
a valid oust order, which also guarantees score ties at the finals cutoff so the
random toss is always exercised; the toss shuffle is seeded from the tournament
uid, so the optimistic result and the server agree. The test awaits the
`StartRound` response before scoring and the `FinishFinals` response before
checking rankings, because the ratings recompute and SSE push happen inside that
request. The caution's indicator dot renders from IndexedDB, so its appearance
proves SSE delivery — the sanction POST is not optimistic. Seating changes use the
click-based unseat/seat flow; drag-and-drop is not reliably scriptable.

## Traps

**Never `git checkout` during mutation testing** — it has wiped uncommitted feature
code mid-run. Back the file up first.

**The backend `test_db` fixture wipes only `type = 'user'` rows**
(`backend/tests/conftest.py`) — a test that creates tournaments or decks cleans up
after itself, as the existing suites do with `_cleanup()` context managers.

**`test_access_levels.py` is the only place in the backend suite that asserts
projection field membership.** Everything else mentioning `"public"` asserts row
sets, sizes, or the `calendar_token` exclusion — never which keys a projection
carries. That is deliberate: it makes "have I just made a field public without
noticing?" a one-file question, and the file is pure-unit with no DB, so it runs
even on a skipped-DB run. When reviewing a widened or narrowed projection, read
that file first; if the sensitive field is already pinned there, a further
"public ⊆ member" test is redundant — say so and add nothing.

**Field-list drift is pinned in four files, and each pin is exhaustive** — a new
model field fails one of them rather than leaking. `test_go_online.py` classifies
every `Tournament` field as server-owned, merged, stamped or carried from the
device's snapshot; `test_account_surgery.py` classifies every `User` field across
the detach split; `test_access_levels.py` holds the member-visible complement of
the tournament denylist, the api-visible complement of the tournament and player
api denylists and the withheld complement of the user api allowlist, and pins
`compute_user_full` to withholding exactly `calendar_token`;
`test_tournament_field_contracts.py` classifies every
`TournamentActionRequest` field as truthy-only or any-value, and compares the
engine's `CONFIG_FIELDS`, `TournamentConfig` and `CreateTournamentRequest` while
driving a real create through the shipped engine so the create literal cannot
forget a field. Only the half each classification's code actually uses is
importable; the complement lives in the test, so there is one copy of each.

**No test can catch a missing projection backfill, so do not propose one.** The
access-version resync fires when a *viewer's* level changes. When the *server's
definition* of a level changes, no viewer transitioned and no row's `modified_at`
moved, so clients keep the old payload indefinitely. The fix is the re-save script
([sync](sync.md#access-levels)); verify it exists and is deploy-ordered instead.

**The frontend has no unit-test vertical, and adding one is not the answer.**
`vitest` appears nowhere in the repo — only `svelte-check`, Playwright and the smoke
script. Standing up a runner, config and CI wiring for a single test is exactly
what the policy forbids. Compounding it, `tournament-utils.ts` is **not pure**: it
imports from `./engine`, whose helpers read the WASM engine synchronously and
throw when it is absent. Outside a browser that is always, so a Node-side test
would assert the throw and never the real placement logic. Placement semantics belong in Rust,
rendering belongs in Playwright, and the TypeScript in between is marshalling that
`svelte-check` plus the E2E lifecycle spec already covers.

**A fixture's VP vector must be one a table could really produce**, unless the
invalid vector *is* what the test is about. `check_table_vps` decides against the
enumerated reachable sheets
([tournaments](tournaments.md#oust-order-validation)), so a vector it accepts is
one a game can reach — but derive it anyway rather than searching for one that
passes: seats sit in predator-prey order, ousting your prey scores 1 VP and you
inherit their prey, a withdrawal scores 0.5, the last player standing takes an
extra VP for the game win, and at time-out every survivor takes 0.5. Two traps
sit next door: a fixture table that
omits `state` scores nothing at all, which reads as a broken assertion rather than
a broken fixture; and stored per-seat `gw`/`tp` are overwritten by the recompute,
so asserting on them tests nothing. An unseeded mock once fabricated VEKN-less
officials — also engine-impossible — and produced a flaky test.

**Card data is a pinned two-card fixture** (`backend/tests/fixtures/cards.json`,
wired by `CARDS_JSON_PATH` in `conftest.py`). `engine/data/cards.json` is generated
by `just cards` and CI never downloads it, so a test that reads the dev tree's copy
passes locally and fails in CI — which is what once justified mocking the loader.

**A fixture must not derive anything from a uid prefix**: `uuid7` is time-ordered,
so uids minted in the same millisecond share their leading characters. Offline
players take a `TEMP-` vekn from the uid's first 8 chars, and a `uuid7` fixture
collapses a whole table onto one vekn — the frontend mints `crypto.randomUUID()`,
so `uuid4` is what models it.

**The engine emits state strings as bare literals** while the route
strict-converts, so a missing Python enum value 500s every action. A contract test
pins the two together; keep it.

**Post-engine route hooks are not reachable** through the engine-contract test
pattern — the timer and the finish stamp among them. There is no route-level
tournament-action test, and no timer test anywhere.

**Engine permission tests use struct literals**, bypassing JSON parsing, so a new
descriptor key has zero coverage until a backend wrapper test pins it.

**Deliberately untested, don't "fix"**: the ungated `ReportPromos` event (post-finish
corrections are the point, pinned by one replace-whole-list test); the promo-stock
route guards; the "never rate an open-rounds event" skip, which is an inert
in-Python filter while the "never push" half lives in tested shipped queries.

**Over-cap fixture arithmetic**: the round-count helper excludes cancelled tables,
so to place a seated player *at* their cap you must give them N other
non-cancelled finished rounds — a player appearing only in the cancelled round plus
one other counts one, not two.

**SA test design**: the effective-round resolver is shared, so test it once. `gw`
is the discriminator, since `vp` doesn't move. The GW threshold is `>= 2.0`,
inclusive. Cancel a **non-last** round to obtain a `Cancelled` table.

**A fake is legitimate only for a system we neither own nor can run** — Discord,
the VEKN registry, GitHub — and only paired with a guard test pinning it to the
real contract ([dogmas](dogmas.md#testing)). `bot/tests/test_rest_fakes_match_hikari.py`
binds every REST call shape the bot uses against the real `RESTClientImpl` and
against each fake, and `test_refresh_single_flight.py` proves its backend fake
reproduces the bug it stands for. `test_discord_login_redirect.py` fakes Discord
at the HTTP boundary (`DISCORD_API_BASE`) with no contract pin — none is
constructible without a local library encoding Discord's HTTP API, and its
invariant is our redirect round-trip, not Discord's response shape; that backend
arc is deliberately where the post-login redirect is pinned, the frontend legs
being marshalling. Faking our own engine, database or modules is
the banned case itself: the TWDA credit suite runs the real route helper against
the real DB and engine, and the archondata suite finishes a real tournament
through the engine rather than hand-typing a standings sheet.

**The bot startup smoke test earns its keep** (`bot/tests/test_startup.py`): the
lightbulb v2→v3 `.d`/`.di` migration crash-looped 69 times in production while CI
stayed green, because CI has no Discord gateway to fail against. The test pins the
import-and-wire path that incident exposed.
