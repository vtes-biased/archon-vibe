---
name: vekn-gp-league-points
description: GP league points are an app house rule (not VEKN); ties use best-position+skip (not averaging); per-tournament position should be FINAL placement, not prelim order
metadata:
  type: project
---

The GP "Grand Prix points" table (Winner=25, positions 2–5=15, 6th=10, 7th=9, 8th=8, 9th=7, 10th=6, 11th+=3) is an **app-specific league house rule**, NOT a VEKN construct. VEKN's only per-tournament numeric award is RtP (Appendix A: 5 attend + 4/VP + 8/GW + finalist bonus × coefficient), computed by VP/GW/finalist-bonus, never by integer placement index.

**Tie handling for GP:** best-position points + skip (standard competition ranking). Two tied for 6th each get 10; 7th skipped; next is 8th (gets 8). Do NOT average/split. VEKN's "average tied ranks" rule (§3.7.3) is scoped to intra-table Tournament Points only, not cross-tournament placement points.

**Latent bug (file separate from #13):** GP keys off the player's array index in `tournament["standings"]`, but that array is **prelim-only** (finals excluded). Correct per-tournament GP "position" must be FINAL placement: finals Winner → 1 (§3.7.5 "Winner = highest VP in final round only"), other 4 finalists → tie for 2nd, non-finalists from prelim → 6+. Real-world score impact is narrow because positions 2–5 all = 15 (flat band): only the **winner** (25 vs 15) is actually mis-scored when not prelim-1st. RTP mode already handles finalists separately (winner_uid check + bonus), so this latent bug is **GP-mode-specific** — don't "fix" RTP.

**Final-placement spec (shared engine, drives GP + post-finals display):**
- 1st = finals winner = highest VP in **final round only**; winner tie broken by **preliminary ranking** (§3.7.5), NOT finals seat order.
- 2nd–5th = other finalists, who **all tie for 2nd with no tiebreak whatsoever** (§3.7.5 verbatim: "no additional criteria considered"). Emit shared rank 2 for all; the GP "positions 2–5 = 15 flat band" is VEKN-faithful precisely because of this — no change needed.
- 6th+ = non-finalists by prelim GW/VP/TP (shared rank + skip). First non-finalist number is **dynamic** = ranks consumed by finalists (= 6 for a standard 5-seat final with the 4-way tie-for-2nd; = finalist_count+1 if final had fewer seats). Never hardcode 6.
- DQ'd finalist/player: **removed from standings entirely**, everyone below shifts up (judges-guide-v2 §1.1.4 line 140). Not last, not 0-VP placement — excise from the array before ranking.
- No-final tournaments (§3.1.4): final placement = prelim standing verbatim, winner = prelim 1st; tie-for-2nd collapse does NOT apply (finals-only rule).
- VEKN-imported tournaments: trust imported position 1..N as authoritative placement; winner = pos 1; do NOT re-derive or collapse to tie-for-2nd (server-of-record wins). Collapse only app-run finals.

**Why:** engine determinism/correctness work, epic #1. Owner already decided the share+skip model; VEKN supplies the ranking convention, not the point values.

**How to apply:** `compute_gp_points` must consume the shared rank (so ties get equal points), and a separate ticket must make GP position reflect final placement. See [[vekn-standings-toss-scope]].
