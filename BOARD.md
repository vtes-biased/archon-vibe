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

- Confirm on production that the backend's job peaks were what drove the memory thrashing episodes — the streaming cuts have landed and were measured on beta; the prod side and its measurement commands are in `board/prod-memory.md`. **Done when** the stall episodes are attributed to a cause (backup, restore-verify, deploy or the backend's boot VEKN chain, via the memory stall counters sampled across a day), a before/after measurement across the deploy carrying the cuts shows the episodes gone or names what remains, and the Deployment section of `wiki/dev.md` records the backend's settled resident size and peak after that deploy, the box's memory breakdown and working headroom.
- Hold back a TWDA submission for an event with neither a country nor the online flag instead of publishing an empty place line — the organizer's status line names the missing venue, and setting it and re-saving submits. **Done when** such an event records a skipped status with that reason and opens no pull request, the same event submits once its country is set, the reason reads in every locale, and the skip-reason list in `wiki/vekn.md` names it.
- Import old VEKN result sheets faithfully: before October 2010 vekn.net's prelim GW/VP fold the final in, and a few sheets list the same member twice; evidence in `board/vekn-old-sheets.md`. **Done when** the tournament sync takes the final's GW and VP back out of the prelim totals for events before a cutoff measured across every pre-2011 VEKN event, keeps one row per member on a duplicated sheet (the placed one, the other logged), a prod re-sync leaves no prelim GW above the round count and no member twice in any standings, and the Tournaments section of `wiki/vekn.md` states both rules.
- Ship production's journal to Grafana Cloud through Fluent Bit — logs only, prod only, on the VEKN-owned Grafana Cloud stack; Fluent Bit rather than Alloy because the prod box has under 200 MB available. **Done when** a prod deploy leaves Fluent Bit running under a systemd memory cap with its measured footprint recorded, a Grafana query on the prod host returns the backend, bot and public-API units with the same `unit`/`tag`/`level`/`host` labels beta's Alloy emits, beta's server-setup Alloy is untouched, and the Deployment section of `wiki/dev.md` says where production logs live and how to read them.
