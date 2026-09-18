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

Reuse one outbound HTTP session instead of building a fresh TLS client per call — every backend caller that talks to Discord, VEKN, deck providers and GitHub currently pays a full handshake per request, worst on the login path a tournament morning hammers. Done when no `aiohttp.ClientSession(` remains in `backend/src` outside the lifespan singleton, the push fan-out, and the link-preview SSRF guard; `wiki/architecture.md` records the shared transport and `wiki/hazards.md` records why link-preview is exempt. Context and prod measurements in `board/shared-http-session.md`.
