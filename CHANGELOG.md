# Changelog

What changed in Archon, from a player's point of view — one line per change.
Internals, refactors and chrome are left out on purpose.

Written at deploy time by the `post-deploy` skill, newest first. Not every release
gets its own entry: an entry covers everything announced in one go, which is often
several releases at once.

<!-- New entries go directly below this line. -->

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
