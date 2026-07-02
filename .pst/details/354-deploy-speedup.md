# Deploy playbook speedup

Analysis from a session walking `playbooks/deploy.yml` (prod) + `playbooks/deploy-beta.yml`,
all deploy-path roles, `tasks/fetch_release.yml`, `ansible.cfg`, the justfile recipes, and
`.github/workflows/deploy.yml`. Deploys take ~5 min; individual steps are fast — the cost is
~60 tasks × WAN round-trip, plus artifact download/transfer. Transport is already tuned
(pipelining, ControlMaster/Persist 300s, forks; single host so no strategy-level parallelism).

## Where the time goes (typical run)

- `fetch_release`: wipes `build/` and serially re-downloads all 6 release assets (~29 MB,
  dominated by `frontend-dist.tar.gz` at ~26 MB) + untar — every run, even same tag.
- Fact gathering: one full `setup` round trip (~3–8 s over WAN) — and **no deploy-path role
  uses gathered facts** (verified: own roles + server-setup's `postgres_db`/`nginx_site` only
  use magic vars like `ansible_check_mode`; facts are needed only by `migrate_postgres.yml`,
  `upgrade.yml`, and `postgresql/pgdg_repo.yml`).
- ~55–60 dispatched tasks, each ≈ RTT + module exec even when no-op: asserts, mkdirs,
  templates, certbot creates-guard, uv-python/venv guards, vault file drops, systemd enables.
- Real payload: wheel `copy` (~2.7 MB), dist rsync (~26 MB, content-hashed names so mostly
  retransmitted on a new release — irreducible), 2× `uv pip install` per role × 2 roles,
  service restarts.

## 1. Quick path for patch releases (`--tags app`) — the big win

Tasks not matching `--tags` are never dispatched: zero round trips, no skip noise. Keep one
playbook as source of truth, add a fast lane:

- `tags: [app]` on the artifact-ship tasks in `fastapi_backend`, `discord_bot`, `static_site`:
  wheel uploads, requirements upload, `uv pip install` (deps + `--reinstall` wheels), dist
  rsync + chown. ~15 tasks total, mostly real payload.
- `tags: [always]` on each role's `assert` + `set_fact` (controller-side, free, needed by both
  paths) and on the `fetch_release` import in both playbooks.
- Everything else stays untagged → auto-skipped under `--tags app`: `nginx_tls`/certbot,
  vhost + systemd + env templates, `app_user.yml`, server-setup `postgres_db`/`nginx_site`,
  `legacy_sync`, uv-python install + venv detect/recreate guards, vault file drops.
- Handlers unchanged — a notifying task that runs still triggers its restart.
- Entry points: `just deploy-quick-beta` / `deploy-quick-prod` passing `--tags app`; optional
  `quick` boolean input on the CI Deploy workflow.
- Failure mode is safe: full deploy stays the default, so a forgotten tag on a future task
  means "quick path doesn't ship it", not "config silently diverges". Any env/unit/nginx
  change ⇒ use the full deploy. If a quick deploy hits a missing/stale venv (rare python
  bump), the answer is one full deploy — deliberately NOT tagging the venv guards (3 tasks
  × 2 roles of round trips guarding a rare event).

Expected: patch deploy ~1 min (fetch + ~15 dispatches + rsync + restarts).

## 2. Full-path trims

Ordered by payoff:

1. **Measure first** — `ansible.cfg`: `callbacks_enabled = ansible.builtin.profile_tasks,
   ansible.builtin.timer`. Zero risk; confirms the guesses below before restructuring.
   (Aside: `ansible/.ansible_facts/` is empty and unreferenced — leftover, delete.)
2. **`gather_facts: false`** on both deploy playbooks (see verification above).
3. **Cache release artifacts by tag** in `tasks/fetch_release.yml`: write the resolved tag to
   a stamp file (e.g. `build/.release_tag`); skip reset + downloads + untar when it matches.
   Makes the "deploy vX to beta, verify, promote same vX to prod" flow pay the ~29 MB
   download once, and makes re-runs/dry-runs free.
4. **Parallelize asset downloads** (secondary to 3): `async`/`poll: 0` per `get_url` +
   `async_status`, or one `curl --parallel`. Tarball dominates, so modest.
5. **Merge the two `uv pip install` calls per role** into one resolution:
   `uv pip install -r requirements.txt --reinstall-package archon --reinstall-package
   archon-engine <wheel paths>`. Verify the exported requirements don't name the
   project/engine (export uses `--no-emit-project`; engine may appear as a path dep — check).
6. **CI-only**: the Deploy workflow runs `uv run --frozen --group dev ansible-playbook`,
   installing the whole dev toolchain to get ansible. A dedicated `deploy` dependency group
   would cut CI setup. Irrelevant for laptop deploys.

## Not worth touching

- SSH transport settings (already tuned); dist rsync (delta + delete already).
- certbot / `uv python install` / venv-version dance: properly guarded, near-instant when idempotent.
- Forced wheel `--reinstall` + restart handlers: that's the deploy's actual job.

## Relates

- #343 (warning-free prod deploys) touches the same files; batch if convenient.
