# Development Plan - Archon

Reference: [krcg](../krcg) for cards/decks logic. [archon](../archon) for previous app version.

---

## Phase 1: Decklists Management

### 1.1 Cards Data Pipeline (CI Script)

A CI job (daily or hourly) fetches the official VTES cards CSV from the [VEKN GitHub repository](https://github.com/vekn-official) and produces a clean JSON reference file deployed as an app artifact.

**Done when:** CI produces a versioned JSON cards file, accessible by both Rust engine and frontend.

### 1.2 Deck Parsing Engine (Rust)

Using the JSON reference file from 1.1:

- Parse text decklists with format compatibility: Lackey, JOL, TWDA formats (simpler than krcg parser but covers these three)
- Extract a deck from deckbuilder URLs: VDB, vtesdecks, Amaranth
- Produce minimal JSON (author, comments, card IDs) for storage in tournament models
- Produce rich JSON for display (card names, image URLs) from minimal JSON
- Validate tournament format legality (Standard, V5). No validation for Limited format
- Generate TWDA-valid winner decklist text from tournament data + minimal decklist. See [TWDA GitHub](https://github.com/GiottoVerducci/TWD) for format docs

**Done when:** Rust engine can round-trip parse → store → enrich → export decklists in all listed formats.

### 1.3 Decklist Backend API

- Endpoints for decklist upload (text body or deckbuilder URL)
- Store decklists as part of tournament player data (minimal JSON: author, comments, card IDs)
- Support multiple decklists per player for multideck tournaments
- Serve enriched decklist JSON for display

**Done when:** API accepts text/URL uploads, stores minimal JSON, returns enriched JSON.

### 1.4 Decklist Frontend UI

#### Upload Flow
- Text input or deckbuilder URL paste
- QR code scanner (camera) to capture VDB deck URL — preferred method for organizers uploading on behalf of a player
- Both players and organizers can upload

#### Display Component
- Simple modal/panel showing crypt and library in standard order with spacing
- Quantity adjustment buttons and search/completion bar to add cards (single input, searches crypt + library)
- Card preview on click (handle modal-over-modal carefully, especially on mobile)
- Clean, smooth mobile UX is the priority

#### Post-Tournament Display
- Any member can view winner's decklist once tournament is finished
- Depending on tournament config (`decklists_mode`): winner only, finalists, or all players
- Show whether the deck is winner's/finalist's/player's, VP count, and author attribution if requested

**Done when:** Players and organizers can upload/view/edit decklists with smooth mobile UX.

### 1.5 Business Rules (Lifecycle & Incentives)

#### Lifecycle Restrictions
- Players can upload/modify their decklist until the tournament starts
- Multideck tournaments: players cannot modify a decklist once its round has started, but can upload the next round's deck before that round begins
- Organizers can upload/update a player's decklist at any time after the tournament starts
- Players can upload a missing decklist after a tournament finishes (important for winner's decklist recovery)

#### Decklist Required Mode
- Clear reminders at registration and check-in when tournament is marked "decklist required"
- At check-in: warn that a decklist is needed or sanctions apply
- Allow check-in without decklist but auto-apply a WARNING sanction for missing/late decklist
- Warn player before proceeding; don't block check-in to avoid disrupting event flow
- Organizers can lift this warning (like all sanctions) if justified (device/network issues)
- Organizers can manually check in players without decklist — warned about missing decklist before confirming

#### Decklist Optional Mode
- Simple message letting players know they can upload a decklist, explaining it's optional

#### Winner's Decklist Nudges
- Display messages to winner and organizers if winner's decklist is missing on a finished tournament
- Push for upload without blocking

#### Attribution & Anonymity
- Players choose attribution or anonymity when uploading
- Attribution defaults to the player but can be changed to another member (deck author lookup with member search/completion by name or VEKN ID)
- Public display respects the player's choice after the tournament

**Done when:** All lifecycle restrictions enforced, incentive messages displayed, attribution works.

### 1.6 TWDA Integration

- Auto-open a PR against the [TWDA GitHub](https://github.com/GiottoVerducci/TWD) main branch when a sanctioned tournament's winner decklist is available
- Update the PR if the decklist is modified after the fact
- Late uploads (winner adds decklist post-tournament) trigger the PR at that point
- Provide downloadable text report (standings, finals, winner's decklist, app URL) and JSON export for record keeping

**Done when:** Winner decklists auto-generate TWDA PRs; reports downloadable.

Overall: clear UX guidance for decklist management. Good help messages at the right places, clear visual indicators, but not too invasive. Encourage deck list recording without being pushy.

---

## Phase 2: Leagues ✅

### 2.1 League Model & Engine (Rust)

Leagues are collections of tournaments. Only NCs and ICs can create leagues.

**Model fields:** name, country (optional — can be multi-country or worldwide), start date, end date (optional), standings mode, format restriction (optional), organizers list, allow-no-finals flag.

**Standings modes** (computed in Rust engine, reference [archon](../archon)):
- **Score**: GWs + VPs from preliminaries only
- **RP** (Rating Points): classic VEKN-based ranking used in overall ratings
- **GP** (Grand Prix): car-sport style points based on position (top 10)

Standings refresh every time a league tournament finishes or is modified post-finish.

Leagues are a new SSE-streamed base object type (follow SYNC.md patterns).

**Done when:** League CRUD, standings computation for all 3 modes, SSE streaming.

### 2.2 League Backend API

- League CRUD (create/update/delete) restricted to NCs/ICs
- Add/remove organizers
- Tournament-league association (organizers select league when creating tournament)

**Done when:** API supports full league management.

### 2.3 League Frontend UI

- League list and detail pages with standings display
- Tournament creation: show currently active leagues (filter out leagues with end date older than today or tournament start if set), only selectable by league organizers. Show inactive leagues with explanation text for why they're not selectable (not an organizer)
- Option to show past leagues for after-the-fact record keeping
- Tournaments can finish without finals (meaningful for Score leagues; less so outside, but option remains available without being prominent)

**Done when:** League pages functional, tournament-league selection works with clear guidance.

### 2.4 League Standings Integration

- Standings visible on league page, auto-updated

**Done when:** Standings display correctly for all 3 modes.

---

## Phase 3: Tournament Sanctions Enhancement (Delta) ✅

> Existing: sanction model with 6 levels (caution → probation), 5 categories, VP adjustments, soft-delete. What follows is what's **missing**.

### 3.1 In-Tournament Sanction UX

- Organizer interface to issue sanctions during a tournament with round selection
- Only cautions, warnings, score adjustments and disqualifications can be issued during a tournament (no suspension or probation)
- Visual cues on player names everywhere in the organizer console (registration, table seating, standings) when they have active sanctions
- Cautions visible only within their tournament; warnings and above visible in other tournaments and user list for 18 months (for reference only, no impact on escalation)

**Done when:** Organizers can issue sanctions mid-tournament with clear visual indicators.

### 3.2 Escalation Guidance

Reference: [Sanctions categories document](https://docs.google.com/document/d/1Nw3EkVtyXSvgDK2MZ040xcDBVuE3FWfS6LLwGGuhRfM/edit?tab=t.0#heading=h.1yc5szj1lpa5)

- Guide (not force) organizers toward appropriate sanction level based on category/subcategory
- Warn if issuing a sanction lower than existing (e.g., caution when player has a warning)
- Suggest escalation on third sanction (two cautions → third should be a warning)
- Exceptions depend on exact category/subcategory
- Align models/types with the sanctions categories document

**Done when:** Interface guides toward correct escalation; categories match the official document.

### 3.3 Round-Scoped Score Adjustments

- Score adjustment sanctions apply to the current round's VPs for GW determination: need 2 VPs (including adjustments) and more VPs than other players for a GW
- If adjustment cannot be fully applied to the round, remainder applies to overall standings for finals seeding (not carried to next round)
- Rust engine ratings and standings computations updated to account for this everywhere

**Done when:** Score adjustments correctly affect GW determination and overall standings.

### 3.4 Barring Logic

- Disqualified players: marked as finished, cannot check-in in subsequent rounds or be selected for finals. Listed as "disqualified" (not just "finished") in console and standings, including after tournament ends
- League DQ: disqualification in a league tournament bars entry to all other tournaments in that league. League organizers can lift this
- Suspended players: barred from all tournaments until suspension expires or an Ethics Committee member / IC lifts it
- Sanctions above caution and velow suspension can be lifted (soft-deleted) by rulemongers (NOT judges nor judgekins), tournament country's NC, and ICs

**Done when:** Barring enforced at check-in and finals selection; lifting works per role.

---

## Phase 4: Ratings & Hall of Fame ✅

### 4.1 Ratings in Tournament Standings ✅

- RP (rating points) earned displayed in finished tournament standings (PlayersTab)
- Ratings page with top 500 globally, country filters, date sort, bulk-load rankings
- Suspended players hidden from rankings page
- Rating cutoff uses exact 18 calendar months

### 4.2 Hall of Fame ✅

- Hall of Fame page listing players with 5+ tournament wins
- Player name, star per win, sorted by decreasing wins
- Integrated with ratings navigation

---

## Phase 5: QR Code Check-in

Players check in via QR code shown/printed by organizers.

**Challenge:** Ensure players are physically at the venue. GPS is unreliable and not universally available.

**Proposed approach:** QR code encodes a non-URL payload (e.g., a signed token). Players must scan it from within the app — sharing a photo and using it remotely is cumbersome enough to deter abuse without being bulletproof. Trade-off: slightly worse UX (can't scan from camera app) but reasonable venue-presence assurance.

> Open design question: explore alternatives. The goal is "inconvenient enough to deter remote check-in" if not fully secure.

**Done when:** QR check-in works from the app with reasonable venue-presence assurance.

---

## Phase 6: Online Features

### 6.1 Call for Judge

- Player button (when tournament is online) sends SSE alert to organizer console: "Table X requires a judge"
- Organizer sees alert with table reference

**Done when:** Judge call sends real-time SSE notification to organizers.

### 6.2 Shared Timer

- Organizers set round time (same for all prelims, separate for finals)
- Two modes: global timer (organizer-controlled for all tables) or per-table timer (players start when ready)
- Players cannot pause the global timer; optionally allow player pause on per-table timers (configurable)
- Timer visible in the app for players

**Done when:** Timer works in both modes with correct pause permissions.

---

## Phase 7: Printable Round Seating & Table Labels

### Printable Seating ✅

- Print-optimized HTML page of round seating with proper print CSS (`@media print`, page breaks)

### Table Labels

Two modes (keep it lean):
- **Custom names:** organizer provides freeform table names
- **Rooms:** configure named spaces with table counts (e.g., "Lobby: 5 tables, Center room: 15 tables, Garden: 6 tables")

**Done when:** Table labeling works in both modes.

---

## Phase 8: Offline Mode (Full)

> Basic offline CRUD already works (IndexedDB + WASM engine + changes log). This phase adds ownership and conflict resolution.

### Primary Device Ownership

- Organizer takes a tournament offline → becomes primary device owner
- Clear UI guidance explaining the offline model
- Other organizers/players see a message: tournament is offline, no mutations or live updates available

### Device Transfer

- Primary device can transfer ownership to another device (with warning about losing unsaved data on original)
- Other organizers can force the tournament back online (warned they'll lose offline primary device data)

### Sync on Reconnect

- Primary device auto-syncs to server when network detected (primary is authoritative, not server)
- Only syncs if tournament is still offline and device is still primary on server side
- If tournament changed ownership or went back online meanwhile: warn user, offer option to overwrite server data (losing other modifications)

### Offline Member Creation

- Organizers can create new members offline for tournament registration
- Use placeholder VEKN IDs (e.g., `P-` prefix)
- Server assigns real VEKN IDs on sync
- If SSE delivers the real VEKN ID while still offline (brief network), update immediately

### SSE Handling

- Tournament stops sending SSEs while offline
- Primary device ignores tournament SSEs until back online
- Other SSE streams (non-tournament objects) continue syncing as possible

**Done when:** Full offline tournament lifecycle works with clear ownership model and conflict handling.

---

## Phase 9: Entry Fee & Pretix Integration

- Simple paid/unpaid flag per registered player
- Players cannot self-check-in if not flagged as paid; organizers can check in anyone
- Optional: link tournament to a Pretix event via [Pretix API](https://docs.pretix.eu) to auto-track payment status

**Done when:** Payment tracking works; Pretix integration optional but functional.

---

## Phase 10: Venue Completion

- VEKN sync imports venue information via VEKN API
- Tournament creation/edit: auto-complete venue name (country-scoped), auto-fill address, map, URL from last known data for that venue name
- No separate venue table — dynamic in-memory completion from existing tournament data

**Done when:** Venue auto-complete works during tournament creation.

---

## Phase 11: Help & Documentation

### Reference Documents (HTML)

- VTES rules extracted from [rulebook repository](https://github.com/GiottoVerducci/rulebook2024) main branch
- VEKN tournament rules
- Judge's guide — update to [new version](https://docs.google.com/document/d/1Nw3EkVtyXSvgDK2MZ040xcDBVuE3FWfS6LLwGGuhRfM/edit?tab=t.0#heading=h.1yc5szj1lpa5)
- Ethics guide

Previous versions in [archon](../archon).

### User Guides

- Player guide and organizer guide (separate documents)
- Clear, minimal — the shorter the better
- The app UX should provide enough in-context guidance that documentation is rarely needed
- Iterate on content and organization for ease of use

**Done when:** All reference docs converted to clean HTML; guides drafted and reviewed.

---

## Phase 12: Discord Bot

Using [hikari](https://github.com/hikari-py/hikari) with slash commands:

- Player interactions: register, check-in, deck upload, results record
- Auto-create table channels per round, invite correct players
- In-channel timer based on tournament timer preferences
- Good guidance bot <-> webapp (webapp explains how to install bot, easy discord invite linked to online tournament, discaord event & stage management)

**Done when:** Bot manages tournament channels and player interactions on Discord.
