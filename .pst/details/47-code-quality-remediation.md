# EPIC #47 — Code-quality remediation

Goal: compactness and elegance. Remove bloated patterns that look like structure but
carry no functional weight; tighten file scoping; keep the good "why" comments.
This is **quality only** — no behaviour change intended by any child.

## Working agreement (READ BEFORE TOUCHING CODE)

- **Discuss each child together before refactoring.** Re-examine the specific code,
  agree the shape of the change, *then* implement. Do not batch-refactor the epic.
- One child at a time: `pst wip <N>` → discuss → implement → verify build/tests green → `pst close <N>`.
- Default tie-breaker when in doubt: **locality over DRY/abstraction** (owner preference).
  A child may conclude "leave as-is, locality wins" — that's a valid outcome, close it WONTFIX-style with a note.

## Suggested starting point

No hard order. Trivial wins (#48, #49, #50) are good warm-ups; #59 is the only child
with a latent bug behind it (merge_users silently drops new User fields) so it's the
highest-value single pick. Everything else is p3 tidiness.

## Where this came from

Critical read of all four stacks (engine/backend/frontend/bot) on 2026-06-07.
Headline: comments are genuinely good (the "why" comments earn their place — keep them);
the real smell is repeated ceremony/passthrough wrappers and a few multi-concern files.

## Children

Compactness / ceremony (passthrough wrappers with no functional value):
- #48 db.py insert_/update_ twin CRUD wrappers (4 byte-identical upsert pairs)
- #49 access_levels.py identity projection funcs (league ×3, sanction member/full) → shared passthrough
- #50 api.ts ×22 `if(!isOnline()) throw` → one `requireOnline()` guard

Factor repeated boilerplate to one helper:
- #51 backend permission checks scattered/duplicated (`_can_manage_*`) → one permissions module
- #52 backend VEKN-client init/try/close dance ×3-5 → `_with_vekn_client()` ctx mgr
- #53 bot `get_userinfo`+roles-extract+respond ×8 → shared role-check helper

File scoping / oversized:
- #54 db.py (1601 L) — move inline DDL to migration + account-surgery to own module
- #55 api.ts (879 L) — extract optimistic-mutation engine → tournament-actions.ts
- #56 +page.svelte (1064 L) — move pure helpers → lib/tournament-utils.ts
- #57 bot sse_listener.py (882 L) — state→class, formatting→announcements.py
- #58 engine tournament/mod.rs (1977 L) — discuss handler split (locality caveat)

Duplicated domain logic / fragility:
- #59 db.py strip/split twins + merge_users hand-listing all User fields (latent bug) [p2]

Small direct findings:
- #60 db.py micro-cleanup (dead `_decoder`, per-call Decoder, function-local imports)
- #61 api.ts createUser/updateUser query-params→JSON body + FormData via apiRequest
- #62 move hardcoded reference data (rosters, city/tz, COUNTRY_LANGUAGE) → config/data

## Out of scope / explicitly NOT doing

- **db.py per-type `SELECT "full" … → [decode_json]` helpers (22 of them):** keep them
  as explicit per-function SQL. A generic wrapper would turn 3 lines into 1 but loses
  greppability/locality. **Owner decision: locality wins, do not collapse.**
- **Rust seating dedup/split** (fast_lex_score vs compute_score, the two SA impls,
  module split): already tracked under **#19** (epic #1). Conceptually in scope, just
  ticketed elsewhere — do it there, not here.

## Don't-touch list (avoid over-correcting)

- The "why" comments: `_tx_conn` ambient-connection invariant (db.py:61-77), optimistic
  rollback rationale (api.ts:688-696), calendar_token-not-broadcast (db.py:263-271),
  sync high-water-mark. Keep them.
- access_levels.py dispatch-table design — elegant; only the identity funcs are redundant (#49).
- api.ts `enqueueServerAction` per-tournament queue + rollback logic — compact and correct.
- db.py `BroadcastData` pre-serialization (avoids a DB re-read) — a real optimization.
- The 288-line precomputed seating tables — algorithm constant, not bloat.

## Resolution notes

- **#58 (engine tournament/mod.rs split): WONTFIX — locality wins.** `apply_event`
  (mod.rs:181-1961) is a single 39-arm `match TournamentEvent`: the complete
  tournament state machine, in lifecycle order, in one greppable place. The bulk is
  intrinsic, not incidental. Splitting into phase-grouped handler files would
  fragment the state machine across files (following a flow means file-hopping),
  thread `(tournament, actor, sanctions, decks, deck_ops, state)` + destructured
  event fields through ~39 new fn signatures (ceremony that could *grow* line count),
  and churn the cross-stack correctness core (PyO3 + WASM; offline/online must agree)
  with zero behavioural change — the highest-risk module to touch for the weakest
  payoff. The sibling decomposition already done (scoring/standings/raffle/sanctions/
  parsing/helpers/types) is layered; the arms are peers in one dispatch, not layers,
  so the analogous split isn't natural. cf. #19 (seating.rs) where the split *was*
  layered (measure/score/anneal). Discussed and confirmed with owner.
