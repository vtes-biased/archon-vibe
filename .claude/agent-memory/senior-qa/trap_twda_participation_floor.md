---
name: trap-twda-participation-floor
description: TWDA auto-submit has a seated-player floor (TWDA_MIN_PLAYERS); any test fixture on the TWDA path must seat >= that many DISTINCT players or _maybe_submit_twda silently no-ops.
metadata:
  type: project
---

`_maybe_submit_twda` (backend/src/routes/tournaments.py) gates on
`_played_player_count(tournament) >= TWDA_MIN_PLAYERS` — DISTINCT players seated
across `tournament.rounds[*][*].seating` + `tournament.finals.seating`
(participation, NOT the registered roster).

**Why:** small sanctioned events are valid but their winner's deck isn't
TWDA-worthy; below the floor the deck must NOT be published to the public
third-party TWDA archive (wrong-data-to-third-party consequence class).

**How to apply:** `test_twda_submit.py`'s `_tournament` fixture historically
built a rounds-less, finals-less FINISHED tournament — that trips the gate and
every credit test silently no-ops (`export_twda` called 0 times). Any TWDA
fixture must seat >= TWDA_MIN_PLAYERS distinct player_uids in valid 4-5 seat
tables (9 = [5,4], 10 = [5,5]).
Callers of the gate: finish-tournament route, `push_vekn` endpoint,
`archon_import` — all share this single floor. See [[project_archon_merge]].

**Refactor (2026-07, twda_status feature):** `_maybe_submit_twda` no longer
early-returns per skip reason — it now computes an `outcome` tuple
(`TwdaOutcome`, reason_code, pr_url) through an if/elif chain and always calls
`_record_twda_status(uid, *outcome)` at the end (locked fetch-modify-save that
writes `Tournament.twda_status`, broadcast over SSE, organizer-only projection).
Three test-infra consequences for anything on this path:
  1. Patch `src.twda.is_configured` (-> `True`) AND `src.twda.submit_twda_pr` —
     NOT `src.routes.tournaments.*`. `_maybe_submit_twda` does a *local*
     `from ..twda import is_configured, submit_twda_pr` at call time, so the
     effective patch target is the `src.twda` module attribute.
  2. Patch `src.routes.tournaments._record_twda_status` with an `AsyncMock` in
     any DB-less test — it is a REAL locked DB write (tournament_transaction +
     save_tournament + broadcast). Its unchanged-outcome short-circuit and the
     rebuild-preservation in `sync_all_tournaments` (whitelisted field copy
     alongside `checkin_code`) are both untested by design: consequence is a
     transparency-display reset, and `sync_all_tournaments` needs a real DB +
     mocked VEKN client (the pure `_map_vekn_to_tournament` test can't reach it).
  3. Assert the skip *reason code* at the `_record_twda_status` call boundary
     (`record.assert_called_once_with(uid, TwdaOutcome.SKIPPED, "<reason>", "")`)
     — that's the one meaningful interface. `twda_status` is member-excluded via
     per-field assertion pattern in `test_access_levels.py` (no set-contents
     assert to break); an exclusion test for it is redundant — the PR URL is a
     public GitHub link, not a secret like `checkin_code`.
