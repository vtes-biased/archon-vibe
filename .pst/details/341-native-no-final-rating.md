# Native no-final tournament finish: no winner/finalist rating (diverges from vekn.net)

**Status: Rules-Director question set drafted (below); interim stance decided with owner
(2026-07): engine unchanged + ranked/unranked badge companion (#420).** Send the brief;
resolve Q5 (push encoding) before cutover regardless of the rules answer — it decides whether
this is display-only in archon or a real reporting divergence into the system of record.

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

## Rules-Director question set (drafted 2026-07, area-2 product pass)

1. **Intended behavior** — for a §3.1.6-compliant no-final event, should the standings leader
   receive the winner bonus (90·coef) and the +1 winner GW, and ranks 2–5 the finalist bonus
   (30·coef) — i.e. vekn.net's current behavior — or is that an implementation accident, with
   the rules-literal zero bonus being the intent?
2. **Eligibility gate** — if credited: every no-final finish, or only legitimate §3.1.6 events
   (<8 players, announced before round 1)? An 8+-player event finished without the required
   final: credited anyway, or treated as incomplete/unranked?
3. **Finalist semantics** — in a no-final event, is "finalist" simply top-5 by final standings?
   Exactly min(5, N)? A tie at the 5th position: resolved by toss (like the finals cut), or all
   tied players credited?
4. **Winner determination** — the standings leader under the normal GW > VP > TP order (toss on
   the cut tie), receiving the same +1 GW a finals winner gets?
5. **Push encoding — gates cutover.** When archondata is uploaded for a no-final event, does
   vekn.net recompute rtp from positions/GW/VP, or store the pushed per-player `rtp` verbatim
   (we push our own computed rtp)? Riders for the same conversation: does a results re-upload
   REPLACE or APPEND (needed by the reopen→refinish repair path, see the area-2 reopen ticket),
   and is the Hall of Fame convention IRL-only wins (archon's HoF currently counts online wins)?

## Interim stance (decided with owner, 2026-07)

Engine unchanged — native no-final finishes stay uncredited. Rationale: rules-literal, quiet,
recoverable; over-crediting then reversing would churn ratings/HoF and mis-report to vekn.net.
Companion: derived ranked/unranked badge (#420) so the missing bonus reads as a rule, not a bug.

## Per-branch plan (once answered)

- **A — credit like vekn.net** (matches system of record): `FinishTournament`-without-finals
  derives winner (standings leader) + top `min(5, N)` finalists behind the Q2 eligibility gate,
  reusing the #387 winner-derivation fix; add the winner +1 GW in the rating path; do NOT
  overload the "played the final table" meaning of the finalist flag on UI surfaces — restrict
  to rating/push derivation or introduce a distinct standings-finalist concept; encode the push
  per Q5. A credited no-final event with ≥8 players then IS ranked — reconcile the #420 badge.
- **B — rules-literal (zero bonus intended)**: engine stays as-is. Flag the asymmetry with
  imported history (importer credits from `pos`): either accept it (imports mirror the source
  of record) or ask VEKN to fix vekn.net's implementation. #420 badge explains the outcome.
- **C — hybrid (credit only <8)**: branch A behind a `player_count < 8` gate; an 8+ no-final
  finish stays uncredited and gets an "incomplete — final required" treatment in the badge.

## References

- `engine/src/tournament/mod.rs:2107` (FinishTournament), `:1936` (StartFinals sets finalist),
  `:2009` (FinishFinals sets winner)
- `engine/src/ratings.rs` (compute_rating_points), `backend/src/ratings.py:106`
  (_finalist_position), `:123` (_compute_entry_sync → compute_rating_vp_gw)
- `backend/src/vekn_tournament_sync.py:202-234` (importer credits no-final from `pos`)
- VEKN rules §3.1.6, §A.2, §A.2.1 (vtes skill `references/tournament-rules.md`)
- Verification scripts (throwaway): scratchpad `vekn_scan.py` / `vekn_10842.py`
