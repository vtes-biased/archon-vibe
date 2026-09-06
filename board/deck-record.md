Doc-impact: `wiki/product.md` — the post-tournament upload sentence ("add but not
replace") becomes owner corrections. `wiki/tournaments.md` — the Finished row of the
state machine, "Stamped is locked", "Only an organizer names a round", the unpublish
paragraph, the event catalog entries for Unregister/RemovePlayer, the Multideck row
of the configuration table, the player-states paragraph on `missing_decklist`, and
"Who may do what". `wiki/vekn.md` — the five enumerated TWDA triggers become the one
post-finish pass, and the commit message. `wiki/hazards.md` — the
"rating-irrelevant is not Hall-of-Fame-irrelevant" trap dissolves into the pass.
Not `wiki/architecture.md`: the DeckObject fields are unchanged. Not
`wiki/public-api.md`: the state table regenerates from the apply arms.

Owner decisions, September 2026: post-finish corrections by the owner are allowed
because the archive now follows the record; the record itself is corrected by one
pass rather than by enumerated triggers.

## What ships, and where each piece stands today

**Live decks only.** `get_decks_for_tournament` (`backend/src/db.py:303`) has no
`deleted_at` filter and backs `_build_decks_json` (`routes/tournaments.py:134`), so
the engine counts tombstones toward its locks, and the upsert in
`_process_deck_ops` (`:186-221`) matches `(user_uid, round)` against a tombstoned row
and saves through `save_object_from_model`, which carries `deleted_at` along: a
delete-then-re-upload during registration lands in the tombstone and vanishes once
SSE delivers it. `_winner_deck_twda` (`:354`) reads the same list. The client
already filters (`frontend/src/lib/db.ts:944-950`), so offline and online disagree.
The tournament soft-delete cascade (`db.py:1046-1058`) relies on the unfiltered read
to tombstone every deck — give it its own read or filter after.

**A finish without a final crowns first place.** `FinishTournament`
(`engine/src/tournament/mod.rs:2440`) never writes `winner`; the only writers are
`FinishFinals`, `CancelFinals`, `SetArchivalResults` and the finals re-score in
`standings.rs:255`, which re-derives only an already-set winner. §3.1.6 events are
ranked by §3.1, so first place is the winner. Under the default Winner mode such an
event publishes nothing today. These events sit under the TWDA and Hall of Fame
floors, so nothing else moves.

**Multideck freezes once a round exists.** `UpdateConfig` (`mod.rs:2688`) checks only
rank legality; flipping `multideck` re-keys every read (`routes/tournaments.py:926`,
`PlayersTab.getMultideckSlots`) and strands stamped decks. The Storyline analogue is
an accepted edge in `wiki/tournaments.md`; this one gets a guard.

**Departures release decks.** `Unregister` (`mod.rs:528`), `RemovePlayer` (`:618`) and
`DropOut` (`:637`) touch `players` only. An orphan under the All mode publishes at
finish (`compute_deck_public` returns true unconditionally there). Unregister and
RemovePlayer emit delete ops for the player's decks; DropOut keeps them, they were
played.

**The missing-decklist stamp follows the decks.** Set at `AddPlayer` with
auto-check-in (`mod.rs:604`) and at `CheckIn` (`:767`), cleared only by `CheckIn`
(`:795`) and the Storyline switch (`:2753`). `UpsertDeck` clears it; `DeleteDeck`
restores it when decklists are required, the player is checked in and no live deck
remains. The engine holds the deck list, so it can tell.

**Both deck events carry the same guards.** `DeleteDeck` (`mod.rs:2523`) lacks the
Storyline and registration checks `UpsertDeck` (`:2475`) has.

**Owner corrections after Finished.** Today `UpsertDeck` refuses a non-organizer
holding any deck once Finished (`DeckLockedFinished`, `:2501`) and nulls any round a
non-organizer names (`:2510`), and `DeleteDeck` refuses a stamped multideck deck in
any state (`:2532`). The lock keeps its reason during play: one editable deck at a
time, stamped is locked. Once Finished the owner may add, replace or correct any of
their own decks and may name the round. The UI mirrors: `singleDeckEditable` and
`canModifyPending` in `PlayerDecksSection.svelte:93-103`, and `DeckDisplay.saveDeck`
(`:136-147`) never sends `round`, which is what would let an in-place edit of a
stamped deck land on the pending slot — it must carry the round. The stale comment
at `routes/tournaments.py:1706` claiming players are deck-locked post-finish dies.

**One post-finish pass.** Publication is recomputed in the engine by `FinishFinals`
(`mod.rs:2364`), `FinishTournament` (`:2456`), `ReopenTournament` (`:462`) and a
`decklists_mode` edit (`:2757`), the first two pushing `true` only. A post-finish
finals re-score that moves the winner (`standings.rs:262`) emits no deck op, and
`SetArchivalResults` (`:2739`) replaces the winner with none either. Replace the
four call sites with one `recompute_deck_publication` run after every event applied
to a Finished tournament, pushing `true` and `false`; `compute_deck_public` leaves
`raffle.rs`. Server-side, the same trigger — any action on a Finished tournament —
recomputes wins and resubmits the TWDA when the winner or the winner's deck
changed, replacing the branch at `routes/tournaments.py:1708-1716` and the manual
`recompute_wins` beneath it. `_RATING_IRRELEVANT_ACTIONS` stays for ratings.

**TWDA follows.** `submit_twda_pr` (`backend/src/twda.py:45`) already commits onto
the fork branch, pushes into an open PR and opens a new one otherwise, including
after a merge. It says "Add TWD" on an update (`:165`, `:203`); say "Update" when the
file existed. Check which deck `_winner_deck_twda` picks in a multideck event: it
takes the first deck of the winner, and the finals deck is the one stamped at
`len(rounds)`.
