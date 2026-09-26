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


- Make every public API query index-backed and cheap enough that the API can never crowd out the app: drop the tournament `format` and `state` filters, serve `country` and the `start` bounds from indexed expressions for tournaments and members, cut the API's statement timeout to about 2 s and its pool to 2, and hold every remaining stream and lookup to the same bar. Done when EXPLAIN on beta shows each `/v1` query as an index scan with no whole-type filter pass, a one-week tournament date window returns in well under a second, and [public-api](wiki/public-api.md) (filters, the index paragraph, the isolation figures) is updated.
- Stop a deploy from breaking tabs still running the previous build: keep the prior build's content-hashed `_app/immutable` files for one more deploy, and reload once onto the current build when a lazy chunk fails to load. Done when, on beta, a tab opened before a deploy navigates to a not-yet-loaded route afterwards without error, nginx logs no `_app/immutable` 404 for it, and the deploy section of [hazards](wiki/hazards.md) records the one-build retention.
- Make the hourly VEKN push self-healing and visible, with vekn.net as the source of truth: on PLAYER_ALREADY_EXISTS read the registry's player for that id and overwrite our member's identity fields with it, marking it synced; name the vekn event id and the reason in every failure line; count failed uploads and member pushes in the batch's error total; and add a panel to the production Grafana dashboard listing failing tournaments (uid, vekn event, reason) and members, fit to hand the VEKN API admins. Done when the four stuck members are synced to the registry's record on the first batch after deploy, the batch summary reports non-zero errors while items fail, the panel is applied through `deploy/grafana.py`, and [vekn](wiki/vekn.md) (push rules, including the registry-wins overwrite) and [dev](wiki/dev.md) (dashboard) are updated. The round-count refusals are vekn.net's to fix and wait in [vekn-decommission](wiki/vekn-decommission.md).
- Classify the audit drift since the 2026-09-23 table in [vekn](wiki/vekn.md#results-across-the-three-sources) and refresh it from a fresh prod `audit_results.py` run: the 2026-09-26 run read vekn/twda winner 77 (table: 28), archon/vekn field 29 and archon/twda field 5 (no row), archon/vekn prelim 8 (table: 2), winner 7 + finalists 13 (table: 15), rounds 7 (table: 6) — likely the 76 merged reconstructions now compared, unverified.
- Redirect legacy archon's `/tournament/<legacy-uid>/display.html` links to the page of the event the import kept that uid on, answering an unknown uid with the normal 404. Done when an imported legacy uid 301s to its `/tournaments/<uid>` page on beta, an unknown one 404s, and the legacy-link paragraph in [vekn](wiki/vekn.md) says the form now redirects.
- Serve the fixed paths browsers and crawlers request on their own as real files: `/favicon.ico` and `/apple-touch-icon-precomposed.png` generated from the production icons, `/robots.txt`, and an empty `/.well-known/assetlinks.json`. Done when each returns 200 with its own content type on beta, none of them logs an nginx `open() failed`, and the icon paragraph in [dev](wiki/dev.md) lists them.
