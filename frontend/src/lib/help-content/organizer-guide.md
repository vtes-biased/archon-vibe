# Organizer Guide

This guide walks you through running a tournament with Archon — from setup to final results. It follows the natural lifecycle of an event with practical advice for different situations.

## Setting Up Your Tournament

### Creating the Tournament

Go to **Tournaments** and tap **+ New Tournament**. Fill in:

- **Name**: displayed to players on the tournament page
- **Format**: Constructed, Limited, V5, or Draft
- **Rank**: VEKN ranking tier (Basic, NC, CC, etc.)
- **Date & Time**: start time with timezone. Finish time is optional — useful for players planning their day, but not required.
- **Location**: country, city, venue, address — or mark as **Online**
- **Max Rounds**: number of preliminary rounds (2–4 when VEKN push is enabled)
- **Description**: optional details (supports [Markdown](https://commonmark.org/help/))

> **NOTE**
> Once the first round begins, **name**, **format**, **rank**, and **online** are locked. Max rounds becomes immutable once results have been pushed to VEKN.

### VEKN Calendar

Most organizers push to VEKN early so the event appears on the calendar and players can plan ahead. Tap **Push to VEKN** from the Overview tab to create the calendar entry.

Alternatively, if you created the event on the VEKN website first, it will sync to Archon automatically. Avoid creating the event in both places — duplicates are confusing and hard to resolve.

All players must have VEKN IDs before final results can be pushed. When you finish the tournament, results are uploaded automatically. Failed pushes are retried hourly in the background.

### Configuration

In the **Config** tab you can adjust settings at any time unless noted otherwise.

**Play Options**

- **Allow Proxies** — permit proxy cards (Standard rank only)
- **Multideck** — players submit a separate deck per round (Standard rank only)
- **Decklist Required** — players see a warning badge until they upload a deck (see Deck Management below)

**Standings Visibility** — controls what players see during the event:

- *Private* — standings hidden
- *Cutoff* — standings hidden, but shows the score threshold to reach the top 5
- *Top 10* — only the top 10 shown
- *Public* — full standings visible
- After the tournament finishes, full standings are always visible.

**Decklists Mode** — controls which decks are published after the tournament finishes:

- *Winner* — only the winner's deck
- *Finalists* — decks of the winner and finalists
- *All* — all submitted decklists

> **NOTE**
> Changing decklists mode on a finished tournament immediately recomputes which decks are publicly visible.

**Timer** (online tournaments only)

- **Round time** — duration in minutes (0 = no timer)
- **Finals time** — separate duration for finals (0 = use round time)
- **Extension policy** — how tables get extra time:
  - *Additions* — fixed-time buttons (+1/+2/+3/+5 min)
  - *Clock Stop* — pause/resume per table
  - *Both* — both mechanisms available

Only organizers have access to timer controls (start, pause, reset, per-table extensions). Players see the countdown but cannot modify it.

**Other Settings**

- **Max Rounds** — cannot be set below the number of completed rounds; locked once pushed to VEKN
- **League** — link the tournament to an active league (e.g., Grand Prix, Iberian League). This is a grouping mechanism for series events — league membership does not affect tournament scoring or standings.
- **Table Rooms** — assign room names to table number ranges. For multi-room venues, this helps players find their table (e.g., "Room A: tables 1–5, Room B: tables 6–10").

### Co-organizers

Tap **Add Co-organiser** from the tournament page to grant another user full organizer permissions. Co-organisers have equal access — there is no hierarchy. Remove them at any time.

For larger events, having co-organizers is essential: they can help with check-in, scoring, and handling issues at different tables. For multi-judge events (tournament rules recommend 6 judges when judges are playing), co-organizers also serve as judges with full app access.

## Registration

### Opening Registration

From **Overview**, tap **Open Registration**. Players can now self-register from the tournament page.

**Planning ahead**: For events where you need to size the venue, estimate catering, or cap attendance, open registration days or weeks in advance. The player list builds up and gives you a headcount.

**Walk-in events**: If your event is small and everyone registers on-site, you can skip early registration entirely. Open registration, let people sign up on their phones, then move straight to check-in. You can even use **Add Player** to register people manually if they have trouble with the app.

### Closing Registration

When ready, tap **Close Registration & Start Check-in** to move to the Waiting state. This does not remove anyone — all registered players stay in the list.

- **Cancel Registration** — reverts to Planned state. Players already registered stay in the list but registration is closed.
- **Reopen Registration** (from Waiting) — reverts to Registration state. All checked-in players are reset to Registered.

### Adding and Removing Players

- **Add Player** — you can manually add a player in any state (Planned through Finished). This is how you handle late arrivals.
- **Remove Player** — only works before any round has started. After that, use **Drop Out** instead.
- **Drop Out** — marks a player as Finished (dropped). Available during Waiting or Playing. Either the player or you can trigger this.

### Late Arrivals

Players showing up after the event has started is common. Add them with **Add Player** — they enter as Registered.

- **Round just started and there's room on a 4-player table** that hasn't finished the first turn? Use **Seat Player** to add them directly to that table.
- **Round is well underway or no 4-player table available?** They'll sit out this round and play from the next one. Make sure to check them in (or seat them) before the next round starts, or they'll be auto-dropped.

## Check-in

Check-in confirms who is actually present and ready to play. This matters because starting a round with missing players causes real problems — a missing player at a 4-player table makes it illegal, and too many absences can force you to cancel the round entirely.

### Check-in Methods

- **QR Code** — display the tournament QR code from Overview. Players scan it to check themselves in.
- **Manual** — check in individual players from the player list.
- **Check All In** — bulk-check all Registered players at once.
- **Check Out** — revert an individual player from Checked-in to Registered.
- **Reset Check-in** — revert all Checked-in players back to Registered.

### Choosing Your Approach

**Small to medium events (10–40 players, single room)**: You know everyone in the room. Use **Check All In** or check people in manually as you greet them. Between rounds, just keep everyone checked in — you'll notice if someone needs to leave.

**Larger events (50+ players, multi-room venues)**: Consider printing QR code sheets and posting them at the entrance or on tables, or have co-organizers circulate with the QR code displayed on their devices. Players scan as they arrive.

**Between rounds**: Check-in status is preserved — it does not reset automatically when a round ends. For back-to-back rounds at a same-day in-person event, you typically leave check-in as-is and just start the next round. But for events with a lunch break, multi-day events, or online tournaments, use **Reset Check-in** and run a fresh check-in. Online is especially important: players may silently disconnect or have tech issues, and you won't know who's missing until it's too late.

### Check-in Rules

- Players with an active **disqualification** or **suspension** cannot be checked in, even by you.
- If "Decklist required" is enabled and a player has no deck, they get a **missing decklist** warning badge. This is a warning only — it does not block check-in (see Deck Management).

## Deck Management

### Decklist Required

When enabled, players without a deck see a warning badge. This is intentionally non-blocking — the goal is to surface missing decklists so you and the player can address it, not to prevent anyone from playing.

In practice: some players will deliver a paper decklist, others may forget, and that's between the player and the judge. The app flags the issue; what you do about it is your call. You can review who has and hasn't uploaded a deck from the **Decks** tab and issue warnings per the judge's guide if needed.

### How Players Submit Decks

Players can upload decks themselves before the event. The app supports:

- **Pasting** a decklist as text
- **Importing from URL** — supports [VDB](https://vdb.im), [VTESDecks](https://vtesdecks.com), and [Amaranth](https://amaranth.vtes.co.nz)
- **Scanning a QR code** — if a player built their deck on VDB, they can show its QR code. You (or they) can scan it directly in the app using the **Scan QR** button in the deck upload dialog. This is particularly handy on-site when a player struggles with the app.

### Deck Visibility Timeline

Decks follow a lifecycle:

- **Before the first round starts**: you cannot see player deck contents. Players can freely upload, modify, and delete their decks.
- **Once a round starts**: you can now see and modify all decks (to fix issues during the event). Players with a single deck can no longer modify it. In multideck tournaments, players can still upload a deck for the next round.
- **After the tournament finishes**: players can once again upload and modify their decks. This lets winners add a missing deck for TWDA submission, or players fix inconsistencies. Deck publication is controlled by the **decklists mode** setting.

### Organizer Deck Tools

From the **Decks** tab, you can:

- View all player decks (once the first round has started)
- Upload, replace, or delete decks on behalf of any player
- Manage multideck round slots

You bypass all timing restrictions — you can modify decks at any stage, including after the tournament finishes.

## Running Rounds

### Starting a Round

Tap **Start Round** from the Overview tab. Archon seats players automatically using the VEKN seating algorithm — a simulated annealing optimization over 9 fairness rules (see Seating Rules Reference below).

**Requirements:**

- At least **4 checked-in** players
- Not exceeding **max rounds**

> **IMPORTANT**
> Exactly **6, 7, or 11** checked-in players cannot be seated into valid tables of 4–5. Adjust attendance (add or drop a player) before starting.

When a round starts:

- Any Registered (not checked-in) players are **automatically dropped** (set to Finished). This is why check-in matters.
- The seating quality is displayed: **Perfect**, **OK** (minor rule compromises), or **Invalid** (with a rule-by-rule R1–R9 breakdown).

### Viewing Tables

Players see their table and seat assignment in the app. For venues with spotty connectivity or when running offline, use the **Print** button to print the round seating and post it in the room. For 30+ player events, printing becomes particularly useful.

If you configured **Table Rooms**, room assignments appear alongside table numbers to help players find their physical location in multi-room venues.

### Altering Seating

Several tools let you adjust tables after a round starts:

- **Swap Seats** — exchange two players' positions
- **Alter Seating** — full drag-and-drop editor for moving players between tables
- **Seat / Unseat** — add or remove a player from the round
- **Add / Remove Table** — add an empty table or remove one (remove only works on empty tables)

> **NOTE**
> Moving a player to a **different table** resets their score to zero. Keeping them on the **same table** (just changing seat position) preserves their score. Alter Seating rejects changes that create predator-prey repeats (R1 violation).

### Scoring

VP scores drive all other computations (GW, TP) automatically.

The standard workflow is **player self-reporting**: players enter their own VP as games finish, and you monitor for issues. For small casual events where the organizer is not playing, you might enter all scores directly.

- **Players** can enter VP in 0.5 increments from 0 to the table size, but cannot enter (table size − 0.5). Self-reporting is blocked if the table has an override.
- **Organizers** can force any VP value — the table state becomes "Invalid" if scores don't add up.
- VP scores are validated via oust-order simulation. Invalid distributions are rejected for non-organizers.

### Override

Use **Override** when a table needs to be force-finished with a judge ruling — for example, a player leaves mid-game without any VP being awarded, or time expires with an unresolved situation. Override requires a mandatory judge comment explaining the ruling. This locks the table from further player edits.

Use **Unoverride** to reopen a table if the situation changes.

### Judge Calls (Online Only)

During online tournaments, players can tap **Call Judge** from their table view. This sends an alert to all organizers: an amber banner appears at the top of your screen with an audio chime, showing the table number and player name. The banner persists for 2 minutes or until you dismiss it. Multiple calls stack as separate banners.

This is invaluable for online events where you can't physically walk between tables. Players have a 30-second cooldown between calls to prevent spam.

### Finishing a Round

Tap **End Round** when all tables are scored. Every table must be Finished or have an Override. Standings are recalculated.

### Between Rounds

After ending a round, the tournament returns to **Waiting** state. Decide whether to run a fresh check-in or keep everyone checked in (see Check-in section above), then start the next round when ready.

### Cancelling a Round

**Cancel Round** removes the entire round, reverts all players who were playing back to Checked-in, and recalculates standings. Use this if something went fundamentally wrong with seating or if too many players are missing.

## Timer (Online Only)

The timer is available for online tournaments and syncs in real time. Clients compute the countdown locally — there are no per-second broadcasts.

### Global Controls (Organizer Only)

- **Start** — begins the countdown
- **Pause** — stops the clock (resumes where it left off)
- **Reset** — clears the timer to its full duration and removes all per-table extensions

### Colour States

- **Green** — time remaining
- **Amber** — less than 5 minutes left
- **Red** — time expired

### Per-table Extensions (Organizer Only)

The extension policy (set in Config) determines what controls appear:

- **Additions** — buttons for +1, +2, +3, +5 minutes per table. Capped at 10 minutes total extra time per table.
- **Clock Stop** — pause/resume button per table. While paused, the elapsed pause time converts to extra time when resumed.
- **Both** — both mechanisms available.

## Sanctions

Open a player's profile from the player list and tap **Add Sanction**. Select the level, category, and subcategory.

### Sanction Levels

- **Caution** — verbal warning, not formally tracked
- **Warning** — recorded, visible for 18 months
- **Standings Adjustment (SA)** — −1 VP penalty applied to a specific round
- **Disqualification (DQ)** — removed from the event, blocks future check-in until lifted

### Escalation

Archon shows **escalation hints** suggesting the appropriate level based on prior infractions. If you select a level below the suggestion, a **downgrade warning** appears — you can still proceed.

These escalation guidelines come from the judge's guide. The app does not enforce them — it is up to the head judge to decide. That said, judges should not deviate from the guidelines without head judge approval, and the head judge should be conservative about deviations. Archon does not track head judge versus other judges; that's for you to manage between co-organizers.

### Standings Adjustment Details

When issuing an SA, select the **round** it applies to. The −1 VP is subtracted from the player's adjusted VP for that round.

- If the player's raw VP in the SA round is less than 1.0, the shortfall (1.0 − raw VP) overflows as a deduction from their total standings VP.
- SA does not change stored scores — it affects GW and TP computation. A player who would have earned a GW may lose it after the adjustment.

### Lift and Delete

- **Lift** a DQ to allow the player to check in again.
- **Delete** a sanction to remove it entirely.

## Payment Tracking

Many tournaments have an entry fee. Track payments from the player list — each player has a status:

- **Pending** (default) / **Paid** / **Refunded** / **Cancelled**

Use **Mark All Paid** to bulk-set all Pending players to Paid. Players with other statuses (Refunded, Cancelled) are not affected.

> **TIP**
> Payment is informational only — it does not block registration, check-in, or any other action. It's a convenience tracker for you to keep tabs on who has paid.

## Finals

### Resolving Ties

If players are tied in the top 5 (same GW, VP, and TP), a **toss** is needed to break the tie before finals can start.

- **Random Toss** — Archon assigns a deterministic random value
- **Set Toss** — manually assign toss values

You cannot start finals until all top-5 ties are resolved.

### Starting Finals

Requirements:

- Tournament in **Waiting** state (current round finished)
- At least **2 preliminary rounds** completed
- At least **5 eligible** (non-DQ'd) players with results
- No unresolved ties in the top 5

Tap **Start Finals**. The top 5 are selected by GW > VP > TP > toss. DQ'd players are skipped (so the 6th-place player may qualify if a top-5 player was DQ'd).

After selecting the finalists, conduct the **VEKN card-drawing procedure** ("the seating dance") as described in the tournament rules, then input the resulting seating order into Archon.

### Altering Finals Seating

Use **Alter Finals Seating** (drag-and-drop) to change the seating order if needed. The same 5 players must remain — you can only reorder them.

### Scoring Finals

Same scoring UI as preliminary rounds, with two key differences:

- **No 2.0 VP threshold** — the player with the highest VP always gets the GW
- **VP ties broken by seed order** — the higher-seeded player (better preliminary ranking) wins

### Finishing Finals

Tap **Finish Finals** to determine the winner and mark all non-DQ'd players as Finished.

## Finishing the Tournament

Tap **Finish Tournament** from the Overview tab. This:

- Locks results and computes final ratings
- Sets deck visibility based on the decklists mode
- Triggers TWDA submission if the winner has a deck
- Pushes results to VEKN if the event was registered there

A tournament can be finished without running finals (e.g., league events), though note that without finals the event does not award rating points.

### Reopening

**Reopen Tournament** (from Finished) reverts to Waiting state. This clears finals results, winner/finalist flags, and deck publication flags.

DQ'd players stay DQ'd. Use this to correct scoring errors or administrative mistakes — ratings recompute when you finish again.

## Sharing Results

After the tournament finishes, several export options are available:

- **Share Image** — generates a social-media-friendly PNG card (1080×1350) with tournament details, winner, and top-5 standings. Great for posting to Discord or community forums.
- **Copy Text** — copies markdown-formatted results to clipboard (includes standings and winner's decklist)
- **Download Report** — text format (human-readable standings + decklist) or JSON (structured data)
- **TWDA Submission** — automatically submits the winner's deck as a GitHub pull request to the Tournament Winning Deck Archive (if the winner has uploaded a deck)

## Raffle

Run prize draws from the **Raffle** section — common at medium and large events.

### Drawing

Choose a **pool** to filter eligible players (All Players, Non-Finalists, Game Winners, No Game Win, No Victory Point) then:

- Set a **label** for the prize name
- Choose the number of winners to draw
- Toggle **Exclude previously drawn** to skip players who already won a prize
- Tap **Draw** to select random winners
- **Undo** removes the last draw
- **Clear** resets all raffle results

## Offline Mode

Many VTES events take place in venues with unreliable internet — game stores in basements, underground bars, or just buildings with thick walls and no mobile signal. Archon supports full offline operation for these situations.

### Preparing

1. Open the tournament page **while still online** (on Wi-Fi or mobile data) to sync all data to your device
2. Tap **Go Offline** from the Overview tab
3. A device lock is acquired — only your device can edit the tournament

You can prepare at home: load the tournament, go offline, then close the app. When you arrive at the venue without connectivity, reopen the app and navigate to the tournament — it works entirely from local data. The app caches everything needed (tournament data in IndexedDB, app assets via service worker).

### Running Offline

Run the tournament normally. All changes are stored locally. When your device has intermittent connectivity, Archon periodically saves a backup to the server (every 30 seconds), but the tournament stays in offline mode until you explicitly go back online.

### Going Back Online

Tap **Go Back Online** to sync your local changes. The server reconciles any conflicts (server is source of truth) and resumes normal real-time sync.

### Force Takeover

If the original device is unavailable (dead battery, forgotten at home, switching from laptop to phone), another organizer can tap **Force Takeover** to claim the device lock. This transfers editing rights but may lose any unsynced changes from the original device.

For emergencies, an IC (Inner Circle) can **force-unlock** a tournament to clear all offline state.

### Archon File Backup

As an additional safety net, you can download an Archon file export of the tournament data. If all else fails, this file can be re-imported.

> **TIP**
> Test offline mode before tournament day. Open the tournament, go offline, close the app, turn off connectivity, reopen, and navigate back to the tournament. Confirm everything loads.

## Archon Import

Import tournament data from legacy Archon spreadsheets (.xlsx format). This is useful for organizers migrating from the old system.

1. Download the **blank template** from the import dialog
2. Fill in tournament info, player list, and round results
3. Upload the completed spreadsheet

Archon matches players by VEKN ID first, then by email. Unmatched players are created as new accounts. If the tournament already has rounds, you'll be asked to confirm before overwriting.

## Seating Rules Reference

The VEKN seating algorithm optimizes 9 rules in strict priority order (R1 is highest priority). The algorithm uses simulated annealing to find the best possible seating.

| Rule | Name | Description |
|------|------|-------------|
| R1 | Predator-Prey | Two players should not be predator-prey more than once across all rounds |
| R2 | Opponent Every Round | Two players should not face each other in every round |
| R3 | VP Fairness | Minimize the spread (standard deviation) of VP earned across players |
| R4 | Opponent Twice | Two players should not face each other more than once |
| R5 | Fifth Seat Twice | A player should not sit in the fifth seat of a 5-player table more than once |
| R6 | Same Relationship | Two players should not have the same relative position (prey, grand-prey, etc.) more than once |
| R7 | Same Seat | A player should not sit in the same numbered seat more than once |
| R8 | Transfer Fairness | Minimize the spread of transfers (ousts) distributed across players |
| R9 | Same Position Group | Two players should not be neighbours (or non-neighbours) more than once |

R1 and R2 are hard constraints — the algorithm prioritizes them absolutely over all others. When the seating score shows **OK** or **Invalid**, the R1–R9 breakdown tells you exactly which rules had to be compromised.

## FAQ

**Can I run an event without ever opening registration?**
Yes. You can keep the tournament in Planned state, add players manually, and start rounds. This works for small impromptu events.

**What happens if a player self-reports the wrong VP?**
VP scores are validated against oust-order simulation — impossible distributions are rejected. If a valid but incorrect score is entered, you can correct it as organizer.

**Can I change the number of rounds mid-tournament?**
Yes, you can increase max rounds at any time (up to the VEKN limit when pushed). You cannot decrease it below the number of completed rounds.

**A player needs to leave — what do I do?**
Use **Drop Out** to mark them as Finished. If they're mid-game, use **Unseat** to remove them from the table, then resolve scoring with an Override if needed.

**Can I run finals with fewer than 5 players?**
No. Finals require exactly 5 eligible (non-DQ'd) players. If a DQ'd player is in the top 5, the 6th-place player takes their spot.

**I finished the tournament but the scores are wrong — what now?**
Use **Reopen Tournament** to go back to Waiting state, fix the scores, and finish again. Ratings recompute automatically.

**Do I need to run finals?**
No. Some events skip finals — typically league events or tournaments that didn't complete all planned rounds. Note that without finals, the tournament does not award rating points.
