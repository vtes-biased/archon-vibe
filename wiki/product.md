# Product

Archon is an offline-first PWA for running VTES tournaments and managing VEKN
membership. It replaces a legacy spreadsheet-based system with a mobile-friendly
tool that works in venues with poor connectivity.

**Core value**: an organizer can run a full event from their phone with no
internet, and results sync when connectivity returns.

**Out of scope by choice**: card rulings, a rules engine for the card game
itself, replacing the rulebook, and money handling beyond a payment status — see
[dogmas](dogmas.md#product). Organizational data is published to third parties,
read-only and under VEKN IDs rather than names.

## Who uses it

**Organizer / judge** (primary). A Prince, NC or IC running anything from an
8-player local event to a 100+ player continental championship, on a phone, under
time pressure, sometimes while playing. Organizers and judges have identical
permissions inside a tournament; an event can have several organizers, all equal,
with no head-organizer distinction. Pain points the app exists to remove: manual
seating calculation, VP validation errors, slow check-in, re-entering data when
the connection drops.

**Player**. A VEKN member on a phone: register, check in (including by QR), see
their table and seat each round, report their own table's VPs, watch standings,
upload a deck, view rating and history.

**VEKN officials**. NC manages Princes and national organized play; IC/Admin runs
the global organization. NC and IC implicitly act as organizers on tournaments in
their country; a Prince does not — it is a city-level role without that
oversight. Judge-call broadcasts reach the explicit tournament organizers only,
since they are the ones physically present.

VEKN judge certifications (Judge, Sheriff, Rulemonger)
are profile titles. They appear on member profiles and grant no extra power in
tournament management.

Who may do what: [access](access.md).

## Capabilities

**Auth and accounts** — email+password, magic link (signup / reset / invite),
passkeys, Discord OAuth plus Linked Roles, GitHub link (link-only, used to
@-mention a reporter on their feedback issue), JWT sessions with refresh.

**Members** — profiles with contact and socials, avatar upload, VEKN ID
claim/sponsor/link/abandon/force-abandon, the role set (IC, NC, Prince, Judge,
Sheriff, Rulemonger, Ethics, PTC, Playtester, DEV), playtest NDA click-to-sign
with sealed-PDF records gating the PT role and retrievable by the member from
their own Account tab, IC-only account merge, cooptation tracking,
privacy-filtered directory, in-memoriam flag for deceased members.

**Tournaments** — full config, the Planned→Registration→Waiting→Playing→Finished
state machine with reopen, registration and check-in, simulated-annealing seating
over nine priorities including staggered seatings for impossible player counts,
VP entry with oust-order validation, automatic GW/TP, judge override, standings,
finals qualification and toss, seating edits, round and tournament reopen/cancel,
delete, roster CSV export carrying each player's name, VEKN id, country and
region. Details: [tournaments](tournaments.md).

**Open rounds** — a non-VEKN house format gaining traction online: each player
plays up to `max_rounds` rounds of a continuously-run pool, so the event may run
more total rounds than any player plays. Optionally self-organized, where players
seat their own 4–5 pod. Never pushed to VEKN, never rated.

**Decks** — the card database in IndexedDB; upload by paste (local, offline),
deckbuilder URL (VDB / VTESDecks / Amaranth, backend-proxied, online only) or QR;
Rust parse and validation; attribution; decklist-required enforcement with
override; multideck decks stamped with the round they were played in and locked by
that stamp; post-tournament upload; visibility by `decklists_mode`; automatic TWDA
pull request on finish.

**Sanctions** — event-level (Caution, Warning, Standings Adjustment,
Disqualification) and VEKN-wide (Suspension, Probation, Ban), with Judges Guide v2
categories and escalation hints. Rules and visibility:
[tournaments](tournaments.md#sanctions).

**Leagues** — league and meta-league, standings modes RTP / Score / GP,
tournament association by league editors or by same-country Princes when the
league opts in, auto-updating standings, organizer Finish action and rank-1
Champion crowning.

**Ratings and Hall of Fame** — server-side rating from the best 8 tournaments in
a trailing 18 months, rating points in finished standings, a rankings page with
country and date filters, and a Hall of Fame for five wins that would have made
the TWDA with the winning deck on record
([the rule](tournaments.md#configuration)), stated on the page. A member profile
carries the wins behind the count and their decklists on record; your own also
lists the events you won with no decklist attached. The formula and the
standing warning about vekn.net's stored value are [domain](domain/vekn.md#ratings).

**Live-event surfaces** — shared round timer (online only, one global clock,
per-table extra time, client-side countdown), organizer announcements, call for
judge, raffle draws with an optional promo prize, promo catalog and distribution
reporting with an inventory ledger, table rooms, QR check-in, printable seating.

**Web Push** (opt-in) — seating on round start, announcements, and judge calls to
organizers. iOS requires Add-to-Home-Screen first. Discord-bot notifications serve
online events where Discord is the venue; Web Push serves in-person events. A
dual-audience user may get both for the same event — deliberate, no dedup.

**Social and discovery** — shareable finished-tournament image and text,
per-tournament and per-league Open Graph crawler stubs, iCal feeds (personal,
country, global), agenda matching, list filters including National/Continental
championship rank.

**Help and feedback** — in-app rulebook, VEKN tournament rules, Judges Guide v2,
Code of Ethics, and player/organizer guides; members with a VEKN ID can
file bug/feature/question reports that become GitHub issues carrying the VEKN ID
only, never name, email or Discord.

## Product behaviors

The rules themselves live in [domain](domain/tournament-rules.md); how the app
implements them, and where it differs, is [tournaments](tournaments.md). What
follows is the app's own behavior, chosen rather than inherited.

**The front door names the app before it filters it.** `/` is a landing page for a
signed-out visitor — what Archon is, and the two ways in: create an account, or
browse events without one. A visitor who already has a session goes straight to the
tournament list, as does the installed app on launch. Shape and the decisions
behind it: [design](design.md#landing).

**Tournament creation starts from the event, not the fields.** `/tournaments/new`
asks where it is played, what kind of event it is, where the games happen or what
happens at the door, and the deck rules — then hands over the ordinary
configuration form prefilled for that archetype, followed by the steps that need a
tournament to exist first. The plain form stays one click away. The long-running
open-round archetype is an **open series**, never a league: `/leagues` is a
different object. **There is no payment-tracking flag** — per-player payment
status is always present, and "paid or free" only steers the guidance, so a stored
flag would buy nothing but a hidden column.

**Rounds in parallel is the async-platform archetype.** Every round is live at
once and the same player sits in all of them, because a single round on a
play-by-email platform runs for weeks. It is not `open_rounds` — that flag is the
house format, and parallel seating has never needed it — and it leaves the round
timer off, a clock being meaningless over that span. Starting the next round
merely because a table finished early is possible and is not how the feature is
used.

**The door stays open mid-round.** Check-in is allowed while a round is `Playing`
and enrolls a never-registered player; it records presence, never seats. Whether a
late arrival joins a short table now or waits is the organizer's call — **the app
has no default and must not decide**. Mechanics and edge cases:
[tournaments](tournaments.md#player-states).

**An Archon registration is not always the entry.** An organizer who sells entry
on a ticketing platform sets `registration_url`, and a player who registers in the
app is then told so and sent there — the app records them for the organizer, it
does not book their seat. Nothing is prefilled from the wizard's "collected in
advance, somewhere else" answer: the link is a per-event fact the organizer
supplies, and the wizard only names the field. The same link is what tells the
console the paid list will arrive as a file, so the CSV import — always in the
tools sheet — also stands on the action bar for as long as registration is open.

**A registration is never refused.** Past the venue cap a sign-up lands on a
waitlist instead — barred from check-in until an organizer promotes it — and the
app never reorders that queue itself: it shows registration order and payment
status side by side and the organizer decides, because paid-but-waitlisted against
unpaid-but-registered is venue policy, not arithmetic.
Mechanics: [tournaments](tournaments.md#player-states).

**Decklist vs check-in** — when decklists are required, a player without one is
warned at check-in and the organizer may override and check them in anyway.

**Post-tournament deck upload** is allowed, for winner's-deck recovery and TWDA
submission. Post-finish, players may add but not replace.

**Online tournament player display** (frontend only): nickname is the primary
label, with the real name abbreviated to first word plus initials alongside the
VEKN id in parentheses. With no nickname the abbreviation is primary. The
organizer roster keeps the full real name. In-person tournaments show real name
and VEKN id only — the nickname is never shown.

**Visibility during an ongoing event** is organizer-set: standings Private /
Cutoff / Top 10 / Public, decklists Winner / Finalists / All applied only after
finish. These are display defaults, not access boundaries — see
[sync](sync.md#what-members-actually-receive).

## Reference material

The domain the product operates in is compiled into
[domain/](domain/tournament-rules.md) — the game, the tournament rules, judging,
and the VEKN organization — each claim citing its source.

Those sources are the official documents in `reference/`: tournament rules, Judges
Guide v1 and v2, Code of Ethics, the complete VTES rules, game-term translations,
and the rulebook PDFs. They are external artifacts, not ours to edit. The frontend
serves its own help pages from `frontend/src/lib/help-content/`.
