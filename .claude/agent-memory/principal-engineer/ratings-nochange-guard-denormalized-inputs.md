---
name: ratings-nochange-guard-denormalized-inputs
description: The ratings no-change/skip-if-unchanged guard only converges if the upstream fields it denormalizes (tournament name + date) are stable; two narrow non-convergence vectors
metadata:
  type: project
---

`recompute_ratings_for_players` (ratings.py) has a skip-if-unchanged guard: `if cat_rating == getattr(user, category.value) and new_wins == user.wins: continue`. It compares a freshly computed `CategoryRating` (deep msgspec Struct `==`; entries are `frozen`, engine vp/gw/points are deterministic) against the stored one and skips the save+SSE-delta. This is the #366 fix (stop churning the whole rated corpus daily).

**It converges only as far as its denormalized inputs are stable.** Each `TournamentRatingEntry` embeds `tournament_name` (t.name) and `date = (t.finish or t.start or t.modified).date()`. Two ways the guard perpetually re-saves a user daily:

1. **`tournament_name` oscillation** — if the cross-sync tournament-meta flip-flop ([[archon-merge-cross-sync-flipflop]]) is active, an event's `name` flips daily between the archon merge and the VEKN tournament sync → the entry's name flips → cat_rating differs → guard never skips. The guard is necessary-but-not-sufficient while that flip-flop exists; the real fix is single-writer meta.
2. **date-fallback to `t.modified`** — `finish` is frequently None (the engine never stamps it on FinishTournament/FinishFinals; db.py `get_finished_tournaments_for_category` COALESCEs finish→start→modified). For a Finished tournament with BOTH finish AND start null, the entry date == modified; if that tournament's `modified` churns (re-sync), the entry date churns daily. Narrow (needs both null), but both-null is a modeled state.

**Why:** these are pre-existing input-instability vectors, not introduced by the guard, and the guard is strictly better than the prior unconditional daily save. But they bound how much daily SSE churn the guard actually removes.

**How to apply:** when reviewing any skip-if-unchanged/`same_but_modified`-style guard over DENORMALIZED data, list the upstream-mutable fields it embeds and confirm each is stable across runs — an equality guard can't suppress churn that's genuinely present in its inputs (same caveat the flip-flop memory raises for `same_but_modified`). Also note: existing stored `user.wins` were written unsorted by the old code, so the first post-deploy run re-saves every rated user once to normalize to `sorted()` — expected, harmless.
