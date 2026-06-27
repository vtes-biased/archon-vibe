# Native no-final tournament finish: no winner/finalist rating (diverges from vekn.net)

**Status: needs rules-director discussion before implementing.** The right behavior is a
product/rules call, not just an engineering one (see "Rules tension").

## Current behavior

A tournament can be finished without ever running a final: `FinishTournament`
(`engine/src/tournament/mod.rs:2107`) requires only Waiting/Playing/Finished, sets state
Finished, marks all non-DQ players Finished, and calls `update_standings`. It does **not** set
`tournament["winner"]` and does **not** flag any `finalist` — those are set only by
`StartFinals` (finalist flags) / `FinishFinals` (winner). So a native no-final finish yields:

- prelim standings (GW/VP/TP), correctly sorted ✓
- `winner == ""`, `finalist == false` for everyone ✗

Ratings then award nothing special: `_finalist_position` (`backend/src/ratings.py:106`) returns
0 for all (no winner match, no finals, no `standings.finalist`), and `compute_rating_vp_gw`
sums prelim rounds only (no finals → no winner GW). Net: top players get only
`5 + 4·VP + 8·(prelim GW)` — no 90/30 finalist bonus, no winner game-win.

## Why that's a divergence

VEKN.net **does** credit no-final events. Verified by decomposing the per-player `rtp` the VEKN
event API returns, against `floor(5 + 4·(vp+vpf) + 8·(gw + [1 if winner])) + round(bonus·coef)`
(`engine/src/ratings.rs`), bonus = 90 winner / 30 ranks 2-5, coef = log15(pc²)−1+rank_bonus:

- **id=11775** (7p Standard, `rounds="3R"`, no final): winner gw1/vp3 → rtp 72 =
  floor(5+12+8·**2**)+round(90·0.437)=33+39. ranks 2-5 each → +round(30·0.437)=+13. Exact.
- **id=10320** (14p Standard, `rounds="2R"`): winner → +1 GW + round(90·0.949)=85; ranks 2-5 →
  +round(30·0.949)=28. Exact.
- Finals events decompose identically with `vpf=0` for no-final ones — i.e. vekn.net's rating
  engine applies winner/finalist credit to the top-5 *standings positions* without checking
  whether a final was actually played.

So our **VEKN imports** of no-final events get the full credit (importer sets winner + finalist
from `pos`, `vekn_tournament_sync.py:202-234`), but a **native** no-final finish does not.
A TO running a legit <8-player event in archon and finishing without a final is under-rated
versus the identical event on vekn.net (and versus our own imports).

## Rules tension (why the rules director must weigh in)

VEKN Tournament Rules:
- §3.1.6 "Tournament Without Final": for **<8 players** the organizer may omit the final
  (announce before round 1); **prelim results determine standings**. So a no-final winner/order
  is well-defined.
- §A.2: "8 RtP per GW (*including final round victory*)"; §A.2.1 Winner 90 / Finalist 30, coef
  = log15(N²)−1 (NC +0.25, CC +1.0). "Finalist" is defined (§3.1) as a top-5 player who
  *advances to the final*; "Winner" (line 136) is *highest VP in the final round*.

Read literally, a no-final event has no "final round victory" and nobody who "advanced to a
final" ⇒ **no winner GW, no finalist bonus** — which is exactly what archon native does today.
But vekn.net's **implementation** credits them anyway. The two disagree. Our ratings exist to
mirror vekn.net (the system of record), so matching the implementation is the pragmatic answer
— but this should be confirmed with the rules director, because it's a question of intended
VEKN policy, and the answer also affects VEKN push (we'd be pushing native no-final results).

## If we implement (open design questions for the discussion)

To make native match vekn.net, `FinishTournament`-without-finals would designate the standings
leader as `winner`, flag the top `min(5, N)` as `finalist`, and award the winner the
tournament-win GW. Decisions needed:

- **Eligibility gate**: only ≤7 players (§3.1.6), or whenever an organizer explicitly chooses
  "finish without final"? An 8+-player finish-without-final is abnormal (final required) and
  probably should NOT auto-award finalist bonuses.
- **Deliberate vs abandon**: distinguish a §3.1.6 no-final finish from early termination, so we
  don't credit a half-finished event. Possibly a dedicated action/flag rather than overloading
  the generic `FinishTournament`.
- **`finalist` flag semantics**: today it means "played the final table"; reusing it for
  "top-5 of a no-final event" overloads it (though it is what VEKN's rating does).
- **Winner GW reconstruction**: the +1 tournament-win GW isn't naturally in prelim standings;
  `compute_rating_vp_gw` / standings would need to add it for the no-final winner.
- **VEKN push**: `generate_archondata` must encode winner/finalist + winner GW the way vekn.net
  expects for a no-final event.

## References

- `engine/src/tournament/mod.rs:2107` (FinishTournament), `:1936` (StartFinals sets finalist),
  `:2009` (FinishFinals sets winner)
- `engine/src/ratings.rs` (compute_rating_points), `backend/src/ratings.py:106`
  (_finalist_position), `:123` (_compute_entry_sync → compute_rating_vp_gw)
- `backend/src/vekn_tournament_sync.py:202-234` (importer credits no-final from `pos`)
- VEKN rules §3.1.6, §A.2, §A.2.1 (vtes skill `references/tournament-rules.md`)
- Verification scripts (throwaway): scratchpad `vekn_scan.py` / `vekn_10842.py`
