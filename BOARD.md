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

- Move the frontend to SvelteKit 3 with adapter-static 4 — **Done when** the build config lives in the Vite plugin with the old config file gone, no `$lib` import or deprecated `pushState`/`replaceState` call remains, `npm ls` is clean and `npm run check` and the frontend tests pass, and on beta deep links load through the SPA fallback, a tab left open across a deploy still navigates, and an offline reload works; `wiki/architecture.md`, the frontend step of `wiki/testing.md` and the list-view rule in `wiki/design.md` say so. Context in [`board/sveltekit-3.md`](board/sveltekit-3.md).
