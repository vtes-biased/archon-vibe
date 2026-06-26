---
name: project-oauth-consent-test-infra
description: How to test OAuth endpoints at the HTTP layer (mint first-party vs third-party tokens, /oauth mount path, oauth tables not cleaned) + the consent invariants worth pinning.
metadata:
  type: project
---

OAuth subsystem (`routes/oauth.py`, `db_oauth.py`) had **zero behavioral tests**
until `tests/test_oauth_consents.py` (added 2026-06), which pins the one security
invariant of the member-facing consent feature: **consent management is
first-party-only** — a third-party OAuth token must not enumerate/revoke the
user's grants to *other* apps (`_require_first_party` guard). Mutation-verified.

**Non-obvious test facts (real DB + real middleware, no mocks):**
- The oauth router mounts at **root `/oauth/...`** (`app.include_router(oauth.router)`,
  router `prefix="/oauth"`), NOT under `/api`. The middleware gates non-impersonate
  OAuth tokens to paths `startswith("/oauth/")` — so a `profile:read` token DOES
  reach `/oauth/consents` and hits `_require_first_party` (403), rather than being
  bounced earlier.
- To make `get_current_user` accept a third-party token you must (1) `insert_oauth_token`
  a record for its `jti` (middleware does a revocation lookup) and (2) mint the JWT
  via the shipped `_create_oauth_jwt(... "access" ...)` + `ACCESS_TOKEN_LIFETIME`
  (import from `src.routes.oauth`, never hand-roll the JWT). First-party token =
  `conftest.make_auth_header(uid)`.
- `conftest.test_db` teardown only deletes `objects WHERE type='user'` — it does
  **not** clean `oauth_tokens`/`oauth_consents`/`oauth_clients`. Key your rows on
  unique jti/client_id; don't assert "table is empty".
- oauth tables exist in the test DB because `init_db()` applies `schema.sql`.

**Invariant considered but NOT yet tested — consent-authoritative-at-issuance:**
revoking consent must also block a surviving auth-code (≤60s window) and refresh
token from minting new access tokens — `routes/oauth.py` re-checks `get_oauth_consent`
in both `_handle_authorization_code` and `_handle_refresh_token` (400 "Consent has
been revoked"). Strong, non-obvious security invariant; deferred (added via a
concurrent edit, heavier setup: needs a client + issued code/token). Worth one
focused test if/when that hardening lands stably.
