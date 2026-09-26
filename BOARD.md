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


- Keep credentials out of production's logs and give every request an ID that follows it: nginx and the backend's access log mask the `token`, `code` and `state` query values, and nginx issues a request ID that it logs, passes to the backend, which carries it on every log line the request produces, and into PostgreSQL as the connection's application name, so a logged slow statement or error names the request that ran it. Done when, on beta, a Loki query for `token=` or `code=` followed by a value returns no line from either unit after deploy, one `/stream` request's ID appears in nginx's, the backend's and (for a forced slow statement) PostgreSQL's lines, and the logs paragraph in [dev](wiki/dev.md) documents the ID and the mask.
- Throttle the public API per client rather than per address: the streaming and lookup budgets are keyed on the `client_id` the bearer token carries, so a consumer spreading its sync over many addresses gets the same budget as one, while `/oauth/token` stays keyed by address. Done when, on beta, one daemon client sending streams from two source addresses is refused with a 429 at the same count as from one, two different clients from one address each get their full budget, and the throttle table and the per-address paragraph in [public-api](wiki/public-api.md#deployment) describe the client key.
- Redirect legacy archon's `/tournament/<legacy-uid>/display.html` links to the page of the event the import kept that uid on, answering an unknown uid with the normal 404. Done when an imported legacy uid 301s to its `/tournaments/<uid>` page on beta, an unknown one 404s, and the legacy-link paragraph in [vekn](wiki/vekn.md) says the form now redirects.
- Move the backend's main app and public API from FastAPI to Litestar, still served by uvicorn, with request bodies as msgspec Structs instead of Pydantic models, and re-examine draining connections already accepted at shutdown under the new framework. Done when no FastAPI or Starlette import or dependency remains, the test suite passes, on beta the app's `/stream`, the public API's streams and its `/docs` reference serve as before with each route declaring exactly one media type, and [architecture](wiki/architecture.md) (stack, API conventions), [public-api](wiki/public-api.md) (Documentation), [hazards](wiki/hazards.md) (the shutdown-502 item fixed or deferred again), [dev](wiki/dev.md), [sync](wiki/sync.md) and [access](wiki/access.md) are updated — context in [board/litestar.md](board/litestar.md).
