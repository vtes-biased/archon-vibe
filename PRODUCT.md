# Product Reference: Archon VTES Tournament Management

This is the authoritative product reference for agents and developers. It captures domain context, VEKN rules that affect the app, user workflows, and product direction.

## 1. What Archon Is

Archon is an **offline-first Progressive Web App** for managing VTES (Vampire: The Eternal Struggle) tournaments and VEKN (Vampire: Elder Kindred Network) membership. It replaces a legacy spreadsheet-based system with a modern, mobile-friendly tool that works reliably in venues with poor connectivity.

**Core value proposition**: A tournament organizer can run a full VTES event from their phone, even without internet, and results sync automatically when connectivity returns.

**What Archon does NOT do**: handle card rulings, provide a rules engine for the card game itself, or replace the VTES rulebook. It manages the tournament logistics layer.

## 2. User Roles & Personas

### 2.1 Tournament Organizer / Judge (Primary User)

**Profile**: A Prince, NC, or IC. Runs events ranging from 8-player local gatherings to 100+ player continental championships. Works under time pressure on a phone or tablet, sometimes while also playing. Only Princes, NCs, and ICs can create tournaments.

**In a tournament context, organizers and judges have identical permissions.** An event can have multiple organizers, all equal (no "head organizer" distinction in the app). The creator can add/remove other organizers.

**VEKN Judge Certifications** (profile titles, NOT elevated tournament permissions): **Judge** (certified VEKN judge), **Judgekin** (junior), **Rulemonger** (rules specialist). They appear on member profiles but grant no extra power in tournament management.

**Needs**: create/advertise tournaments (venue/date/format); add/remove co-organizers; register players + check-in; generate VEKN-compliant seatings; record + validate results; issue event sanctions; run finals qualification + seating; finish + report.

**Pain points**: manual seating calculations, VP validation errors, slow check-in at large events, re-entering data when connectivity drops.

### 2.2 Player

**Profile**: VEKN member attending tournaments, on a phone. Checks standings, views table assignments, reports own table results.

**Needs**: register for tournaments; check in (incl. QR); view table assignment + seat each round; report VP scores (players at a table can set scores; organizer override locks them); view standings during/after; upload deck when required; view personal rating + history.

### 2.3 VEKN Officials (NC, IC/Admin)

**Profile**: National Coordinators manage Princes and oversee organized play nationally. IC/Admin manages the global VEKN organization.

**CRITICAL: ICs (admins) always have full access to everything and all permissions, everywhere in the app.** When any access rule mentions Princes or NCs, ICs implicitly have the same or greater access.

**Needs**: sponsor new VEKN members; manage Prince/NC appointments; view all tournaments/results in jurisdiction; access player contact info (NC/Prince: same country; IC: all); view + manage sanctions.

**Implicit organizer access**: NC (and IC) implicitly act as organizers on tournaments in their country; a Prince does **not** — it's a city-level role without that oversight. Judge-call broadcasts reach the explicit tournament organizers only (not IC/NC), since they're the ones physically present.

## 3. VEKN Tournament Rules (App-Relevant Summary)

### 3.1 Tournament Configuration

| Setting | Values | Rules |
|---------|--------|-------|
| Format | Standard, V5, Limited | VEKN rules 6-7. V5 has specific decklist validation; Limited has no deck check (Draft events run as Limited) |
| Rank | Standard, National, Continental | National and Continental get a ranking points bonus |
| Proxies | Yes/No | Standard rank only |
| Multideck | Yes/No | Standard rank only; not for Nationals/Continentals |
| Decklist required | Yes/No | Organizer choice; VEKN recommends for ranked events |
| Online | Yes/No | Venue URL is meeting place |

**Ranking eligibility**: A tournament contributes to international rankings only if it has >= 8 players AND includes a final round. Tournaments with < 8 players or without finals are unranked (but can count for league standings).

### 3.2 Player Lifecycle

```
Not registered
  -> Registered (can register anytime while tournament is open)
    -> Checked-in (required before each round)
      -> Playing (assigned to a table)
        -> Finished (round complete)
          -> Back to Checked-in or Dropped

Player states (terminal/near-terminal):
- Completed  — reached per-player max_rounds cap; done with prelims, still finals-eligible
- Finished   — withdrew / dropped / tournament over (not finals-eligible)
- Disqualified — DQ sanction active

Player flags:
- non_competing — proxy player (§5.1.1): a non-competing official standing in for an absent player on a random stock deck. Seat plays normally; excluded from standings rank, rating, and finals. Score shown (not zeroed). Set/cleared by organizers via SetNonCompeting; blocked once finals are seeded or tournament Finished.

Barriers to check-in:
- Decklist required but not uploaded
- Player banned by VEKN
- Player disqualified from this event
- Player reached their per-player max_rounds cap (Open Rounds only)
```

### 3.3 Round Structure

**Minimum rounds**: 3 (2 preliminary + 1 final), per VEKN rules 3.1.

**Table composition** (VEKN rules 3.1.2):
- Groups of 4 and 5, maximizing tables of 5
- Impossible player counts: 6, 7, 11 (cannot form valid tables) — engine uses staggered seatings (bye rotation across rounds so everyone plays equally)
- Seating must be random and impartial

**Seating optimization priorities** (implemented in Rust engine):
1. No repeated predator-prey relationship (MANDATORY, per VEKN rules)
2. No pair shares a table in all rounds
3. Available VPs equitably distributed (4-player vs 5-player tables)
4. No pair shares a table more than necessary
5. No player sits in 5th seat more than once
6. No pair repeats the same relative position
7. No player repeats the same seat position
8. Starting transfers equitably distributed
9. No pair repeats the same relative position group

**Time limit**: Minimum 2 hours per round. Finals may be longer.

**Tournament without final**: Allowed for any tournament (must be announced before the first round). Such tournaments are not ranked internationally — they can only count for league standings.

### 3.4 Scoring System

#### Victory Points (VP)
- 1 VP for each prey ousted
- 0.5 VP for surviving to time limit (not last player)
- 1 VP for being last player standing (normal rules)
- 0.5 VP for withdrawal (not 1 VP as in casual rules)

#### Game Win (GW)
- Requires: VP >= 2.0 AND strictly highest VP at table (no ties)
- Finals exception: Winner gets GW regardless of VP count

#### Tournament Points (TP)
- 5-player table: 60, 48, 36, 24, 12 (1st through 5th by VP)
- 4-player table: 60, 48, 24, 12 (3rd position is empty "table bye")
- Ties: Average TP across tied positions

#### VP Validation
The engine validates that VP combinations match a physically possible oust sequence around the table (considers seating order / predator-prey). See TOURNAMENTS.md for the algorithm.

### 3.5 Finals Qualification

After preliminary rounds, top 5 players qualify. Ranking order:
1. Game Wins (GW)
2. Victory Points (VP) total — tiebreaker
3. Tournament Points (TP) — second tiebreaker
4. Random (toss) — for remaining ties in top 5

Organizers must drop unavailable finalists before launching finals. If a top-5 qualifier withdraws (state `Finished`), `StartFinals` excludes them and auto-promotes the next-ranked qualifier. `Completed` (capped) players remain finals-eligible and are not excluded. Non-competing (proxy) players are excluded from finals qualification entirely — they do not appear in the top-5 candidate pool.

Published preliminary standings rank GW > VP > TP using competition ranking with skips (tied players share a place; the next place is skipped). The random toss resolves only a tie straddling the top-5 finals cutoff — it never re-orders tied players elsewhere in the standings.

### 3.6 Finals Seating Procedure

**Not** algorithm-assigned. Finalists choose seats in a specific order:

1. Each finalist shuffles their crypt; judge draws 3 random cards (public info)
2. Starting with lowest qualifier (#5), each places their name card at either end of a row, OR in a gap between two already-placed cards
3. Read left-to-right for final seating positions
4. Judge randomly determines who plays first

### 3.7 Finals Scoring

- Highest VP in finals = tournament winner
- Tie for highest VP: preliminary standings break the tie
- All other finalists tied for 2nd (no further ranking among them)
- Winning the finals counts as a GW even with < 2 VP

### 3.8 Sanctions

#### Event-Level Sanctions (issued by organizers/judges during a tournament)

| Level | Visibility | Effect |
|-------|-----------|--------|
| Caution | Private to its tournament | Verbal warning, tracked during the event for pattern detection. Never shown on member pages or in other events — visible only inside its own tournament |
| Warning | Member page + other events, 18 months | Tracked in VEKN database, visible to future organizers |
| Standings Adjustment | Member page + other events, 18 months | -1 VP penalty applied to current/next/previous game depending on timing (v2 Judges Guide) |
| Disqualification | Member page + other events, 18 months | Dropped from tournament (player state → Disqualified), prevents further check-in; bars sibling events of the same league |

**Infraction categories** (from v2 Judges Guide — tracked per sanction):
- Procedural Errors (2.x): Missed Mandatory Effect, Card Access Error, Game Rule Violation, Failure to Maintain Game State
- Tournament Errors (3.x): Deck Problems, Outside Assistance, Slow Play, Limited Procedure Violation, Public Info Miscommunication, Obscuring Game State, Marked Cards, Insufficient Shuffling
- Unsportsmanlike Conduct (4.x): Minor, Major, Aggressive Behaviour, Bribery & Wagering, Theft, Stalling, Cheating, Fraud, Collusion, Health & Safety, Rage-Quitting, Failure to Play to Win

#### VEKN-Wide Sanctions (issued by Ethics Committee)

| Level | Scope | Effect |
|-------|-------|--------|
| Suspension | VEKN-wide, time-limited | Banned from all sanctioned events. Up to 18 months. Forfeits all VEKN roles for 2x duration |
| Probation | VEKN-wide, up to 12 months | Retains privileges, but any further violation triggers mandatory suspension. Once per career |
| Ban | VEKN-wide, permanent | Implemented as suspension without end date. Removed from ratings |

**On-site sanction**: A head judge can issue an immediate 30-day national suspension for gross ethics violations. Must be escalated to Ethics Committee within 5 days or it's lifted. See `reference/code-of-ethics.md`.

#### Visibility Rules

- **Caution**: belongs to the tournament where it was issued — shown only in that event's context (the sanction dot next to the player). Hidden on member pages (member detail, members list, the "sanctioned" filter) and in other events — for everyone, including IC/Ethics, who see it inside the tournament instead.
- **Warning / SA / DQ**: visible on the member detail page and members list, and in other tournaments' context, for **18 months** from issuance.
- **Suspension / Probation**: membership-level, always visible; a permanent ban (suspension without expiry) stays visible past 18 months.
- IC/Ethics see all levels on every surface. The filtering is a display rule — all sanction records sync to all members' clients (member access level).

#### Permissions

| Action | Caution / Warning / SA / DQ | Suspension / Probation |
|--------|-----------------------------|------------------------|
| Issue | IC, Ethics, or an organizer of the tournament | IC, Ethics |
| Lift | IC, Rulemonger, NC of the tournament's country; a league organizer for a DQ in their league event | IC (Ethics for modify) |
| Edit fields | IC, Ethics | IC, Ethics |
| Delete (soft) | IC, Ethics — plus the tournament's own organizer **while the event is not Finished** (mistake correction: delete + reissue; organizers cannot edit) | IC, Ethics |

Single source: `engine/src/permissions.rs` (`can_issue_sanction`, `can_lift_sanction`, `can_delete_sanction`), consumed by the backend (PyO3) and frontend (WASM).

#### Lifecycle Effects

- **DQ ↔ player state**: issuing a DQ sets the player to Disqualified on the tournament; lifting or deleting an active DQ restores them (Finished). Standings recompute immediately on DQ create (and on lift/delete).
- **DQ standings effect**: DQ'd players appear last in standings with VP/GW/TP zeroed (forfeited) and no numeric rank. Opponents keep all scores earned at their table. DQ'd players earn no rating points (no participation base, no finalist bonus, no rating-history entry). Player count for the rating coefficient stays inclusive of DQ'd players (tournament-rules A.2).
- **Probation requires an expiry** (≤ 18 months); suspension expiry is optional — none means permanent ban.
- **Cleanup job (daily)**: sanctions expired for over 18 months are soft-deleted; soft-deleted records are hard-deleted after 30 days (a mistaken organizer delete stays recoverable by IC in that window).
- **Active suspension** blocks check-in/registration in any sanctioned event and blocks self-abandoning the VEKN ID; sanctions stay attached to the VEKN record through account merge/detach (see ARCHITECTURE.md).

### 3.9 Special Situations

- **Late arrivals**: Can be added mid-tournament, play from next round
- **Drops during seating**: 5-player table becomes 4-player; 4-player table requires redistribution
- **Multideck finals**: Best-Performing Deck method or Free Choice method (announced pre-tournament)
- **Multiple organizers**: Events can have multiple organizers (all equal permissions). Organizers can also play in the event

## 4. Data Access Model

Three data levels control what each connected client sees:

| Level | Who | Gets |
|-------|-----|------|
| Public | Unauthenticated / no VEKN ID | Prince/NC list (with contact), minimal tournament info |
| Member | Has VEKN ID | All users (no contact info), sanctions, tournaments with standings/own tables/filtered decks |
| Full | IC (always, everywhere), NC/Prince (same country), organizer | Everything: all rounds, finals, check-in codes, contact info |

### Tournament Field Visibility (Member Level)

**Access is enforced per-row, not per-viewer.** Each object stores three pre-computed
projection columns (public/member/full); SSE reads the matching column. There is no
per-viewer field filtering at read time. Consequently the member projection of a
tournament (`compute_tournament_member`) ships the **entire** tournament object — all
rounds, finals, and per-player results — to **every** member, excluding only
`checkin_code` and `vekn_pushed_at`. During an ongoing event, full structural data
lands in every member's IndexedDB.

Two real server-side boundaries do exist within the member level:
- **Decks** are a separate object type with their own per-deck member projection — a deck
  is shipped only when the engine sets its `public` flag (from `decklists_mode` +
  tournament state + winner/finalist status). This row *is* an access control.
- **`checkin_code` / `vekn_pushed_at` / `vekn_results_stale`** are stripped from the member projection.

Everything else below is a **frontend display default**, not an access boundary —
`standings_mode` (Private/Cutoff/Top 10/Public), the "my tables" view, and the
ongoing-event hiding of per-player results are rendered by the client off data it
already holds. They shape the UI; they do not gate what a member can read from IndexedDB.

| Field | Server boundary? | Display default (frontend) |
|-------|------------------|----------------------------|
| Config | — (always shipped) | shown |
| Players | No (full per-player data shipped) | per-player results hidden mid-event |
| Standings | No | per `standings_mode` |
| Decks | **Yes** — per-deck `public` flag (`decklists_mode`) | — |
| Finals | No (shipped) | hidden until finished |
| My tables | No (all tables shipped) | only the viewer's own tables shown |
| Rounds | No (shipped) | hidden |
| checkin_code / vekn_pushed_at / vekn_results_stale | **Yes** — stripped | — |

This is an accepted tradeoff: viewer-specific visibility ("my tables") cannot be expressed
in pre-computed per-row columns, and frontend hiding suits the threat model (a local-event
attendee is not expected to crack open IndexedDB to influence standings). Making any of the
display defaults a real boundary would require a per-player overlay — more complexity than
the risk warrants. Treat the matrix as UI defaults, not a security guarantee.

### Anonymous (not-logged-in) Display Gates

A further frontend display layer gates on `getAuthState().isAuthenticated`. Not-logged-in
visitors see a reduced UI — these are **frontend-only gates, not backend access-control
boundaries**. The `public` projection is unchanged: officials' contact info (contact_email /
contact_phone, base64-obfuscated via `_obfuscate_public_contacts`) still flows over SSE and
into IndexedDB for anonymous viewers. Officials are meant to be reasonably contactable so
newcomers can join the association; the obfuscation is a harvest speed-bump, not access
control. Do not "fix" this by stripping the public projection — that reverses a deliberate
decision.

| Surface | Logged-out display | Backend data on wire? |
|---------|--------------------|-----------------------|
| Community tab — Officials Directory | Hidden | Yes (public projection) |
| Members tab / UserList | Replaced by sign-in prompt | Partial — officials + link-holders only; full roster is member-level |
| Tournament list | Current + upcoming only (`state !== 'Finished'`) | Yes (full list in IndexedDB) |
| League list | Active only (`showPast=false`, toggle hidden) | Yes (full list in IndexedDB) |
| Finished tournament detail (`/tournaments/{uid}`) | Accessible (direct link / og:image crawl) | Yes |

The `.ics` calendar feeds are a further deliberate exception: anonymous (no-token) feeds render
venue/address into LOCATION from the full column even though those fields are member-level in the
projections — the calendar is an advertising artifact mirroring vekn.net's public event calendar
(which shows full addresses anonymously); venue granularity is the organizer's data-entry choice.

## 5. Feature Map

A compact map of what exists; implementation detail lives in code and the docs in §9. **Outstanding/planned work is tracked in pst tickets, not here** — that previously included the Discord tournament bot, tournament audit logs, Draft/Limited pod support, multi-day events, auto-close, deck statistics, and spectator mode.

- **Auth & accounts**: email+password, magic link (signup/reset/invite), passkeys, Discord OAuth + Linked Roles (auto-assign VEKN roles), JWT sessions with refresh.
- **Members**: profiles (name, country, city, socials, contact), avatar upload (client crop + server compress), VEKN ID claim/sponsor/link/abandon/force-abandon, roles (IC, NC, Prince, Judge, Judgekin, Rulemonger, Ethics, PTC, Playtester, DEV), same-country user merge, cooptation tracking, privacy-filtered directory.
- **Tournament core**: full config (format/rank/proxies/multideck/online/venue/dates/tz/country/max_rounds), state machine Planned→Registration→Waiting→Playing→Finished (+reopen), registration + check-in (single/all/reset), simulated-annealing seating (9 priorities) incl. staggered seatings for 6/7/11, VP entry with oust-order validation, GW/TP auto-compute, judge override/unoverride, standings (GW>VP>TP), finals qualification + manual/random toss, finals AlterSeating, round/registration/tournament reopen + cancel, delete (Planned only). **Open Rounds** (`max_rounds > 0`): per-player cap — each player plays up to `max_rounds` rounds of a continuously-run pool; the tournament MAY run more total rounds than `max_rounds`; players hit their cap individually and move to state `Completed` (finals-eligible). Non-VEKN format gaining traction online. `max_rounds = 0` = no cap.
- **Seating editor**: tap-to-swap/move (tap player then tap target seat; same table = reorder, cross-table = swap, open seat = move), per-player issue indicators (sanction; deck/payment deliberately not shown on seat rows), Swap/Seat/Unseat/AddTable/RemoveTable/AlterSeating (prelim + finals).
- **Round timer** (online): global start/pause/reset, per-round/finals config, per-table extra time (cap 600s), client-side countdown (no per-second broadcasts). Deliberately online-only and hidden for parallel rounds — offline venues and async pods rely on the wall clock (owner decision; no per-table timer model planned).
- **Call for judge** (online): ephemeral SSE alert to organizers + IC, stacking banners + chime, auto-dismiss 120s, validates seated/Playing/online.
- **Raffle**: random draw from pools (AllPlayers/NonFinalists/GameWinners/NoGameWin/NoVictoryPoint), draw/undo/clear.
- **Table rooms**: named rooms over table ranges, shown as labels in seating/print/player views.
- **Decks**: card DB in IndexedDB; upload via paste (local, offline) / deckbuilder URL (VDB/VTESDecks/Amaranth, backend-proxied via krcg, online only) / QR (URL-scan shortcut, online only); Rust parse (Lackey/JOL/TWDA) + validate (counts, banned, group, V5, multideck) + enrich; attribution (self/named author/anonymous); decklist-required enforcement (override w/ warning); multideck per-round locking; post-tournament upload; visibility by decklists_mode (Winner/Finalists/All); TWDA auto-PR on finish.
- **Result reporting**: player self-report VP during round; organizer override locks the table (comment required); oust-order validation; text/JSON report download (organizer).
- **Sanctions**: event-level (Caution/Warning/SA/DQ) + VEKN-wide (Suspension/Probation/Ban, IC/Ethics); JG v2 categories + escalation hints; SA −1 VP; league-wide + suspension barring at check-in/finals; lift permissions per §3.8; daily cleanup of >18mo. (Rules: §3.8.)
- **Leagues**: league + meta-league (NC/IC); standings modes RTP/Score/GP; organizer-filtered tournament association; auto-updating standings; finish-without-finals support.
  - *GP (Grand Prix) standings* — an established league-scoring convention (not part of the hard VEKN tournament rules). Points by final placement: Winner 25; 2nd–5th (finalists) 15; 6th 10; 7th 9; 8th 8; 9th 7; 10th 6; 11th+ 3. Ties take best-position points with competition skip (two tied for 6th each get 10; next is 8th) — never averaged. Position is FINAL placement (winner=1, other finalists tie 2nd, non-finalists by prelim GW/VP/TP), not prelim array order.
- **Ratings & HoF**: server-side rating = best 8 tournaments in trailing 18mo (§8); RP in finished standings; rankings page (top 500, country/date filters, bulk-load); Hall of Fame (5+ wins); suspended hidden; daily recompute.
- **Payments**: per-player status (Pending/Paid/Refunded/Cancelled), SetPaymentStatus/MarkAllPaid, shown in registration list. Deliberately status-only — no fee amounts or money reconciliation in-app; if richer money handling is ever needed, integrate a ticketing platform rather than building a ledger.
- **QR check-in**: organizer-displayed tournament QR (printable), in-app camera scan self-check-in (`POST /{uid}/qr-checkin`).
- **Web Push notifications** (opt-in): three notification types — (1) individual seating push to each newly-seated player on round/finals start (`StartRound`/`SelfOrganizeRound`/`StartFinals`; not `RestoreRound`); (2) announcement push to all checked-in participants (except the poster) on `POST /{uid}/announce`; (3) judge-call push to the tournament's organizers (except the caller) on `POST /{uid}/call-judge` — the highest-urgency type, alerting a judge who's away from the screen. Opt-in gated behind live-tournament involvement (per-tournament `PushOptIn.svelte` card, with player or organizer copy) plus a profile-level toggle. iOS requires Add-to-Home-Screen (standalone PWA mode) before push is available — a nudge is shown to iOS users not yet in standalone. The judge call is the one organizer-facing push; still deferred: timer warnings (would need a server-side timed scheduler), sanction/DQ notifications, other organizer-facing pushes. Discord-bot notifications serve online events (Discord is the venue) while Web Push serves IRL events — a dual-audience user may receive both for the same event; deliberate, no dedup.
- **Social & discovery**: shareable finished-tournament PNG + text; iCal feed (personal via calendar_token / country / global, online toggle; token stripped from SSE); agenda matching; tournament list filters (country/format/search, My Agenda, include-online).
- **Printable views**: round seating, QR (`@media print`, page breaks).
- **Help**: in-app VTES rulebook, VEKN tournament rules, Judges Guide v1+v2, Code of Ethics, player/organizer guides (source in `frontend/src/lib/help-content/`), paginated viewer with TOC.
- **Feedback**: members with a VEKN ID submit bug/feature/question reports from the Help page (no VEKN id → no feedback, so every issue carries an identifiable reporter); filed as GitHub issues on `vtes-biased/archon-vibe` via a dedicated server-side GitHub App (Issues-only, separate from TWDA's). Rate-limited (60s cooldown, 10/day). Issue body includes the VEKN ID only (public on vekn.net); never name, email, or Discord. Unconfigured → 503 (graceful degradation).
- **VEKN integration**: outbound push (calendar on create, results on finish, hourly catch-up), inbound member sync (~6h, infers coopted_by), inbound tournament sync (venue seeding), member push on sponsor; format→event-type mapping; `external_ids["vekn"]`/`vekn_pushed_at`; `max_rounds` immutable once pushed (Open Rounds is non-VEKN and not pushed to VEKN). The results push is **write-once**: once successfully pushed, vekn.net cannot be updated or corrected through the API — post-push corrections require manual admin fixes on vekn.net. A post-push result change (reopen + rescoring, or an SA/DQ-driven standings recompute) sets the sticky `vekn_results_stale` flag, surfaced to organizers as an "Out of sync with vekn.net" header badge (see VEKN_SYNC.md).
- **OAuth2 provider**: PKCE auth-code flow, OIDC userinfo, client management (DEV role), consent persistence, scopes `profile:read` / `user:impersonate`, Argon2 secrets + refresh-token rotation + revocation, scheduled token cleanup.
- **Offline mode**: single primary-device ownership; others read-only "offline"; force-takeover (data-loss warning) + IC force-unlock; go-online pushes full authoritative state (no CRUD log); offline member creation with temp UIDs (`TEMP-` placeholder VEKN ids) remapped on sync; SSE suppressed while offline.
- **Infrastructure**: PWA + service workers (update detection); IndexedDB for all reads (5 stores + cards); SSE with 3 precomputed access levels (public/member/full); personal/role overlays; optimistic WASM updates; resync on role/VEKN-ID change; 15-min gzip snapshot endpoint; Web Push (VAPID, opt-in, server-side `push_subscriptions` side table); i18n EN/FR/ES/PT-BR/IT (Paraglide, browser auto-detect) + locale switcher; GeoNames autocomplete; scheduled jobs (VEKN sync/push, sanction cleanup, rating recompute, OAuth cleanup, snapshot, deleted-objects purge).

## 6. Technical Constraints & Design Decisions

### 6.1 Architecture Pillars (from Principal Engineer)

1. **Offline-first is non-negotiable**: All UI reads from IndexedDB. Backend API handles mutations only. SSE pushes state changes.
2. **Shared Rust mutation pipeline**: All business logic in Rust, compiled to WASM (frontend) and PyO3 (backend). No business logic in Python or TypeScript.
3. **Server is source of truth**: Optimistic local updates; SSE delivers authoritative state; client always accepts server corrections.
4. **KISS and DRY**: Simple data model (single JSONB table), no over-abstraction, minimal dependencies.

### 6.2 UX Principles (from Staff Frontend Engineer)

1. **Mobile-first**: Minimum 44x44px touch targets, no hover-only interactions, bottom navigation
2. **Auto-save**: No explicit save buttons; changes sync immediately
3. **Progressive disclosure**: Essential info default, details on demand
4. **Self-discoverable**: Clear labeling, contextual hints, good empty states
5. **Reversibility over confirmation**: prefer making actions cleanly reversible to adding confirm dialogs (no confirmation bloat); reserve explicit confirmation for genuinely irreversible or external effects (e.g. finishing → write-once VEKN push, removing your own organizer access)

### 6.3 Design System

Gothic horror / Vampire aesthetic. Dark mode primary. Colors: crimson (accent), bone (backgrounds), dusk (surfaces), ash (text/borders), mist (muted). See `frontend/DESIGN.md`.

### 6.4 Internationalization

Five languages: EN (British), FR, ES, PT-BR, IT. Official VTES game terms must use translations from Black Chantry rulebooks (reference: `reference/game_terms.json`).

## 7. Key Domain Edge Cases

Behaviors the app must get right that go beyond the headline rules in §3.

### Scoring & VP
- **Player drops mid-round**: a 5-player table becomes 4-player; the dropped seat is marked finished with 0 VP and the predator gets **no** VP (administrative removal, not an oust). Same for a mid-game DQ.
- **Intentional draw**: all players agree to accept current scores as if time expired (VEKN 3.6); each survivor gets 0.5 VP.
- **Concession cascade**: when all-but-one concede, the remaining player is treated as ousting them in sequence.
- **Fractional VPs**: always multiples of 0.5; `table_size − 0.5` is impossible (e.g. 4.5 on a 5-player table).
- **SA penalty**: a full −1 VP for the penalized round, applied uniformly wherever VP feeds scoring — GW determination, TP rank (the table re-ranks/re-averages, JG v2 1.1.3 Ex. 2), and the standings VP total used for finals seeding. Standings recompute GW/TP from the adjusted VPs, so an SA issued *after* the round was scored still re-decides the GW and re-ranks TP, not just the total. May go negative; the per-round VP displayed stays raw; never carried to another round.

### Finals
- **<5 available finalists**: the organizer must drop unavailable qualifiers before launching finals (app-enforced).
- The physical card-drawing seating procedure (§3.6) is recorded via AlterSeating, not enforced by the app.

### Tournament lifecycle
- **Event becomes unsanctioned**: if drops create an impossible player count between rounds and staggered seatings don't apply, the event may lose sanctioning but can still distribute prizes and report.
- **Reopen**: a finished tournament can be reopened to correct scores; ratings recompute on the next finish.
- **Cancel round**: returns players to Checked-in.
- **Late registration**: players may register after round 1 and play from the next round; fewer rounds for standings but can still qualify.

### Sanctions
- **Escalation guidance**: the app suggests an appropriate level by category/subcategory and warns when issuing below an existing level (e.g. two cautions → third should be a warning).

### Offline
- **Single ownership**: one device owns an offline tournament; others are read-only. Force-takeover loses the primary's unsynced data; IC force-unlock skips syncing.
- **Offline member creation**: temp UIDs (`TEMP-` placeholder VEKN ids), remapped to real VEKN IDs on sync (updated immediately if SSE delivers the real UID while still offline).

### Decks
- **Decklist vs check-in**: when decklists are required, players without one are warned at check-in; organizers can override and check in anyway.
- **Multideck locking**: a round's deck locks once that round starts; the next round's deck can still be uploaded beforehand.
- **Post-tournament upload**: decklists can be added after finish (winner's-deck recovery, TWDA submission).
- **Attribution**: self, another member as author, or anonymous — public display respects the choice.

### Visibility
- **Standings during ongoing events**: organizer-set Private / Cutoff / Top 10 / Public (manages information asymmetry).
- **Decklists**: organizer-set Winner / Finalists / All, applied only after finish.
- **Self-reporting window**: players set scores during the round until an organizer override locks the table.
- **Online tournament player display** (frontend only): nickname is the primary label; real name abbreviated as first word + remaining initials (e.g. "Lionel MP") alongside VEKN id in parens. No nickname: abbreviation is primary. Organizer Players-tab roster keeps the full real name. Offline (IRL) tournaments: real name + VEKN only — the nickname is never shown.
- Member-level field visibility and its security caveats: see §4.

### VEKN
- **VEKN IDs required to push**: results can't be pushed until every player has a `vekn_id`; organizers sponsor/link first.
- **Fire-and-forget**: pushes never block user actions; an hourly batch catches misses. `max_rounds` is immutable once pushed (Open Rounds tournaments are non-VEKN and not pushed).

## 8. VEKN Rating System (Reference)

Rating = sum of best 8 tournaments in trailing 18 months.

Per tournament (DQ'd players earn zero — no entry created):
- 5 RtP for attendance
- 4 RtP per VP scored
- 8 RtP per GW (including final round victory)
- Finalist bonus: `Points * Coefficient`
  - Winner: 90 points, Finalist: 30 points
  - Coefficient: `log15(NumPlayers^2) - 1` — NumPlayers includes DQ'd players (tournament-rules A.2)
  - +0.25 for National Championship
  - +1.0 for Continental Championship

Player removed from rankings after 12 months of inactivity; rating preserved indefinitely.

## 9. Reference Documents

| Document | Location | Content |
|----------|----------|---------|
| Tournament Rules | `reference/tournament-rules.md` | Official VEKN tournament rules (complete) |
| Judges Guide v1 | `reference/judges-guide.md` | Original judges guidelines (2004) |
| Judges Guide v2 | `reference/judges-guide-v2.md` | Updated Tournament Conduct & Infraction Guide (2026) |
| Code of Ethics | `reference/code-of-ethics.md` | VEKN Code of Ethics v1.5 |
| Archon Help | `reference/archon-help.md` | User-facing help text for the Archon platform |
| Game Terms | `reference/game_terms.json` | Official VTES game terminology translations (EN/FR/ES/PT-BR/IT/JP/LATIN) |
| Rulebooks | `reference/rulebooks/` | Official VTES rulebook PDFs in multiple languages |
| Help Content | `frontend/src/lib/help-content/` | Frontend-served help pages (VTES rules, tournament rules, judges guide, ethics, player/organizer guides) |
| Architecture | `ARCHITECTURE.md` | Technical architecture reference |
| Sync | `SYNC.md` | SSE streaming and IndexedDB sync patterns |
| Tournaments | `TOURNAMENTS.md` | Tournament system implementation details |
| Design | `frontend/DESIGN.md` | UI design guidelines |
