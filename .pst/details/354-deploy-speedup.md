# Deploy playbook speedup

## Measured (beta deploy, 2026-07-03, after gather_facts off)

Total 2:21 for ~50 remote dispatches. The cost is fixed per-task dispatch, not payload:
plain module tasks ≈ 1.5 s flat, file-shipping tasks (copy/template) ≈ 3.2 s flat
(the extra transfer op roughly doubles the base). Real payload is ~30 s total:
asset download 4.9 s (29 MB — fast; caching it is pointless), rsync 2.4 s,
uv pip installs ~4 s, restarts ~8 s. Every deploy now prints this profile
(`ansible.posix.profile_tasks` + `timer` in ansible.cfg — note: these callbacks
live in `ansible.posix`, not `ansible.builtin`).

## Done

- `callbacks_enabled = ansible.posix.profile_tasks, ansible.posix.timer` (ansible.cfg).
- `gather_facts: false` on both deploy playbooks — grep-verified no deploy-path role
  (own or server-setup's `postgres_db`/`nginx_site`) reads gathered facts.
- Quick lane via **role-level tags in the playbooks only** (no tags inside roles):
  `tags: [app]` on the `fastapi_backend`/`static_site`/`discord_bot` role entries,
  `tags: [always]` on the `fetch_release` import; `QUICK=1 just deploy-beta|-prod`
  adds `--tags app`. Skips ~45 s of provisioning re-checks (beta: app_user 10.5 s +
  postgres_db 8.2 s + nginx_tls 11.2 s + nginx_site 15 s; prod skips nginx_tls ×2 +
  legacy_sync + db_backup). Verified with `--list-tasks` on both playbooks: exactly
  fetch + the three app roles are selected. Version bump ≈ 1:35 expected.
  Full deploy stays the default; any nginx/TLS/db/unit change needs it.

## Rejected (with reasons)

- Fine-grained per-task `app` tags inside roles (ticket's original plan): spreads a
  second "what ships" model through 3 role files for ~15 s more; not worth it.
- Release-artifact cache by tag: the full download is 4.9 s — measured, pointless.
- Merging the two `uv pip install` calls per role: saves ~2 s, complicates the command.
- Parallel asset downloads: download is already 4.9 s.
- Mitogen would collapse the ~1.5–3.2 s per-task floor to ~0.2 s (deploy ≈ 40 s) but
  adds a third-party strategy plugin dependency — the only remaining big lever if
  deploy time ever matters again.

## Open (minor)

- CI Deploy workflow has no `quick` input — add a boolean input passing `--tags app`
  if CI-driven prod bumps feel slow (4 lines in .github/workflows/deploy.yml).
- CI installs the whole dev group to get ansible; a dedicated `deploy` dependency
  group would trim CI setup time (CI-only, not a round-trip issue).
