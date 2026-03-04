<script lang="ts">
  import { renderGuideSection } from "$lib/markdown";
  import ExampleBox from "./ExampleBox.svelte";
  import {
    QrCode, WifiOff, Wifi, Share2, ClipboardCopy, Download, Dices, Dice3, Undo2, Trash2,
    Play, Pause, RotateCcw, Clock, ChevronDown, ChevronRight,
    ShieldCheck, PauseCircle, PlayCircle, Gavel, X,
  } from "lucide-svelte";

  let openFaq = $state<number | null>(null);
  const faqs = [
    { q: "Can I run an event without ever opening registration?", a: "Yes. You can keep the tournament in Planned state, add players manually, and start rounds. This works for small impromptu events." },
    { q: "What happens if a player self-reports the wrong VP?", a: "VP scores are validated against oust-order simulation — impossible distributions are rejected. If a valid but incorrect score is entered, you can correct it as organizer." },
    { q: "Can I change the number of rounds mid-tournament?", a: "Yes, you can increase max rounds at any time (up to the VEKN limit when pushed). You cannot decrease it below the number of completed rounds." },
    { q: "Can I run finals with fewer than 5 players?", a: "No. Finals require exactly 5 eligible (non-DQ'd) players. If a DQ'd player is in the top 5, the 6th-place player takes their spot." },
    { q: "I finished the tournament but the scores are wrong — what now?", a: "Use **Reopen Tournament** to go back to Waiting state, fix the scores, and finish again. Ratings recompute automatically." },
    { q: "Do I need to run finals?", a: "No. Some events skip finals — typically league events or tournaments that didn't complete all planned rounds. Players still receive base rating points — only the finalist bonus (winner/runner-up) requires finals." },
    { q: "How does staggered seating work for 6, 7, or 11 players?", a: "Not everyone plays every round. Extra rounds are added automatically and players rotate sitting out, with those who have the fewest games played prioritized for the next round. This ensures everyone gets a fair number of games." },
    { q: "When are events pushed to VEKN?", a: "When you finish a tournament that has a VEKN event ID, results are pushed automatically. If the push fails, it retries periodically in the background. The winner's deck is also submitted to the TWDA." },
    { q: "Can I delete a tournament?", a: "Yes, but only in **Planned** state (before registration opens). Any organizer or IC member can delete. Use **Reopen Tournament** to fix issues on finished events." },
    { q: "What is the difference between Remove Player and Drop Out?", a: "**Remove Player** is for players who haven't played any rounds. If they've already played, use **Drop Out** instead — it preserves their scores but excludes them from future seating." },
    { q: "A player is disqualified — what happens?", a: "DQ removes them from future rounds and blocks check-in. Existing scores stay. If currently seated, unseat them first and handle the table via **Override**. If the DQ'd player was in the top 5, the 6th-place player qualifies for finals. DQ can be lifted." },
    { q: "How do I handle a multi-day tournament?", a: "Between days, use **Reset Check-In** and run fresh check-in the next morning. Use **Go Offline** if the venue has unreliable internet." },
    { q: "What does decklists mode control?", a: "Controls which decks become visible to all members after the tournament finishes. **Winner** = only winner's deck. **Finalists** = top 5. **All** = every submitted deck. Changeable at any time." },
  ];
</script>

{@html renderGuideSection(`
This guide walks you through running a tournament with Archon — from setup to final results. It follows the natural lifecycle of an event with practical advice for different situations.

## Setting Up Your Tournament

### Creating the Tournament

Go to **Tournaments** and tap **+ New Tournament**. Fill in:

- **Name**: displayed to players on the tournament page
- **Format**: Standard, V5, or Limited
- **Rank**: Standard (default), National Championship, or Continental Championship — rank affects rating point multipliers
- **Date & Time**: start time with timezone. Finish time is optional — useful for players planning their day, but not required.
- **Location**: country, city, venue, address — or mark as **Online**
- **Max Rounds**: number of preliminary rounds (2–4 when VEKN push is enabled)
- **Description**: optional details (supports [Markdown](https://commonmark.org/help/))

> **NOTE**
> Once the first round begins, **name**, **format**, **rank**, and **online** are locked. Max rounds becomes immutable once results have been pushed to VEKN.

### Deleting a Tournament

A tournament can only be deleted while in **Planned** state — before registration opens. Any organizer or IC member can delete. Deletion is permanent and requires confirmation — there is no undo.

### VEKN Calendar

Most organizers push to VEKN early so the event appears on the calendar and players can plan ahead. Tap **Push to VEKN** from the Overview tab to create the calendar entry.

Alternatively, if you created the event on the VEKN website first, it will sync to Archon automatically. **Avoid creating the event in both places** — duplicates are confusing and hard to resolve.

When you finish the tournament, results are uploaded automatically. Failed pushes are retried hourly in the background.

### Configuration

In the **Config** tab you can adjust settings at any time unless noted otherwise.
`)}

<div class="not-prose my-4 grid gap-3 sm:grid-cols-2">
  <div class="rounded-lg border border-ash-700 bg-dusk-900/40 p-4">
    <h4 class="text-sm font-semibold text-bone-100 mb-2">Play Options</h4>
    <dl class="space-y-1.5 text-sm">
      <div><dt class="text-ash-300 inline font-medium">Allow Proxies</dt> <dd class="text-ash-400 inline">— proxy cards (Standard rank only)</dd></div>
      <div><dt class="text-ash-300 inline font-medium">Multideck</dt> <dd class="text-ash-400 inline">— separate deck per round (Standard rank only)</dd></div>
      <div><dt class="text-ash-300 inline font-medium">Decklist Required</dt> <dd class="text-ash-400 inline">— warning badge until deck uploaded</dd></div>
    </dl>
  </div>
  <div class="rounded-lg border border-ash-700 bg-dusk-900/40 p-4">
    <h4 class="text-sm font-semibold text-bone-100 mb-2">Standings Visibility</h4>
    <p class="text-xs text-ash-500 mb-1.5">What players see during the event:</p>
    <dl class="space-y-1 text-sm">
      <div><dt class="text-ash-300 inline font-medium">Private</dt> <dd class="text-ash-400 inline">— hidden</dd></div>
      <div><dt class="text-ash-300 inline font-medium">Cutoff</dt> <dd class="text-ash-400 inline">— hidden, shows top-5 threshold</dd></div>
      <div><dt class="text-ash-300 inline font-medium">Top 10</dt> <dd class="text-ash-400 inline">— only top 10 shown</dd></div>
      <div><dt class="text-ash-300 inline font-medium">Public</dt> <dd class="text-ash-400 inline">— full standings visible</dd></div>
    </dl>
    <p class="text-xs text-ash-500 mt-1.5">Always public after the tournament finishes.</p>
  </div>
  <div class="rounded-lg border border-ash-700 bg-dusk-900/40 p-4">
    <h4 class="text-sm font-semibold text-bone-100 mb-2">Decklists Mode</h4>
    <p class="text-xs text-ash-500 mb-1.5">Which decks are published after the tournament:</p>
    <dl class="space-y-1 text-sm">
      <div><dt class="text-ash-300 inline font-medium">Winner</dt> <dd class="text-ash-400 inline">— only the winner's deck</dd></div>
      <div><dt class="text-ash-300 inline font-medium">Finalists</dt> <dd class="text-ash-400 inline">— winner and finalists</dd></div>
      <div><dt class="text-ash-300 inline font-medium">All</dt> <dd class="text-ash-400 inline">— all submitted decklists</dd></div>
    </dl>
    <p class="text-xs text-ash-500 mt-1.5">Changing this on a finished tournament takes effect immediately.</p>
  </div>
  <div class="rounded-lg border border-ash-700 bg-dusk-900/40 p-4">
    <h4 class="text-sm font-semibold text-bone-100 mb-2">Timer <span class="text-xs text-ash-500 font-normal">(online only)</span></h4>
    <dl class="space-y-1.5 text-sm">
      <div><dt class="text-ash-300 inline font-medium">Round time</dt> <dd class="text-ash-400 inline">— minutes (0 = no timer)</dd></div>
      <div><dt class="text-ash-300 inline font-medium">Finals time</dt> <dd class="text-ash-400 inline">— separate duration (0 = use round time)</dd></div>
      <div><dt class="text-ash-300 inline font-medium">Extension policy</dt> <dd class="text-ash-400 inline">— Additions, Clock Stop, or Both</dd></div>
    </dl>
  </div>
  <div class="rounded-lg border border-ash-700 bg-dusk-900/40 p-4 sm:col-span-2">
    <h4 class="text-sm font-semibold text-bone-100 mb-2">Other Settings</h4>
    <dl class="space-y-1.5 text-sm">
      <div><dt class="text-ash-300 inline font-medium">Max Rounds</dt> <dd class="text-ash-400 inline">— cannot go below completed rounds; locked once pushed to VEKN</dd></div>
      <div><dt class="text-ash-300 inline font-medium">League</dt> <dd class="text-ash-400 inline">— link to an active league (grouping only, no effect on scoring)</dd></div>
      <div><dt class="text-ash-300 inline font-medium">Table Rooms</dt> <dd class="text-ash-400 inline">— room names for table ranges in multi-room venues</dd></div>
    </dl>
  </div>
</div>

{@html renderGuideSection(`

### Co-organizers

Tap **Add Co-organiser** from the tournament page to grant another user full organizer permissions. Co-organisers have equal access — there is no hierarchy. Remove them at any time. IC (Inner Circle) members automatically have organizer access to all tournaments.

For larger events, having co-organizers is essential: they can help with check-in, scoring, and handling issues at different tables. For multi-judge events (tournament rules recommend 6 judges when judges are playing), co-organizers also serve as judges with full app access.

## Registration

### Opening Registration

From **Overview**, tap **Open Registration**. Players can now self-register from the tournament page.
`)}

<ExampleBox>
  <button class="px-4 py-2 text-sm font-medium btn-emerald rounded-lg">
    Open Registration
  </button>
</ExampleBox>

{@html renderGuideSection(`
> **TIP**
> All players should link their VEKN ID before the tournament finishes, so results can be pushed to VEKN.

**Planning ahead**: For events where you need to size the venue, estimate catering, or cap attendance, open registration days or weeks in advance. The player list builds up and gives you a headcount.

**Walk-in events**: If your event is small and everyone registers on-site, you can skip early registration entirely. **Move straight to check-in** — checking in an unregistered player registers and checks them in at the same time, which is the ideal workflow for small walk-in events.

As organizer, you can manually add or remove players at any time, whether or not registration is open.

### Start Check-in

When the event is about to start, tap **Start Check-in** to verify who is actually present before seating the first round.
`)}

<ExampleBox>
  <div class="flex gap-3 items-center">
    <button class="px-4 py-2 text-sm font-medium btn-amber rounded-lg">
      Start Check-in
    </button>
    <button class="px-3 py-1.5 text-sm text-ash-300 border border-ash-600 rounded-lg">
      Back to Planning
    </button>
  </div>
</ExampleBox>

{@html renderGuideSection(`
- **Back to Planning** — reverts to Planned state. Players already registered stay in the list but registration is closed.

## Check-in

Check-in confirms who is actually present and ready to play. This matters because starting a round with missing players causes real problems — a missing player at a 4-player table makes it illegal, and too many absences can force you to cancel the round entirely.

### Check-in Methods
`)}

<ExampleBox>
  <div class="space-y-3 max-w-sm">
    <div class="flex gap-2 items-center">
      <button class="px-3 py-1.5 text-sm text-ash-300 border border-ash-600 rounded-lg flex items-center gap-1.5">
        <QrCode class="w-4 h-4" />
        Show Check-in QR Code
      </button>
    </div>
    <div class="flex gap-2">
      <button class="px-3 py-1.5 text-sm btn-emerald rounded">Check All In</button>
      <button class="px-3 py-1.5 text-sm text-ash-300 border border-ash-600 rounded">Reset Check-In</button>
    </div>
    <div class="bg-dusk-950 border border-ash-800 rounded-lg p-3">
      <div class="flex justify-between items-center text-sm">
        <span class="text-ash-300">Alice</span>
        <div class="flex gap-2">
          <button class="px-2 py-1 text-xs btn-emerald rounded">Check In</button>
          <button class="px-2 py-1 text-xs text-ash-400 border border-ash-700 rounded">Check Out</button>
        </div>
      </div>
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(`
- **QR Code** — display the tournament QR code from Overview. Players scan it to check themselves in.
- **Manual** — check in individual players from the player list.
- **Check All In** — bulk-check all Registered players at once.
- **Check Out** — revert an individual player from Checked-in to Registered.
- **Reset Check-In** — revert all Checked-in players back to Registered.

### Choosing Your Approach

**Small to medium events (10–40 players, single room)**: You know everyone in the room. Use **Check All In** or check people in manually as you greet them. Between rounds, just keep everyone checked in — you'll notice if someone needs to leave.

**Larger events (50+ players, multi-room venues)**: Consider printing QR code sheets and posting them at the entrance or on tables, or have co-organizers circulate with the QR code displayed on their devices. Players scan as they arrive.

**Between rounds**: Check-in status is preserved — it does not reset automatically when a round ends. For back-to-back rounds at a same-day in-person event, you typically leave check-in as-is and just start the next round. But for events with a lunch break, multi-day events, or online tournaments, use **Reset Check-In** and run a fresh check-in. Online is especially important: players may silently disconnect or have tech issues, and you won't know who's missing until it's too late.

### Late Arrivals

Players showing up after check-in is common. Use **Add Player** to add them — during the Waiting state they are automatically checked in. During a round, they enter as Registered and sit out until the next round. If a round just started and there's room on a 4-player table, use **Seat Player** to add them directly.

### Check-in Rules

- Players with an active **disqualification** or **suspension** cannot be checked in, even by you.
- If "Decklist required" is enabled and a player has no deck, they get a **missing decklist** warning badge. This is a warning only — it does not block check-in (see [Deck Management](#deck-management)).

If you moved to check-in too early and need to go back, use **Reopen Registration** to revert to Registration. All checked-in players are reset to Registered.
`)}

<ExampleBox>
  <div class="pt-2 border-t border-ash-800">
    <button class="px-3 py-1.5 text-sm text-ash-500">
      Reopen Registration
    </button>
  </div>
</ExampleBox>

{@html renderGuideSection(`
## Deck Management

### Decklist Required

When enabled, players without a deck see a warning badge. This is intentionally non-blocking — the goal is to surface missing decklists so you and the player can address it, not to prevent anyone from playing.

In practice: some players will deliver a paper decklist, others may forget, and that's between the player and the judge. The app flags the issue; what you do about it is your call. You can review who has and hasn't uploaded a deck from the **Decks** tab and issue warnings per the [judge's guide](/help/judges-guide) if needed.

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

From the **player list**, you can:

- View all player decks (once the first round has started)
- Upload, replace, or delete decks on behalf of any player
- Manage multideck round slots

Organizers can modify decks at any stage, including after the tournament finishes — but cannot see deck contents until the first round begins.

## Understanding Standings and Scoring

Standings are computed automatically from VP scores. Here's how the numbers work:

### Victory Points (VP)

VP are reported in 0.5 increments and validated against an oust-order simulation — impossible VP distributions are rejected. The total VP at a table must equal the number of players at the table.

### GW, TP, and Standings Order

A player earns a **Game Win (GW)** when their VP is **at least 2.0** and **strictly the highest** at the table. VP ties at 2.0 or above do not award a GW to either player.

**Tournament Points (TP)** are position-based. Ties average their positions' values:

- **5-player table**: 60 / 48 / 36 / 24 / 12
- **4-player table**: 60 / 48 / 24 / 12 — the missing 36 position is the "table bye"

Players are ranked by **GW > VP > TP** (in that priority).

### Standings Adjustment (SA) Effect

A −1 VP penalty is applied to the adjusted round. If the player's raw VP in that round is less than 1.0, the shortfall (1.0 − raw VP) overflows as a deduction from their total standings VP. SA can change GW and TP results for that round.

### Finals Scoring Differences

In finals, the GW rules differ from preliminary rounds:

- **No 2.0 VP threshold** — the player with the highest VP always gets the GW
- **VP ties broken by seed order** — the higher-seeded player (better preliminary ranking) wins

## Running Rounds

### Starting a Round

Tap **Start Round** from the Overview tab. Archon seats players automatically using the VEKN seating algorithm, which optimizes 9 fairness rules (see [Seating Rules Reference](#seating-rules-reference) below).
`)}

<ExampleBox>
  <button class="px-4 py-2 text-sm font-medium btn-emerald rounded-lg">
    Start Round 1
  </button>
</ExampleBox>

{@html renderGuideSection(`
**Requirements:**

- At least **4 checked-in** players
- Not exceeding **max rounds**

> **NOTE - STAGGERED SEATING**
> For player counts that don't divide evenly into tables of 4–5 (e.g. 6, 7, or 11), Archon uses **staggered seating**: extra rounds are added automatically and players rotate sitting out. Players with the fewest games played are prioritized for the next round, so everyone gets a fair number of games.

When a round starts:

- Any Registered (not checked-in) players are **automatically dropped** (set to Finished).
- The seating quality is displayed: **Perfect**, **OK**, or **Invalid** (with an R1–R9 breakdown).

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
`)}

<ExampleBox>
  <div class="bg-ash-900/50 rounded-lg p-4 max-w-sm">
    <div class="flex items-center justify-between mb-2">
      <h3 class="text-sm font-medium text-bone-100">Table 1</h3>
      <span class="text-xs px-2 py-0.5 rounded badge-amber">Playing</span>
    </div>
    <div class="divide-y divide-ash-800">
      {#each ["Alice", "Bob", "Charlie", "Diana"] as name}
        <div class="py-1.5 flex items-center justify-between text-sm">
          <span class="text-ash-300">{name}</span>
          <div class="flex items-center gap-2">
            <span class="text-ash-400 text-xs">VP:</span>
            <select class="bg-ash-800 text-bone-100 text-xs rounded px-1.5 py-0.5 border border-ash-700" tabindex="-1">
              <option>0</option>
              <option>0.5</option>
              <option>1</option>
              <option>1.5</option>
              <option>2</option>
              <option>2.5</option>
              <option>3</option>
            </select>
            <span class="text-ash-500 text-xs">0GW 0TP</span>
          </div>
        </div>
      {/each}
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(`
- **Players** can enter VP in 0.5 increments from 0 to the table size, but cannot enter (table size − 0.5). Self-reporting is blocked if the table has an override.
- **Organizers** can force any VP value — the table state becomes "Invalid" if scores don't add up.
- VP scores are validated via oust-order simulation. Invalid distributions are rejected for non-organizers.
- On 4-player tables, TP values are 60/48/24/12. The missing 36 position is the "table bye."

### Override

Use **Override** when a table needs to be force-finished with a judge ruling — for example, a player leaves mid-game without any VP being awarded, or time expires with an unresolved situation. Override requires a mandatory judge comment explaining the ruling. This locks the table from further player edits.
`)}

<ExampleBox>
  <div class="space-y-3 max-w-sm">
    <div class="flex gap-2 items-center">
      <button class="px-3 py-1.5 text-sm btn-amber rounded flex items-center gap-1">
        <ShieldCheck class="w-3.5 h-3.5" />
        Override
      </button>
      <button class="px-3 py-1.5 text-sm text-ash-400 border border-ash-700 rounded">
        Remove override
      </button>
    </div>
    <textarea
      class="w-full px-3 py-2 text-sm bg-dusk-900 border border-ash-700 rounded-lg text-bone-100 placeholder-ash-500"
      placeholder="Judge comment (required for override)"
      rows="2"
      tabindex="-1"
    ></textarea>
    <button class="px-3 py-1.5 text-sm btn-amber rounded">
      Override &rarr; Finished
    </button>
  </div>
</ExampleBox>

{@html renderGuideSection(`
Use **Remove override** to reopen a table if the situation changes.

### Judge Calls (Online Only)

During online tournaments, players can tap **Call Judge** from their table view. This sends an alert to all organizers: an amber banner appears at the top of your screen with an audio chime, showing the table number and player name. The banner persists for 2 minutes or until you dismiss it. Multiple calls stack as separate banners.

This is invaluable for online events where you can't physically walk between tables. Players have a 30-second cooldown between calls to prevent spam.
`)}

<ExampleBox>
  <div class="space-y-3 max-w-sm">
    <button class="px-2 py-1 text-xs text-amber-400 border border-amber-800 rounded-lg flex items-center gap-1">
      <Gavel class="w-3 h-3" />
      Call Judge
    </button>
    <div class="banner-amber border rounded-lg p-3 flex items-center justify-between">
      <div class="flex items-center gap-2">
        <Gavel class="w-5 h-5 text-amber-400 shrink-0" />
        <div>
          <span class="text-sm font-medium text-bone-100">Judge Call!</span>
          <span class="text-sm text-ash-300 ml-1">Table 3 &mdash; Alice</span>
        </div>
      </div>
      <button class="text-ash-400 p-1">
        <X class="w-4 h-4" />
      </button>
    </div>
    <div class="banner-amber border rounded-lg p-3 flex items-center justify-between">
      <div class="flex items-center gap-2">
        <Gavel class="w-5 h-5 text-amber-400 shrink-0" />
        <div>
          <span class="text-sm font-medium text-bone-100">Judge Call!</span>
          <span class="text-sm text-ash-300 ml-1">Table 7 &mdash; Bob</span>
        </div>
      </div>
      <button class="text-ash-400 p-1">
        <X class="w-4 h-4" />
      </button>
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(`
### Finishing a Round

Tap **End Round** when all tables are scored. Every table must be Finished or have an Override. Standings update only when a round ends — during a round, standings reflect previous rounds only.
`)}

<ExampleBox>
  <button class="px-4 py-2 text-sm font-medium btn-amber rounded-lg">
    End Round
  </button>
</ExampleBox>

{@html renderGuideSection(`
### Between Rounds

After ending a round, the tournament returns to **Waiting** state. Decide whether to run a fresh check-in or keep everyone checked in (see [Check-in](#check-in) section above), then start the next round when ready.

### Drop Outs

If a player needs to leave, use **Drop Out** to mark them as Finished. Either the player or you can trigger this. For handling mid-round drops (unseating, table adjustments, overrides), see the [judge's guide](/help/judges-guide#51-event-organization-unexpected-drop).

### Cancelling a Round

**Cancel Round** removes the entire round, reverts all players who were playing back to Checked-in, and recalculates standings. Use this if something went fundamentally wrong with seating or if too many players are missing.
`)}

<ExampleBox>
  <button class="px-4 py-2 text-sm font-medium text-crimson-400 border border-crimson-800 rounded-lg">
    Cancel Round
  </button>
</ExampleBox>

{@html renderGuideSection(`
## Timer (Online Only)

The timer is available for online tournaments and syncs in real time.
`)}

<ExampleBox>
  <div class="space-y-3 max-w-xs">
    <div class="flex gap-4 justify-center">
      <div class="text-center">
        <span class="text-2xl font-mono text-emerald-400">1:23:45</span>
        <p class="text-xs text-ash-500 mt-1">Time remaining</p>
      </div>
      <div class="text-center">
        <span class="text-2xl font-mono text-amber-400">4:30</span>
        <p class="text-xs text-ash-500 mt-1">&lt; 5 minutes</p>
      </div>
      <div class="text-center">
        <span class="text-2xl font-mono text-red-400">0:00</span>
        <p class="text-xs text-ash-500 mt-1">Expired</p>
      </div>
    </div>
    <div class="flex gap-2 justify-center">
      <button class="px-3 py-1.5 text-sm btn-emerald rounded flex items-center gap-1">
        <Play class="w-3.5 h-3.5" />
        Start
      </button>
      <button class="px-3 py-1.5 text-sm btn-amber rounded flex items-center gap-1">
        <Pause class="w-3.5 h-3.5" />
        Pause
      </button>
      <button class="px-3 py-1.5 text-sm text-ash-300 border border-ash-600 rounded flex items-center gap-1">
        <RotateCcw class="w-3.5 h-3.5" />
        Reset
      </button>
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(`
- **Start** — begins the countdown
- **Pause** — stops the clock (resumes where it left off)
- **Reset** — clears the timer to its full duration and removes all per-table extensions

### Per-table Extensions

The extension policy (set in Config) determines what controls appear:
`)}

<ExampleBox>
  <div class="space-y-3 max-w-sm">
    <div class="flex gap-1">
      <button class="px-2 py-1 text-xs btn-emerald rounded">+1min</button>
      <button class="px-2 py-1 text-xs btn-emerald rounded">+2min</button>
      <button class="px-2 py-1 text-xs btn-emerald rounded">+3min</button>
      <button class="px-2 py-1 text-xs btn-emerald rounded">+5min</button>
      <span class="text-xs text-ash-400 self-center ml-1">0/10 min extra</span>
    </div>
    <div class="flex gap-2 items-center">
      <button class="px-3 py-1.5 text-sm btn-amber rounded flex items-center gap-1">
        <PauseCircle class="w-3.5 h-3.5" />
        Clock Stop
      </button>
      <button class="px-3 py-1.5 text-sm btn-emerald rounded flex items-center gap-1">
        <PlayCircle class="w-3.5 h-3.5" />
        Resume Clock
      </button>
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(`
- **Additions** — fixed-time buttons (+1, +2, +3, +5 minutes) per table, capped at 10 minutes total.
- **Clock Stop** — pause/resume per table. Elapsed pause time converts to extra time when resumed.

## Sanctions

Open a player's profile from the player list and tap **Add Sanction**. Select the level, category, and subcategory.

### Sanction Levels

- **Caution** — verbal warning, not formally tracked
- **Warning** — recorded, visible for 18 months
- **Standings Adjustment (SA)** — −1 VP penalty applied to a specific round
- **Disqualification (DQ)** — removed from the event, blocks future check-in until lifted

### Escalation

Archon shows **escalation hints** suggesting the appropriate level based on prior infractions. If you select a level below the suggestion, a **downgrade warning** appears — you can still proceed.

These escalation guidelines come from the [judge's guide](/help/judges-guide). The app does not enforce them — it is up to the head judge to decide. That said, judges should not deviate from the guidelines without head judge approval, and the head judge should be conservative about deviations. Archon does not track head judge versus other judges; that's for you to manage between co-organizers.

### Standings Adjustment Details

When issuing an SA, select the **round** it applies to. The −1 VP is subtracted from the player's adjusted VP for that round.

- If the player's raw VP in the SA round is less than 1.0, the shortfall (1.0 − raw VP) overflows as a deduction from their total standings VP.
- SA does not change stored scores — it affects GW and TP computation. A player who would have earned a GW may lose it after the adjustment.

### Lift and Delete

- **Lift** a DQ to allow the player to check in again.
- **Delete** a sanction to remove it entirely.

## Payment Tracking

Many tournaments have an entry fee. Track payments from the player list — each player shows as **Pending** or **Paid**. Tap the badge to toggle.
`)}

<ExampleBox>
  <div class="space-y-3 max-w-sm">
    <div class="flex gap-2 items-center">
      <span class="text-ash-300 text-sm">Alice</span>
      <span class="text-xs px-2 py-0.5 rounded badge-amber">Pending</span>
      <span class="text-ash-300 text-sm ml-3">Bob</span>
      <span class="text-xs px-2 py-0.5 rounded badge-emerald">Paid</span>
    </div>
    <button class="px-3 py-1.5 text-sm btn-emerald rounded">Mark All Paid</button>
  </div>
</ExampleBox>

{@html renderGuideSection(`
Use **Mark All Paid** to bulk-set all Pending players to Paid.

> **TIP**
> Payment is informational only — it does not block registration, check-in, or any other action. It's a convenience tracker for you to keep tabs on who has paid.

## Finals

### Resolving Ties

If players are tied in the top 5 (same GW, VP, and TP), a **toss** is needed to break the tie before finals can start.
`)}

<ExampleBox>
  <div class="flex gap-2 items-center">
    <button class="px-4 py-2 text-sm font-medium btn-emerald rounded-lg">
      Start Finals
    </button>
    <button class="px-3 py-1.5 text-sm text-ash-300 bg-ash-800 rounded-lg">
      <Dice3 class="w-4 h-4 inline mr-1" />
      Random Toss
    </button>
    <button class="px-3 py-1.5 text-sm text-ash-300 bg-ash-800 rounded-lg">
      Edit toss
    </button>
  </div>
</ExampleBox>

{@html renderGuideSection(`
- **Random Toss** — Archon assigns a deterministic random value
- **Edit toss** — manually assign toss values

You cannot start finals until all top-5 ties are resolved.

### Starting Finals

Requirements:

- Tournament in **Waiting** state (current round finished)
- At least **2 preliminary rounds** completed
- At least **5 eligible** (non-DQ'd) players with results
- No unresolved ties in the top 5

Tap **Start Finals**. The top 5 are selected by GW > VP > TP > toss. DQ'd players are skipped (so the 6th-place player may qualify if a top-5 player was DQ'd).

After selecting the finalists, conduct the **VEKN card-drawing procedure**: the top seed draws a random card to determine starting position, then picks their seat. Remaining players pick seats in reverse standing order. Input the resulting seating order into Archon.

### Altering Finals Seating

Use **Alter Finals Seating** (drag-and-drop) to change the seating order if needed. The same 5 players must remain — you can only reorder them.

### Scoring Finals

Same scoring UI as preliminary rounds, with two key differences:

- **No 2.0 VP threshold** — the player with the highest VP always gets the GW
- **VP ties broken by seed order** — the higher-seeded player (better preliminary ranking) wins

### Finishing the Tournament

Tap **Finish Finals** to determine the winner. This:

- Locks results and computes final ratings
- Sets deck visibility based on the decklists mode
- Triggers TWDA submission if the winner has a deck
- Pushes results to VEKN if the event was registered there
`)}

<ExampleBox>
  <button class="px-4 py-2 text-sm font-medium btn-amber rounded-lg">
    Finish Finals
  </button>
</ExampleBox>

{@html renderGuideSection(`
If the winner hasn't uploaded a decklist, you'll see a reminder banner:
`)}

<ExampleBox>
  <div class="banner-amber border rounded-lg p-3 text-sm max-w-sm">
    Winner's decklist is missing. Please remind Alice to upload their deck.
  </div>
</ExampleBox>

{@html renderGuideSection(`
You can **Finish a tournament** without running finals (e.g., league events). Players still receive base rating points — only the finalist bonus (winner/runner-up) requires finals.
`)}

<ExampleBox>
  <div class="pt-2 border-t border-ash-800 flex flex-wrap gap-2">
    <button class="px-3 py-1.5 text-sm text-ash-500">
      Finish Tournament
    </button>
    <button class="px-3 py-1.5 text-sm text-ash-500">
      Reopen Tournament
    </button>
  </div>
</ExampleBox>

{@html renderGuideSection(`
**Reopen Tournament** reverts to Waiting state, clearing finals results, winner/finalist flags, and deck publication flags. DQ'd players stay DQ'd. Use this to correct scoring errors or administrative mistakes — ratings recompute when you finish again.

## Sharing Results

After the tournament finishes, several export options are available:
`)}

<ExampleBox>
  <div class="flex gap-2 items-center">
    <button class="px-3 py-1.5 text-sm bg-ash-800 text-ash-200 rounded-lg flex items-center gap-2">
      <Share2 class="w-4 h-4" />
      Share Image
    </button>
    <button class="px-3 py-1.5 text-sm bg-ash-800 text-ash-200 rounded-lg flex items-center gap-2">
      <ClipboardCopy class="w-4 h-4" />
      Copy Text
    </button>
    <span class="px-3 py-1.5 text-sm bg-ash-800 text-ash-200 rounded-lg flex items-center gap-2">
      <Download class="w-4 h-4" />
      Download Report (JSON)
    </span>
  </div>
</ExampleBox>

{@html renderGuideSection(`
- **Share Image** — generates a social-media-friendly PNG card (1080×1350) with tournament details, winner, and top-5 standings. Great for posting to Discord or community forums.
- **Copy Text** — copies markdown-formatted results to clipboard (includes standings and winner's decklist)
- **Download Report (JSON)** — organizer-only. Downloads a structured JSON export of the tournament data.

## Raffle

Run prize draws from the **Raffle** section — common at medium and large events. Choose a **pool** to filter eligible players (All Players, Non-Finalists, Game Winners, No Game Win, No Victory Point) then:

- Set a **label** for the prize name
- Choose the number of winners to draw
- Toggle **Exclude previously drawn** to skip players who already won a prize
`)}

<ExampleBox>
  <div class="space-y-3 max-w-sm">
    <div class="flex gap-2 items-center">
      <select class="bg-ash-800 text-bone-100 text-sm rounded px-2 py-1.5 border border-ash-700" tabindex="-1">
        <option>All Players</option>
        <option>Non-Finalists</option>
        <option>Game Winners</option>
      </select>
      <input type="text" placeholder="Prize name" class="flex-1 px-2 py-1.5 text-sm bg-dusk-900 border border-ash-700 rounded text-bone-100 placeholder-ash-500" tabindex="-1" />
    </div>
    <div class="flex gap-2">
      <button class="px-3 py-1.5 text-sm btn-emerald rounded flex items-center gap-1">
        <Dices class="w-3.5 h-3.5" />
        Draw
      </button>
      <button class="px-3 py-1.5 text-sm text-ash-300 border border-ash-600 rounded flex items-center gap-1">
        <Undo2 class="w-3.5 h-3.5" />
        Undo
      </button>
      <button class="px-3 py-1.5 text-sm text-crimson-400 border border-crimson-800 rounded flex items-center gap-1">
        <Trash2 class="w-3.5 h-3.5" />
        Clear all
      </button>
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(`
## Offline Mode

Many VTES events take place in venues with unreliable internet — game store basements or buildings with no mobile signal. Archon supports full offline operation for these situations.

### Preparing

1. Open the tournament page **while still online** (on Wi-Fi or mobile data) to sync all data to your device
2. Tap **Go Offline** from the Overview tab
3. A device lock is acquired — only your device can edit the tournament
`)}

<ExampleBox>
  <button class="px-4 py-2 text-sm text-amber-300 border border-amber-700 rounded-lg flex items-center gap-2">
    <WifiOff class="w-4 h-4" />
    Go Offline
  </button>
</ExampleBox>

{@html renderGuideSection(`
You can prepare at home: load the tournament, go offline, then close the app. When you arrive at the venue without connectivity, reopen the app and navigate to the tournament — it works entirely from local data. The app caches everything needed (tournament data in IndexedDB, app assets via service worker).

### Running Offline

Run the tournament normally. All changes are stored locally. When your device has intermittent connectivity, Archon periodically saves a backup to the server (every 30 seconds), but the tournament stays in offline mode until you explicitly go back online. The periodic backup is a safety net, not live sync — other users see the backup state (read-only), not real-time updates.

### Going Back Online

Tap **Go Back Online** to sync your local changes. The server reconciles any conflicts (server is source of truth) and resumes normal real-time sync.
`)}

<ExampleBox>
  <div class="space-y-3 max-w-sm">
    <div class="bg-amber-900/30 border border-amber-800/50 rounded-lg p-3 flex items-center gap-2">
      <WifiOff class="w-5 h-5 text-amber-400 shrink-0" />
      <span class="text-amber-200 font-medium text-sm">OFFLINE MODE — Changes are stored locally</span>
    </div>
    <button class="px-4 py-2 text-sm font-medium btn-emerald rounded-lg flex items-center gap-2">
      <Wifi class="w-4 h-4" />
      Go Back Online
    </button>
  </div>
</ExampleBox>

{@html renderGuideSection(`
### Force Takeover

If the original device is unavailable (dead battery, forgotten at home, switching from laptop to phone), another organizer can tap **Force Takeover** to claim the device lock. This transfers editing rights but may lose any unsynced changes from the original device.

## Archon Import

Import tournament data from legacy Archon spreadsheets (.xlsx format). This is useful for organizers migrating from the old system.

1. Download the **blank template** from the import dialog
2. Fill in tournament info, player list, and round results
3. Upload the completed spreadsheet

Archon matches players by VEKN ID first, then by email. Unmatched players are created as new accounts. If the tournament already has rounds, you'll be asked to confirm before overwriting.

## League Integration

Leagues group a series of tournaments with aggregated standings — common for regional circuits, seasonal series, or national championships. Only NC (National Coordinator) or IC members can create leagues.

### Linking a Tournament to a League

In the **Config** tab, use the **League** dropdown to link a tournament to an active league. If the league has a format set, the tournament format must match.

### Standings Modes

Leagues support three standings calculation modes:

- **RTP (Rating Points)** — sums rating points across all tournaments in the league, including finals.
- **Score** — sums GW, VP, and TP from preliminary rounds only. Finals are excluded.
- **GP (Grand Prix)** — position-based points awarded per tournament: Winner = 25, 2nd–5th = 15, 6th = 10, decreasing to 11th+ = 3. Includes finals.

### Meta-leagues

Leagues can form a parent/child hierarchy (max 2 levels deep). A meta-league aggregates standings from all its child leagues.

### League Organizers

League organizers work the same way as tournament co-organizers — equal access, no hierarchy. You cannot remove the last organizer.

### League-wide Disqualification

A DQ in one league tournament blocks check-in to **all other tournaments** in the same league. League organizers can lift DQs.

### Dates and Status

Leagues have start and finish dates. No finish date means the league is ongoing.

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
`)}

<div class="not-prose my-6 space-y-1">
  {#each faqs as faq, i}
    <div class="border border-ash-700 rounded-lg overflow-hidden">
      <button
        class="w-full px-4 py-3 flex items-center gap-2 text-left text-sm font-medium text-bone-100 hover:bg-dusk-800/50 transition-colors"
        onclick={() => openFaq = openFaq === i ? null : i}
      >
        {#if openFaq === i}
          <ChevronDown class="w-4 h-4 text-ash-400 shrink-0" />
        {:else}
          <ChevronRight class="w-4 h-4 text-ash-400 shrink-0" />
        {/if}
        {faq.q}
      </button>
      {#if openFaq === i}
        <div class="px-4 pb-3 text-sm text-ash-300 doc-prose prose max-w-none">
          {@html renderGuideSection(faq.a)}
        </div>
      {/if}
    </div>
  {/each}
</div>
