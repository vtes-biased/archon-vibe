# Alter seating: let the submitted seating decide who is in the round

Doc-impact: `wiki/tournaments.md` (the `AlterSeating` and `SeatPlayer`/`UnseatPlayer`
rows of the events table, ~line 405). `wiki/architecture.md` and `wiki/testing.md`
checked and expected unchanged — reasons below.

## Where this came from

A player reported that after using **Check All In** they could not remove players.
The investigation found two things.

**Check All In defeats both round-1 no-show safety nets at once.** `StartRound`
only withdraws players still in `Registered` state (`engine/src/tournament/mod.rs`,
the `Some("Registered") if drop_no_shows` arm), and the pre-flight warning that
names who is about to be recorded as a no-show filters on the same state
(`ActionBar.svelte`, `prospectiveNoShows`). `CheckInAll` flips every registrant to
`Checked-in`, so absentees stop being warned about and get seated at real tables.

**Once the round is seated, the Players tab offers nothing.** The per-player "More"
drawer gates Drop Out on `state === "Waiting"` and Remove on `!hasRounds`
(`PlayersTab.svelte`), and seating *is* starting — `StartRound` sets state to
`Playing` immediately. In `Playing` both are false, so neither control renders, on
mobile card or desktop row. The remedies exist but only in the Rounds tab: the
unlabelled unseat icon per seat, and Cancel Round.

The owner's verdict on the remedy: the out-of-mode unseat/seat chips are fine and
stay — they are the quick path for the common case. **The missing piece is that
"Alter seating" mode cannot do everything you might want.** Being unable to finish
the job inside the mode is the frustrating part, in a moment that is already
stressful.

## Why alter seating cannot do it today

`AlterSeating` is locked to the round's existing player set by two guards in the
`TournamentEvent::AlterSeating` arm:

- a total-count check rejecting any payload whose seat count differs from the
  round's, as `PlayerCountMismatch`;
- a per-uid lookup into the round's existing seating, rejecting anything unknown as
  `PlayerNotInRound`.

So it is a pure rearrangement event by contract. The UI is honest about it:
`RoundsTab.svelte` carries a comment and a `rounds_alter_pool_hint` message telling
the organizer to leave the mode to add a player. Removing one is not even hinted
at.

## The design

**One event does the whole job.** The frontend submits the round's desired final
seating; the engine diffs that against the round's current seating and applies the
seat and unseat work itself. Atomic, one event, one sync record.

### Refusals: structural only

The engine refuses what is **incoherent**, and nothing else:

- a uid that is not a tournament player;
- duplicate uids across the payload (the existing `DuplicatePlayer` guard, which
  predates this and is untouched — it is what makes sitting twice impossible);
- table sizes outside 0/4/5;
- fewer tables than the round has (`TableCountMismatch` — tables are emptied, never
  dropped from the payload; empty ones are dropped on rebuild as today).

The count check and the not-in-this-round check both go.

**No player-state filter at all.** This was argued down in three steps and each
step matters:

1. *Rejected: reuse `SeatPlayer`'s `present_and_unseated` test
   (`Registered`/`Checked-in`).* It is already stricter than `StartRound`, whose
   online branch deliberately admits `Playing` players into a new round
   (`(is_online && s == Some("Playing"))`). Online events run rounds in parallel;
   a state filter would block legitimate seating there. The `PlayerWrongState`
   rejection is a defect for online play, not a protection worth carrying over.
2. *Rejected: bar disqualified players from being added.* We allow a DQ'd player to
   sit, to be rearranged and to be unseated, and we allow a seated player to be
   DQ'd. So "DQ'd player on a table" is reachable by another route — add them, then
   DQ them. A guard against a reachable state is theatre, and it forbids something
   an organizer may genuinely want (they removed a DQ'd player by mistake and want
   them back in their place). At most a warning.
3. *Rejected: bar players at their per-player round cap.* `SeatPlayer` has no such
   check, so adding one would make alter mode stricter than the chip it replaces —
   the exact frustration being fixed. The cap belongs where it is enforced today,
   at `CheckIn` and in `StartRound`'s selection. A refusal here fails the save at
   the worst possible moment. A frontend warning in alter mode is acceptable; an
   engine refusal is not.

The principle to keep: **the engine refuses the incoherent and warns on the merely
unusual.** It reads the same way as the existing "the app has no default and must
not decide" stance on seating a late arrival.

### Player state: one promotion rule, one demotion rule, nothing else touched

- **Promote** — a payload uid not previously seated in this round becomes
  `Playing`, **only if the round is live**.
- **Demote** — a previously-seated uid absent from the payload becomes
  `Registered`, **only if** their current state is `Playing` **and** they are not in
  `players_in_other_active_rounds` (`engine/src/tournament/helpers.rs`, already used
  by `FinishRound` and `CancelRound`).
- Touch nobody else.

Liveness means *any table not `Finished`/`Cancelled`* — what `isRoundLive` computes
in `RoundsTab.svelte`. Deliberately **not** `resolve_live_round`, which treats the
last round as live unconditionally.

The demotion clause's three conditions each pay for themselves:

- *Only when live* — correcting a finished round 1 to add a player who actually
  played but was never listed must not set them `Playing` while the tournament sits
  between rounds. There is no correct player state for a round that is over, so
  the answer is to not touch it. This replaced an earlier proposal to forbid player-
  set changes on non-live rounds entirely; that proposal was rejected because the
  correction case is real and legitimate.
- *Only in other active rounds* — in online parallel play, removing someone from
  round 2 while they are still seated in a live round 1 must leave them `Playing`.
- *Only from `Playing`* — a player who dropped out mid-round stays seated (drop
  never vacates a seat). Unseating them must leave them `Finished`, not silently
  reinstate them, because `Finished` players are dropped from finals eligibility in
  `standings.rs`.

### `UnseatPlayer` inherits the same fix

`UnseatPlayer` today sets the player unconditionally to `Registered` (with a
`Finished`-tournament mirror). That is wrong on all three counts above: it
reinstates a dropped-out player, it strands a parallel-round player, and its
tournament-state mirror becomes unnecessary once demotion only fires from `Playing`
(nobody is `Playing` in a `Finished` tournament). Same rule, same abstraction, two
lines — it is fixed inside this task rather than left as a known-wrong sibling next
to the corrected event. Scope grows in place.

### Frontend

- Alter mode gains an **unseat** control per seat and a **pool add** per table,
  both editing the draft (`alterTables`) rather than firing events — the save is
  still one `AlterSeating` call, so Cancel keeps meaning exactly one thing.
- `seatablePlayers` in `RoundsTab.svelte` filters to `Registered`/`Checked-in`
  today, so a player who is unlisted or `Finished` never appears — the engine change
  alone would not reach the correction case. With the refusal set now purely
  structural, the pool rule is simply *every tournament player not already seated in
  this round*. That is computable locally; an engine-side helper was offered and is
  not obviously worth it now that the rule is trivial, but it is an open
  implementation call.
- Any warnings (DQ'd player added, player over cap) are frontend-side, alongside
  the existing R1 and table-size notices. Warn, never block.
- `rounds_alter_pool_hint` and the cross-link comment above it die.
- The existing `rounds_alter_scores_warning` covers cross-table result resets; it
  needs to cover removing a player who has a score.
- The undersized-table guard (`hasUndersizedTable`) already blocks saving a table
  left at 1–3, so unseating down to three forces the organizer to empty the table
  or redistribute. That behaviour is correct and unchanged.

## Docs

- `wiki/tournaments.md` — the `AlterSeating` row of the events table rewrites: it is
  no longer a fixed-player-set rearrangement. **This is a recorded decision being
  changed deliberately, not violated as a side effect.** The finals branch keeps its
  fixed player set — that one is deliberate and untouched. The
  `SeatPlayer`/`UnseatPlayer` row is adjacent to the demotion fix and should be
  re-checked while there (it says "act on the **last** round", but both resolve an
  earlier live round too).
- `wiki/tournaments.md` line ~200's "every checked-in player exactly once" is
  `StartRound`'s validation, not `AlterSeating`'s. No conflict, no change.
- `wiki/architecture.md` push-trigger table — **checked, no change needed.**
  `build_reseat_specs` in `backend/src/push_service.py` diffs by (table, seat)
  position, so a player newly added by `AlterSeating` already has no old position
  and gets paged, and an unseated player already gets nothing. The documented rule
  survives the change verbatim.
- `wiki/testing.md` says the e2e seating test uses the click-based unseat/seat flow.
  The out-of-mode chips stay, so the test should be unaffected — confirm, don't
  assume.
- No domain page changes. The domain did not change and no source was misread.

## Tests that flip

`test_alter_seating_unknown_player_fails` and the count-mismatch assertions in
`engine/src/tournament/tests.rs` invert. Per the testing dogma, the new coverage
worth having is at the engine interface, one per invariant: the demotion rule's
three conditions (dropped-out stays `Finished`, parallel-round player stays
`Playing`, non-live round touches no state) are each a real regression risk and
none is observable from the frontend.

## Knowingly not covered

- **The Players tab still offers no drop or unseat while `Playing`.** That is the
  surface the original report was standing on. The owner's call is that the seating
  editor is where this belongs; if the gap is worth closing it is a separate ask.
- **Check All In still defeats the round-1 no-show warning and auto-drop.** Making
  the warning count checked-in-but-absent players, or warning at Check All In time,
  is a separate ask. Nothing in the data distinguishes absent from present at that
  moment, which is why it was not folded in here.
- **Wiki/code divergence on Drop Out confirmation.** `wiki/tournaments.md` states
  Drop Out carries no confirmation; the organizer path in `PlayersTab.svelte` shows
  a `ConfirmActionModal` while the self-service path in `PlayerView.svelte` does
  not. Blocks nothing; one of the two should move. Not part of this line.
