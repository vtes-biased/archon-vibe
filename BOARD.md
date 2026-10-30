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

- Show each member's last-active date in the members directory — their latest event played or organised — with an "inactive for 18+ months" filter and the date in the CSV export for officials — gh-77: the directory filters by role and country (`frontend/src/lib/components/UserList.svelte:41-58`) but nothing shows activity, though every play record already lists events played and organised — **Done when** a member row shows the date of their latest finished event played or event organised, an official can filter the list to members with none in the last 18 months, the export carries the date, and the Members paragraph in `wiki/product.md` describes it.
