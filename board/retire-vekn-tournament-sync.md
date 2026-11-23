Doc-impact: docs/domain/vekn.md, docs/vekn.md, docs/tournaments.md, docs/architecture.md, docs/hazards.md, docs/dev.md, docs/vekn-decommission.md, WATCH.md

# Retire VEKN tournament sync (Stage 1)

BCP removed the legacy `www.vekn.net` event calendar, event creation, and event
management pages. This is the greenlight for Stage 1 in `docs/vekn.md#decommission`.

## Owner decisions (2026-11-24)

1. **Stage 1 only** — member roster sync (`VEKNSyncService`) and member creation
   push (`push_member`, hourly `batch_push` member leg, `VEKN_PUSH` /
   `VITE_VEKN_PUSH` member pending-sync badges) stay on until vekn.net closes
   member registration (Stage 2).
2. **Keep `FormatForbidsRank`** — only Standard and Limited may be National or
   Continental Championships (VEKN policy, not just a vekn.net API gap). Reword
   the error text in `engine/src/error.rs` (and any matching i18n message) so it
   cites VEKN policy rather than vekn.net event types.
3. **Finished-tournament deletion is IC-only** — lift the VEKN-footprint delete
   block (`gh-6`), allow organizers to delete non-`Finished`, non-offline-locked
   tournaments they organize, and restrict deleting `Finished` tournaments to IC
   only. Keep the offline-locked refusal and hide Delete on offline-locked
   tournaments (and on `Finished` tournaments for non-IC organizers) in the UI.

## Scope checklist

### 1. Stop two-way tournament sync (keep member sync & push)
- **Inbound**: remove `run_tournament_sync` from `run_vekn_sync` in
  `backend/src/main.py`, remove `POST /admin/sync-vekn-tournaments` from
  `backend/src/routes/admin.py`, drop `tournament_sync` from `/admin/vekn-status`
  and `frontend/src/routes/profile/AdminSection.svelte`, and delete
  `backend/src/vekn_tournament_sync.py` (check `backend/scripts/audit_results.py`
  and tests that import from it; delete dead tournament-sync tests and dead
  push-repair scripts such as `fix_stuck_vekn_push.py` / `audit_vekn_placement.py`
  if nothing uses them). Keep `_corpus_write_lock` only if still needed, and keep
  `migrate_from_archon.py` intact.
- **Outbound**: remove `push_tournament_event`, `push_tournament_results`,
  `maybe_push_results`, `UNCREATED_EVENTS_QUERY`, and `UNPUSHED_RESULTS_QUERY`
  from `backend/src/vekn_push.py` so `batch_push` drains unsynced members only.
  Remove `_maybe_push_vekn_event`, `POST /api/tournaments/{uid}/push-vekn`, and
  `"push-vekn"` from `backend/src/middleware/auth.py` (and `pushVekn` from
  `frontend/src/lib/api.ts`). Verify `maybe_submit_twda` still fires on finish,
  post-finish, archon-import, and go-online without depending on a results push.
- **Stale / absent tracking**: stop writing `vekn_results_stale` (in
  `backend/src/routes/tournaments.py` and `backend/src/routes/sanctions.py`) and
  `vekn_event_absent_at`. Keep `external_ids["vekn"]` on historical rows for
  `/t/{code}` resolution and archive provenance. Check `models.py`,
  `access_levels.py`, `public_api/examples.py`, `types.ts`, and `mise run
  model-drift` before dropping any persisted fields (msgspec decodes strictly;
  read `docs/hazards.md#fields-silently-dropped`).
- **Observability**: remove the `Failing tournaments` panel from
  `deploy/grafana.py` (keep `Failing members` and the `VEKN push` row).

### 2. Lift VEKN-calendar limitations
- **`max_rounds` cap & immutability**: remove the `VEKN_PUSH` 2–4 round check on
  create and `UpdateConfig` (`backend/src/routes/tournaments.py`,
  `frontend/src/routes/tournaments/new/+page.svelte`,
  `frontend/src/lib/components/TournamentFields.svelte`), and remove the `409`
  immutability lock on `external_ids["vekn"]` (engine's `MaxRoundsBelowCompleted`
  and started-state locks stay). Default `max_rounds` to `0` (uncapped) at create.
- **Frozen config fields**: remove `VeknFrozenField` from `engine/src/error.rs`
  and `engine/src/tournament/mod.rs` (`rank`, `format`, `start`), and drop the
  `pushedToVekn` locks in `frontend/src/routes/tournaments/[uid]/TournamentDetailsForm.svelte`
  (`rank`, `format`, `start`, `proxies`, `open_rounds`, `max_rounds`).
- **Archival result corrections**: remove `ArchivalResultsVeknLinked` from
  `engine/src/error.rs` and `engine/src/tournament/mod.rs`, and drop
  `!tournament.external_ids?.vekn` from `ToolsSheet.svelte`.
- **Delete gate (`gh-6`)**: remove the `external_ids.vekn` / `vekn_pushed_at` /
  `vekn_event_absent_at` block in `DELETE /api/tournaments/{uid}`, enforce
  IC-only when `tournament.state == TournamentState.FINISHED` (keep organizer
  permission for non-`Finished` events and keep the `offline_mode` refusal), and
  mirror that rule in `frontend/src/routes/tournaments/[uid]/+page.svelte`
  (hiding Delete when `offline_mode` is true, or when `Finished` and viewer is
  not IC). Check `engine/src/permissions.rs` so role gating stays single-sourced
  in Rust (`mise run permission-drift`).
- **Inline `event_code` stamping**: stamp `tournament.event_code` inline inside
  `POST /api/tournaments` (`resolve_event_code`), and delete
  `_stamp_missing_event_codes` from `backend/src/main.py` along with its query.

### 3. Clean up dead tournament-sync UI & i18n
- Remove the dead `https://www.vekn.net/event-calendar/event/{id}` link badge,
  `syncVeknItem` ("Sync to VEKN" in `ToolsSheet.svelte` / `+page.svelte`),
  pending-results / `vekn_results_stale` / `vekn_event_absent_at` badges and
  banners (`ActionBar.svelte`, `FinishedResults.svelte`), and VEKN-push copy in
  `FinishConfirmModal.svelte` and `ReopenConfirmModal.svelte`.
- Update organizer-guide and error strings across all 5 locales (`en`, `fr`,
  `es`, `pt`, `it`) — `mise run locale-parity` must pass.
- Note: keep `VITE_VEKN_PUSH` member sync badges in `VeknManagement.svelte` and
  `ProfileIdentity.svelte` intact (Stage 2).

### 4. Docs and `WATCH.md`
- Update all docs named in `Doc-impact:`.
- In `WATCH.md`:
  - Remove the 3 folded code items from *VEKN stage 1* (`ArchivalResultsVeknLinked`,
    inline `event_code` / drop boot sweep, and the delete-capability / offline-lock
    part of gh-6 — keep the production data deletion list `events to delete`,
    duplicate cleanup, winner disagreements, 8 archive reconstruction pairs, and
    `run_twda_sync` retirement waiting on Stage 1 deploy).
  - Delete *The VEKN admins correct the calendar entries* and *The VEKN API
    maintainers answer on the 15 placements*.
  - Drop Q5 (push encoding) from *The Rules Director answers on no-final rating
    credit*.
