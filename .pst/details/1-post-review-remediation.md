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

## Suggested order
p0 first (#2, #3), then the sync/offline correctness cluster (#5, #6, #7, #8, #4), then engine determinism (#9, #13) and bot security (#10, #11). Answer #18 before touching projections. Docs (#16, #17) trail the code fixes.

## Not issues (checked, OK)
- Server-side authorization is genuinely re-enforced by the Rust engine; clients cannot spoof `is_organizer`.
- No PII leaks into `public`/`member` projections; OAuth tokens / password hashes live in separate tables, never projected.
- `.env`, `backend.log`, `frontend.log` are gitignored and untracked — no secrets in the repo.
