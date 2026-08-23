> Elaborated context for a line in `BOARD.md`. Deleted with the line.

# No-final tournaments and rating credit

**The deliverable is the question set below — send it to the Rules Director.**
Everything after it is the evidence backing the questions.

Interim stance, owner-approved: the engine stays rules-literal and credits
nothing. The shipped ranked/unranked badge makes the outcome read as a rule rather
than a bug.

## The questions

1. **Is the credit intended?** For a §3.1.6 no-final event, should the standings
   leader get the winner bonus (90·coef) and the +1 winner GW, and ranks 2–5 the
   finalist bonus (30·coef)? That is what vekn.net does today. Or is that an
   implementation accident, and the rules-literal zero bonus the intent?

2. **What about an event that lost its final to force majeure?** §3.1.6 only
   covers a *planned* no-final event under 8 players. Archon deliberately allows a
   no-final finish at **any** size, because a venue closing or an emergency
   termination (JG §5.3) has to be recordable. So: does a 20-player event that
   played two rounds and never reached its final count toward ratings at all — and
   if it does, does its standings leader receive winner credit? The three plausible
   answers are *credited like a §3.1.6 event*, *unranked entirely*, or *rated for
   participation and VP but with no winner or finalist bonus*.

3. **Finalist semantics** — in a no-final event, is "finalist" simply top-5 by
   final standings? Exactly `min(5, N)`? On a tie at 5th, is it resolved by toss
   like the finals cut, or are all tied players credited?

4. **Winner determination** — the standings leader under the normal GW > VP > TP
   order, receiving the same +1 GW a finals winner gets?

5. **Push encoding — this one gates the cutover.** When archondata is uploaded for
   a no-final event, does vekn.net recompute `rtp` from positions/GW/VP, or store
   the pushed per-player `rtp` verbatim? Riders for the same conversation: does a
   results re-upload **replace or append**, and is the Hall of Fame convention
   IRL-only wins? (Archon's HoF currently counts online wins.)

Q1 and Q2 decide the engine. Q5 decides whether this is a display-only difference
inside archon or a real reporting divergence into the system of record — resolve it
before the cutover regardless of the rules answer.

## What we do today

`FinishTournament` without a final sets state Finished and prelim standings, but
sets no `winner` and flags no `finalist` — only `StartFinals` and `FinishFinals`
do. Ratings then award the top players only `5 + 4·VP + 8·(prelim GW)`: no 90/30
bonus, no winner game-win.

Our **VEKN imports** of no-final events *do* get full credit, because the importer
sets winner and finalist from the upstream position. So a native no-final finish is
under-rated against the identical event imported from vekn.net.

The **archon-file importer** is a third answer again: with no finals table in the
file it stamps the top preliminary row as `winner` outright
(`archon_import.py`, the `if not winner_uid` fallback after the standings sort).
That winner then takes rank 1 and a Hall-of-Fame-eligible win —
a fact invented locally, where the VEKN importer at least carries one the upstream
record states and the engine deliberately states none. `wiki/tournaments.md` does
contemplate a no-final *import* carrying a winner, so this is not simply a bug to
delete: whichever way Q1 and Q2 are answered, the three paths have to end up saying
the same thing, and the archon importer is the one with no source to point at.

On that exact shape — a `winner` named with no row flagged a finalist — the
owner-approved interim answer is now implemented: `compute_final_standings` stamps
every `finalist_position` 0 and the +1 tournament-win GW is withheld, so the rating,
league scoring and the standings screen all decline both, and the winner still
places 1st. The reasoning is the league
one: an event run without a final is weighting participation over winners, so
crediting a winner there cuts against the format. **Q1 and Q2 still decide whether
that holds** — a ruling that no-final events rate like vekn.net's would reverse it,
and the archon importer's invented winner is the path that would then need a source.

## The evidence that vekn.net credits them

Decomposing the per-player `rtp` the VEKN event API returns, against
`floor(5 + 4·(vp+vpf) + 8·(gw + [1 if winner])) + round(bonus·coef)`:

- **vekn 11775** — 7 players, 3 rounds, no final. Winner gw1/vp3 → rtp 72 =
  `floor(5+12+8·2) + round(90·0.437)` = 33+39. Ranks 2–5 each +`round(30·0.437)`
  = +13. Exact.
- **vekn 10320** — 14 players, 2 rounds, no final. Winner → +1 GW +
  `round(90·0.949)` = 85; ranks 2–5 +`round(30·0.949)` = 28. Exact.

Finals events decompose identically with `vpf=0`, so vekn.net applies winner and
finalist credit to the top-5 **standings positions** without checking whether a
final was played.

## The rules tension

§A.2 gives "8 RtP per GW (*including final round victory*)" and §A.2.1 Winner 90 /
Finalist 30. "Finalist" is a top-5 player who *advances to the final*; "Winner" is
highest VP *in the final round*. Read literally, a no-final event has no final-round
victory and nobody who advanced ⇒ no credit, which is what we do. vekn.net's
implementation credits them anyway. Our ratings exist to mirror vekn.net as the
system of record, so matching the implementation is the pragmatic answer — but it
is a question of intended policy, and it also affects what we push.

## If we implement

`FinishTournament`-without-finals would designate the standings leader as `winner`,
flag the top `min(5, N)` as `finalist`, and add the winner's +1 GW in the rating
path. Three things to decide with it:

- **The Q2 gate.** Whatever answer comes back has to distinguish a deliberate
  §3.1.6 finish from a truncated event, or we credit half-finished tournaments.
  That may want its own action or flag rather than overloading `FinishTournament`.
- **Don't overload `finalist`.** Today it means "played the final table". Reuse it
  for rating and push derivation only, or introduce a distinct standings-finalist
  concept — do not change what UI surfaces read it as.
- **A credited no-final event with ≥8 players then IS ranked**, so the
  ranked/unranked badge has to be reconciled with the new rule.

If the answer is rules-literal instead, the engine stays as-is and the only
outstanding item is the asymmetry with imported history — either accept it, since
imports mirror the source of record, or ask VEKN to change vekn.net.

## Where to look

- `engine/src/tournament/mod.rs` — `FinishTournament`, and `StartFinals` /
  `FinishFinals`, which are the only writers of `finalist` and `winner`
- `engine/src/ratings.rs`, `backend/src/ratings.py` — `_finalist_position`,
  `compute_rating_vp_gw`
- `backend/src/vekn_tournament_sync.py` — the importer that credits no-final
  events from the upstream position
- Rules: `wiki/domain/tournament-rules.md` §3.1.6, and
  `wiki/domain/vekn.md` for A.2 / A.2.1
