---
name: tournament-get-route-prefix
description: GET-tournament/user/league-by-uid lives under /api/v1 (api_v1.py), while mutation routes live under /api/tournaments (tournaments.py) — easy to use the wrong prefix
metadata:
  type: project
---

The single-object GET endpoints and the tournament mutation endpoints live on **different router prefixes**, which is a trap when writing frontend fetch URLs.

- `backend/src/routes/api_v1.py` — prefix `/api/v1`. Has `GET /api/v1/tournaments/{uid}`, `GET /api/v1/users/{uid}`, `GET /api/v1/leagues/{uid}`, `GET /api/v1/sanctions/...`. Returns the raw JSONB at the viewer's access level (404 if not visible / not found). This is the ONLY GET-tournament-by-uid route.
- `backend/src/routes/tournaments.py` — prefix `/api/tournaments`. Has `POST /api/tournaments/`, `POST /api/tournaments/{uid}/action`, `DELETE /api/tournaments/{uid}`, timer/organizer sub-routes. There is **no** `GET /api/tournaments/{uid}`.

So `GET /api/tournaments/{uid}` (without `/v1`) hits a nonexistent route (405/404), not the tournament.

**Why:** discovered reviewing pst #8 (optimistic rollback) — `reconcileTournamentAfterRejection` in `frontend/src/lib/api.ts` fetched `/api/tournaments/${uid}` instead of `/api/v1/tournaments/${uid}`, so the authoritative re-fetch always failed and the rollback never ran. See [[p1-sync-fixes-review-2026-06]].

**How to apply:** When code needs to re-fetch a single object by uid from the server (rare — offline-first means reads come from IDB), use the `/api/v1/...` prefix. Flag any frontend GET to `/api/tournaments/{uid}` (bare) as a bug. Also remember `api_v1.get_tournament` returns 404 when the object isn't visible or doesn't exist — callers must handle that (e.g. a rejected create leaves nothing to fetch; delete the local optimistic copy instead).
