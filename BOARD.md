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


- File VEKN calendar events with their final, so an event that plays one stops being refused on the round count, and rewrite the deferred round-count item around the real cause. **Done when** an event created before its outcome is known reaches vekn.net as `NR+F`, the deferred item in `wiki/vekn-decommission.md` names the missing flag as the cause and lists every entry needing correction, stuck results and upcoming events alike, and `wiki/vekn.md`'s refused-events account agrees. Context in `board/vekn-final-flag.md`.
- Keep snapshot passes discreet on production's disk: store the `objects` JSON in the row with `STORAGE MAIN`, raise the volume's read-ahead to 1 MB, and move the pass's gzip off the event loop, keeping the 15-minute cadence. **Done when** new installs and production both carry the storage setting, production has been rewritten, the read-ahead survives a reboot, a cold pass on production makes under 500 device reads and leaves under 50 MB of `objects` in `shared_buffers`, gzip no longer runs on the event loop, and `wiki/sync.md`, `wiki/hazards.md` and `wiki/dev.md` record it. Context in `board/snapshot-storage.md`.
