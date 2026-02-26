# Organizer Guide

This guide covers every feature available to tournament organizers in Archon, from creation to final results.

## Creating a Tournament

Go to **Tournaments** and tap **+ New Tournament**. Fill in:

- **Name**: displayed to players
- **Format**: Constructed, Limited, V5, or Draft
- **Rank**: VEKN ranking tier (Basic, NC, CC, etc.)
- **Date & Time**: start/end with timezone
- **Location**: country, city, venue, address — or mark as **Online**
- **Max Rounds**: number of preliminary rounds (2–4 when VEKN push is enabled)
- **Description**: optional details (supports Markdown)

> **NOTE**
> Once the tournament has started (first round begun), **name**, **format**, **rank**, and **online** cannot be changed. Max rounds becomes immutable once results have been pushed to VEKN.

## Configuration

In the **Config** tab you can adjust settings at any time unless noted otherwise.

### Play Options

- **Allow Proxies** — permit proxy cards (Standard rank only)
- **Multideck** — players submit a separate deck per round (Standard rank only)
- **Decklist Required** — players see a warning badge until they upload a deck

### Visibility

- **Standings mode** — controls what players see during the event:
  - *Private* — standings hidden
  - *Cutoff* — standings hidden, but shows the score threshold to reach the top 5
  - *Top 10* — only the top 10 shown
  - *Public* — full standings visible
  - After the tournament finishes, full standings are always visible.
- **Decklists mode** — controls which decks are published after the tournament finishes:
  - *Winner* — only the winner's deck
  - *Finalists* — decks of the winner and finalists
  - *All* — all submitted decklists

> **NOTE**
> Changing decklists mode on a finished tournament immediately recomputes which decks are publicly visible.

### Timer (Online Only)

- **Round time** — duration in minutes (0 = no timer)
- **Finals time** — separate duration for finals (0 = use round time)
- **Extension policy** — how tables get extra time:
  - *Additions* — fixed-time buttons (+1/+2/+3/+5 min)
  - *Clock Stop* — pause/resume per table
  - *Both* — both mechanisms available

### Other Settings

- **Max Rounds** — cannot be set below the number of completed rounds; locked once pushed to VEKN
- **League** — link the tournament to an active league
- **Table Rooms** — assign room names to table number ranges (useful for multi-room venues)

## Managing Registration

### Opening and Closing

1. From **Overview**, tap **Open Registration** — state moves to Registration
2. Players self-register from the tournament page
3. When ready, tap **Close Registration & Start Check-in** — state moves to Waiting

### Cancel / Reopen

- **Cancel Registration** (from Registration) — reverts to Planned state. Players already registered stay in the player list but registration is closed.
- **Reopen Registration** (from Waiting) — reverts to Registration state. All checked-in players are reset to Registered.

### Adding and Removing Players

- **Add Player** — organizer can manually add a player in any state (Planned through Finished)
- **Remove Player** — only works if no rounds have been played yet. After any round starts, use **Drop Out** instead.
- **Drop Out** — marks a player as Finished (dropped). Available during Waiting or Playing. The player or the organizer can trigger this.

## Co-organisers

Tap **Add Co-organiser** from the tournament page to grant another user full organizer permissions. Co-organisers have equal access — there is no hierarchy. Remove them at any time.

## Check-in

Before each round, players must check in to confirm their attendance.

### Check-in Methods

- **QR Code** — display the QR code from Overview for players to scan at the venue
- **Manual** — check in individual players from the player list
- **Check All In** — bulk-check all Registered players
- **Reset Check-in** — revert all Checked-in players back to Registered

### Check-in Rules

- Players with an active **disqualification** or **suspension** cannot be checked in, even by the organizer.
- If "Decklist required" is enabled and a player has no deck, they get a **missing decklist** warning badge. This is a warning only — it does not block check-in.
- **Check Out** — reverts an individual player from Checked-in to Registered.

## Running Rounds

### Starting a Round

Tap **Start Round** from the Overview tab. Archon seats players automatically using the VEKN seating algorithm (simulated annealing optimizing 9 rules).

**Requirements:**

- At least **4 checked-in** players
- Not exceeding **max rounds**

> **IMPORTANT**
> Exactly **6, 7, or 11** checked-in players cannot be seated into valid tables of 4–5. Adjust attendance before starting.

When a round starts:

- Registered (not checked-in) players are **automatically dropped** (set to Finished)
- The seating score is displayed: **Perfect**, **OK** (minor rule compromises), or **Invalid** (with a rule-by-rule R1–R9 breakdown)

### During a Round

- View tables in the **Rounds** tab
- Enter scores for each table as games finish
- Players can self-report VP scores unless the table has an override

### Altering Seating

Several tools let you adjust tables after a round starts:

- **Swap Seats** — exchange two players' positions
- **Alter Seating** — full drag-and-drop editor for moving players between tables
- **Seat / Unseat** — add or remove a player from the round
- **Add / Remove Table** — add an empty table or remove one (remove only works on empty tables)

> **NOTE**
> Moving a player to a **different table** resets their score to zero. Keeping a player on the **same table** (just changing seat position) preserves their score. Alter Seating rejects changes that create predator-prey repeats (R1 violation).

### Scoring

VP scores drive all other computations (GW, TP) automatically.

- **Non-organizers** can enter VP in 0.5 increments from 0 to the table size, but cannot enter (table size − 0.5). Self-reporting is blocked if the table has an override.
- **Organizers** can force any VP value — the table state becomes "Invalid" if scores don't add up.
- VP scores are validated via oust-order simulation. Invalid distributions are rejected for non-organizers.

### Override

Use **Override** to force-finish a table with a mandatory judge comment. This locks the table from further player edits. Use **Unoverride** to reopen it.

### Finishing a Round

Tap **End Round** when all tables are scored. Every table must be Finished or have an Override. Standings are recalculated.

### Cancelling a Round

**Cancel Round** removes the entire round, reverts all players who were playing back to Checked-in, and recalculates standings.

## Timer (Online Only)

The timer is only available for online tournaments and is synced in real time via SSE. Clients compute the countdown locally — there are no per-second broadcasts.

### Global Controls

- **Start** — begins the countdown
- **Pause** — stops the clock (resumes where it left off)
- **Reset** — clears the timer to its full duration

### Colour States

- **Green** — time remaining
- **Amber** — less than 5 minutes left
- **Red** — time expired

### Per-table Extensions

The extension policy (set in Config) determines what controls appear:

- **Additions** — buttons for +1, +2, +3, +5 minutes. Capped at 600 seconds (10 min) total extra time per table.
- **Clock Stop** — pause/resume button per table. While paused, the elapsed pause time converts to extra time when resumed.
- **Both** — both mechanisms available.

## Sanctions

Open a player's profile from the player list and tap **Add Sanction**. Select the level, category, and subcategory.

### Sanction Levels

- **Caution** — verbal warning, not formally tracked
- **Warning** — recorded, visible for 18 months
- **Standings Adjustment (SA)** — −1 VP penalty applied to a specific round
- **Disqualification (DQ)** — removed from the event, blocks future check-in until lifted

### Escalation and Downgrade

Archon shows **escalation hints** suggesting the appropriate level based on prior infractions. If you select a level below the suggestion, a **downgrade warning** appears — you can still proceed.

### Standings Adjustment Details

When issuing an SA, select the **round** it applies to. The −1 VP is subtracted from the player's adjusted VP for that round.

- If the player's raw VP in the SA round is less than 1.0, the shortfall (1.0 − raw VP) overflows as a deduction from their total standings VP.
- SA does not change stored scores — it affects GW and TP computation. A player who would have earned a GW may lose it after the adjustment.

### Lift and Delete

- **Lift** a DQ to allow the player to check in again
- **Delete** a sanction to remove it entirely

## Payment Tracking

Track player payments from the player list. Each player has a payment status:

- **Pending** (default) / **Paid** / **Refunded** / **Cancelled**

Use **Mark All Paid** to bulk-set all Pending players to Paid. Players with other statuses (Refunded, Cancelled) are not affected.

> **TIP**
> Payment is informational only — it does not block registration, check-in, or any other action.

## Finals

### Toss and Tiebreakers

If players are tied in the top 5 (same GW, VP, and TP), a **toss** is needed to break the tie.

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

The organizer inputs the finals seating order following the **VEKN card-drawing procedure**.

### Altering Finals Seating

Use **Alter Finals Seating** (drag-and-drop) to change the seating order. The same 5 players must remain — you can only reorder them.

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
- Triggers TWDA submission if the winner has a deck (see VEKN Integration)

A tournament can be finished without running finals — not all events need them.

## Reopening a Tournament

**Reopen Tournament** (from Finished) reverts to Waiting state. This clears:

- Finals results
- Winner and finalist flags
- All deck public flags (decks become private again)

DQ'd players stay DQ'd. This is useful for correcting errors — ratings recompute when you finish again.

## Deck Management

From the **Decks** tab, organizers can:

- View all player decks
- Upload, replace, or delete decks on behalf of any player
- Manage multideck round slots

> **NOTE**
> Organizers bypass all deck timing restrictions. You can modify decks at any stage, including after the tournament finishes (useful for TWDA submissions).

## Raffle

Run prize draws from the **Raffle** section.

### Pool Types

Choose which players are eligible:

- **All Players** — everyone who played in any round
- **Non-Finalists** — played but not in finals
- **Game Winners** — players with at least 1 GW
- **No Game Win** — players with 0 GW
- **No Victory Point** — players with 0 VP

### Drawing

- Set a **label** for the prize name
- Choose the number of winners to draw
- Toggle **Exclude previously drawn** to skip players who already won a prize
- Tap **Draw** to select random winners
- **Undo** removes the last draw
- **Clear** resets all raffle results

## Sharing and Reports

After the tournament finishes, several export options are available:

- **Share Image** — generates a PNG card (1080×1350) with tournament details, winner, and top-5 standings
- **Copy Text** — copies markdown-formatted results to clipboard (includes standings and winner's decklist)
- **Download Report** — text format (human-readable standings + decklist) or JSON (structured data)
- **TWDA Submission** — automatically submits the winner's deck as a GitHub pull request to the Tournament Winning Deck Archive (if configured)

## VEKN Integration

### Push to VEKN

Tap **Push to VEKN** to create a calendar entry on the VEKN website. When the tournament finishes, results are pushed automatically.

- All players must have VEKN IDs before results can be pushed
- Failed pushes are retried hourly in a background batch
- Once pushed, **max rounds becomes immutable**

The tournament's VEKN event ID is stored and displayed for reference.

## Archon Import

Import tournament data from legacy Archon spreadsheets (.xlsx format).

1. Download the **blank template** from the import dialog
2. Fill in tournament info, player list, and round results in the template
3. Upload the completed spreadsheet

Archon matches players by VEKN ID first, then by email. Unmatched players are created as new accounts. If the tournament already has rounds, you'll be asked to confirm before overwriting.

## Offline Mode

For venues without reliable internet, Archon supports full offline operation.

### Going Offline

1. Open the tournament page while online to sync all data
2. Tap **Go Offline** from the Overview tab
3. A device lock is acquired — only your device can edit the tournament
4. Run the tournament normally. All changes are stored locally and periodically saved to the server (every 30 seconds when connected)

### Going Back Online

Tap **Go Back Online** to sync your local changes. The server reconciles any conflicts (server is source of truth) and resumes normal SSE streaming.

### Force Takeover

If the original device is unavailable, another organizer can tap **Force Takeover** to claim the device lock. This transfers editing rights but may lose any unsynced changes from the original device.

For emergencies, an IC (International Coordinator) can **force-unlock** a tournament to clear all offline state.

> **TIP**
> Test offline mode before tournament day to make sure everything works smoothly.

## Player Count Reference

Quick reference for seating constraints:

| Constraint | Value |
|---|---|
| Minimum players to start a round | 4 |
| Impossible to seat (no valid 4/5 split) | 6, 7, or 11 |
| Minimum eligible players for finals | 5 (non-DQ'd) |
| Minimum preliminary rounds before finals | 2 |
