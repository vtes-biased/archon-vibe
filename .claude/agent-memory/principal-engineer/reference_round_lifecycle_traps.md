---
name: round-lifecycle-traps
description: Non-obvious engine round/finals state quirks to check when reviewing any round-lifecycle hook (timers, broadcasts, side-effects keyed on round start/end)
metadata:
  type: reference
---

When reviewing backend hooks keyed on tournament round-start/round-end events (e.g. the timer lifecycle block in `backend/src/routes/tournaments.py` action handler), these engine behaviors (in `engine/src/tournament/mod.rs`) are easy to miss:

- **RestoreRound can land on a *fully Finished* round.** It re-derives each table's state from retained scores (`check_table_vps`): a cancelled round whose scores were complete+valid re-derives to all-`Finished` (round NOT live). So treating `RestoreRound` as an unconditional "round starting" event is wrong — guard on whether the restored round actually has any non-`Finished` table.
- **Finals are NOT in `rounds`.** The finals table lives in the separate `finals` field, never in `tournament.rounds`. Any "rounds in progress" count built by iterating `rounds` excludes finals. `StartFinals`/`CancelFinals`/`FinishTournament` therefore see 0 prelim rounds live (finals require/leave state `Waiting`→`Playing`→`Waiting`/`Finished`).
- **Table states:** `Finished` / `In Progress` / `Invalid` / `Cancelled` (`TableState` in `backend/src/models.py`). "Live round" = any table whose state != `Finished` (Invalid and Cancelled both count as non-Finished).
- **Timer is online-only**, never touched by the Rust engine or WASM; the engine sets table/round/tournament *state*, the Python action handler layers the timer on top. Offline rounds started/ended via WASM won't run these hooks — the server overwrites timer state on go-online.

How to apply: when a hook fires on a round-start event, verify it checks the *resulting* round liveness rather than assuming the event implies a live round — RestoreRound is the counterexample that breaks the assumption. See [[round-lifecycle-traps]] siblings if added.
