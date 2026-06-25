---
name: bot-active-tables-finals-seating-trap
description: bot _active_tables keys finals on seating-truthiness not result-state — consumers that should stop at finals completion (timer reminders) over-trigger
metadata:
  type: project
---

In `bot/src/archon_bot/sse_listener.py`, `_active_tables(obj)` returns the
`"finals"` tag whenever `finals.seating` is non-empty — it does NOT consult
`finals.result`. A reported-but-not-finalized finals stays in state `Playing`
with `seating` populated, so any consumer keyed off `_active_tables` treats it
as a live, in-progress finals.

**Why:** This is correct for channel routing (the finals voice channel should
exist until teardown) but WRONG for any consumer that should stop at finals
*completion* — e.g. `compute_timer_reminders` would otherwise keep a "Time!" post
scheduled for a finals that finished early but whose tournament hasn't been
finalized. NOTE the obvious-looking guard `finals.get("result")` (used by
`find_player_table`) is a **no-op**: there is no top-level `result` field on
`Table`/`FinalsTable` (backend `models.py` — only `seating`, `state`, `override`,
plus per-*seat* `result`). The real completion signal is the table itself:
`state == "Finished"` or a judge `override`.

**How to apply:** When adding a new per-table side-effect keyed off
`_active_tables`, ask whether it should fire on a finished-but-not-finalized
table/finals. If not, gate on `_table_pending(table)` — pending = NOT in
`{Finished, Invalid, Cancelled}` and no `override` (i.e. still being played); do
NOT gate on `finals.get("result")`. And if the effect is scheduled/cancelled,
make its change-guard signature sensitive to per-table pending-state
(`_timer_signature` does this), else a table finishing won't trigger the cancel.
`_table_pending` + the signature fix shipped for the timer feature. `finals_time`
is often 0 in VEKN (untimed finals), so the timer's `total <= 0` guard already
suppresses the finals case there too.

Related: [[online-only-tournament-subdata-carveout]] (the carve-out pattern the
bot timer/announcement features live inside).
