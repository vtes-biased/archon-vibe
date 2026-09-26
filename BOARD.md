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
wiki. **No waiting state**: externally-gated work is deferred on the wiki page
that owns it — see [wiki/vekn-decommission.md](wiki/vekn-decommission.md) — with a
named trigger, and returns through `/intake` when the trigger fires.

**Every line must be completable** — if "done" cannot be stated, it is a subject:
promote it to a [wiki](wiki/index.md) page and delete the line. Context lives in
the wiki; asks live here. Bulky context for an in-flight line goes in
`board/<slug>.md`, deleted with the line.

Board changes ride the commit that earns them.


- Move the backend's main app and public API from FastAPI to Litestar, still served by uvicorn, with request bodies as msgspec Structs instead of Pydantic models, and re-examine draining connections already accepted at shutdown under the new framework. Done when no FastAPI or Starlette import or dependency remains, the test suite passes, on beta the app's `/stream`, the public API's streams and its `/docs` reference serve as before with each route declaring exactly one media type, and [architecture](wiki/architecture.md) (stack, API conventions), [public-api](wiki/public-api.md) (Documentation), [hazards](wiki/hazards.md) (the shutdown-502 item fixed or deferred again), [dev](wiki/dev.md), [sync](wiki/sync.md) and [access](wiki/access.md) are updated — context in [board/litestar.md](board/litestar.md).
- Give a registered `api:read` client a member's active suspensions and probations on the public API's user lookup, so the VEKN forum's login bridge can suspend a banned member on every site without waiting for a login: each with its level and end date (none for a ban), no other sanction level, and nothing to a user's token or an anonymous caller. Done when `/v1/users/{uid}` answers them to a client token only — lifted, expired and deleted ones absent — a test at the endpoint pins both audiences, and [public-api](wiki/public-api.md) (the one exception to "sanctions never appear"), [sync](wiki/sync.md) (the sanction row) and [access](wiki/access.md) are updated.
