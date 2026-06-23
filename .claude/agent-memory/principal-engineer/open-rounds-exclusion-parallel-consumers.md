---
name: open-rounds-exclusion-parallel-consumers
description: Excluding open_rounds/self_organized events from VEKN/ratings must cover EVERY parallel tournament aggregator — the wins query (HoF) is a separate path that leaks
metadata:
  type: project
---

`open_rounds` is now a persisted Tournament bool (decoupled from `max_rounds`): non-VEKN house format, excluded from VEKN push AND ratings/RTP. The exclusion was added to the obvious paths (vekn_push.py queries + early-return, ratings.py rating-points filter) but **parallel aggregators that walk Finished tournaments independently are easy to miss**.

**Why:** ratings has TWO outputs from `recompute_ratings_for_players`: (a) the rating `total`/`entries` — correctly filtered by the `all_tournaments = [t for t ... not (t.open_rounds or t.self_organized_rounds)]` list; and (b) `user.wins = wins_map.get(...)`, sourced from `db.get_tournament_wins_for_users`, a SEPARATE query (`"full"->>'state'='Finished' AND winner IN (...)`) with NO open_rounds filter and NO date window. `user.wins` drives the Hall of Fame board (`rankings/+page.svelte`: filters `wins.length>=5`, sorts by `wins.length`) — so an open-rounds win still inflates HoF even though it never touches the rating number. Same class as [[excluded-not-zeroed-standings-consumers]] (a parallel iterator leaking a score that the primary path excluded).

**How to apply:**
- When excluding a tournament class from "competitive" aggregation, grep for ALL queries keyed on `state='Finished'` / `winner` / iterating `stream_objects_new("tournament", ...)` — not just the rating loop. Known sites: `recompute_ratings_for_players` (filtered), `recompute_all_ratings` pass-1 (filtered), `get_tournament_wins_for_users` (NOT filtered — the gap), `get_finished_tournaments_for_category` (unfiltered SQL; in-code filter compensates only for the ratings caller, not other callers).
- The two ratings paths (`recompute_all_ratings` pass-1 collect + `recompute_ratings_for_players` pass-2 re-filter) are consistent — both skip open_rounds, no double-count. The leak is strictly the wins query.
- Engine-level coupling gap (answers "should self_organized require open_rounds?"): `validate_config_fields` (engine/src/tournament/mod.rs) gates `self_organized_rounds=true` only on `max_rounds>0`, NOT on `open_rounds=true`. So `self_organized=true, open_rounds=false, max_rounds=3` is byte-identical-to-standard-VEKN and currently legal. Push/ratings still exclude it (both check self_organized independently), so no leak — but the invariant "self_organized ⟹ open_rounds" is UI-only, not enforced in Rust. If a future consumer keys only on `open_rounds`, that combo leaks.
- Old rows decode safe: Tournament structs are NOT `forbid_unknown_fields` and `open_rounds: bool = False` has a default, so pre-flag tournaments decode to `False`. The vekn_push SQL uses `IS DISTINCT FROM 'true'`, which keeps NULL (`->>` on absent key) in the push set — correct for legacy rows.
- This change supersedes #297 (self_organized push guard was build-separation-only; now a hard query guard). `max_rounds>0` WITHOUT open_rounds/self_organized stays VEKN-pushable — the guards key on the flags, never on max_rounds.

See also [[open-rounds-per-player-cap]] (the format design), [[completed-player-state-finalist-withdrawal]].
