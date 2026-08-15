---
name: player-count-four-implementations
description: "How many players played" is implemented four times across Rust/Python/TS with two different definitions; plus league.rs already owns the key name `player_count` for a caller-injected value.
metadata:
  type: reference
---

"Players who actually played" — the field size feeding every rating coefficient,
the ranking floor and the TWDA floor — has **four** implementations, three of them
outside Rust:

1. `engine/src/ratings.rs` `players_with_rounds` — rounds→seats (+finals), else
   standings rows carrying any score. DQ-inclusive (rules A.2). The canonical one.
2. `backend/src/ratings.py` `_players_with_rounds` / `_player_count` — hand-written
   Python twin of (1). `_player_count` feeds `compute_rating_points` and
   `vekn_push.py` (`_player_count` is imported there).
3. `backend/src/routes/tournaments.py` `_played_player_count` — **different
   definition**: rounds/finals seats only (no standings fallback → returns 0 for any
   rounds-less import) and it *subtracts* `non_competing` proxies. Gates
   `TWDA_MIN_PLAYERS`.
4. `frontend/src/lib/tournament-utils.ts` `playedPlayerUids` / `seatedPlayerCount` —
   TS twin of (1), consumed by `leagues/[uid]/+page.svelte` which computes league
   standings **client-side** and injects the count into the engine.

**How to apply:** any change to the counting rule (e.g. adding an attested/reported
count fallback for roster-less archival imports) must land in all four or they
silently disagree — and (3) disagrees *by design*, so "share the constant, not the
function" is usually the right call between (3) and the rest. Prefer adding a single
PyO3/WASM entrypoint and deleting (2)/(4)'s arithmetic over writing a fifth copy.
See [[sa-penalty-duplicated-in-python]] for the same failure mode already realized.

**Name collision:** `engine/src/league.rs:53` reads `tournament["player_count"]` from
a **caller-synthesized** summary object, not from the Tournament model. Adding a
`player_count` field to `Tournament` would make real tournament JSON silently satisfy
that read with different semantics. Any new count field on the model must be named
something else (`reported_player_count`).
