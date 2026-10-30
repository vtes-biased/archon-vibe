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

- Resolve a US member's city with their vekn.net state instead of the most populous city of that name — gh-76: the member sync calls `match_city` and drops `statename` (`backend/src/vekn_sync.py:553`) though `match_city_in` takes a state hint (`backend/src/geonames.py:248`), so Ohio's Newark and Canton land in New Jersey and Michigan; the vekn.net tournament city fill does the same (`backend/src/vekn_tournament_sync.py:535`) — **Done when** a member synced with city Newark and state Ohio is stored in Newark (Ohio), the tournament city fill uses the event's state wherever vekn.net gives one, members already placed wrong are corrected by the next sync, and the member-sync identity bullet in `wiki/vekn.md` says the state disambiguates the city.
- Finish a tournament automatically 7 days after its final table was scored but never closed, and show its organisers every other played tournament they left open — the engine credits nobody without `FinishFinals`, finishing pushes to vekn.net and opens the TWDA pull request, and an offline-held event cannot be finished server-side — **Done when** a daily job runs `FinishFinals` on an online event whose final table is scored and 7 days old, and tells its organisers it did; an organiser sees a banner listing their events dated 2+ days ago with rounds played and not finished, each with a way to finish it; and the state lifecycle in `wiki/tournaments.md`, the organiser tools in `wiki/product.md` and the scheduled jobs in `wiki/architecture.md` describe both.
- Open the feedback form from every page, for members with a VEKN ID: from the side rail on desktop, and on phones by leading the Help page with it — gh-70, gh-78: the form only opens from the Help page (`frontend/src/routes/help/+page.svelte:84`), so every report arrives saying `Page: /help`, though the modal already records the current route (`frontend/src/lib/components/FeedbackModal.svelte:70`); the phone bottom bar has no room for a seventh icon — **Done when** a VEKN member can open the feedback form from the side rail on any page, the Help page leads with the feedback button, every filed issue names the page the member was on (the one they came from when filed from Help), the Help and feedback paragraph in `wiki/product.md` says so, and the feedback-triage skill no longer tells the reader to ignore `Page:`.
- Tell a member how long to wait when feedback is rate-limited — gh-72: the 60-second cooldown and the 10-a-day cap both answer 429 "please wait a moment" with no `Retry-After` (`backend/src/routes/feedback.py:48-60,115-119`), and the modal shows that English server text (`frontend/src/lib/components/FeedbackModal.svelte:78`) — **Done when** the 429 carries `Retry-After` for whichever limit was hit, and the modal shows a translated wait time, counting down on the submit button for the cooldown. Doc-impact: none, the wiki doesn't describe the limits and this only reports them.
- Show a member's win rate and their game wins and VPs per game on their play record, per rating category and over all time or the trailing 18 months — gh-74: imports carry each player's preliminary GW and VP, finals VP and a WD/DQ placement, and the event its round count (`wiki/vekn.md`, archondata format) — **Done when** the profile shows win rate (wins / events), GW per game and VP per game with withdrawn and disqualified events left out of the per-game figures and said to be, filterable by category and by the 18-month window, the per-game figures blank wherever an event's round count is unknown, and the play-record sentence in `wiki/product.md` lists them.
- Show each member's last-active date in the members directory — their latest event played or organised — with an "inactive for 18+ months" filter and the date in the CSV export for officials — gh-77: the directory filters by role and country (`frontend/src/lib/components/UserList.svelte:41-58`) but nothing shows activity, though every play record already lists events played and organised — **Done when** a member row shows the date of their latest finished event played or event organised, an official can filter the list to members with none in the last 18 months, the export carries the date, and the Members paragraph in `wiki/product.md` describes it.
