# Board

A list designed to shrink. **The goal is zero.** Completion is deletion — there is
no closed state, no archive; git history is the record and `git blame` knows a
line's age.

**Order is priority.** Ranking rules, applied top to bottom when two unrelated
lines compete:

1. user-reported defects
2. correctness
3. blocking work and useful refactorings
4. polish
5. new capability

**Hard limit: 15 lines.** Adding a sixteenth forces a drop or a promotion to the
docs. **No waiting state**: work that waits on a date or an outside trigger is in
[WATCH.md](WATCH.md), and returns through `/intake` when its trigger fires.

**Every line must be completable** — if "done" cannot be stated, it is a subject:
promote it to a [docs](docs/index.md) page and delete the line. Context lives in
the docs; asks live here. Bulky context for an in-flight line goes in
`board/<slug>.md`, deleted with the line.

Board changes ride the commit that earns them.

- Retire the two-way VEKN member roster sync and outbound member push (Stage 2) — stopping inbound member sync (`VEKNSyncService`, `POST /admin/sync-vekn`) and outbound member creation push (`vekn_push.py`, `VEKN_PUSH` / `VITE_VEKN_PUSH`), deleting `vekn_api.py` and `audit_cities.py`, removing the pending-sync member badges, sync-tracking fields on `User`, VEKN API deploy env vars, and the `VEKN push` Grafana row while keeping `twda_sync`, `judge_sync`, and all local VEKN ID workflows intact — detailed in `board/retire-vekn-member-sync.md`. **Done when** no scheduled job, admin action, or route calls `www.vekn.net`, `twda_sync`, `judge_sync`, and local VEKN ID allocation/claim/sponsor/link/merge keep working, `mise run test` and `mise run lint` pass, and the docs, privacy policy, `docs/post-deploy.md`, and `WATCH.md` listed in `board/retire-vekn-member-sync.md` are updated.
