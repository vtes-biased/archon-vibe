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
- Quote every value the deploy writes into the backend, public-API and bot env files, so the files load cleanly in bash — today an unquoted value containing spaces runs its second word as a command whenever a runbook loads the file with `set -a; .`, printing fragments of the mail password to the terminal and truncating it in that shell. **Done when** the three env templates write each value in single quotes and the deploy refuses a value that itself holds one, a beta and a prod deploy leave loading the file silent with every service still starting, the value-extraction command in `wiki/vekn-decommission.md` still yields a bare database URL, and the Deployment section of `wiki/dev.md` says the env files load cleanly in bash.
- Ship production's journal to Grafana Cloud through Fluent Bit — logs only, prod only, on the VEKN-owned Grafana Cloud stack; Fluent Bit rather than Alloy because the prod box has under 200 MB available. **Done when** a prod deploy leaves Fluent Bit running under a systemd memory cap with its measured footprint recorded, a Grafana query on the prod host returns the backend, bot and public-API units with the same `unit`/`tag`/`level`/`host` labels beta's Alloy emits, beta's server-setup Alloy is untouched, and the Deployment section of `wiki/dev.md` says where production logs live and how to read them.
- Let IC, and an NC for members of their own country, correct or clear who sponsored a member, from the member's page — the recorded sponsor today is whatever legacy archon or the VEKN sync's inference wrote, with no way to fix it. **Done when** an authorised official can set the sponsor to any live member holding a VEKN ID, or clear it, and anyone else is refused; the edit survives both a legacy-archon merge and a VEKN member sync (the co-opted-by inference respects the pin, so a cleared sponsor stays cleared); and `wiki/access.md` names who may edit it, the single-writer table and co-opted-by rule in `wiki/vekn.md` record the official edit, and `wiki/product.md`'s cooptation tracking says it is editable.
- Keep a list's search text when the viewer leaves it through the nav and comes back, as its filters already are — a player (gh-36) loses the search on every tab switch because `frontend/src/lib/last-view.ts` drops the query as transient, reversing the nav-menu memory rule of `wiki/design.md`'s list view state, which calls the query an intent rather than a view preference. **Done when** typing a search on Tournaments or Community, switching tab and clicking back reopens the list with the query in its box and the results filtered, the 30-minute window and per-tab scope still apply, the page number is still dropped, and that nav-menu memory bullet in `wiki/design.md` says the query is kept and why.
- Let an organizer open a seated player's deck straight from their seat in the Rounds tab — today it takes a detour through the Players tab and that player's card, mid-round. Opening a deck mid-event writes a view-log entry, so it must be a deliberate action, never a side effect of a tap meant for scoring or sanctions; the seat row is already dense, so the way in takes the least room that stays unambiguous (an existing tap target only if it has no other use there, otherwise one small control that fits the row on a phone). **Done when** an organizer can open, from a seat in the Rounds tab, that player's deck for that round (the round's deck in a multideck event, the single deck otherwise), a mid-event open records in the same view log as the Players tab, a seat with no deck gets no affordance, the row does not wrap on a phone, non-organizers see no change, and no wiki page changes (none lists where an organizer can open a deck, and the view log's audience in `wiki/sync.md` is unchanged).
- Show the size of the field next to each place on a member's events-played list, as their Ratings tab already does — a player (gh-38) asked for a deck's result to read as place out of field; the list prints `#5` with no denominator. **Done when** every row whose event has a known field size reads place / field size, the size comes from the engine's attested player count (never the round count, which reads zero for the whole rounds-less historic corpus), a row whose size is unknown keeps the bare place rather than "/ 0", and no wiki page changes (none describes the events-played row).
- Let the tournament list filter by a date window — a Prince (gh-41) wants to see every event in a given month; the list has no date filter. The first-viewport rule in `wiki/design.md` puts it inside the folded filter panel, one row of two native date inputs, nothing added in the open. **Done when** an optional from and to date (either alone works) keep only events whose start falls inside the window, in both the agenda and the all views; the pair counts in the fold's active-filter number and Clear filters empties it; both ride the URL and the remembered view like the other filters; the calendar-feed link ignores them; the list still reaches its first rows without scrolling on a 393×852 phone; and `wiki/product.md`'s list filters name the date window.
