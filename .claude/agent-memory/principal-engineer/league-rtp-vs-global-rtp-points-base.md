---
name: league-rtp-vs-global-rtp-points-base
description: league.rs RTP points use prelim-only standings vp/gw (finals NOT in the points base); the global rating uses total vp/gw — the two RTP consumers diverge
metadata:
  type: project
---

`engine/src/league.rs` RTP mode computes per-tournament points at `compute_rating_points(vp, gw, finalist_position, ...)` where `vp`/`gw` are read straight from the **prelim-only** standings row (league.rs ~line 113). Finals VP/GW are added to the *displayed* `entry.gw/vp/tp` only, AFTER the points call (league.rs ~line 137-146) — they never enter the `4·vp + 8·gw` points base. The finalist *placement* bonus IS included (via `finalist_position`), but per-seat finals VP and the winner's finals GW are not.

The **global** rating (`backend/src/ratings.py` → `engine.compute_rating_vp_gw`) uses **total** vp/gw (prelim + finals + win_gw) in the same `compute_rating_points`. So the same tournament contributes a DIFFERENT RTP to a player's global rating than to a league RTP leaderboard. VEKN's authoritative RTP formula uses `vp+vpf` and `gw+[winner]` (total) — so the global path matches VEKN, league RTP undercounts finals.

**Why:** surfaced reviewing #340 (VEKN import prelim-only standings). Pre-#340, legacy imports had *folded* standings (prelim+finals), so league RTP accidentally matched VEKN for imports. #340 makes import standings prelim-only ⇒ league RTP points for imported finalists DROP to match native (native standings were always prelim-only). Consistent across origins now, but league RTP still diverges from global/VEKN RTP for everyone.

**How to apply:** when reviewing any standings/finals/RTP change, treat league.rs RTP and ratings.py as TWO RTP consumers with different vp/gw inputs (cf. [[sa-round-targeting-two-consumers]]). If a ticket claims league "RTP totals unchanged", verify the *points* field, not just displayed gw/vp. Whether league.rs:113 should pass total vp/gw (to match global) is an open latent-bug question — out of #340 scope. See [[standings-prelim-only-contract]], [[rounds-standings-coupling-engine]].
