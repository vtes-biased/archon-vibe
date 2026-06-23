---
name: online-only-tournament-subdata-carveout
description: Timer pattern — online-only live tournament sub-data is a Tournament field mutated by a backend route (no Rust engine), broadcast via tournament_transaction→save_object→broadcast_precomputed
metadata:
  type: project
---

The round timer (#277-era) is the canonical pattern for **online-only, ephemeral, live tournament sub-data that does NOT need the Rust engine**:

- Modeled as a field on the `Tournament` model (`timer: TimerState`, `table_extra_time: dict`), NOT a separate synced object type. Sub-struct (`TimerState`) is a plain `msgspec.Struct`.
- Comment in models.py marks it explicitly: "Timer state (online-only, not processed by Rust engine)".
- Mutated by dedicated backend routes in `routes/tournaments.py` (`timer_start`/`pause`/`reset`/`add-time`), each: `async with tournament_transaction(uid)` → validate (organizer + state==Playing + not offline_mode) → mutate field → `_save_timer_tx` (sets `modified`, `save_object`) → `broadcast_precomputed(bd)` after commit. Returns the full Tournament JSON as the HTTP response.
- engine/src/tournament/ has ZERO timer logic (only `test_update_config_timer_fields` validating round_time/finals_time as config).
- Frontend api.ts: plain POST helpers, NO optimistic WASM update — server is authoritative, SSE delivers the new state.

**Why:** the design intent (`.pst/details/68`) is that the timer serves only ONLINE events; offline tournaments have no timer. Business logic that must run offline lives in Rust; online-only live UI state is a justified backend carve-out. Late-joiners/reconnects get current state for free because the field rides the whole-tournament-row SSE snapshot (`SELECT col::text`).

**How to apply:** for new online-only live broadcast features (announcements #290, etc.) mirror this exactly — field on Tournament + backend route, no engine, no optimistic update, no new object type. Only reach for a new synced object type if the data needs independent soft-delete lifecycle, its own uid, or out-of-tournament-scope sync. See [[tournament-member-projection-is-exclude-list]] for why member delivery is automatic.
