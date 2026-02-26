# Player Guide

Welcome to Archon, the official VEKN tournament management app. This guide covers everything you need as a player — from finding events to understanding your ratings.

## Finding Tournaments

Browse the **Tournaments** page to see upcoming events. Use the filters to narrow by country, format, and date range.

Toggle **My Agenda** to see only tournaments you're registered for or organising.

**Calendar feed:** Tap the calendar icon in the top bar to subscribe to a personal iCal feed. Tournament dates will appear in your phone or desktop calendar app automatically.

## Registering

Once the organiser opens registration, a **Register** button appears on the tournament page. Tap it to sign up — your status changes to "Registered."

To withdraw before check-in opens, tap **Unregister**. Once registration closes, only the organiser can remove you.

## Uploading Your Decklist

Go to the **Decks** tab on the tournament page. You can upload a deck by:

- **Pasting** the deck list text directly
- **From URL** — paste a link from VDB, VTESDecks, or Amaranth
- **QR code** — scan a VDB deck QR code with your camera

The deck is validated automatically: you'll see errors (illegal deck) or warnings (e.g. non-V5 cards in a V5 event) immediately.

### When can I change my deck?

- **Before the tournament starts** — you can replace or delete your deck freely.
- **During the tournament (single-deck)** — your deck is locked once any round has started. You cannot replace or delete it.
- **During the tournament (multideck)** — each round has its own deck slot. You can upload a new deck for an upcoming round, but slots for rounds already played are locked.
- **After the tournament** — if you never submitted a deck, you can still upload one (useful for the Tournament Winning Deck Archive). You cannot change an existing deck.

> **TIP**
> If the organiser has enabled "Decklist required," you'll see a warning badge until you upload a deck. Upload it before check-in to avoid issues.

## Checking In

Before each round, the organiser opens a check-in phase. You can check in by:

- **QR Code** — tap "Scan QR to Check In" and point your camera at the code displayed at the venue.
- **Self check-in** — tap the **Check In** button on the tournament page.
- **Organiser check-in** — the organiser checks you in from their player list.

If you don't check in before a round starts, you are automatically marked as finished (dropped) for that round.

### What blocks check-in?

You cannot check in if you have an active **disqualification** or **suspension** sanction. The organiser cannot override this.

## During a Round

After a round starts, check the **Rounds** tab to see your **table assignment** and who you're playing with. Tables show player names in seating order (your predator is above you, your prey below).

### Reporting Results

Any player seated at a table can enter VP scores once the game finishes. Tap on the score fields for your table and enter each player's VP. Once the scores are valid, the table is marked as finished.

If the organiser or judge has placed an **override** on your table, player scoring is locked — only the organiser can modify results.

### Calling a Judge

During an online tournament, tap the **Call Judge** button to alert organisers that your table needs assistance. This sends a real-time notification — it does not interrupt your game.

## Standings

The **Players** tab shows the current standings, depending on the organiser's visibility setting:

- **Private** — standings hidden during the event
- **Cutoff** — standings hidden, but shows the score threshold needed to reach the top 5
- **Top 10** — only the top 10 shown
- **Public** — full standings visible to all

After the tournament finishes, full standings are always visible. Your score shows **GW** (game wins), **VP** (victory points), and **TP** (tournament points).

### How are scores computed?

- **GW**: You earn 1 game win if you have the highest VP at your table *and* at least 2.0 VP (adjusted for any standings adjustment sanction). If two players tie for the highest VP, neither gets a GW.
- **VP**: Your raw victory points from the game.
- **TP**: Tournament points based on your VP rank within the table (60 for 1st, down to 12 for last). Tied players average their position points.

## Finals

If you qualify for the top 5 after the preliminary rounds, you play a finals table.

- The top 5 is determined by GW, then VP, then TP. Ties are resolved by a toss (random or manual, set by the organiser).
- Finals seating order is determined by the organiser following the VEKN card-drawing procedure.
- In finals, the player with the highest VP always gets the GW — there is no 2.0 VP threshold. If two finalists tie on VP, the higher-seeded player (from preliminary standings) wins.

## Viewing Decklists

After the tournament finishes, decklists may be visible depending on the organiser's setting:

- **Winner** — only the tournament winner's deck is shown
- **Finalists** — decks of the winner and finalists
- **All** — all submitted decklists

Your own deck is always visible to you regardless of this setting.

## Ratings & Rankings

After a finished tournament, your **rating points (RtP)** are calculated and visible on the **Rankings** page. Ratings are tracked separately by format:

- Constructed
- Constructed Online
- Limited
- Limited Online

Your overall rating is based on your **best 8 tournaments** in the trailing 18 months. Per tournament: 5 base RtP + 4 per VP + 8 per GW, plus a finalist bonus scaled by event size and rank.

Check the **Rankings** page to see your position and the **Hall of Fame** for players with 5+ tournament wins.

## Sanctions

If you receive a sanction during a tournament, it appears as a badge next to your name. Sanction levels:

- **Caution** — verbal warning, not formally tracked
- **Warning** — recorded on your profile, visible for 18 months
- **Standings Adjustment (SA)** — a −1 VP penalty applied to a specific round (see [How are scores computed?](#how-are-scores-computed))
- **Disqualification (DQ)** — removed from the event, blocks future check-in until lifted

Suspensions and bans are issued by the VEKN Ethics Committee, not tournament organisers.

## Your VEKN ID

Your Archon account is linked to your VEKN ID. If you need to unlink it (e.g. duplicate accounts), use the **Abandon VEKN ID** option in your profile. This preserves your tournament history but disassociates your account.

## Offline Resilience

Archon works offline. If you lose connectivity during a tournament, the app continues to display your table assignments and tournament data from its local cache. Your data will sync automatically when you're back online.
