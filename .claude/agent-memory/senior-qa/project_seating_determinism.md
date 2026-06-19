---
name: seating-determinism
description: Tournament seating is deterministic (seeded ChaCha8Rng); which paths consume the seed and what the determinism tests cover
metadata:
  type: project
---

Tournament seating in the Rust engine is deterministic: `rand::thread_rng()` was replaced with `rand_chacha::ChaCha8Rng::seed_from_u64`, and a `seed: u64` is threaded through `compute_seating`/`compute_next_round`/`optimize_sa`/`optimize_sa_multi`. `seating::seed_for_round(tournament_uid, round_index)` derives the seed (FNV-1a over uid, mixed with round index via an LCG step). StartRound (tournament/mod.rs) and compute_seating_json (lib.rs) both derive the seed this way, so WASM/PyO3/offline-replay/bot all reproduce the same seating without forwarding the result.

**File layout (post-split):** `seating.rs` was split into `seating/{mod,measure,score,anneal,precomputed,stagger,tests}.rs`, public API unchanged. `seed_for_round` + `compute_seating`/`compute_next_round` live in `seating/mod.rs`; SA in `anneal.rs` (`optimize_sa_multi`/`optimize_sa`); scorers in `score.rs`; precomputed fast path in `precomputed.rs` (`apply_precomputed`); staggered path in `stagger.rs` (`get_staggered_rounds`); seating tests in `seating/tests.rs`. Two-scorer dedup: `fast_lex_score` and `compute_score` now share one private `score_measure` core (both read its tuple — incapable of diverging on rule counts). `optimize_sa` drives accept/reject with `fast_lex_score` on intermediates but RETURNS `compute_score` on the final measure; the dedup is what guarantees the optimization target and the reported score agree. The split also dropped a redundant pre-shuffle in `optimize_sa_multi` (optimize_sa reshuffles from its own sub-seed) — RNG stream and thus per-seed OUTPUT changed vs the old engine, still fully deterministic; guarded by the determinism + structural-invariant tests (no new test warranted).

**Why:** offline-first means seating may be computed in multiple runtimes; they must agree by construction.

**How to apply:** when reviewing seating coverage, remember the three paths and which consume the seed:
- Precomputed fast path (no previous + exactly 3 rounds + n in 4-25 except 6/7/11): returns `apply_precomputed`, NEVER calls SA — deterministic by construction, seed irrelevant. Don't bother adding determinism tests here.
- Staggered path (n in {6,7,11}, no previous): deterministic `get_staggered_rounds` then FALLS THROUGH to `optimize_sa_multi` — seed DOES matter.
- General SA path (n=13, or any call with previous rounds): `build_round` init then `optimize_sa_multi` — seed matters.

`test_compute_seating_is_deterministic` (`seating/tests.rs`) covers the general SA path (n=13), the staggered path (n=7), and seed_for_round stability/uniqueness. `test_start_round_computed_seating_is_deterministic` (`tournament/tests.rs`) covers determinism across the `process_tournament_event` StartRound event boundary with NO submitted seating (the only path that actually exercises the seed branch in tournament/mod.rs). Both added 2026-06-06, closing the gaps the original review flagged.
