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

- Make clearing your contact email or phone on your profile actually remove it, tell every member who can see their contact, and keep every Prince and NC reachable — gh-69: a cleared field is sent as `undefined`, which `JSON.stringify` drops, so the PATCH arrives empty and the value is back on reload (`frontend/src/routes/profile/ProfileContact.svelte:79,85`), and only officials get the visibility note; on production 248 Princes and 14 NCs have only the imported email, 7 Princes nothing — **Done when** clearing either field and reloading shows it empty; a non-official's contact section says only they, IC and their country's NC can see it; an NC or Prince is refused removing their last channel (email, phone or Discord) with a message naming the alternatives, sees a banner when they have none, and a one-line nudge towards Discord when they have only one; and the email-of-record section of `wiki/access.md` states the one-channel floor.
- Let a league play its own final and crown its winner Champion instead of the standings leader ([context](board/league-final.md)) — **Done when** a league organiser can seat a final from the league's top five and enter its result on the league page, scored like a tournament final with seeds from league rank, a finished league crowns that final's winner (the standings leader when no final was played), and the Leagues paragraph in `wiki/product.md`, a "league final" row in `wiki/glossary.md` and the finals scoring section of `wiki/tournaments.md` state it.
- Give tied members the same rank on the rankings page, Hall of Fame and rating tabs alike (1, 2, 2, 4, tied rows ordered by name) — gh-68: rows are numbered by position (`frontend/src/routes/rankings/+page.svelte:233`) after a sort on the score alone — **Done when** two members with equal wins or equal rating points show the same rank and the next member's rank skips past them, and the Ratings and Hall of Fame paragraph in `wiki/product.md` says ties share a rank.
- Open the feedback form from every page, for members with a VEKN ID: from the side rail on desktop, and on phones by leading the Help page with it — gh-70, gh-78: the form only opens from the Help page (`frontend/src/routes/help/+page.svelte:84`), so every report arrives saying `Page: /help`, though the modal already records the current route (`frontend/src/lib/components/FeedbackModal.svelte:70`); the phone bottom bar has no room for a seventh icon — **Done when** a VEKN member can open the feedback form from the side rail on any page, the Help page leads with the feedback button, every filed issue names the page the member was on (the one they came from when filed from Help), the Help and feedback paragraph in `wiki/product.md` says so, and the feedback-triage skill no longer tells the reader to ignore `Page:`.
