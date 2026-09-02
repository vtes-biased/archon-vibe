# Changelog

What changed in Archon, from a player's point of view — one line per change.
Internals, refactors and chrome are left out on purpose.

Written by the `changeset` skill before a release is cut, newest first, and
headed `## Unreleased` until `just release` stamps it with the tag and the date.
The app bundles this file and shows each reader the entries they have not seen, so
these are player-facing lines, not developer notes.

<!-- New entries go directly below this line. -->

## v1.1.2 — 2026-09-02

- A disqualification now applies only to the tournament it was issued at.
- Sanctions on a profile now link to their tournament.

## v1.1.1 — 2026-09-02

- Storyline tournaments.
- New front page for signed-out visitors.
- Tournament creation wizard.
- A tournament can now link the platform that takes its registrations.
- The tournament list now filters by championship rank.
- A tournament's players list can now be exported (CSV) with players' country and region.
- When adding a player, an already registered look-alike now shows in the search.
- Fixed TWDA sync.
- A tournament that vekn.net has since removed can now be deleted by its organizer.
- (testing) Playtesters NDA in-app.
- Self-registration over a tournament's cap now joins a waitlist.
- A member's profile is now split into tabs instead of one long page.
- Fixed a number of navigation, sync, and performance issues.

## v1.0.8 — 2026-08-24

- The winner's decklist from a tournament now reaches the TWDA archive.
- Invite links now last a week, and an expired one offers a fresh link.
- A member invited by email is no longer given a second account when they play at a venue.
- A tab that loses its live connection now notices and reconnects on its own.
- The offline indicator no longer claims you are online while the connection is retrying.
- The member and tournament lists load and filter far faster.
- A member created at the tournament desk now syncs to vekn.net.
- The winner reported to vekn.net is now the player who won the final, not the top seed.
- A tournament that ended without a final no longer pays its standings leader the winner's rating points.
- A disqualification recorded on vekn.net is kept when the tournament is imported.
- A registered player who never sat is no longer ranked among the field in an imported tournament.

## v1.0.7 — 2026-08-21

- The seating editor can now add and remove players from the round.
- Announcements and other notifications now read clearly on a phone.
- Sanctions past their 18 months expire on schedule.
- The deck archive picks up new TWDA entries daily.

## v1.0.3 — 2026-08-19

- The location for an event declared in the app is kept (not replaced by the vekn.net Antarctica venue anymore)
- The new-member button is offered only to the officials who can actually submit it.
- Fixed tournament display for logged-out visitors
- Cancelling rounds in a multiple-active-rounds tournament no longer strands rounds.
- Fixed an issue that prevented resolving some tie situations for finals seeding.
- Copying a tournament's results works offline.
- The Community page has been reworked: easier to curate, clearer display for all links.
- Search finds names with accented or crossed letters: typing "Pawel" now finds "Paweł".
- Escape closes every dialog.
- Fixed display issues on an installed phone app.
- The TWDA has been fully added, and the Hall of Fame recomputed based on it.
- Every tournament now has a short link of its own — `/t/CODE`. VEKN event IDs will outlive vekn.net this way.

## v1.0.2 — 2026-08-10

Covers v1.0.0 → v1.0.2.

- The tournament organizer console has been redesigned: the immediate actions more accessible, everything else moved into the Tools sheet, and the players tab is more compact.
- Check-in stays open once a round has started, so a latecomer can be added more easily.
- Dropping a player out is reversible.
- A judge playing at a table counts as a player at that table.
- Printed seating sheets show real names.
- Round count and open rounds are set on the create form, since VEKN fixes them when the event is created.
- Judge and Judgekin ranks lost in the move to Archon v2 are restored — 64 members.
- Your rating history shows where you finished in each tournament, over how many participants.
- Judge override made more accessible in odd VP cases (eg. Life Boon).
- Fixed rating points display - it now matches the ones on the profile.
- Limited National and Continental championships count as championships
- Member and card search were too slow, they are instant now.
- 423 tournaments whose end date fell before their start date are corrected
- A migrated tournament whose results had never reached vekn.net was unstuck and pushed.

## v1.0.0 — 2026-08-07

Archon v2 replaced the original app at archon.vekn.net. Accounts, tournament
history, leagues, sanctions and ratings all carried over. Sessions did not:
**everyone needs to sign in again** — Discord login unchanged, email logins need to reset password.

**Running an event**

- Offline mode: run a whole event with no internet at the venue, and it syncs back when you reconnect.
- Seatings and scores appear on every player's phone as they happen, with push notifications — no refreshing.
- One synchronized timer across all tables.
- Players can call a judge from their table.
- Announcements pushed to every player's screen.
- Table rooms: in a multi-room venue, seatings tell players where to go.
- Staggered rounds handle 6, 7 and 11-player tournaments transparently.
- Promos and raffles: track promo distribution and draw prize winners.
- Entry fees tracked with one click per player.

**Showing off an event**

- Tournament banners and social cards, so a shared link looks right on Discord, Facebook and Reddit.
- A personal agenda, and calendar feeds anyone can subscribe to.
- Standings visibility: keep them private, show the finals cutoff score, the top 10, or go fully public between rounds.
- Decklists editable in the app and published as the winner's, all finalists' or all of them — and sent to the TWDA automatically.

**Community**

- Community tab: forums, Discord and WhatsApp groups per country, plus an officials directory.
- A Hall of Fame, and live rankings filterable by country.
- Rulebook, tournament rules and judges guide in the app, with shareable links down to a single paragraph.
- Five languages — English, French, Spanish, Portuguese, Italian — plus light and dark themes.
- Send feedback from the Help section without leaving the app.
