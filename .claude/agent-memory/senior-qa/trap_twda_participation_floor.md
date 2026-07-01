---
name: trap-twda-participation-floor
description: TWDA auto-submit has a seated-player floor (TWDA_MIN_PLAYERS); any test fixture on the TWDA path must seat >= that many DISTINCT players or _maybe_submit_twda silently no-ops.
metadata:
  type: project
---

`_maybe_submit_twda` (backend/src/routes/tournaments.py) gates on
`_played_player_count(tournament) >= TWDA_MIN_PLAYERS` — DISTINCT players seated
across `tournament.rounds[*][*].seating` + `tournament.finals.seating`
(participation, NOT the registered roster). The gate returns *before* any DB or
engine call.

**Why:** small sanctioned events are valid but their winner's deck isn't
TWDA-worthy; below the floor the deck must NOT be published to the public
third-party TWDA archive (wrong-data-to-third-party consequence class).

**How to apply:** `test_twda_submit.py`'s `_tournament` fixture historically
built a rounds-less, finals-less FINISHED tournament — that now trips the gate
and every credit test silently no-ops (`export_twda` called 0 times). Any TWDA
fixture must seat >= TWDA_MIN_PLAYERS distinct player_uids in valid 4-5 seat
tables (9 = [5,4], 10 = [5,5]). To assert the *negative* branch is
mutation-meaningful you must mock the downstream (`_winner_deck_twda` ->
truthy, `src.twda.submit_twda_pr`) so removing the gate would reach the submit.
Callers of the gate: finish-tournament route, `push_vekn` endpoint,
`archon_import` — all share this single floor. See [[project_archon_merge]].
