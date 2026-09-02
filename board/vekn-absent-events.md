# The event vekn.net no longer has

Doc-impact: `wiki/vekn.md`, `wiki/vekn-decommission.md`.

## The trap that decides the design

`fetch_all_events` filters what it yields:

```python
if not players and not is_future:
    continue          # backend/src/vekn_api.py:487
```

A past event with no players is fetched, exists upstream, resets the empty run —
and is never yielded. That is the exact profile of an event created by mistake,
so **absence from the scan's yield is not absence upstream**, and diffing against
the yielded set false-positives on the only population this line serves. Commit
`2adb1ace` recorded the trap; `wiki/vekn-decommission.md` states it as "never the
bulk sweep".

The evidence is the branch *above* the filter: `event_data is None`
(`vekn_api.py:468`) is the API confirming no event at that id, per id, unaffected
by the yield filter and free — the scan already probes every id every run. Harvest
there, zipping the id range onto `asyncio.gather`'s order-preserving results.

Two bounds keep it sound: never judge an id the scan failed transiently on
(`fetch_event` raises rather than returning None precisely so these stay
distinguishable), and never judge an id above the highest the scan confirmed,
since the run stops on `empty_run_limit` and everything past that is unprobed.

## The flag

`vekn_event_absent_at: datetime | None` on `Tournament` — an instant, like
`vekn_pushed_at`, so we know when it was confirmed. There is no `extras` dict;
this is the `vekn_pushed_at` / `vekn_results_stale` idiom.

Five registrations, all precedent-backed by `vekn_results_stale`:

- `backend/src/access_levels.py` `_TOURNAMENT_MEMBER_EXCLUDE`
- `backend/src/routes/tournaments.py` `SERVER_OWNED_TOURNAMENT_FIELDS` — **not
  bookkeeping.** It gates a delete, so a client that could write it could delete
  a live sanctioned event.
- `backend/src/public_api/examples.py`
- `frontend/src/lib/types.ts`, plus a header badge gated like the out-of-sync one
- the sync's field-by-field rebuild — **deliberately not carried over**, inverting
  the rule `wiki/vekn.md` states for `checkin_code` and `twda_status`. A rebuild
  only runs when the event was found upstream, so letting it reset is what makes
  the flag self-clearing.

## Scope boundary

Deletion unlocks for the organizer on this state alone, reusing the existing
`organize_tournament` check. The IC blanket-delete capability stays deferred at
`wiki/vekn-decommission.md`: permissions resolve in the Rust core and
`is_organizer` already folds IC/NC in, so "ICs only" means a new capability
through engine + WASM + PyO3, and the dogmas forbid gating on `is_official`.

A false positive costs a duplicate, not data: the soft-deleted row keeps its vekn
id, `get_tournament_by_external_id` skips tombstones, and the next sync re-creates
a live copy.

Not in scope: making the hourly push batch skip a confirmed-absent event. Same
root cause, different module, and the batch cannot read per-run in-process state.
