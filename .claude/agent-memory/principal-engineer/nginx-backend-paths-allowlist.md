---
name: nginx-backend-paths-allowlist
description: Prod nginx proxies ONLY the _backend_paths prefix allowlist to FastAPI; a new top-level route family outside it 404s in prod but passes dev CORS
metadata:
  type: reference
---

Production reverse proxy (`ansible/roles/static_site/templates/https.conf.j2` + `defaults/main.yml` `static_site_backend_paths_default`) proxies to the backend **only** the URL prefixes in the `_backend_paths` allowlist — currently `/api`, `/auth`, `/oauth`, `/vekn`, `/sanctions`, `/admin`, `/snapshot` (plus `/stream` as the SSE path). Everything else falls through to the static SPA handler.

**Why:** locations are nginx prefix matches (`location /api` covers `/api/time`, `/api/promos`, …). A new backend endpoint under an existing prefix needs no infra change; a new **top-level route family** (e.g. a bare `/time` or `/health2`) would silently 404 in prod while working in dev (dev uses app-wide `CORSMiddleware` + direct uvicorn, no allowlist).

**How to apply:** when reviewing a new FastAPI route, check its path is under an allowlisted prefix. If it introduces a new top-level segment, flag that `_backend_paths` (and per-inventory `r.backend_paths` overrides, if any) must gain it — otherwise green dev/tests hide a prod-only 404. `/api/time` (pst #512) verified safe under `/api`.
