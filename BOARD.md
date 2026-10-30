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

- Tell a member how long to wait when feedback is rate-limited — gh-72: the 60-second cooldown and the 10-a-day cap both answer 429 "please wait a moment" with no `Retry-After` (`backend/src/routes/feedback.py:48-60,115-119`), and the modal shows that English server text (`frontend/src/lib/components/FeedbackModal.svelte:78`) — **Done when** the 429 carries `Retry-After` for whichever limit was hit, and the modal shows a translated wait time, counting down on the submit button for the cooldown. Doc-impact: none, the wiki doesn't describe the limits and this only reports them.
- Show a member's win rate and their game wins and VPs per game on their play record, per rating category and over all time or the trailing 18 months — gh-74: imports carry each player's preliminary GW and VP, finals VP and a WD/DQ placement, and the event its round count (`wiki/vekn.md`, archondata format) — **Done when** the profile shows win rate (wins / events), GW per game and VP per game with withdrawn and disqualified events left out of the per-game figures and said to be, filterable by category and by the 18-month window, the per-game figures blank wherever an event's round count is unknown, and the play-record sentence in `wiki/product.md` lists them.
- Show each member's last-active date in the members directory — their latest event played or organised — with an "inactive for 18+ months" filter and the date in the CSV export for officials — gh-77: the directory filters by role and country (`frontend/src/lib/components/UserList.svelte:41-58`) but nothing shows activity, though every play record already lists events played and organised — **Done when** a member row shows the date of their latest finished event played or event organised, an official can filter the list to members with none in the last 18 months, the export carries the date, and the Members paragraph in `wiki/product.md` describes it.
