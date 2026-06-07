# 43 — Shared final-placement standings (engine) + reuse everywhere

## Problem
"Final placement" (winner first, then finalists, then non-finalists) is
reconstructed ad-hoc in **4 places**, with subtle divergences:
1. `engine/src/league.rs` GP branch — keyed off prelim array index (the bug).
2. `engine/src/league.rs` RTP branch — `finalist_position` from `winner`.
3. `frontend/.../tournaments/[uid]/+page.svelte` `computeStandings()` — TWO paths
   (VEKN-synced + rounds/finals), each ordering non-winner finalists by **prelim**.
4. `frontend/.../OverviewTab.svelte` getRatingPts — winner/finalist from `winner`.

## VEKN spec (confirmed by product-manager against reference/tournament-rules.md
§3.1 / §3.7.5 and judges-guide-v2 §1.1.4)
- **Rank 1**: finals winner = highest finals VP, tiebroken by prelim ranking.
- **Rank 2 (SHARED)**: every other finalist — they *tie for 2nd with no tiebreak*
  (§3.7.5, verbatim). NOT finals VP, NOT prelim. Array order is a cosmetic
  terminal key (user_uid) only; it must never change the rank number.
- **Non-finalists**: standard competition ranking (shared rank + skip, "1,2,2,2,2,6,7…")
  on prelim GW→VP→TP. First non-finalist rank = `finalist_count + 1` (normally 6;
  never hardcode 6 — a sub-5 final shifts it).
- **No finals** (sub-8 events, §3.1.4): plain prelim ranking; winner = prelim 1st;
  2nd–5th are genuinely distinct (the tie-for-2nd collapse is finals-only).
- **VEKN-imported**: trust imported positions 1..N; winner = position 1; do NOT
  collapse 2–5.
- **DQ** (§1.1.4): disqualified player removed from standings entirely, others
  shift up; if the winner is DQ'd, recompute winner among survivors. → separate
  follow-up; not in the core ranking helper's input shape yet.
- **UX**: reorder results to final placement after finals; render 2nd–5th as a
  flat "Finalist" band (a crown on the winner), NOT distinct 2/3/4/5 medals.

## Design (Option B — no denormalization)
Pure engine fn `compute_final_standings(standings, winner) -> reordered standings
with `rank`` added. Signal for "a final was played" = presence of `finalist`
flags (FinishFinals sets them on the top 5). Imports/no-finals have no flags →
degrade to prelim competition ranking with winner forced to rank 1.
- Expose at the lib boundary (WASM + PyO3) as `compute_final_standings(config_json)`.
- league.rs GP + RTP consume the rank (GP points unchanged vs the landed fix).
- frontend `computeStandings()` + OverviewTab consume it via WASM (#63).

## "Did a final happen?" — the signal is the `finalist` flag, NOT finals data
Checked all writers: engine StartFinals, archon_import, and vekn_sync ALL set
`finalist` flags when a final exists. But **vekn_sync stores no `finals` table at
all** (the VEKN API gives positions, not seat results). So the `finalist` flag is
the only portable signal — keying off finals-data presence would make every
VEKN-imported tournament look final-less. "Flagless finals" does not occur in
real data (the old test that implied it had incomplete data; now fixed).
Round count is irrelevant: a many-round prelim with no final has zero finalist
flags → plain preliminary ranking.

## Status
- [x] GP points fix landed (winner→rank 1) + regression test.
- [x] Extracted `compute_final_standings` engine fn (tournament/standings.rs) + 4
      unit tests + lib boundary (WASM `computeFinalStandings` / PyO3).
- [x] league.rs GP + RTP reuse it (GP points unchanged; RTP behavior-preserving).
- [x] Renamed `compute_standings` → `compute_preliminary_standings` for symmetry.
- [x] principal-engineer review: ship it (doc-comment invariant + RTP flag-gating
      noted; flagless-finals "footgun" was a phantom from bad test data).
- [ ] #63 frontend display reuses it (flat finalist band, winner on top).
- [ ] follow-up: DQ excision from final standings.
