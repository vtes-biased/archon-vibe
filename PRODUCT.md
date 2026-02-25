# Product Reference: Archon VTES Tournament Management

This is the authoritative product reference for agents and developers. It captures domain context, VEKN rules that affect the app, user workflows, and product direction.

## 1. What Archon Is

Archon is an **offline-first Progressive Web App** for managing VTES (Vampire: The Eternal Struggle) tournaments and VEKN (Vampire: Elder Kindred Network) membership. It replaces a legacy spreadsheet-based system with a modern, mobile-friendly tool that works reliably in venues with poor connectivity.

**Core value proposition**: A tournament organizer can run a full VTES event from their phone, even without internet, and results sync automatically when connectivity returns.

**What Archon does NOT do**: Archon does not handle card rulings, provide a rules engine for the card game itself, or replace the VTES rulebook. It manages the tournament logistics layer.

## 2. User Roles & Personas

### 2.1 Tournament Organizer / Judge (Primary User)

**Profile**: A Prince, NC, or IC. Runs events ranging from 8-player local gatherings to 100+ player continental championships. Works under time pressure on a phone or tablet, sometimes while also playing. Only Princes, NCs, and ICs can create tournaments.

**In a tournament context, organizers and judges have identical permissions.** An event can have multiple organizers, all equal (no "head organizer" distinction in the app). The creator can add/remove other organizers.

**VEKN Judge Certifications** (profile titles, NOT elevated tournament permissions):
- **Judge**: Certified VEKN judge
- **Judgekin**: Junior judge certification
- **Rulemonger**: Rules specialist

These appear on member profiles but do not grant additional powers in tournament management.

**Needs**:
- Create and advertise tournaments with venue/date/format info
- Add/remove co-organizers
- Register players, manage check-in
- Generate round seatings that follow VEKN rules
- Record and validate table results
- Issue event-level sanctions (Caution, Warning, Standings Adjustment, DQ)
- Run finals qualification and seating
- Finish and report tournament results

**Pain points**: Manual seating calculations, VP validation errors, slow check-in at large events, re-entering data when connectivity drops.

### 2.2 Player

**Profile**: VEKN member attending tournaments. Checks standings, views table assignments, reports own table results. Uses a phone.

**Needs**:
- Register for upcoming tournaments
- Check in (including via QR code)
- View table assignment and seat position each round
- Report table results (VP scores) — players at a table can set scores; organizer override locks them
- View standings during and after the event
- Upload deck list when required
- View personal rating and history

### 2.3 VEKN Officials (NC, IC/Admin)

**Profile**: National Coordinators manage Princes and oversee organized play nationally. IC/Admin manages the global VEKN organization.

**CRITICAL: ICs (admins) always have full access to everything and all permissions, everywhere in the app.** When any access rule mentions Princes or NCs, ICs implicitly have the same or greater access.

**Needs**:
- Sponsor new VEKN members
- Manage Prince/NC appointments
- View all tournaments and results in their jurisdiction
- Access player contact information (NC/Prince: same country; IC: all)
- View and manage sanctions

## 3. VEKN Tournament Rules (App-Relevant Summary)

### 3.1 Tournament Configuration

| Setting | Values | Rules |
|---------|--------|-------|
| Format | Standard, V5, Limited, Draft | VEKN rules 6-7. V5 has specific decklist validation; Limited/Draft have no deck check |
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

Barriers to check-in:
- Decklist required but not uploaded
- Player banned by VEKN
- Player disqualified from this event
```

### 3.3 Round Structure

**Minimum rounds**: 3 (2 preliminary + 1 final), per VEKN rules 3.1.

**Table composition** (VEKN rules 3.1.2):
- Groups of 4 and 5, maximizing tables of 5
- Impossible player counts: 6, 7, 11 (cannot form valid tables)
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

**Tournament without final**: Allowed for any tournament (must be announced before the first round). However, tournaments without finals are not ranked in international rankings — they can only count for league standings.

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
The engine validates that VP combinations match a physically possible oust sequence around the table. This considers seating order (predator-prey). See TOURNAMENTS.md for the algorithm.

### 3.5 Finals Qualification

After preliminary rounds, top 5 players qualify. Ranking order:
1. Game Wins (GW)
2. Victory Points (VP) total — tiebreaker
3. Tournament Points (TP) — second tiebreaker
4. Random (toss) — for remaining ties in top 5

Organizers must drop unavailable finalists before launching finals.

### 3.6 Finals Seating Procedure

**Not** algorithm-assigned. Finalists choose seats in a specific order:

1. Each finalist shuffles their crypt; judge draws 3 random cards (public info)
2. Starting with lowest qualifier (#5), each places their name card:
   - At either end of a row, OR
   - In a gap between two already-placed cards
3. Read left-to-right for final seating positions
4. Judge randomly determines who plays first

### 3.7 Finals Scoring

- Highest VP in finals = tournament winner
- Tie for highest VP: preliminary standings break the tie
- All other finalists tied for 2nd (no further ranking among them)
- Winning the finals counts as a GW even with < 2 VP

### 3.8 Sanctions

#### Event-Level Sanctions (issued by organizers/judges during a tournament)

| Level | Scope | Effect |
|-------|-------|--------|
| Caution | Event only | Verbal warning, tracked during event for pattern detection |
| Warning | Permanent record | Tracked in VEKN database, visible to future organizers |
| Standings Adjustment | Event + permanent | -1 VP penalty applied to current/next/previous game depending on timing (v2 Judges Guide) |
| Disqualification | Event + permanent | Dropped from tournament, prevents further check-in |

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

**App tracking**: Archon tracks all sanction types. Event-level sanctions are managed via a sanctions modal on the tournament page. VEKN-wide sanctions (suspension/probation) are managed via a modal on the members list. Suspended/banned players are blocked from check-in.

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

| Field | Finished | Ongoing (player) | Ongoing (non-player) |
|-------|----------|-------------------|----------------------|
| Config | Yes | Yes | Yes |
| Players | Full | No per-player results | No per-player results |
| Standings | Yes | Per standings_mode | Per standings_mode |
| Decks | Per decklists_mode | No | No |
| Finals | Yes | No | No |
| My tables | Yes | Yes | N/A |
| Rounds | No | No | No |

## 5. Feature Inventory

### 5.1 Implemented

**Authentication & Accounts**:
- Email + password registration and login
- Magic link authentication (signup, password reset, invite flow — link valid until password is actually set)
- WebAuthn / Passkeys (registration and login, both for existing and new users)
- Discord OAuth login and account linking
- JWT-based sessions with refresh tokens
- Auto-focus first input field when modals open

**Member Management**:
- User accounts with profile (name, country, city, social links, contact info: email, Discord, phone)
- Avatar upload with client-side cropping and server-side compression
- VEKN ID claiming (existing members), sponsoring (new members), linking (admin), force-abandon (admin)
- VEKN ID abandon (self-service: unlink account from VEKN ID, keeps history)
- Role management: IC, NC, Prince, Judge, Judgekin, Rulemonger, Ethics, PTC, Playtester, DEV
- User merging (IC/NC/Prince, same-country constraint — merges all associated data)
- Cooptation tracking (`coopted_by`, `coopted_at` on User, inferred during VEKN sync)
- Privacy-filtered user directory (contact info hidden at member level)
- User profile page with ratings history, tournament wins, sanctions

**Tournament Core**:
- Tournament creation with full configuration: format (Standard/V5/Limited/Draft), rank (Basic/NC/CC), proxies, multideck, online, venue, dates, timezone, country, description, max_rounds
- State machine: Planned → Registration → Waiting → Playing → Finished (with Reopen options)
- Player registration, unregistration, add/remove player, drop-out
- Check-in (single, check-in-all, reset check-in)
- Round seating via simulated annealing (Rust engine) with 9 optimization priorities
- Staggered seatings for impossible player counts (6, 7, 11) — bye rotation across rounds
- VP score entry with oust-order validation (simulates physical oust sequence around table)
- GW/TP auto-computation per VEKN rules
- Judge override (forces table to Finished with mandatory comment) / Unoverride
- Standings calculation (GW > VP > TP ranking)
- Finals qualification with toss for ties (manual and random toss)
- Finals seating with AlterSeating (organizer inputs result of physical card-drawing procedure)
- Cancel round, cancel registration, reopen registration, reopen tournament
- Tournament finish and deletion (Planned state only)
- Tournament configuration update (format, rank, settings — some fields immutable after VEKN push)
- `UpdateConfig` action for timer settings, standings/decklists modes, table rooms

**Seating Editor**:
- Drag-and-drop seating editor with touch support (`@dragdroptouch`)
- Per-player issue indicators (sanctions, missing deck, payment status)
- SwapSeats, SeatPlayer, UnseatPlayer, AddTable, RemoveTable, AlterSeating events
- AlterSeating for both preliminary rounds and finals table

**Round Timer** (online-only):
- Global round timer: start/pause/reset, visible to all connected players
- Per-round and per-finals time configuration
- Time extension policy: Additions (+N minutes per table), Clock Stop (per-table pause/resume), or Both
- Per-table extra time (capped at 600s total)
- Per-table clock stop/resume (pause duration converted to extra time on resume)
- Visual countdown with warning state (<5 min) and expired state
- Timer state synced via normal SSE (no per-second broadcasts — clients compute locally)

**Call for Judge** (online-only):
- Player button sends ephemeral SSE alert to organizer console and IC users
- Stacking dismissible banners with audio chime
- Auto-dismiss after 120s
- Validates: player seated at specified table, tournament in Playing state, not offline

**Raffle**:
- Random draw from configurable player pools: AllPlayers, NonFinalists, GameWinners, NoGameWin, NoVictoryPoint
- Draw/Undo/Clear actions
- RaffleSection component in tournament organizer view

**Table Rooms**:
- Organizers assign named rooms to table ranges (e.g., "Lobby: tables 1-5")
- Room names appear as table labels in seating displays, print views, and player views
- `TableRoomsEditor.svelte` for configuration

**Deck Management**:
- VTES card database loaded from JSON into IndexedDB (`cards` store)
- Deck upload: text paste, deckbuilder URL (VDB, VTESDecks, Amaranth), QR code scanner (camera)
- Deck parsing in Rust: Lackey, JOL, TWDA formats
- Deck validation: crypt/library counts, banned cards, group rules, V5 format, multideck rules
- Deck enrichment: card names, types, disciplines, image URLs from card database
- Deck attribution: player or named author (autocomplete member search)
- Decklist requirement enforcement (blocks check-in if deck not uploaded — organizer can override with warning)
- Multideck support: per-round decks, locked once their round starts
- Post-tournament deck upload (winner's deck recovery)
- Deck visibility filtering by `decklists_mode` (Winner/Finalists/All)
- Card search component with autocomplete (searches crypt + library)
- Card quantity adjustment buttons in deck editor
- Collapsible decklists in player view
- CORS proxy fallback for deck URL fetching
- TWDA-format deck export per player (`GET /{uid}/decks/{player_uid}/twda`)
- TWDA auto-PR: on tournament finish, winner's deck submitted as GitHub PR to TWDA repository

**Result Reporting**:
- Player self-reporting: any player at a table can set VP scores during the round
- Organizer override locks player editing for that table (requires comment)
- VP validation via oust-order algorithm (seating-order-aware simulation)
- Tournament report download: text and JSON formats (organizer-only)

**Sanctions**:
- Event-level: Caution, Warning, Standings Adjustment, Disqualification
- VEKN-wide: Suspension, Probation, Ban (IC/Ethics Committee only)
- Judges Guide v2 categories and subcategories (Procedural Errors, Tournament Errors, Unsportsmanlike Conduct) with escalation guidance
- SA score adjustments applied to round GW computation with overflow to standings
- DQ barring: tournament-level, league-wide (DQ in any league tournament bars all others), suspension-wide
- On-site suspension: 30-day national suspension for gross ethics violations (must be escalated within 5 days)
- Barring enforced at check-in and finals qualification
- Visual indicators on player names in registration, seating, and standings
- Cautions visible only within their tournament; warnings+ visible for 18 months
- Lifting permissions: IC, Ethics, Rulemonger, NC (same country), league organizers (DQ only)
- Sanction cleanup: expired sanctions (>18 months) soft-deleted daily, hard-deleted after 30 days

**Leagues**:
- League and meta-league management (NC/IC only)
- League fields: name, country, start/end dates, format, online, description, organizers, parent (for meta-leagues), allow_no_finals
- Three standings modes: RTP (rating points), Score (GW/VP/TP from prelims), GP (Grand Prix F1-style points)
- Tournament-league association with organizer-filtered selection
- Auto-updating standings on league detail page
- Tournaments can finish without finals (meaningful for Score leagues)

**Ratings & Hall of Fame**:
- Player ratings computed server-side, updated on tournament finish or modification
- Rating = sum of best 8 tournaments in trailing 18 months
- RP display in finished tournament standings
- Rankings page: top 500 global, country filters, date sort, bulk-load pagination
- Hall of Fame: players with 5+ tournament wins, sorted by wins
- Suspended players hidden from rankings
- Daily full recompute of all player ratings and wins
- Rating cutoff uses exact 18 calendar months

**Payment Tracking**:
- Payment status per player: Pending, Paid, Refunded, Cancelled
- `SetPaymentStatus` and `MarkAllPaid` actions
- Organizers can toggle payment status; visible in registration list

**QR Code Check-in**:
- Organizer displays tournament-scoped QR code (with print option)
- Players scan from within the Archon app to self-check-in
- `checkin_code` on tournament model, `POST /{uid}/qr-checkin` endpoint
- Camera-based QR scanner component

**Social & Discovery**:
- Social sharing for finished tournaments: canvas-rendered PNG card + plain text with decklist info
- iCal calendar feed: personal agenda (via `calendar_token`), country-scoped, global, with online toggle
- Calendar token generated on demand, stripped from SSE (only visible via `/auth/me`)
- Agenda matching: organizer/participant events + same country/online/NC/CC on continent
- Tournament list with "My Agenda" toggle and "Include online" toggle
- Simplified filters: country, format, search

**Printable Views**:
- Print-optimized round seating (HTML with `@media print`, page breaks)
- QR code print

**Help & Reference**:
- In-app help pages: VTES rulebook, VEKN tournament rules, Judges Guide (v1+v2), Code of Ethics
- Player guide and organizer guide
- Paginated help viewer with table of contents
- Source markdown in `frontend/src/lib/help-content/`

**VEKN Integration (Complete)**:
- **Outbound push**: Tournament events pushed to VEKN on create (calendar entry), results pushed on finish (archondata format). Batch job catches missed pushes hourly
- **Inbound member sync**: Pulls/updates VEKN member database periodically (every 6h default). Infers `coopted_by` relationships
- **Inbound tournament sync**: Imports historical tournaments from VEKN API, seeding venue autocomplete data
- **Member push**: Locally-coopted members pushed to VEKN registry on sponsor
- Format → VEKN event type mapping (Standard/Limited/V5 × Basic/NC/CC)
- `max_rounds` immutable once pushed to VEKN
- `external_ids["vekn"]` and `vekn_pushed_at` tracking on tournaments

**Archon Import**:
- Import tournament results from legacy Archon Excel files (`.xlsx`)
- Template download endpoint (`GET /tournaments/archon-template`)
- Full round-level data import with player matching

**OAuth2 Provider**:
- Full PKCE authorization code flow (authorize, consent, token exchange, refresh, revoke)
- OpenID Connect userinfo endpoint
- OAuth client management (register, list, get, regenerate secret, deactivate) — DEV role required
- Developer section in user profile for client management
- Consent persistence (users don't re-approve same client+scopes)
- Scopes: `profile:read`, `user:impersonate`
- Argon2-hashed client secrets, refresh token rotation, revocation chain tracking
- Scheduled cleanup of expired codes and tokens

**Offline Mode (Full)**:
- Primary device ownership (organizer takes tournament offline)
- Other devices see "offline" message — no mutations available
- Force-takeover by other organizers (with data loss warning)
- Go-online with CRUD log reconciliation (primary device is authoritative)
- IC emergency force-unlock (without syncing offline data)
- Opportunistic sync when network detected
- Offline member creation with temp UIDs remapped on sync
- SSE suppressed for offline tournaments; primary device ignores tournament SSEs until back online

**Infrastructure**:
- Offline-first PWA with service workers (update detection and application)
- IndexedDB for all read operations (5 object stores + cards + changes log)
- SSE real-time sync with role-based filtering (3 access levels: public/member/full)
- Pre-computed access-level JSONB columns (no per-viewer filtering at read time)
- Personal overlay for own objects and role-based full-access
- Optimistic updates via WASM engine (tournament actions update IndexedDB immediately)
- Resync mechanism on role/VEKN ID changes
- Snapshot endpoint for fast initial sync (gzip, regenerated every 15 minutes)
- Internationalization: EN, FR, ES, PT-BR, IT (Paraglide JS, browser auto-detection)
- Locale switcher in sidebar
- GeoNames-based country/city autocomplete
- Scheduled background tasks: VEKN sync, sanction cleanup, rating recompute, VEKN push, OAuth cleanup, snapshot generation, deleted objects purge

### 5.2 Not Yet Implemented / Planned

See `development-plan.md` for implementation phasing.

#### Discord Integration (Phase 12)

- **Role verification webhook**: Discord Linked Roles integration — auto-assign VEKN roles to Discord server members
- **Tournament butler bot**: Full tournament management via Discord slash commands (see `development-plan.md` Phase 12.2)

#### Tournament Features

- **Tournament logs**: Audit trail of organizer actions during an event
- **Draft/Limited tournament support**: Pod management, product distribution, deck building timer
- **Limited format constraints**: Mono-vampire, mono-clan, card lists (low priority, manual enforcement for now)
- **Multi-day tournament support**
- **Auto-close old tournaments**: Automatically finish stale tournaments after a period

#### Analytics & Data

- **Deck statistics**: Aggregate stats on decks played at events (clan distribution, most-played cards, crypt trends)

#### Other

- **Spectator mode**: Live standings/results for non-participants
- **Event description with Markdown rendering**

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
5. **Confirmation for destructive actions**: Start round, finish tournament, drop player

### 6.3 Design System

Gothic horror / Vampire aesthetic. Dark mode primary. Colors: crimson (accent), bone (backgrounds), dusk (surfaces), ash (text/borders), mist (muted). See `frontend/DESIGN.md`.

### 6.4 Internationalization

Five languages: EN (British), FR, ES, PT-BR, IT. Official VTES game terms must use translations from Black Chantry rulebooks (reference: `reference/game_terms.json`).

## 7. Key Domain Edge Cases

These are situations that come up in real tournaments and that the app must handle correctly:

### Seating & Player Counts

1. **Impossible player counts**: 6, 7, 11 players cannot form valid tables of 4-5. The engine handles these via staggered seatings (bye rotation across rounds so everyone plays equally).

2. **Player drops mid-round**: A 5-player table becomes 4-player. The round continues but the dropped player's seat is marked finished with 0 VP. Their predator does NOT get a VP for this (administrative removal, not an oust).

3. **Late registration**: Players can register even after the first round. They play from the next round onwards. Late players have fewer rounds for standings but can still qualify for finals.

4. **Seating optimization across rounds**: The simulated annealing algorithm considers all previous rounds to avoid repeated predator-prey relationships, equitably distribute available VPs (4 vs 5-player tables), and minimize repeated table sharing.

### Scoring & VP Validation

5. **Oust-order validation**: VP combinations must match a physically possible oust sequence around the table (seating order matters). The engine simulates ousts clockwise to validate. Invalid combinations show as "Invalid" table state.

6. **Intentional draws**: All players agree to accept current scores as if time expired. Legal per VEKN rules 3.6. Each surviving player gets 0.5 VP.

7. **Concession cascade**: Players may concede if all-but-one agree. Remaining player is treated as having ousted them in sequence.

8. **Fractional VPs**: 0.5 VP for surviving to time limit or withdrawing. VP values are always multiples of 0.5. Value `table_size - 0.5` is impossible (e.g., 4.5 on 5-player table).

9. **4-player TP gap**: On 4-player tables, 3rd place TP position is empty ("table bye"). Positions are 1st, 2nd, 4th, 5th with TPs 60, 48, 24, 12.

10. **GW conditions**: Requires VP >= 2.0 AND strictly highest VP at table (no ties). Finals exception: winner gets GW even with < 2 VP.

11. **Score adjustment overflow**: SA penalty applied to current round's VPs for GW determination. If VP-adjusted is negative or penalty cannot fully apply, remainder overflows to overall standings for finals seeding — never carried to next round.

### Finals

12. **Finals qualification**: Top 5 players by GW > VP > TP. Ties for 5th position resolved by random toss (organizer can set manually or randomize).

13. **Finals with < 5 available players**: Organizer must drop unavailable qualifiers before launching finals. App enforces this.

14. **Finals seating**: Not algorithm-assigned. Physical card-drawing procedure (VEKN rules 3.5). Organizer inputs the result via AlterSeating. App does not enforce the procedure — just records the outcome.

15. **Finals scoring**: Highest VP wins. Tie for highest VP broken by preliminary standings. All non-winners tied for 2nd. Winner gets GW even with < 2 VP.

16. **Multideck finals**: Best-Performing Deck method or Free Choice method (announced pre-tournament). Players may use a different deck in finals.

### Sanctions & Barring

17. **Disqualification mid-game**: DQ is administrative, not an oust. No VP awarded to predator. DQ'd player marked as finished, cannot check-in for subsequent rounds or be selected for finals.

18. **League-wide DQ**: DQ in any league tournament bars the player from all other tournaments in that league. Only league organizers can lift this.

19. **Suspension barring**: Suspended players cannot check-in to any tournament. Suspension can be lifted by Ethics Committee member or IC.

20. **Sanction escalation guidance**: The app guides organizers toward appropriate sanction level based on category/subcategory. Warns if issuing lower than existing level. Suggests escalation on third offense (two cautions → third should be a warning).

### Tournament Lifecycle

21. **Event becomes unsanctioned**: If drops create an impossible player count between rounds and staggered seatings don't apply, the event may lose sanctioning but can still distribute prizes and report.

22. **Tournament without finals**: Allowed for any tournament (must be announced before first round). Tournaments without finals are not ranked in international rankings — they count only for league standings.

23. **Reopen tournament**: A finished tournament can be reopened (e.g., to correct scores). Ratings are recomputed on subsequent finish.

24. **Cancel round**: The current round can be cancelled (e.g., if seating errors detected). Players return to "Checked-in" state.

### Offline Mode

25. **Offline device ownership**: Only one device owns an offline tournament. Other organizers see "offline" status with no mutation capability.

26. **Force-takeover**: Another organizer can force the tournament back online (losing offline primary device's unsaved data). IC can force-unlock without syncing.

27. **Offline member creation**: Organizers create members with temp UIDs (`P-` prefix). Server assigns real VEKN IDs on sync. If SSE briefly delivers real UID while still offline, it's updated immediately.

### Decks

28. **Decklist requirement vs check-in**: If tournament requires decklists, players without a deck are warned at check-in. Organizers can override and check in without a deck (with explicit warning).

29. **Multideck locking**: In multideck tournaments, a deck for a round is locked once that round starts. Players can still upload the next round's deck before it begins.

30. **Post-tournament deck upload**: Players and organizers can upload missing decklists after a tournament finishes (important for winner's decklist recovery and TWDA submission).

31. **Deck attribution**: Players choose attribution (themselves or another member as author) or anonymity. Public display respects choice.

### Visibility & Privacy

32. **Standings visibility during ongoing events**: Configurable by organizer: Private (no standings shown), Cutoff, Top 10, Public. Manages information asymmetry.

33. **Decklists visibility**: Configurable by organizer: Winner only, Finalists, All. Only applies after tournament finishes.

34. **Player self-reporting window**: Players at a table can set scores during the round. Once organizer overrides, player editing is locked for that table.

35. **Member-level tournament visibility**: Ongoing tournaments hide rounds, finals, and per-player results from non-organizers. Only own tables visible to participating players.

### VEKN Integration

36. **max_rounds immutability**: Once a tournament is pushed to VEKN (has `external_ids["vekn"]`), `max_rounds` cannot be changed (enforced backend + frontend).

37. **All players need VEKN IDs**: Results cannot be pushed to VEKN until all players have a `vekn_id`. Organizers must sponsor or link players before finishing.

38. **VEKN push is fire-and-forget**: Never blocks user actions. Batch job catches missed pushes hourly.

## 8. VEKN Rating System (Reference)

Rating = sum of best 8 tournaments in trailing 18 months.

Per tournament:
- 5 RtP for attendance
- 4 RtP per VP scored
- 8 RtP per GW (including final round victory)
- Finalist bonus: `Points * Coefficient`
  - Winner: 90 points, Finalist: 30 points
  - Coefficient: `log15(NumPlayers^2) - 1`
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
| Development Plan | `development-plan.md` | Implementation roadmap and phasing (maintained by product manager) |
