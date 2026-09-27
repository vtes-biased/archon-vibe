Doc-impact: `wiki/hazards.md` (service-worker entry rewritten), `wiki/sync.md` (Cache Storage paragraph confirmed or corrected).

# Service worker vs its recorded design

`wiki/sync.md` records: Cache Storage holds exactly precached build assets and SPA
navigations (plus promo images, cache-first).

What the code does (`frontend/src/service-worker.ts`, checked against the built
`frontend/build/service-worker.js`):

- `respondFromCache` answers a navigation with `cache.match('/200.html')`, but
  `200.html` is the adapter-static fallback written after the build and is in
  neither `build` nor `files`, so it is never precached. Every navigation falls
  through to `networkFirst`.
- `networkFirst` caches any 200 response under its own URL, so every same-origin
  navigation that returned 200 lands in Cache Storage — not only SPA routes.
  Backend-served navigations reachable that way: `/api/calendar/tournaments.ics`
  (player guide button), `/api/calendar/tournaments/<uid>.ics` (tournament page,
  `download`). OAuth authorize/callback answer 302 and are not cached.
- Offline, a reload of a route never visited on that device answers the SW's own
  `Offline` 503.
- The `LEGACY_DISPLAY` exclusion (added 2026-09-26) guards against a shell answer
  that never happens today; the in-app 404 it targeted likely had another cause.

Trap for the fix: precaching the shell alone makes every same-origin navigation
answer with the SPA — `/auth/discord/authorize`, `/auth/github/authorize`, their
callbacks, the `.ics` feeds and the display redirect — breaking login on every
device with the SW installed. Exclusions must land in the same change. nginx's
backend prefixes live in `deploy/routes.py` (`BACKEND_PATHS`, `SSE_PATH`), already
loaded by `backend/tests/test_route_collisions.py`; the vhost also carries regex
locations (`deploy/templates/app.conf.j2`).

SvelteKit's client router loads an unmatched same-origin link natively
(`server_fallback` → `native_navigation`), so in-app links to backend paths reach
the SW as navigations.
