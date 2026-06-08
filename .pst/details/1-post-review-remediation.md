# Post-review remediation (epic #1)

Findings from a full-stack code review (engine / backend / frontend / bot) on 2026-06-03.
Each finding is a child ticket with `parent:#1`. Severity: p0 (broken now) → p3 (cleanup).
"Confidence" = whether the offending code was read line-by-line during review.

## Confirmed (read + verified in code)

| # | Sev | Area | Finding | Key locations |
|---|-----|------|---------|---------------|
| 2 | p0 | bot | Bot dispatches on the SSE `event:` field, but the backend never sends one — every event is `data: {"type":...}`. Bot parses then discards everything; all reactive logic is dead. | `bot/src/sse_listener.py:165-194`, `backend/src/broadcast.py:43`, `backend/src/main.py:573/686/697` |
| 3 | p0 | backend/offline | `go-online` references undefined `broadcast_user_event` → `NameError` 500. Hit when an offline player resolves to an existing email-user lacking `vekn_id`. | `backend/src/routes/tournaments.py:1542` (fix: `broadcast_precomputed(bd)`) |
| 4 | p1 | backend/calendar | `compute_user_full` strips `calendar_token` before it's written to the `full` column, but the lookup queries `"full"->>'calendar_token'` — never matches. Personal `.ics` feed always falls back to anonymous; partial index dead. | `backend/src/access_levels.py:94`, `backend/src/db.py:399/640/249` |
| 5 | p1 | sync | On `QueueFull`, broadcast drops the message and evicts the connection from the set, but the generator keeps yielding keepalives → browser stays `OPEN` and deaf. Unrecoverable desync on high-write days. | `backend/src/broadcast.py:82-85`, `backend/src/main.py:690-703` (fix: close stream on overflow) |
| 6 | p1 | sync | Sync cursor only advances on `sync_complete`, never on live events — reconnect re-streams from a stale point; compounds #5. | `frontend/src/lib/sync.ts:207` vs `231-243` |
| 7 | p1 | backend/offline | Offline lifecycle endpoints do unlocked get→update (no `FOR UPDATE`) while every action/timer endpoint uses `tournament_transaction`. TOCTOU: two devices can both acquire the device-lock, defeating "no conflicts possible". | `backend/src/routes/tournaments.py` go_offline:1462 / go_online:1584 / force_takeover:1695 / sync_offline:1737 / force_unlock:1781 |
| 8 | p1 | frontend/sync | Optimistic write committed to IndexedDB; on server rejection only `console.error('SSE will correct')` — but a rejected action emits no SSE, so bad state persists with no user feedback. `catch {}` also swallows WASM panics. | `frontend/src/lib/api.ts:578/602-616` |
| 9 | p2 | engine | Seating uses `rand::thread_rng()` — non-deterministic and non-reproducible. Only browser `StartRound` is mitigated (seating forwarded); `computeSeating` preview, offline replay, bot-driven StartRound, RandomToss, RaffleDraw still diverge. | `engine/src/seating.rs:543/550` |

## Reported by review subagents — plausible, code-paths spot-checked, NOT each line-traced (`needs-verify`)

| # | Sev | Area | Finding |
|---|-----|------|---------|
| 10 | p1 | security/bot | `user:impersonate` refresh tokens stored plaintext in SQLite (`bot/src/token_store.py`). Backend Fernet-encrypts Discord tokens; bot should too. |
| 11 | p2 | bot | Concurrent refresh (SSE loop + slash command) can trip the backend's refresh-rotation reuse-detection and revoke the organizer's whole chain. Needs single-flight refresh per `discord_id`. |
| 12 | p2 | perf/backend | Action handler acquires extra pooled connections while holding `FOR UPDATE`, incl. one per player for sanctions (`tournaments.py:828-969`). Pool starvation risk on ~2GB VPS (pool max 20). Prefetch before the transaction. |
| 13 | p2 | engine | Standings lack a final `user_uid` tiebreak → `HashMap`-order-dependent ordering for fully-tied players, flipping position-based GP league points (`standings.rs`, `league.rs`). Same nondeterminism in card prefix lookup (`cards.rs`). |
| 14 | p2 | frontend/offline | DB version bump deletes all stores incl. in-flight offline tournaments (`db.ts:93-99`). A PWA auto-update mid-offline-tournament loses unsynced work. |
| 15 | p2 | backend/offline | Temp-UID remap is whole-JSON `str.replace`, leaving stale `TEMP-xxxx` vekn_id (8-char prefix) on player records (`tournaments.py:1577`). Remap structurally. |

## Docs / questions

| # | Type | Finding |
|---|------|---------|
| 16 | docs | `engine/TOURNAMENT.md` + `engine/README.md` describe a 3-arg `process_tournament_event` and `src/tournament.rs`; real is 5-arg returning `deck_ops` in a `tournament/` module, ~20 events undocumented. ARCHITECTURE.md bot "snapshot on reconnect" assumes an SSE format that doesn't exist (see #2). |
| 17 | docs | Document SSE realities in SYNC.md/CLAUDE.md: live-phase cursor behavior, and that rejected actions emit no SSE (so "SSE always overwrites" is false). Depends on outcome of #5/#6/#8. |
| 18 | p3/deferred | Personal overlay broadcasts internal/sync fields (`discord_id`, `resync_after`, `local_modifications`, `vekn_synced_at`) to same-country NC/Prince via the `full` projection (`access_levels.py:91`, `main.py:608-626`). **Decision: accepted for now** — low sensitivity; revisit only if a clean projection split is cheap. |

## Refactor

- **19** (p3): split `engine/src/seating.rs` (2263 lines) — dedup `fast_lex_score` vs `compute_score` and the two SA implementations; modularize measure/score/anneal/precomputed/stagger.

## Decisions (2026-06-03)
- **Bot (#2 / #10 / #11):** confirmed not live and not yet tested, but **in scope** for prod prep — keep as real work.
- **#18 internal-field overlay:** accepted for now (low sensitivity); deferred, not closed.
- **Docs (#16 / #17):** fix the bugs first, then rewrite the behavior docs. Ticket *pointers* have been added to the affected docs (ARCHITECTURE.md, SYNC.md, engine/TOURNAMENT.md, engine/README.md) for discoverability in fresh sessions.

### Decision (2026-06-06): #10 right-sized — Fernet declined, file perms hardened
The `needs-verify` premise was **false**: the backend does *not* Fernet-encrypt Discord
tokens — it stores them as plaintext JSONB in `transient_tokens` (`db.py:1439`); there is no
`cryptography`/`Fernet` anywhere in `backend/` or `bot/`. Threat-model on the actual deploy:
the bot's `tokens.db` holds backend OAuth tokens (`user:impersonate`, rotating, server-revocable
via `revoke_oauth_token_chain`). An at-rest key would live in the systemd `EnvironmentFile`, so it
co-locates with the data under host compromise / disk-snapshot theft → encryption would be theater
there; the only genuine win (data file copied without the key, e.g. a future `state_dir`-scoped
backup) is hypothetical for a not-yet-live bot. So full Fernet (new dep + vaulted secret +
key-rotation semantics) is over-engineering. **Done instead:** `tokens.db` chmod `0600` on init
(`token_store.py`) + systemd `UMask=0077` (covers `-wal`/`-shm`/`-journal` sidecars,
`service.j2`). Real blast-radius control remains server-side token-chain revocation. Closed.

### Resolution (2026-06-06): #9 seating made deterministic (seeded PRNG)
Replaced `rand::thread_rng()` in the SA seating optimizer with a value-stable
`rand_chacha::ChaCha8Rng` seeded via new `seating::seed_for_round(uid, round_index)`
(FNV-1a over uid + LCG mix of round). Threaded `seed: u64` through
`compute_seating`/`compute_next_round`/`optimize_sa`/`optimize_sa_multi`; the
StartRound handler (`tournament/mod.rs`) derives the seed from `tournament["uid"]` +
`previous_rounds.len()`, so WASM (offline), PyO3 (backend/bot), and the browser all
compute byte-identical seating — the api.ts forwarding is now a safety net, not a
requirement. `compute_seating_json` (preview, no live JS caller) derives the same seed
from `tournament_uid`+`round`. **RandomToss/RaffleDraw were already deterministic** (LCG
seeded from uid / caller seed) — no change needed there. Tests: added unit determinism
(incl. n=7 staggered path) + a StartRound event-path determinism test; full engine suite
green (131 + 1 ignored). Docs updated: ARCHITECTURE.md StartRound section, engine/README.md.
principal-engineer review: LGTM. Closed. (#13 standings/card tiebreaks still open.)

### Resolution (2026-06-06): #13 deterministic standings + tie handling + card lookup
product-manager confirmed the VEKN tie rule: equal (GW, VP, TP) ⇒ SHARED standing
(standard competition ranking with skips: 12, 12, 14); the toss is cutoff-only and must
NOT split published non-finalist ranks. GP point values are an app house rule, not VEKN.
Three fixes:
- **standings.rs**: added `user_uid` as the terminal sort tiebreak (toss kept for the
  finals cutoff, but it is NOT part of the GP rank key). Without it, fully-tied players
  came out in nondeterministic HashMap order.
- **league.rs (GP mode)**: GP points now key off the **shared standing rank** (standard
  competition rank over the (gw,vp,tp) key), not the array index — so tied players get
  EQUAL points and the next distinct score skips ranks (option (a), best-position points).
- **cards.rs**: prefix lookup picks a deterministic winner (shortest matching name, then
  lowest id) instead of arbitrary HashMap order; and the index now resolves ambiguous bare
  names (e.g. all three "Theo Bell" printings index "theo bell") to the non-adv first
  release (lowest id) instead of "last insert wins". Validated on real cards.json: 77
  colliding keys, 0 won by an adv card. ADV/grouped lookups are unaffected (unique exact
  keys). Typical TWDA lines resolve via exact match after crypt-tail stripping; prefix is
  a rare fallback.
Tests: standings tie-order determinism, GP shared-rank + skip, prefix determinism, bare-name
collision. Full engine suite green (135 + 1 ignored).
**Scope split:** filed #43 (p2) — GP "position" uses prelim standing order, not final
placement, so a finalist who WINS the finals but didn't finish prelim-1st is scored 15 not
25. RTP already handles finalists via `tournament["winner"]`; GP mode does not. Only the
non-prelim-1st winner is mis-scored (positions 2–5 are a flat 15 band). Closed #13.

### Resolution (2026-06-06): #12 action handler no longer fans out pooled connections under lock
The action handler (`tournament_action`) ran its read helpers — incl. a **per-player**
`get_sanctions_for_user` loop — *inside* `tournament_transaction`'s `FOR UPDATE`, each
grabbing its own pooled connection. With pool `max_size=20`, ~20 concurrent actions pin all
connections via their `tx_conn`, then every in-lock acquire blocks → starvation/deadlock.
**Chosen fix: connection reuse, NOT prefetch-before-lock.** Prefetch was the ticket's
literal suggestion but would reintroduce a TOCTOU window — the per-player sanction set
depends on the *locked* tournament's player list, so it can only be read after the FOR
UPDATE resolves. Instead: added `db._acquire(conn=None)` (yields a passed-in conn, else
pulls from the pool) and threaded an optional `conn` through the read helpers
(`get_object_full`, `get_user_by_uid`, `get_tournament_by_uid`, `get_decks_for_tournament`,
`get_sanctions_for_tournament`/`_for_user`, `get_all_leagues`). All ~55 connection-less
callers are unchanged (default → pool); only the locked path passes `conn=tx_conn`, so one
in-flight action consumes exactly one connection. Collapsed the per-player loop into a single
batched `get_sanctions_for_users` (`user_uid = ANY(%s)`). Tests: `test_action_conn_reuse.py`
(acquire-reuse, batched==per-user union, zero pool checkouts while locked). Full backend
suite green (141). principal-engineer review: LGTM. **Note for future readers: keep it as
connection-reuse — do not "fix" it back to prefetch (TOCTOU).** The lower-frequency
per-player loop in the offline `sync-offline`/go-online path (writes new users) was left
as-is — once-per-go-online, not the hot action path; overlaps #15's area. Closed #12.

### Resolution (2026-06-06): #44 ambient transaction connection (reads reuse, writes independent)
Generalised #12's manual `conn=` threading into an automatic, guarded mechanism so the
"never acquire a second connection while holding the lock" invariant can't be forgotten.
- **Ambient read reuse:** `tournament_transaction` publishes its `FOR UPDATE` connection in a
  `ContextVar` (`_tx_conn`, holding `(conn, owner_task)`); `_acquire` (the read-helper path)
  resolves explicit `conn=` → ambient → pool. Reads called inside a transaction now reuse
  `tx_conn` automatically (snapshot-consistent, zero extra checkout) — incl. go-online's
  per-player `get_user_by_vekn_id`/`get_auth_method_by_identifier`/`get_user_by_uid`.
- **Writes stay independent (deliberate, load-bearing):** `get_connection` is NOT
  ambient-aware. Discovered that making writes ambient would BREAK go-online: each new user's
  `insert_user` must commit and be visible to the next `allocate_next_vekn_id` (its own
  advisory-locked txn); folding inserts into the outer txn (uncommitted) → **duplicate VEKN
  IDs**. So writes pool independently; a write joins the txn only via explicit `conn=tx_conn`
  (the action handler's single tournament save). The global "request-scoped / take-conn-high"
  idea was rejected for the same reason + because actions do heavy non-SQL work (PyO3 engine,
  VEKN HTTP push, ratings, broadcasts) — holding a pooled conn across that defeats the small
  pool on a 2GB VPS. Unit of work is the **transaction**, not the request.
- **Cross-task guard:** `_acquire` raises if the ambient conn is reached from a task other than
  the owner — catches a `create_task`/`gather` spawned inside a transaction (single-threaded,
  but one `await execute` yields mid-flight → interleaving on the shared conn, or the child
  outliving the `with` block). Verified none exist inside any `tournament_transaction` today
  (spawned DB tasks — Discord/VEKN sync — all fire post-commit).
Kept #12's explicit `conn=tx_conn` threading (PE: strictly safer, task-independent, makes the
txn boundary visible at the call site — survives the exact failure the guard catches). Tests:
`test_ambient_conn.py` (read reuses ambient / write pools independently / allocate→insert→
allocate distinct ids / cross-task raises). Full backend suite green (145). principal-engineer
review: LGTM. Documented in ARCHITECTURE.md "Database Access & Connection Model".
**Deferred:** go-online still checks out a short-lived independent connection per new-user
write inside the lock — pool pressure (not deadlock: different rows, short hold), rare
(once per go-online). Clean fix = resolve/create players BEFORE taking the `FOR UPDATE` lock;
tracked on #44's note + overlaps #15. Closed #44.

### Resolution (2026-06-06): #45 go-online resolves players before the lock
Restructured `go_online` (`tournaments.py`) so user creation no longer happens inside the
`FOR UPDATE` lock. New order: (1) cheap request validation (UID match); (2) **pre-lock gate** —
unlocked `get_tournament_by_uid` + `_is_organizer`/device-lock checks to fail fast and gate
side effects; (3) **resolve/create players** (`_resolve_or_create_offline_player` loop:
insert_user / allocate_next_vekn_id / invite emails) OUTSIDE any lock; (4) **lock** only to
re-verify auth+device authoritatively (TOCTOU), merge organizers, remap temp UIDs, and
`save_object(conn=tx_conn)`. The lock now holds only `tx_conn` — re-checks on the locked
object (no DB), CPU remap, one write — zero per-player pooled-connection acquisition.
TOCTOU protection preserved (the locked re-check is still the serialization point; sequential
reconcile is last-writer-wins as before). Tests: `test_go_online.py` — non-organizer→403 and
wrong-device→409 both create ZERO users (side-effect gating), organizer→200 resolves+creates+
remaps the player and clears offline_mode. Full backend suite green (148). principal-engineer
review: LGTM. **Known benign race (documented inline):** if the caller's organizer rights are
revoked between the pre-check and the lock, the re-check 403s after users were created →
orphaned real/coopted accounts. Accepted (rare, harmless). Closed #45.

### Resolution (2026-06-07): #15 temp-UID remap — verified premise wrong, fixed the real (deck) bug
The ticket premise ("stale TEMP- vekn on **player** records") was **wrong** on verification:
the engine's player object carries no vekn_id (`engine/tournament/mod.rs` AddPlayer stores only
`user_uid`), and a player's `user_uid` is the *full* temp UUID, which the existing whole-JSON
`str.replace(temp_uid, real_uid)` already remaps correctly (incl. nested seating, standings,
`finals.seed_order`, raffles, winner). The **one real stale-`TEMP-`** case is a **deck's
`attribution`**: `DeckUpload.svelte` sets a "self"-attributed deck's attribution to the player's
vekn, which offline is `TEMP-<uid[:8]>` (the UID's 8-char *prefix*, not the full UID) — so the
replace can't touch it, and the deck stays attributed to a non-existent vekn (matters for the
winner-deck → TWDA path + display).
**Decision (course-corrected mid-implementation):** an initial *structural* rewrite of the remap
was abandoned — principal-engineer caught it silently dropping `finals.seed_order` (the
enumerate-and-miss-a-field trap), and a whole-JSON replace is complete-by-construction for full
UUIDs. Final shape:
- **Tournament** (nested fields): whole-JSON **byte** replace via `msgspec.json.encode/decode`
  (faster than stdlib `json`).
- **Sanctions / decks** (flat single objects): repoint the one UID field directly on the typed
  model (`uid_map.get(...)`) — no JSON round-trip at all.
- **Deck `attribution`** is a vekn (the "designed by" credit, NOT redundant with `user_uid` =
  who *played* it), so a temp player's own-deck attribution is their offline `TEMP-<uid[:8]>`
  vekn. Repoint it to the resolved **real** vekn via a direct `TEMP-vekn → real-vekn` map
  (`vekn_remap`, built in the resolve loop from `player_data.vekn_id` → `real_user.vekn_id`);
  drop it if the temp player didn't resolve. We *preserve* attribution (don't null it) because
  it's meaningful credit.
Tests: `test_go_online.py::test_nested_uids_and_deck_attribution_remapped` (nested seating/winner
remapped, deck attribution → real vekn, no `TEMP-`/temp UID survives) + the new-player real-VEKN
assertions; removed the deprecated substring unit test. Full backend suite green (148).
Docs (ARCHITECTURE.md/SYNC.md) updated. **Filed #46:** TWDA submission ignores `attribution` —
it should emit the "designed by" credit into the TWDA header. Closed #15.

### Resolution (2026-06-07): #11 concurrent token refresh single-flighted per organizer
Verified the `needs-verify` premise — it was **real**. The backend rotates refresh tokens
with reuse-detection (`routes/oauth.py:350-406`): a refresh revokes the presented token and
issues a new pair; replaying an already-revoked refresh token calls
`revoke_oauth_token_chain(parent)` and kills the organizer's whole chain. The bot had two
uncoordinated refreshers on one shared `ArchonAPI` (single asyncio process): the SSE loop on a
`/stream` 401 (`sse_listener.py:145`) and any slash command on a 401 (`archon_api.py` `_request`).
Both read the same stored refresh token and POSTed it → A rotates R0→R1, B replays stale R0 →
reuse detected → chain revoked → organizer logged out, SSE stops.
**Fix:** single-flight per `discord_id`. Added a `dict[str, asyncio.Lock]` (`_refresh_locks`,
get-or-create in `_refresh_lock_for` — atomic, no await between get and assign). `_refresh_tokens`
now takes `stale_access_token`, takes the lock, **re-reads the store**, and if the stored access
token already differs from the one that 401'd (a concurrent refresher rotated while we waited)
returns the fresh pair WITHOUT POSTing; otherwise calls the extracted `_do_refresh` (original
POST+persist) under the lock. Both call sites pass the token that 401'd. The re-check is the load-
bearing part: serializing the POST alone wouldn't help — the loser would still replay its stale
token. Genuine-expiry path is correct: first waiter clears the store under the lock, later waiters
find no tokens and return None without a second POST.
Tests: `bot/tests/test_refresh_single_flight.py` — stdlib `unittest` (no pytest in the bot venv),
a `FakeBackend` modeling rotation+reuse-detection, incl. a guard test proving the fake actually
exhibits chain-revocation under double-spend (so the single-flight assertions aren't vacuous).
5/5 pass; ruff clean; imports OK. Docs: ARCHITECTURE.md bot status pointer updated.
principal-engineer review: **LGTM**. Notes: (a) the in-process `asyncio.Lock` is sufficient only
because the bot is single-process/single-replica — horizontal scaling would need a DB-level CAS on
the stored token (known boundary, out of scope); (b) pre-existing, unrelated to #11: the SSE 401
path `continue`s with no backoff reset — minor, left as-is. Closed #11. (#2 SSE `event:` dispatch
still open — the bot's reactive logic remains dead until that lands.)

### Resolution (2026-06-08): #14 destructive IDB upgrade now rescues unsynced offline data
The frontend `getDB()` upgrade handler (`frontend/src/lib/db.ts`) dropped & recreated ALL
object stores on any `DB_VERSION` bump (intended: force a full SSE resync of synced data). But
an in-flight **offline** tournament is locked to this device and may hold changes not yet pushed
to the server — a PWA auto-update bumping the version mid-offline-tournament silently destroyed
unsynced work. Fix: rescue offline-pending data across the destructive rebuild.
- **`db.ts`** — `rescueOfflineData(db, tx)` runs inside the (now `async`) versionchange
  transaction BEFORE the drop loop; `restoreOfflineData(tx, rescued)` writes it back into the
  freshly recreated stores. The `offline_*` metadata keys are the manifest; rescue pulls the
  referenced rows: the offline tournament row, temp player user-stubs (from `offline_players`
  `temp_uid`), offline sanction rows, offline deck rows. Synced data + `last_sync_timestamp` are
  deliberately NOT preserved → clean resync. **Transaction-liveness:** awaits only IDB ops; the
  manifest read is one `Promise.all`, then ALL per-row reads are issued in a single synchronous
  burst and awaited via one `Promise.all` (a sequential await-per-row loop can let the
  versionchange transaction go inactive — idb's documented "transaction lifetime" hazard).
  Store-existence guards handle fresh installs / old schemas.
- **`sync.ts`** — folded in the same-class bug the PE flagged (more common trigger):
  `clearAllStores()` (resync/refresh path) rescued ONLY the tournament row, so a server-driven
  `resync` for an offline device dropped the offline **sanction/deck rows** (metadata pointers
  survived, but `goOnline()`'s `getSanction`/`getDeck` then returned undefined → silently dropped
  from reconciliation) and player stubs. Now rescues+restores the full offline set.
- The fix is preventive: `DB_VERSION` left at 15 (bumping it just to exercise the path would
  needlessly churn every current user's synced data); the new handler runs on the next schema bump.
Validated in a throwaway fake-indexeddb sandbox (per owner's "sandbox-only, no new test vertical"):
offline rows + `offline_*` metadata preserved across a v14→v15 destructive upgrade, synced data +
cursor wiped, restored rows reachable via recreated indexes, fresh-install no-op. `npm run check`
(svelte-check) green, 0 errors. Docs: SYNC.md upgrade behavior updated, #14 pointers removed from
SYNC.md/ARCHITECTURE.md. principal-engineer review: **LGTM** on the db.ts migration (all four
design points sound); clearAllStores fold-in done at its recommendation. Closed #14.

### Decision (2026-06-08): #18 closed won't-fix
Re-examined the internal-field overlay leak in full and confirmed the original "accepted, low
sensitivity" call stands. Findings from the re-trace:
- **Leak surface is 3 sites, all emitting the User `full` representation:** (A) the `full.json.gz`
  snapshot served to IC on first connect — IC sees these for *all* users, every country
  (`snapshots.py` + `_viewer_level`→FULL); (B) the initial personal overlay for same-country users
  (`main.py:611-617`); (C) the live broadcast to IC (all) + same-country NC/Prince
  (`broadcast.py:65-73`). Broader than the ticket's "same-country NC/Prince" (IC is global).
- **The genuinely-internal fields are 4:** `resync_after` (server-only; read off the loaded model
  at `main.py:511`, not even in the frontend type), `local_modifications`, `vekn_synced`,
  `vekn_synced_at` (backend bookkeeping; type-declared on the frontend but **no code reads them**).
- **`discord_id` is NOT a real leak** (ticket mis-grouped it): it's a contact field the UI uses to
  build `discord.com/users/{id}` links for officials (`User.svelte:564`, `CommunityTab.svelte`);
  NC/Prince/IC are meant to have member contact info. Excluded from any fix.
- **Constraint:** the `full` column is canonical storage (model round-trip + `vekn_push.py:288`
  queries `"full"->>'vekn_synced'`), so the fields must stay in the column; only what's *emitted*
  could change. A cheap migration-free fix exists (Postgres JSONB `-` to strip the 4 keys in the
  snapshot/overlay SELECTs + a precomputed `full_broadcast_json` for the live path, ~30-40 lines).
**Decision (owner): close won't-fix.** No secrets/credentials; zero client consumers (the fields
just sit unused in IndexedDB); not worth touching the hot sync path. The cheap-fix recipe above is
recorded here should the calculus change (e.g. if a future field on the User model IS sensitive,
revisit the broadcast-vs-storage split). Closed #18.

### Resolution (2026-06-08): #66 account-surgery writes now broadcast live to other clients
`merge_users` / `detach_user_from_vekn` (`db.py`) write multiple user records via `save_user`
(which returns `BroadcastData`) but DISCARDED those BDs; callers only `broadcast_resync(owner_uid)`
(a full-resync signal to the *owner's own* SSE connection). So other connected clients
(same-country NC/Prince, IC) that cache these records kept stale copies — notably the orphaned
VEKN record's now-nulled `discord_id`/contacts — until their next reconnect/catch-up. DB +
VEKN-push + fresh snapshots were already correct; only live propagation lagged. Pre-existing,
surfaced by #59.
**Fix (the layering-respecting shape the ticket prescribed — db.py can't import broadcast):**
- `merge_users -> tuple[User, list[BroadcastData]] | None` returning `(merged, [merged_bd,
  soft_delete_bd])`; `detach_user_from_vekn -> tuple[User, User, list[BroadcastData]] | None`
  returning `(personal, vekn_record, [personal_bd, vekn_bd])`.
- Every caller now `broadcast_precomputed`s each returned BD, then keeps the existing
  `broadcast_resync(owner)` (owner's data-LEVEL change — gained/lost vekn_id): `vekn.py`
  claim/abandon/link(displace+merge)/force-abandon, `admin.py` merge (previously broadcast
  NOTHING), `auth/discord.py` link-merge (+ its follow-up discord-field save).
- `/link` order is safe: detach writes then merge writes the same uid → strictly later
  `modified_at`, broadcast later; frontend applies `saveUser` by uid unconditionally → last wins
  (PE confirmed the cross-stack reasoning).
Tests: `test_account_surgery.py` updated for the new return shapes + `len(broadcasts) == 2`
assertions on both functions. Full backend suite green (158). Ruff clean. principal-engineer
review: **LGTM**. Docs: `.pst/details/59-vekn-detach.md` #66 note marked fixed.
**Filed two follow-ups the review flagged (both parent:#1):** #77 — frontend ignores user
soft-deletes over SSE (`sync.ts` users `del` is a no-op, so the merged dup lingers until a
snapshot resync; one-line fix, `deleteUser` exists); #78 — `merge_users` `reassign_*`
(sanctions/decks/coopted_by) mutations still aren't broadcast (sanction staleness is
correctness-visible to same-country NC/Prince). Both deliberately out of #66's user-record scope.
Closed #66.

## Suggested order
p0 first (#2, #3), then the sync/offline correctness cluster (#5, #6, #7, #8, #4), then engine determinism (#9, #13) and bot security (#10, #11). Answer #18 before touching projections. Docs (#16, #17) trail the code fixes.

## Not issues (checked, OK)
- Server-side authorization is genuinely re-enforced by the Rust engine; clients cannot spoof `is_organizer`.
- No PII leaks into `public`/`member` projections; OAuth tokens / password hashes live in separate tables, never projected.
- `.env`, `backend.log`, `frontend.log` are gitignored and untracked — no secrets in the repo.
