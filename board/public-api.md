# Public read-only API — shared context for the two board lines

Doc-impact: line 1 → new `wiki/public-api.md`, `wiki/access.md`; line 2 →
`wiki/access.md`, `wiki/dev.md`, `wiki/public-api.md`.

Owner decisions (this intake, 2026-08-22): officials' names stripped (VEKN IDs
only), deck `author` stripped, sanctions never surfaced, auth required (no
anonymous), Archon-native rather than under the krcg umbrella — krcg stays the
card-data authority, Archon is the system of record for organizational data; a
static mirror of the bulk export to `static.krcg.org` stays a deferred option.

Related dogma scoping: "No server-side pagination" governs the app's role-scoped
online-only reads; the public API is a different surface and paginates (keyset).
`access.md`'s "There is no public read API" sentence drops with line 1.

## The API app (line 1)

`backend/src/public_api/` (same wheel), its own FastAPI app: no engine import, no
scheduler, no SSE, small own DB pool (separate process — cannot starve the main
app's 20 connections). Endpoints resurrect the pass-through pattern of the
removed `/api/v1` surface (commit `3abb708`): `SELECT api::text FROM objects`,
raw `Response`, list endpoints string-joined — no Python deserialization.

`/v1` endpoints, all GET: tournaments (filters country/format/state/date-range/
`since`; keyset cursor `(modified_at, uid)` — index exists), tournament by
event_code-or-uid, leagues (+by uid), users by VEKN ID, rankings (sort over the
api column's rating totals — minimal compute is acceptable), public decks
(+by tournament), community links (flattened from user rows), bulk export
(streams the `api` snapshot file). No cards (krcg's), no sanctions, no promos,
no league standings (engine-computed client-side today — deferred).

Docs: `scalar-fastapi` serves the app's OpenAPI at `/docs`. Pass-through
responses bypass FastAPI schema generation, so assemble response schemas from the
real msgspec Structs via `msgspec.json.schema()` — no parallel doc-models. Drift
test: project a sample full object through the api projection, validate against
the documented schema.

Isolation guard, three layers: structural (own subdomain, no frontend env var or
helper); lint `check_public_api_isolation.py` modeled on
`check_permission_drift.py` — fails on any API-host/prefix reference under
`frontend/` and on `public_api` importing broadcast/SSE/engine — wired into
`just lint` **and** `ci.yml` (two existing checks live only in the justfile;
don't repeat that); a test asserting the route table is GET/HEAD only.

Auth from day one: bearer required; before line 2 lands, existing user
`oauth_access` tokens suffice for local testing.

## Daemon identity and deploy (line 2)

`client_credentials` grant on the existing `/oauth/token`, gated on the client's
existing registration (DEV/IC-managed CRUD). Issues a short-lived **stateless**
JWT of new type `oauth_client` carrying `client_id` + `api:read` — deliberately
no `oauth_tokens` row: `OAuthToken.user_uid` is non-optional and the main
middleware unconditionally resolves a User, so the new type never touches either.
Revocation = the client's `active` flag, checked by the API app's own auth
dependency. The main app's middleware never learns the type and rejects daemon
tokens by construction. The API accepts both daemon tokens and user
`oauth_access` tokens; same response either way (user tokens are attribution).

Deploy mirrors the Discord bot's ansible role: own `service.j2`/`env.j2`, own
nginx vhost on `api.<domain>` with `limit_req` rate limiting, wide-open CORS
(GET-only public data), added to `deploy.yml`/`deploy-beta.yml`. Beta first.

## Deferred (record on `wiki/public-api.md` when it exists, with triggers)

- **User-level TWD opt-out** ("I don't want my name/deck in TWD") — trigger: a
  member asks for it.
- **League standings endpoint** — needs engine compute or promo-stock-style
  cross-object reprojection on tournament save. Trigger: a consumer asks.
- **krcg static mirror of the bulk export** — trigger: owner wants krcg-ecosystem
  entry point.
- **`POST /oauth/revoke`** (RFC 7009, removed in `3abb708`) — worth restoring for
  third parties alongside line 2 if cheap.
