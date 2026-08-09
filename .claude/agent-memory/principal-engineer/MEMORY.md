# Principal Engineer Agent Memory

## Project Structure
- Backend: `backend/src/` (FastAPI, Python 3.11+, msgspec, psycopg3 async)
- Frontend: `frontend/src/` (Svelte 5 runes, Vite, TypeScript, IndexedDB)
- Engine: `engine/src/` (Rust, WASM via wasm-pack, PyO3 via maturin)
- Build: `justfile` at project root

## Key Files
- `backend/src/main.py` — SSE endpoint, personal/organizer overlays, broadcast wiring
- `backend/src/broadcast.py` — `BroadcastData` + `broadcast_precomputed` (broadcast injection lives here, not main.py)
- `backend/src/access_levels.py` — write-time public/member/full projections
- `backend/src/models.py` — domain models (msgspec.Struct)
- `backend/src/db.py` — PostgreSQL ops, streaming, CRUD, account-surgery (merge/detach)
- `backend/src/permissions.py` — thin PyO3 wrapper over engine authz (decision lives in Rust)
- `backend/src/routes/auth/` — auth flows split into a package (email_password, discord, passkeys, magic_link, profile, _tokens)
- `backend/src/routes/tournaments.py` — tournament create/action/delete + go_online
- `frontend/src/lib/sync.ts` — SSE SyncManager singleton, spec-based buffering
- `frontend/src/lib/db.ts` — IndexedDB wrapper, batch ops, by-tournament indexes
- `frontend/src/lib/api.ts` — API client, optimistic updates + rollback for tournament actions
- `frontend/src/lib/engine.ts` — WASM engine wrapper
- `frontend/src/lib/stores/auth.svelte.ts` — auth state ($state runes)

## Conventions
- All objects: `uid` (UUID v7), `modified`, `deleted_at` (soft-delete) in one unified `objects` JSONB table.
- Access is **pre-computed at write time** into three columns (public/member/full); SSE reads the matching column. No per-viewer filtering at read time.
- Business mutations only via `POST /{uid}/action` → Rust engine → CRUD → SSE. No per-event REST routes.
- **SSE serves raw JSON via `SELECT col::text`** — never reintroduce a parse→Struct→reserialize cycle (that was the original perf sink; design intent is zero re-serialization on the stream path).
- Optimistic updates: WASM applies locally first, server confirms via SSE, frontend rolls back on rejection. Reads stay offline-first (IndexedDB only) — no API GET for display.
- Pydantic for request parsing, msgspec for response serialization.
- Authz decisions are single-sourced in Rust (`engine/src/permissions.rs`), exposed via PyO3 + WASM — see ARCHITECTURE.md (Authorization).

## Open items (verified residual, 2026-06)
- `engine.ts` `TournamentEventType` is missing `CheckOut` vs the Rust enum (optimistic update silently falls back to server-only for that event).
- `jwt_config.py` `JWT_SECRET` still falls back to a dev default string — should hard-fail in production.
- i18n: leftover hardcoded English in some pages (e.g. `leagues/[uid]/+page.svelte`). Rust engine error-code i18n is the one deferred i18n phase (errors still emit English strings).

## Deck Architecture Patterns
- All deck mutations go through `POST /{uid}/action` (engine `deck_ops` side-effects); `DeleteDeck` engine action → `tournamentAction()` on frontend.
- `BroadcastData.org_uids` is NOT auto-populated for DeckObjects (no `organizers_uids` field). `_process_deck_ops()` manually stamps `bd.org_uids` after save — the correct pattern. `broadcast_precomputed()` uses `org_uids` to decide full-level SSE access.
- Visibility: `public` column always NULL for decks; `member` non-NULL only when `deck.public == True`; `full` always present. Own decks + organizer's tournament decks sent at full via personal/organizer overlay. NC/Prince same-country get NO deck access.
- Dedup is consistent across stack: `saveDeck()` (db.ts) and `_process_deck_ops()` upsert both key on `(tournament_uid, user_uid, round)`.

## Recurring trap: lazy-import renames
- [Lazy-import rename trap](lazy-import-rename-trap.md) — renaming a symbol can silently break function-level (lazy) import callers (used across routes.tournaments/vekn_push/archon_import to break cycles); invisible to module-load AND a green test suite, and swallowed by try/except post-effect blocks. Grep ALL refs incl. in-function imports.

## Recurring trap: manual object reconstruction
- Several call sites hand-rebuild a `Sanction(...)` / `User(...)` from fields (sanction cleanup in `main.py`, sanctions delete endpoint, merge/detach in `db.py`). When a model gains a field, grep ALL manual constructors — prefer `msgspec.structs.replace` over hand-listing fields (hand-listing silently drops new fields, e.g. `resync_after`).
- Two from-scratch `User(...)` rebuilds of an EXISTING user silently drop unlisted fields on a routine path: `vekn_sync.py` `_infer_coopted_by` prefix branch (nightly job — already drops `city_geoname_id`/`phone_is_whatsapp`/`community_links`/ratings; github_login/github_id were the latest victims) and the `accounts.py` `detach_user_from_vekn` `vekn_record` *null-list* (the inverse trap: a NEW personal/login field must be ADDED to the null-list or it leaks onto the abandoned VEKN record for the next claimant — github_login/github_id were missed there). All other `User(...)` sites are fresh-uid creates (nothing to drop).
- Reassigning object refs (sanctions/decks/coopted_by on merge/detach) MUST return `BroadcastData` and broadcast, or other clients stay stale until snapshot resync — the established pattern; preserve it in any new merge-like flow.
- Svelte 5 `$props()`: props must be listed in the destructure, not just the type annotation.

## Sync-correctness traps
- [Destructive store-wipe offline rescue](destructive-store-wipe-offline-rescue.md) — db.ts upgrade AND sync.ts clearAllStores both wipe stores; must rescue the FULL offline set (tournament + sanctions + decks + player-stubs).
- objects has two timestamps (column modified_at vs JSONB modified); never mix in the since-cursor — see SYNC.md (Sync Cursor).
- tournament_transaction connection discipline (reads join txn; writes acquire pool independently; never a 2nd conn under lock) — see ARCHITECTURE.md (Database Access & Connection Model).
- [Asset-cleanup autocommit non-atomicity](asset-cleanup-autocommit-nonatomic.md) — pool is autocommit=True, so multi-statement writes needing consistency require explicit conn.transaction(); delete_object/purge are the fixed exemplar (object + avatars/banners/push_subscriptions side-row deletes, no FK cascade) — don't re-fix them.
- [finals.seed_order is a UID field](finals-seed-order-uid-field.md) — holds player user_uids; easily missed in any per-player UID remap.
- [Error localization across throw surfaces](error-localization-offline-path-trap.md) — engine-error localization covers HTTP + offline WASM + JS pre-checks (wired); preserve all three when changing error presentation.
- [DECLARE-plan quirk](snapshot-cursor-and-declare-plan-quirks.md) — a psycopg named cursor runs `DECLARE … CURSOR FOR`, costed with cursor_tuple_fraction=0.1; EXPLAIN the DECLARE, not the bare SELECT, or the plan you verify isn't the one that runs.
- [Resync branch zero-delay loop](sync-resync-branch-zero-delay-loop.md) — sync.ts resync onmessage branch reconnects with NO delay; cold-start trigger fixed, branch unguarded for any other persistent resync cause; route resync reconnects through backoff.
- [go-online self-echo + 409 gap](go-online-self-echo-409-gap.md) — FIXED: broadcast_precomputed exclude_device_id self-excludes the initiating device + goingOnlineUids guard (HTTP response is sole authority in-flight) + 409→clearOfflineState. Residual: bounded in-flight reconciliation window.
- [Offline re-pull of server-managed Tournament fields](offline-repull-server-managed-fields.md) — new backend-only Tournament field must be added to go_online's "server wins" re-pull block (alongside checkin_code/vekn_pushed_at/…), else offline round-trip silently reverts it; online /action is safe (engine json-rust preserves unknown keys). twda_status currently omitted.

## Web Push (#314)
- [Web Push VAPID thread + claims traps](webpush-vapid-thread-and-claims.md) — `vapid_claims` dict IS mutated per-send (fresh dict required); `Vapid01` instance is NOT (safe to share across to_thread). Backwards from intuition.
- Push subs = `push_subscriptions` side table (endpoint PK), NOT synced objects — same carve-out as avatars/banners/oauth_*. Pruned on 404/410 at send + owner hard-delete (delete_object AND purge).
- Sends are fire-and-forget `asyncio.create_task` POST-commit (outside tournament_transaction); helpers own their errors. No DB-touching task inside the lock — preserve for any new push trigger.
- `pushsubscriptionchange` SW handler re-subscribes LOCALLY only (SW has no auth); app lazy-reconciles via authed `/api/push/subscribe` on next open (reconcilePush in +layout). No unauthenticated endpoint-rewrite path — keep it that way.

## Deck Parsing
- [Deck parser prefix-match trap](deck-parser-prefix-match-trap.md) — try_name_first count-strip + by_name prefix match miscount count-less lines (Channel 10/AK-47/Kpist m/45); group-from-tail (Annabelle G3 vs G6) untested bug; fix = exact-key gating, not krcg regex.
- [Card three-name model + set-names traps](card-three-name-model-traps.md) — printed(display)/unique(text export)/full(image filename = normalize(full_name)) roles; sets are display NAMES not codes so deck.rs V5 `starts_with("V5")` matches nothing; accent fold has no CI ASCII guard; enrich_deck is a dead export.

## Formats
- [Open rounds per-player cap](open-rounds-per-player-cap.md) — max_rounds as per-player cap (computed rounds-played gate); resting-state hazard; UpdateConfig/multideck/is_deck_locked/vekn_push ripple sites.
- [Open-rounds exclusion parallel consumers](open-rounds-exclusion-parallel-consumers.md) — open_rounds now a persisted flag (excluded from VEKN/ratings); get_tournament_wins_for_users (→HoF) is an unfiltered parallel path that leaks; self_organized⟹open_rounds is UI-only, not engine-enforced.
- [Completed PlayerState (finalist withdrawal)](completed-player-state-finalist-withdrawal.md) — open-rounds + finalist-withdrawal forces a 6th `Completed` state (cap-done, finals-eligible) vs `Finished` (withdrew, ineligible); StartFinals excludes {Disqualified, Finished}; top5_has_ties must realign to eligible set; full cross-stack ripple.

## Engine config & player-authorized events
- [Config field create/UpdateConfig asymmetry](config-field-create-updateconfig-asymmetry.md) — a tournament config field must be added to BOTH create_tournament's literal AND UpdateConfig's config_fields array; table_rooms is a live one-site gap. Shared rules go in validate_config_fields.
- [Online create bypasses the engine gate](online-create-bypasses-engine-gate.md) — POST /tournaments builds Tournament() directly in Python (no PyO3 call); engine create-time gates run ONLY on offline/WASM create + UpdateConfig. "Enforce X at create in the engine" tickets silently miss the online path.
- [Player-authorized engine event pattern](player-authorized-engine-event-pattern.md) — non-organizer events (CheckIn/SetScore exemplars); eligibility-predicate landmines: state-set (exclude Registered/Playing), dual-DQ, per-player cap, mid-array round removal unsafe, start≠finish authority.

## Scoring & Standings
- compute_final_standings = shared VEKN placement (winner=1, finalists tie 2nd) — see ARCHITECTURE.md (engine modules / League System).
- [SA penalty single-sourced in Rust](sa-penalty-duplicated-in-python.md) — SA scoring lives only in `engine.compute_rating_vp_gw`; never re-derive in Python.
- [SA standings recompute on sanction mutation](sa-standings-recompute-on-sanction-mutation.md) — sanctions.py `_recompute_tournament_standings` refreshes tournament.standings on SA create/lift/delete via the python-only `update_standings_json` engine entrypoint; frontend reads standings (not raw seats). Don't reintroduce the "sanction writes skip the tournament recompute" assumption.
- [Standings are prelim-only](standings-prelim-only-contract.md) — `tournament.standings` = SA-adjusted prelim, finals excluded; the Python archon importer violates this (stores finals-inclusive) → league double-counts finals.
- [Rounds⇔standings coupling](rounds-standings-coupling-engine.md) — engine invariant: standings non-empty iff rounds non-empty; makes the VEKN `batch_push` `rounds>0` guard safe (excludes imports, keeps in-app tournaments).
- [SA round-targeting consumers](sa-round-targeting-two-consumers.md) — SA −1 VP has THREE consumers (prelim standings, rating, SetScore); all share resolve_sa_effective_rounds or VP/GW/TP silently diverge; seated_in is Cancelled-aware (soft-cancelled seat can't anchor an SA), redirect can land later than stored (JG v2 §1.1.3).
- [DQ dual-signal divergence traps](dq-signal-divergence-traps.md) — DQ = state||active-sanction; audit every consumer for the combined signal, and any DQ sanction create/lift/delete must recompute standings.
- [Excluded-but-not-zeroed standings consumers](excluded-not-zeroed-standings-consumers.md) — proxy/non_competing is non-ranked but score is KEPT (DQ zeroes); league.rs + vekn_push iterate standings unfiltered and leak proxy scores; filter on disqualified||non_competing.
- [League RTP vs global RTP points base](league-rtp-vs-global-rtp-points-base.md) — league.rs RTP points use PRELIM-ONLY standings vp/gw (finals only added to displayed totals); global rating uses TOTAL vp/gw; the two RTP consumers diverge — verify the `points` field, not just displayed gw/vp.

## Online-only live tournament sub-data
- [Online-only Tournament sub-data carve-out](online-only-tournament-subdata-carveout.md) — timer pattern: field on Tournament + backend route (tournament_transaction→save_object→broadcast_precomputed), NO Rust engine, NO optimistic update, NO new object type; reserved for online-only live UI state (announcements #290 mirror this).
- [Tournament member projection is a denylist](tournament-member-projection-is-exclude-list.md) — compute_tournament_member excludes only {checkin_code, vekn_pushed_at}; any new Tournament field auto-reaches members at SSE; organizer-only secrets MUST be added to _TOURNAMENT_MEMBER_EXCLUDE or they leak.
- [Round lifecycle traps](reference_round_lifecycle_traps.md) — engine round/finals state quirks (RestoreRound re-derives to fully Finished, finals not in `rounds`, table states, timer online-only) to check when reviewing round-lifecycle hooks.
- [bot _active_tables finals-seating trap](bot-active-tables-finals-seating-trap.md) — bot _active_tables tags "finals" on seating-truthiness, NOT completion; consumers that should stop at table/finals completion (timer reminders) over-trigger. There is NO top-level table.result (find_player_table's guard is a no-op) — gate on _table_pending (NOT Finished/Invalid/Cancelled/override).

## Discord bot (scoped SSE consumer)
- [Bot scoped-stream frame ordering](bot-scoped-stream-frame-ordering.md) — tournament frame precedes participant User frames on the LIVE path; reconcile logic using the `_user_names` discord_id fallback for a just-added organizer/player is one message stale (bites #judges organizer sync); catch-up is safe.

## Authorization (cross-stack)
- Authz predicates single-sourced in engine/src/permissions.rs (PyO3+WASM); frontend fail-closed, UX-only — see ARCHITECTURE.md (Authorization).
- [Projection tier: column vs content split](projection-tier-column-vs-content-split.md) — new precomputed access column ONLY when projection CONTENT must vary by viewer at the same level (else collapse onto existing column + shrink lower one); base64 contact obfuscation is a harvester speed-bump, not access control.
- [Role writes have two out-of-band consumers](role-write-out-of-band-consumers.md) — Discord Linked Roles push fires on ANY role delta (no periodic reconcile); resync/access-version fires only for IC/NC. Non-users.py writers skip both silently.
- [entitled_level vs overlay catch-up asymmetry](entitled-level-vs-overlay-catchup-asymmetry.md) — a new full-access branch in entitled_level only wires the LIVE path; non-country/non-own-object full grants must ALSO be added to _overlay_frames (main.py) or the resync re-delivers the lower projection (promo holdings for NC is the exemplar gap).

## Deploy / infra (cross-stack)
- [nginx _backend_paths allowlist](nginx-backend-paths-allowlist.md) — prod nginx proxies ONLY the prefix allowlist (/api,/auth,/oauth,/vekn,/sanctions,/admin,/snapshot,+/stream) to FastAPI; a new route under an existing prefix is fine, a new TOP-LEVEL segment 404s in prod but passes dev CORS/tests.

## Error handling (cross-stack)
- [aiohttp timeout escapes ClientError](aiohttp-timeout-escapes-clienterror.md) — ClientTimeout breach raises asyncio.TimeoutError, NOT aiohttp.ClientError; `except aiohttp.ClientError` misses timeouts (→ 500 not 502) on every external-proxy route (feedback/twda/webpush).
- [Error-codes contract](error-codes-contract.md) — `EngineError` enum = single error taxonomy; `{code,params,message}` wire JSON across WASM/PyO3/HTTP; domain rejection MUST be an explicit variant (From-impls silently demote to internal); EngineRejection-in-transaction is sound FastAPI.

## Ratings recompute
- [No-change guard bounded by denormalized inputs](ratings-nochange-guard-denormalized-inputs.md) — the skip-if-unchanged guard only converges if the entry's embedded tournament_name + date(finish/start/modified fallback) are stable; meta flip-flop + both-null date are the two daily re-save vectors.

## Migration / legacy-archon merge (residual hazards)
- [Archon-merge cross-sync flip-flop](archon-merge-cross-sync-flipflop.md) — daily `--merge` shares fields with both VEKN syncs; both known vectors (tournament meta, officials' contact_email) are FIXED and guarded — check the guards, don't re-report them as live.
- [Vekn-less drop is NOT ref-free (measured)](migration-veknless-orphan-measured.md) — dropping the 142 vekn-less members orphans 9 refs (4 players + 5 seats) in 3 Finished tournaments; old archon never enforced vekn at registration. Reusable probe recipe in file.
- [vekn_id unique index spans tombstones](vekn-unique-index-spans-tombstones.md) — index has no deleted_at exclusion; soft-deleted user reserves its vekn_id; deleted_at-filtered lookups disagree → seed-insert can crash on a reserved number. UNFIXED, reachable on steady-state nightly merges (admin user-delete keeps vekn_id).
- The vekn-id-matching redesign (member matching, no tombstone, vekn-less shells, `member_uid_map` remap of all member-uid refs) shipped; full impl + ref surface in `.pst/details/169-vekn-id-matching-merge.md`.
