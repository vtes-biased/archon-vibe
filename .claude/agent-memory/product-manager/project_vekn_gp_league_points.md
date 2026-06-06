---
name: vekn-gp-league-points
description: GP league points are an app house rule (not VEKN); ties use best-position+skip (not averaging); per-tournament position should be FINAL placement, not prelim order
metadata:
  type: project
---

The GP "Grand Prix points" table (Winner=25, positions 2–5=15, 6th=10, 7th=9, 8th=8, 9th=7, 10th=6, 11th+=3) is an **app-specific league house rule**, NOT a VEKN construct. VEKN's only per-tournament numeric award is RtP (Appendix A: 5 attend + 4/VP + 8/GW + finalist bonus × coefficient), computed by VP/GW/finalist-bonus, never by integer placement index.

**Tie handling for GP:** best-position points + skip (standard competition ranking). Two tied for 6th each get 10; 7th skipped; next is 8th (gets 8). Do NOT average/split. VEKN's "average tied ranks" rule (§3.7.3) is scoped to intra-table Tournament Points only, not cross-tournament placement points.

**Latent bug (file separate from #13):** GP keys off the player's array index in `tournament["standings"]`, but that array is **prelim-only** (finals excluded). Correct per-tournament GP "position" must be FINAL placement: finals Winner → 1 (§3.7.5 "Winner = highest VP in final round only"), other 4 finalists → tie for 2nd, non-finalists from prelim → 6+. Real-world score impact is narrow because positions 2–5 all = 15 (flat band): only the **winner** (25 vs 15) is actually mis-scored when not prelim-1st. RTP mode already handles finalists separately (winner_uid check + bonus), so this latent bug is **GP-mode-specific** — don't "fix" RTP.

**Why:** engine determinism/correctness work, epic #1. Owner already decided the share+skip model; VEKN supplies the ranking convention, not the point values.

**How to apply:** `compute_gp_points` must consume the shared rank (so ties get equal points), and a separate ticket must make GP position reflect final placement. See [[vekn-standings-toss-scope]].
