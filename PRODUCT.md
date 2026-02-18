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
- Check in (including via QR code — planned)
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

**Member Management**:
- User accounts with email/OAuth authentication
- VEKN ID claiming (existing members) and sponsoring (new members)
- Role management (IC, NC, Prince, Judge, Judgekin, etc.)
- Profile with personal info, country, social links
- Privacy-filtered user directory

**Tournament Core**:
- Tournament creation with full configuration (format, rank, proxies, multideck, online, venue, dates)
- State machine: Planned -> Registration -> Waiting -> Playing -> Finished
- Player registration and check-in (including check-in-all)
- Round seating via simulated annealing (Rust engine)
- VP score entry with validation (oust-order algorithm)
- GW/TP auto-computation
- Judge override for irregular table results
- Standings calculation (GW > VP > TP ranking)
- Finals qualification with toss for ties
- Tournament finish

**Deck Management**:
- Card database loaded from JSON into IndexedDB
- Deck upload/validation (crypt/library counts, banned cards, group rules)
- Decklist requirement enforcement (blocks check-in if deck not uploaded)
- Deck visibility filtering by decklists_mode

**Result Reporting**:
- Player self-reporting: any player at a table can set VP scores during the round
- Organizer override locks player editing for that table
- VP validation via oust-order algorithm

**Sanctions**:
- Event-level: Caution, Warning, Standings Adjustment, Disqualification
- VEKN-wide: Suspension, Probation (IC/Ethics only)
- Judges Guide v2 categories and subcategories with escalation guidance
- SA score adjustments applied to round GW computation with overflow to standings
- DQ barring (tournament, league-wide, suspension-wide) enforced at check-in and finals
- Tracked per event and on player profile with visual indicators in standings
- Lifting permissions: IC, Ethics, Rulemonger, NC (same country), league organizers (DQ)

**Leagues**:
- League and meta-league management (NC/IC only)
- Three standings modes: RTP, Score (GW/VP/TP from prelims), GP (F1-style points)
- Tournament-league association with organizer-filtered selection
- Auto-updating standings on league detail page

**Ratings**:
- Player ratings computed server-side, updated on tournament finish or modification
- Rankings page

**Organizer UX**:
- Mobile-first organizer console
- Drag-and-drop seating editor with per-player issue indicators
- Printable round seating (print-optimized CSS)
- Payment tracking (paid/unpaid toggle per player)
- Multiple organizers management (add/remove co-organizers)
- IC implicit organizer access on all tournaments

**Social & Discovery**:
- Social sharing for finished tournaments (PNG card + text with decklist)
- iCal calendar feed (personal agenda, country, global; with online toggle)
- Tournament list with "My Agenda" view

**Ratings & Hall of Fame**:
- RP display in finished tournament standings
- Rankings page (top 500 global, country filters, date sort)
- Hall of Fame (players with 5+ wins)

**Infrastructure**:
- Offline-first PWA with service workers
- IndexedDB for all read operations
- SSE real-time sync with role-based filtering
- Optimistic updates via WASM engine
- Resync mechanism on role/VEKN ID changes
- Internationalization support (EN, FR, ES, PT-BR, IT)

### 5.2 Not Yet Implemented / Planned

See `development-plan.md` for implementation phasing.

#### Tournament Features

- **QR code self-check-in** (planned Phase 5; basic self-check-in button exists but no QR generation/scanning)
- **Round timer**: Organizer-controlled countdown (start/pause/reset), visible to all players via SSE. Shared per round or per table.
- **Ask for a Judge button**: Player sends notification from table view to organizers (push notification + on-screen alert)
- **Raffle**: Random draw from configurable player pools (round winners, non-finalists, non-winners, all players, etc.) for prize attribution
- **Staggered seatings**: Bye rotation for impossible player counts (6, 7, 11). Each round, some players sit out; over multiple rounds everyone plays equally. Round-by-round seating engine handles this naturally.
- **Finals seating UI** (manual procedure; organizer inputs the result after physical card-drawing)
- **Table labels**: Custom names or room-based layout (e.g., "Lobby: 5 tables, Center room: 15 tables")
- **Tournament logs**: Audit trail of organizer actions during an event (#49)
- **Player view live updates**: SSE-driven real-time updates on the player's tournament view (#91)

#### Analytics & Data

- **Deck statistics**: Aggregate stats on decks played at events (clan distribution, most-played cards, crypt trends). Requires good decklist data.
- **VEKN results reporting** (automated submission to VEKN; may be manual/export)

#### VEKN Integration (Beta Requirement)

- **VEKN results reporting**: Push tournament results to vekn.net on finish (and on subsequent modifications)
- **VEKN member sync**: Pull/update member database from vekn.net
- **Historical event import**: Import past tournaments from vekn.net

#### Member & Roles

- **Additional roles**: Playtest Coordinator (PTC), Playtester, Ethics Committee
- **Abandon VEKN**: Unlink account from VEKN ID (keeps history)
- **Tournament deletion** (admin only, cleans associated ratings/sanctions)

#### Ratings

- **4 rating categories**: Constructed Online, Constructed Onsite, Limited Online, Limited Onsite
- **Grand Prix points**: Separate scoring for GP leagues (same concept as championship scoring)

#### API & Integration

- **OAuth2 for third-party clients**: Client registration, authorization flow, token management
- **Venue autocomplete**: Country-scoped suggestions from historical tournament data (name, address, city, URL, map URL)

#### Discord Integration

- **Role verification endpoint**: Webhook-based endpoint for Discord's Linked Roles feature. Players link their Discord account to Archon, Discord fetches their VEKN roles (Prince, NC, Judge, etc.) and assigns matching Discord server roles automatically.
- **Tournament bot** (reference implementation: `../archon-bot`):
  - Slash commands for players: `/register`, `/check-in`, `/drop`, `/upload-deck`, `/report` (VP), `/status`
  - Slash commands for judges: `/register-player`, `/drop-player`, `/disqualify`, `/note`, `/fix-report`, `/validate-score`
  - Tournament lifecycle: `/open-tournament`, `/configure-tournament`, `/round start|finish|reset`, `/finals`, `/standings`, `/close-tournament`
  - Discord infrastructure: auto-creates table text+voice channels per round in the tournament category, assigns per-table roles
  - Role management: Organizer, Judge, Player, Spectator, Bot roles per tournament
  - Deck validation: URL import (VDB), file upload, format-specific rules
  - `/raffle` for prize draws
  - `/download-reports` for VEKN-compatible CSV export
  - Staggered seating support for 6/7/11 players
  - Compatible with timer bots and card reference bots (KRCG)
  - **Architecture**: Thin client reusing the shared Rust engine. Two options (decision deferred to implementation): (A) call Archon's HTTP API, simpler but network overhead; (B) use Rust engine directly via PyO3 if co-located on same server, no network overhead but tighter coupling

#### Other

- **Tournament text report / download**: Standings + winner deck in TWD format
- **Print views**: Seating cards, standings sheets
- **Auto-close old tournaments**: Automatically finish stale tournaments after a period
- **Draft/Limited tournament support** (pod management, product distribution, deck building timer)
- **Limited format constraints** (mono-vampire, mono-clan, card lists — low priority, manual enforcement for now)
- **Multi-day tournament support**
- **Spectator mode** (live standings/results for non-participants)
- **Event description with Markdown rendering**
- **Developer/OAuth pages** (routes exist; may be for API consumers)
- **VEKN # autocomplete on registration** (#36)

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

1. **Odd player counts**: 6, 7, 11 players cannot form valid tables of 4-5. The engine must reject or handle with sit-outs.

2. **Player drops mid-round**: A 5-player table becomes 4-player. The round can continue but seating violations may appear.

3. **Late registration**: Players can register even after the first round. They cannot be added to games in progress.

4. **Intentional draws**: All players agree to accept current scores as if time expired. Legal per VEKN rules 3.6.

5. **Concession cascade**: Players may concede if all-but-one agree. Remaining player is treated as having ousted them in sequence.

6. **Fractional VPs**: 0.5 VP for surviving to time or withdrawing. VP values are always multiples of 0.5.

7. **4-player TP gap**: On 4-player tables, 3rd place TP position is empty ("table bye"). Positions are 1st, 2nd, 4th, 5th.

8. **Multiple tables going to finals**: Only top 5 qualify regardless of number of preliminary rounds.

9. **Finals with < 5 available players**: Organizer must drop unavailable qualifiers before launching finals. App should warn.

10. **Disqualification mid-game**: No VP awarded to predator. Game continues with one fewer player. DQ is administrative, not an oust.

11. **Event becomes unsanctioned**: If drops create an impossible player count between rounds, the event loses sanctioning but can still distribute prizes and report.

12. **Standings visibility during ongoing events**: Configurable by organizer (Private, Cutoff, Top 10, Public) to manage information asymmetry.

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
| Architecture | `ARCHITECTURE.md` | Technical architecture reference |
| Sync | `SYNC.md` | SSE streaming and IndexedDB sync patterns |
| Tournaments | `TOURNAMENTS.md` | Tournament system implementation details |
| Design | `frontend/DESIGN.md` | UI design guidelines |
| Development Plan | `development-plan.md` | Implementation roadmap and phasing (maintained by product manager) |
