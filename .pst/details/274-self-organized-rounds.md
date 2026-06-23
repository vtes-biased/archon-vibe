# #274 — Self-organized rounds (open-rounds tournaments)

## DECISIONS LOCKED (2026-06-23) — supersede the "bot-first" PM notes below

Owner reframed the feature; this section governs. Children: #291–#294.

- **App-first, not bot-first** (reverses the original PM decision). No Discord bot work in
  MVP — the web app already has the optimistic-action pipeline + player-selection UI, and every
  online-league player runs their own PWA. The bot's net-new multi-player flow isn't worth it.
- **Trust-based — no consent machinery.** No opt-in, no all-seat confirmation, no pending
  proposal. The integrity gate is **registration**: you can only seat players already registered;
  you can't register anyone unless you're an organizer. Collusion / phantom-round risk is
  accepted (non-VEKN house format); safety net = social pressure + organizer veto.
- **Config flag `self_organized_rounds`** (bool, default false), settable only when
  `max_rounds > 0` (open rounds). Organizer turns it on.
- **New player-authorized engine event `SelfOrganizeRound { player_uids }`** (NOT
  `require_organizer`). Eligible iff: flag on + `max_rounds>0` + `online`; state Waiting/Playing,
  `finals` null; 4–5 distinct uids; **initiator among them**; each a participant in state
  `Registered`/`Checked-in` — **reject `Playing` (concurrent-pod guard), at-cap/`Completed`,
  `Disqualified`**. Engine computes single-table subset seating (`compute_next_round`, R1
  best-effort); marks only seated players `Playing` (leaves other `Registered` untouched, unlike
  `StartRound`); stamps `organized_by: <initiator>` on the table for audit.
- **Round lifecycle: organizer finishes (batch).** Players start/play/score pods autonomously;
  the organizer runs `FinishRound` (any round, out of order — already supported) to release
  players. No auto-finish in MVP.
- **Organizer veto / cancel any round.** `CancelRound` generalized to soft-cancel any *non-last*
  round (mark its table(s) `Cancelled`, keep the slot — mid-array removal corrupts index-tagged
  `deck.round` / `standings_adjustment.round_number`); last round still hard-removes. Also fixes
  organizer-started parallel rounds. `Override` remains the per-table result void.
- **Never for finals** (organizer-only); **never VEKN-pushed**.
- principal-engineer APPROVE-WITH-CHANGES (trust boundary sound; cap/finals/standings/subset
  seating/member-projection/offline-lock verified unchanged; mid-array removal confirmed unsafe).

## Implemented (2026-06-23) — children #291–#294 done

- **Engine**: `self_organized_rounds` flag + `SelfOrganizeRound` event + `CancelRound` soft-cancel
  (new `TableState::Cancelled`, excluded from cap/standings/rating/active-round in 6 sites).
  2 regression tests (eligibility predicate; soft-cancel preserves slot + drops cap/standings).
- **Backend**: `player_uids` passthrough + timer hook. **Trap**: the action route strict-converts
  the engine JSON (`msgspec.convert(t_data, Tournament)`), so `models.py` REQUIRED
  `TableState.CANCELLED` + `Table.organized_by` + `TournamentConfig.self_organized_rounds` —
  without them soft-cancel 500s and the flag/provenance silently drop. 1 backend contract test
  guards this engine↔model serialization drift (`test_engine_model_contract.py`).
- **Frontend**: config checkbox, player self-organize dialog + picker, RoundsTab voided-round +
  `organized_by` badge, organizer cancel-any-round; types/engine.ts/error-codes; i18n ×5.
- **No `DATA_SCHEMA_VERSION` bump** — all changes additive (new optional fields + new enum value
  on an already-shipped field); member projection is a passthrough so no `access_levels.py` change.
- **Known follow-up**: `rounds_cancel_msg` ("results permanently lost") reads wrong for a
  *soft-cancelled* non-last round (record retained/voided, not deleted) — tracked as a p3.
- Verified green: engine 178 + clippy, backend 242 + ruff, frontend svelte-check + `just lint-check`.

---

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
