# Changelog

What changed in Archon, from a player's point of view — one line per change.
Internals, refactors and chrome are left out on purpose.

Written by the `changeset` skill before a release is cut, newest first, and
headed `## v1.0.3 — 2026-08-19` until `just release` stamps it with the tag and the date.
The app bundles this file and shows each reader the entries they have not seen, so
these are player-facing lines, not developer notes.

<!-- New entries go directly below this line. -->

## Unreleased

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
