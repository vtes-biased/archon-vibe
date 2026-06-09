# EPIC #95 — pre-beta API surface cleanup

Audit (2026-06-09): traced all 81 real backend HTTP endpoints against both clients —
frontend (`api.ts` + stores + `href`/`download`/`<img>` uses) and bot (`archon_api.py`,
`sse_listener.py`). Also checked the in-process apscheduler for internal callers.

**69/81 endpoints map to a real caller.** The offline-first model holds: frontend never
GETs data (reads come from `/stream` + `/snapshot` → IndexedDB). 12 are reached by neither
client. Two `middleware/auth.py` "routes" (`/admin-only`, `/nc-or-prince`) are docstring
examples, not real endpoints; the bot's `/oauth/callback` is its own local listener.

## Children
- **#96 (p1)** — bot path-prefix bug. Fixing immediately.
- **#97 (p2)** — trim forward-looking/superseded surface.
- **#98 (p3)** — decide on force-unlock + admin sync endpoints.

## The 12 unused-by-both endpoints

### Bucket A — deliberate external surface → trim (#97)
- `GET /api/v1/users/`, `/api/v1/users/{uid}`, `/api/v1/tournaments/{uid}`,
  `/api/v1/leagues/{uid}`, `/api/v1/sanctions/user/{user_uid}` — whole `routes/api_v1.py`,
  header-docstringed "Third-party API endpoints (v1)".
- `POST /oauth/revoke` (`routes/oauth.py:464`) — RFC 7009 token revocation; bot lets tokens lapse.
- `GET /oauth/clients/{client_id}` (`routes/oauth.py:610`) — single-client read; frontend
  only lists (`GET /oauth/clients`), creates, regenerates-secret, deletes.

Rationale: untested against real consumers, v1 reads duplicate access-projection logic
already in the SSE path. Delete now; design a real public API (docs/versioning/rate-limit)
as a separate post-beta effort.

### Bucket B — ops/admin manual triggers → keep-or-script (#98)
- `POST /admin/sync-vekn`, `/admin/sync-vekn-tournaments`, `/admin/sync-twda-decks`
  (`routes/admin.py:39/61/85`) — IC-only manual wrappers around jobs the apscheduler already
  runs (`main.py`). No UI; curl-only break-glass. (`/admin/users/merge` IS frontend-used.)

### #98 resolution (decided + implemented)
Both halves got IC-only UI (owner's call), behind strong confirm modals:
- **Admin sync ×3** → new IC-gated `AdminSection` on `/profile` + reusable
  `ConfirmActionModal` (loading/stats/error) + `api.ts` helpers. (staff-frontend-engineer
  picked /profile over CommunityTab/`/admin`.)
- **force-unlock** → IC-gated crimson button in the offline locked banner + inline confirm.

Guards verified DB-sourced (roles from `get_user_by_uid`, never JWT) + new
`test_admin_guards.py`. principal-engineer review then found force-unlock was
**broken even as the curl endpoint** — fixed:
- **C1 (graceful):** the wedged lock-holder never received the unlock (SSE drops
  updates for locally-offline tournaments). Added `lostOfflineLock`/`handleOfflineLockLost`
  in `offline.svelte.ts`; the 3 sync.ts offline-skip filters now reconcile + warn when
  the server shows this device lost the lock (force-unlock OR force-takeover) — so a
  lost/recovered device "gets the memo" on reconnect and discards its orphaned offline state.
- **C2 (corruption):** go-online's device-lock check sat inside `if offline_mode:`, so a
  stale device could blind-overwrite after an unlock. Now returns **410** (pre-lock +
  in-tx) when the server isn't in offline mode; client un-wedges on 410. Test:
  `test_go_online_refused_when_server_not_offline`.
- **I2 (privilege):** force-unlock now rejects OAuth tokens (`request.state.oauth_client_id`),
  matching the `/admin/*` lockdown.

### Bucket C — orphaned / superseded
- `GET /api/tournaments/{uid}/decks/{player_uid}/twda` (`routes/tournaments.py:1045`) —
  server-side per-player TWDA export via Rust engine. Never wired into any client (frontend
  `DeckDisplay` renders decks in TWDA order but has no export action; the winner auto-PR
  uses `engine.export_twda` server-side directly, not this HTTP route). → delete (#97).
  [DONE — removed in #97]
- `POST /api/tournaments/{uid}/force-unlock` (`routes/tournaments.py:1752`) — IC emergency
  unlock, the escape hatch named in ARCHITECTURE.md/CLAUDE.md, but no UI wires to it (only
  `force-takeover` is wired). Decide: wire UI vs. document curl-only (#98).

## Separate finding — live bot bug (not dead code) → #96
Bot and frontend both target the same backend root (`ARCHON_URL` / `VITE_API_URL`,
default `http://localhost:8000`). Frontend correctly hits `/vekn/claim`, `/sanctions/`.
Bot hits nonexistent paths (routers mount at `/vekn`, `/sanctions` — no `/api`):
- `archon_api.py:228` `POST /api/vekn/claim`   → should be `/vekn/claim`
- `archon_api.py:239` `POST /api/vekn/sponsor` → should be `/vekn/sponsor`
- `archon_api.py:266` `POST /api/sanctions/`   → should be `/sanctions/`
Method docstrings already say the correct paths; `tournament_action`'s `/api/tournaments/...`
is correct because that router IS under `/api`. No bot test asserts these paths.
