---
name: vekn-standings-toss-scope
description: VEKN final-standings ranking key, share-a-standing tie rule, and the strict scope of the random toss (cutoff only, never general tiebreak)
metadata:
  type: project
---

VEKN published-standings ranking key is exactly 3 fields, in order: 1) Game Wins, 2) total VPs, 3) Tournament Points (tournament-rules.md §3.1). Ties on all three SHARE a standing using standard competition ranking with skips ("1224": two tied for 12th both publish 12th, 13th skipped, next is 14th).

The **random toss** has only two sanctioned jobs and must NOT be a general tiebreaker:
- Breaks a tie that straddles the **top-5 finals cutoff** (who is 5th finalist vs 6th non-finalist). §3.1: "Remaining ties for top 5 broken randomly."
- Finals first-player is random; finals seating uses a separate crypt-reveal procedure (§3.1.3), not the prelim toss.

The toss never splits tied non-finalists in the published ranking.

**Why:** Owner confirmed share-a-standing rule; engine bug (epic #1, ticket #13) had `compute_standings` sorting `gw,vp,tp,toss desc` from a HashMap with no unique final key — nondeterministic array order, and `toss` (0 for most players) doesn't make it deterministic.

**How to apply:** When touching standings/ranking: compute the rank integer from the 3-field key only (skip-style ties); use `user_uid` as a deterministic terminal sort key for array order (never affects the rank number); keep `toss` scoped to cutoff resolution. See [[vekn-gp-league-points]].
