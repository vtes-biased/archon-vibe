Doc-impact: docs/vekn.md, docs/domain/vekn.md, docs/architecture.md, docs/access.md, docs/dev.md, docs/testing.md, docs/vekn-decommission.md, docs/post-deploy.md, WATCH.md

# Retire VEKN member sync and push (Stage 2)

BCP confirmed that `www.vekn.net` member sync is closing in both directions.
This is the greenlight for Stage 2 in `docs/vekn.md#decommission`.

## Owner decisions (2026-11-27)

1. **Drop `local_modifications` along with `vekn_synced` and `vekn_synced_at`** —
   with both `VEKNSyncService` and legacy archon sync retired, no live sync
   overwrites user fields. Remove all three fields from `User` (and frontend
   `types.ts`), stop recording `local_modifications` in profile/user/discord
   edit and anonymize routes, simplify `merge_users` sponsor precedence to
   `keep_user.coopted_by or delete_user_obj.coopted_by`, and remove
   `local_modifications` / `vekn_synced` reads from `migrate_from_archon.py`
   and `check_merge.py`.
2. **Keep `/admin/vekn-status` route** — drop `member_sync` and `batch_push`
   from the status payload and `AdminSection.svelte`, keeping `twda_sync` and
   `judge_sync` on the existing endpoint.
3. **Prince / NC divergence stays in `WATCH.md`** — it is a separate editorial
   review by officials, gated on Stage 2 being deployed on production.

## Scope checklist

### 1. Stop inbound member sync and outbound member push
- **Delete modules**: `backend/src/vekn_api.py`, `backend/src/vekn_sync.py`,
  `backend/src/vekn_push.py`, and `backend/scripts/audit_cities.py`.
- **Inline `OFFICIALS_EMAILS`**: `backend/scripts/migrate_from_archon.py`
  imports `OFFICIALS_EMAILS` from `backend.src.vekn_sync`; inline or clean up
  before deleting `vekn_sync.py`.
- **Scheduler (`backend/src/main.py`)**: remove `VEKNSyncService`, `run_vekn_sync`,
  `vekn_sync` job, `VEKN_SYNC_ENABLED` / `VEKN_SYNC_INTERVAL_HOURS`,
  `run_vekn_push`, `vekn_push` job, `VEKN_PUSH` / `VEKN_PUSH_INTERVAL_HOURS`,
  and `member_sync` runner wiring. Keep `twda_sync`, `judge_sync`, and
  `set_sync_runners(twda_sync=..., judge_sync=...)`.
- **Admin routes (`backend/src/routes/admin.py`, `backend/src/vekn_status.py`)**:
  remove `POST /admin/sync-vekn`, `_sync_service` / `set_sync_service`, and the
  `member_sync` / `batch_push` keys.
- **Member mutation routes (`backend/src/routes/vekn.py`, `backend/src/routes/users.py`)**:
  remove `push_member_background` calls and `vekn_synced` / `vekn_synced_at`
  assignments; keep `allocate_next_vekn_id`, claim, abandon, sponsor, link,
  force-abandon, and merge intact.

### 2. Remove `vekn_synced`, `vekn_synced_at`, and `local_modifications`
- **Backend**: remove from `User` in `backend/src/models.py`, `backend/src/accounts.py`
  (including `merge_users`, `detach_user_from_vekn`, `anonymize_member`,
  `ANONYMIZED_FIELDS` / field copy lists), `backend/src/routes/auth/profile.py`,
  `backend/src/routes/auth/discord.py`, `backend/src/routes/users.py`,
  `backend/scripts/migrate_from_archon.py`, `backend/scripts/check_merge.py`,
  and `backend/scripts/loadtest_users.py`.
- **Frontend**: remove `vekn_synced` / `vekn_synced_at` from
  `frontend/src/lib/types.ts`, remove `VITE_VEKN_PUSH` and pending-sync badges
  from `frontend/src/lib/components/VeknManagement.svelte` and
  `frontend/src/routes/profile/ProfileIdentity.svelte`, remove `syncVeknMembers`
  from `frontend/src/lib/api.ts`, and remove `member_sync` / `batch_push` /
  VEKN member sync button from `frontend/src/routes/profile/AdminSection.svelte`.
- **i18n**: remove dead keys (`vekn_sync_pending_member`, `vekn_sync_pending_hint`,
  `admin_status_member_sync`, `admin_status_batch_push`, `admin_sync_vekn_*`)
  across all five locales (`en`, `es`, `fr`, `it`, `pt`) and regenerate
  Paraglide messages.

### 3. Deploy, env, Grafana, and legal copy
- **Deploy & env**: remove `VEKN_SYNC_ENABLED`, `VEKN_SYNC_INTERVAL_HOURS`,
  `VEKN_API_BASE_URL`, `VEKN_API_USERNAME`, `VEKN_API_PASSWORD`, `VEKN_PUSH`,
  and `VITE_VEKN_PUSH` from `deploy/deploy.py`, `deploy/group_data/beta.py`,
  `deploy/group_data/prod.py`, `.env.example`, `docker-compose.yml`, and
  `frontend/Dockerfile.test` (do not edit `deploy/secrets/`).
- **Grafana (`deploy/grafana.py`)**: remove the `VEKN push` row, `Failing members`
  panel, `push_failures` helper, and `BACKEND` constant if unused.
- **Privacy & README**: update `frontend/src/lib/legal-content/privacy.md`
  (drop `vekn.net` profile sync and data-sharing entry, bump date) and
  `README.md`.

### 4. Tests
- Delete `backend/tests/test_vekn_member_sync.py`,
  `backend/tests/test_vekn_push_batch.py`, and `backend/tests/mock_vekn_data.py`
  (check for any remaining imports first).
- Update `backend/tests/conftest.py`, `test_access_levels.py`,
  `test_account_surgery.py`, `test_admin_guards.py`, `test_archon_merge.py`,
  `test_calendar.py`, `test_profile_update.py`, `test_ratings.py`,
  `test_users.py` to remove `vekn_synced` / `local_modifications` /
  `/admin/sync-vekn` assertions.
- Run `mise run test` and `mise run lint` (including `scripts/check_permission_drift.py`).

### 5. Docs & Watch
- Update all pages listed in `Doc-impact:` above, including updating the
  pending Grafana dashboard section in `docs/post-deploy.md` to reflect removal
  of the entire `VEKN push` row and narrowing Stage 2's trigger in `WATCH.md`
  to Stage 2 being deployed on production.
