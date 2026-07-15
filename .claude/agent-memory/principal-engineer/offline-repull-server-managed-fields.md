---
name: offline-repull-server-managed-fields
description: Adding a server-managed (non-engine) Tournament field requires updating the go-online re-pull block, else offline round-trip silently reverts it
metadata:
  type: project
---

Server-managed Tournament fields (the WASM engine never touches them; only backend
routes write them) must be re-pulled from the locked server row on the offline
write-back paths, or a stale client snapshot reverts them on go-online.

The canonical set today: `banner_path`, `external_ids`, `checkin_code`,
`vekn_pushed_at`, `vekn_results_stale`, `twda_status` — re-pulled in
`routes/tournaments.py` `go_online` right before
`msgspec.convert(tournament_data, Tournament)` (the block commented "Server wins
for non-engine fields"). `twda_status` was initially missed exactly this way
(review caught it): the reachable revert was an online-finished tournament
recording twda_status, taken offline on a device whose cached snapshot predates
the record, coming back online → server value blanked.

Two offline write paths reconstruct the tournament from the CLIENT snapshot via
`msgspec.convert(..., Tournament)`:
- go-online (`go_online`): re-pulls the siblings above — the place to add any new field.
- offline snapshot backup (`sync_offline`, "Background data backup ... without unlocking"):
  preserves only offline-lock fields, drops ALL server-managed fields (pre-existing,
  no broadcast) — it can overwrite the DB copy DURING the offline window, so a
  go-online-only fix re-pulls whatever the last snapshot wrote.

The ONLINE `/action` path is safe: the engine round-trips the tournament as a
json-rust `JsonValue` (`process_tournament_event`, `tournament["state"]`-style
indexing), so unknown/backend-only fields survive untouched — no engine change needed
for a backend-only field. `vekn_tournament_sync`'s hand-listed rebuild is the third
reconstruction site and must also preserve the field (twda_status was added there).

**Why:** the engine is dynamic-JSON (preserves unknown keys) but the offline paths
rebuild through a typed `Tournament` struct that defaults any field the client omitted.
**How to apply:** when reviewing a new server-only Tournament field, grep the four
`msgspec.convert(..., Tournament)` sites + `_TOURNAMENT_MEMBER_EXCLUDE` + the
vekn_tournament_sync rebuild; the go-online re-pull block is the one most easily missed.
See also [[migration-veknless-orphan-measured]] family of manual-reconstruction traps.
