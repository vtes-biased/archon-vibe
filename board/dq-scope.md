Doc-impact: `wiki/tournaments.md` — the sanctions section gains the binding rule
(which levels require a tournament, which forbid one) and the profile-display
rule, loses the league-organizer clause from the Lift row, and its
`has_dq_sanction` warning around line 436 becomes a statement of the fixed
contract rather than a trap. `wiki/access.md` — the `lift_league_disqualification`
row goes with the capability. `wiki/hazards.md` — the "DQ signal is two signals"
entry must say the sanction half is scoped to the event, or the next consumer
repeats the bleed. The `pg_leagues` help text in all five catalogs — it currently
promises the league-wide block to users. Not `wiki/domain/judging.md` or
`wiki/domain/tournament-rules.md`: the domain already says a DQ removes the player
from *the event* and lists only VEKN suspension and VEKN/BCP prohibition as entry
bars — the code diverged from the rules, the rules did not change.
Not `wiki/public-api.md`: `/sanctions/` is not proxied there.

## The behaviour this reverses

Two independent mechanisms leak a DQ out of its event, and both must go.

**The league bar.** `_check_player_barred` (`backend/src/routes/tournaments.py:495`,
called from the Register and AddPlayer paths at 1351 and 1605) refuses a player
holding an active DQ from any tournament sharing the current event's
`league_uid`. Its suspension branch stays; only the disqualification branch goes.

**The global bleed.** `backend/src/routes/tournaments.py:1552-1564` appends every
active DQ a player holds, from any tournament, into the sanctions payload handed
to the engine for the current event — and drops `tournament_uid` when serialising.
`has_dq_sanction` (`engine/src/tournament/sanctions.rs:95`) matches on user and
level alone, so those foreign rows make the player DQ'd *here*: barred from
check-in, zeroed in standings, and denied a rating, in every tournament rather
than only a league sibling. The suspension rows in that same loop are legitimate
and stay. `wiki/tournaments.md` already warns that a list gathered for player
context zeroes a player for a DQ taken elsewhere; the backend does exactly that.

The frontend repeats it offline: `getTournamentContextSanctions`
(`frontend/src/lib/db.ts:568`) returns 18 months of cross-event sanctions for
player context, and whatever feeds that list into an engine call carries the same
foreign DQs. Audit its consumers — the fix is the same shape on both sides.

## Traps

- `tournament.player_disqualified` and its `err_tournament_player_disqualified`
  message are **shared**. `engine/src/error.rs:128` emits the code for the
  legitimate own-event check-in barrier, which stays. Only the backend league
  branch goes. The unused `error_league_dq` key in `frontend/messages/en.json` is
  an orphan and goes with it.
- A DQ must still zero standings, bar check-in and kill the rating **in its own
  event**. The regression to avoid is a fix that scopes the signal so tightly the
  event's own DQ stops landing.
- The DQ signal is two signals — `player.state == "Disqualified"` or an active
  sanction. Scoping the sanction half does not touch the state half.

## The binding invariant

Caution, Warning, Standings Adjustment and Disqualification require a
`tournament_uid`; Suspension and Probation must not carry one. Enforce on both
paths in `backend/src/routes/sanctions.py`: the create endpoint, which today
accepts a null tournament at any level, and the update endpoint, which today lets
a re-level move an unbound member-level sanction to `disqualification`. The
member-profile edit modal (`frontend/src/lib/components/SanctionsManager.svelte`,
level options around line 428) offers all six levels on a sanction that may have
no tournament — it must offer only what the sanction's binding permits. Its create
modal is already correct, offering probation and suspension alone.

The Discord bot always issues against a tournament-scoped OAuth actor
(`bot/src/archon_bot/archon_api.py:277`), so the guard cannot break it.

**Legacy rows.** `backend/scripts/migrate_from_archon.py:799` falls back to a
possibly-null tournament, so imported sanctions may already violate the invariant.
Report the count of unbound tournament-level rows; leave them as read-only history
rather than rewriting imported records. Once the bleed is closed they are inert.

## Retiring the league lift

`lift_league_disqualification` (`engine/src/permissions.rs:433`, widened in
`can_lift_sanction` around line 917) exists only because a DQ used to reach across
a league. Without that effect it leaves a league organizer holding a lift right
the tournament's own organizer lacks. Retire the capability and the widening; the
tournament-level chain — IC, Rulemonger, the NC of the tournament's country —
covers DQs. `_can_lift_sanction` in `backend/src/routes/sanctions.py` no longer
needs to fetch the league.

## Profile display

`SanctionsManager` renders level, description and date and never names the event.
An official reading a member's profile must see the tournament behind each
Warning, SA and DQ, as a link. The client already holds a tournament list
(`getTournamentListItems`), so the name resolves locally; decide what a row shows
when the tournament is not in the local store rather than rendering a dead link.
