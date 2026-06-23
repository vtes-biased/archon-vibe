---
name: excluded-not-zeroed-standings-consumers
description: non_competing (proxy) is excluded-from-rank but score is NOT zeroed, breaking the DQ "excluded⟹zeroed" assumption in standings consumers (league.rs, vekn_push)
metadata:
  type: project
---

Standings now carry TWO "non-ranked" flags with different score semantics:
`disqualified` (score **zeroed** in `compute_preliminary_standings`) and
`non_competing` / proxy (score **kept** — the seat's VPs are real for opponents
and table-sum checks). Several consumers iterate `tournament.standings` and only
ever worked because DQ rows were zeroed; with proxy they now leak real GW/VP/TP.

**Why:** found reviewing the proxy-player feature (`.pst/details/285-proxy-player.md`).
The engine excludes proxies from rank/rating/finals correctly, but two consumers
of the raw standings array have NO `disqualified`/`non_competing` filter:
- `engine/src/league.rs` standings loop (~line 68) — adds gw/vp/tp and
  `tournaments_count += 1` for every row; proxies surface as ranked league
  entries (GP mode also feeds the proxy's continuation-rank into `compute_gp_points`).
- `backend/src/vekn_push.py` `generate_archondata` (~line 88) — emits the proxy
  to vekn.net (the external system of record) with real vp/gw/tp; only `rtp` is
  zeroed (via the engine rating guard). Worst leak: writes the non-competing
  official to the official upload as a placed competitor.

**How to apply:** any code that reads `tournament.standings` rows and treats
them as competitors must filter on `disqualified || non_competing` (the combined
non-ranked signal), NOT rely on the score being zero. The fix also cleans a
latent DQ artifact (DQ rows inflate `tournaments_count` with a 0/0/0 entry).
Contrast: keeping proxies in the rating HEAD-COUNT (`ratings.py` `_player_count`
/ `_players_with_rounds`) IS correct — opponents really played a full table
(tournament-rules A.2, same as DQ). So "include" vs "exclude" depends on whether
you're counting the proxy's OWN participation (exclude) or the table size others
faced (include). See [[dq-signal-divergence-traps]], [[standings-prelim-only-contract]].
