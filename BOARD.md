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

- **Let officials find players without a VEKN ID from the Members search.** For a viewer who can sponsor, the name search (`frontend/src/lib/components/UserList.svelte:203`) also returns the non-members they may list, marked No VEKN with the Sponsor action, instead of only under the No VEKN toggle; and a countryless non-member (signup collects no country) becomes listable by any NC or Prince, not IC alone (`engine/src/permissions.rs:310`). A Prince could not find a new player to sponsor. Done when a Prince's name search finds a fresh countryless signup and sponsors it, with the `list_non_member` row and paragraph in `wiki/access.md` and the "find your account in the Members page" help text updated. gh-64
- **Show a sanction's full description on the member page, and bound it at input.** `SanctionsManager.svelte:244` prints the description with `truncate`, so anything past one line is lost; the full text only exists in the badge's hover `title` (`SanctionBadge.svelte:46`), out of reach on touch and undiscoverable with a mouse. Let it wrap, keeping line breaks and breaking long unbroken strings (`overflow-wrap: anywhere`). Nothing bounds the text today (`backend/src/routes/sanctions.py:254,264`): cap `description` at 2000 characters on the create and update requests only, so migrated rows still decode, with a matching `maxlength` on the sanction form's textarea (gh-62, a Sheriff reading a player's sanction). **Done when** a multi-line description and a 300-character unbroken string both read in full on `/users/[uid]` at phone width without horizontal scroll, and a 2001-character description is refused with 400. Doc-impact: none, layout and input validation only.
- **List a member's organised events on their profile.** Under the events-played record on the member page and `/profile`, show every tournament whose organisers include the member — any state, newest first, deleted ones excluded — read from the local tournament index (`organizers_uids`, `frontend/src/lib/db.ts:748`). Asked for by a Prince/Judge who looked for their own events in the Agenda (gh-50). **Done when** a Prince's profile lists the events they organised, VEKN-synced ones included, and the Members paragraph of `wiki/product.md` names the list.
- **Let the tournament list show online events only, and remember the choice.** Turn the "Show online events" switch (`includeOnline`, `frontend/src/routes/tournaments/+page.svelte:109`) into all / no online / online only, in both the full list and the Agenda, with `?online=only` in the URL (gh-54, a Prince). Remember the choice per viewer like the agenda/all view preference, the URL winning over it (gh-61, a Sheriff who wants it to stick in their Agenda). **Done when** "online only" lists just online events in both views, the choice survives a reload and a fresh visit without the URL parameter, and the Calendar paragraph of `wiki/architecture.md` says whether feeds carry it.
- **Split the tournament list into Upcoming and Past tabs.** The state filter (`frontend/src/routes/tournaments/+page.svelte:89,127`) hides "finished" inside the Filters modal (`:762`), so the default "all" list makes a member scroll about three pages of the 156 upcoming and in-progress events before the past divider (`:499`, `sortUpcomingFirst` at `frontend/src/lib/db.ts:911`); and "upcoming" keeps every Playing/Waiting event from any earlier date (`db.ts:877-884`), so 18 abandoned events back to June head it. Replace it with two tabs above the list, shown in both the Agenda and All views and to logged-in members only: Upcoming (events dated today or later plus live ones — in progress and started within the last two days — ascending, the default) and Past (finished events and older unfinished ones, which keep their state badge, newest first). Retire "all", its divider and the separate "ongoing" choice, and keep the choice in the URL (gh-58, a Sheriff; gh-66, a player). **Done when** a logged-in member reaches finished events in one tap from `/tournaments`, no event older than two days leads Upcoming, the Filters modal has no state select, logged-out visitors see no tabs, and the list-filters sentence in `wiki/product.md` (Social and discovery) names the tabs and the two-day live window.
- **Filter the rankings by city.** The rankings page (`frontend/src/routes/rankings/+page.svelte:29,152`) filters by country only, which is too coarse for a playgroup in a large country. Once a country is picked, offer a city select listing the cities of that country's ranked members, matched on `city_geoname_id` (`backend/src/models.py:315`), re-ranking from 1 as the country filter does, carried in the URL and applied to the Hall of Fame tab too (gh-63, a Brazilian Prince). **Done when** picking Brazil then São Paulo lists only members with that GeoNames city, numbered from 1, the choice survives a reload, and the rankings sentence in `wiki/product.md` (Ratings and Hall of Fame) names the city filter.
