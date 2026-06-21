# #274 — Self-organized rounds (open-rounds tournaments)

Exploratory P3, owner-proposed 2026-06-21. Let *present* players in an **open-rounds**
tournament (`max_rounds > 0`, the non-VEKN house format) organize and play a round among
themselves without an official pressing StartRound/FinishRound. Goal: make multi-week /
casual league-style open events feasible without an organizer at every play session.

**Why it's safe to experiment here:** open rounds are deliberately non-VEKN ("Not pushed to
VEKN", TOURNAMENTS.md §Open Rounds), so this sits outside VEKN compliance. Recently shipped
per-player open rounds + finalist withdrawal + CancelFinals show active investment in the
long-running-event story; the remaining bottleneck is organizer presence.

## PM decisions to hold if this advances
- **Bot-first, not app-first.** The Discord bot already exposes per-user OAuth mutations
  (`/register`, `/checkin`, `/report`, `/judge` via `tournament_action`) and miru confirm-flows
  — async multi-player pod coordination is Discord-native. The co-located, organizer-driven app
  is a poor fit for *initiating* a round. Split roles: bot = player initiate/confirm/score;
  app = organizer oversight (CancelRound/Override already are the veto). Never build the same
  thing in both. (bot: `bot/src/archon_bot/commands/player.py`.)
- **Online-only by design.** Fights the offline device-lock model otherwise; don't attempt an
  offline path.
- **Seating rule (MVP): a self-organized pod is exactly 4 or 5 players (one table).** This
  sidesteps the 6/7/11 awkward-count machinery entirely — 6/7/11 are only un-seatable as
  *multi-table single-round totals*; the stagger logic that handles them is tournament-level,
  not pod-level. (Legal table = 4–5; every total ≥4 partitions into 4s/5s except 6/7/11 —
  `engine/src/seating/mod.rs:122`, `engine/src/seating/stagger.rs:19`, precomputed 4–25 excl 6/7/11.)
- **Integrity is the hard part, not the engine.** Plumbing is ~80% there: StartRound accepts a
  validated *submitted* seating; SetScore lets table players submit VPs with oust-order
  validation that rejects impossible combos for non-organizers. The unsolvable-by-design risk is
  **collusion / pod self-selection** — accept it (non-VEKN). Mitigate, don't pretend to
  eliminate: engine-assigned seating only (players pick *who*, engine picks *where*, enforce R1
  pred-prey vs prior rounds), all-participant opt-in before the round materializes, all-seat
  score confirmation, mandatory audit provenance (initiator + confirmations), organizer veto.
- **Never for finals** (organizer-only) and **never VEKN-pushed**.

## Open question for principal-engineer (decide before building)
StartRound is `require_organizer`-gated (`engine/src/tournament/mod.rs:641`). Either relax that
for this path, or give the bot a delegated identity. Touches the actor-context trust boundary.

P3 is correct (niche, non-blocking) but *well-formed* (real demand, clear MVP, low compliance
risk); graduates to P2 if multi-week leagues become a strategic push.
