<script lang="ts">
  import { renderGuideSection } from "$lib/markdown";
  import ExampleBox from "./ExampleBox.svelte";
  import { KeyRound, Mail, UserPlus, Link, Unlink, QrCode, Gavel, Calendar } from "lucide-svelte";
  import DiscordIcon from "$lib/components/DiscordIcon.svelte";
</script>

{@html renderGuideSection(`
Welcome to Archon, the official VEKN tournament management app. This guide covers everything you need as a player — from creating your account to understanding your ratings.

## Creating Your Account

Go to the **Login** page. You'll see two tabs at the top: **Login** and **Sign Up**.
`)}

<ExampleBox>
  <div class="flex bg-dusk-900 rounded-lg p-1 max-w-xs">
    <button class="flex-1 py-2 px-4 rounded-md text-sm font-medium text-ash-400 hover:text-ash-200">
      Login
    </button>
    <button class="flex-1 py-2 px-4 rounded-md text-sm font-medium bg-crimson-700 text-white">
      Sign Up
    </button>
  </div>
</ExampleBox>

{@html renderGuideSection(`
Select **Sign Up** and choose one of the following methods:

### Passkey (recommended)

The fastest and most secure option. Tap the passkey button and follow your device's prompt — this uses your fingerprint, face, or device PIN. No password to remember.
`)}

<ExampleBox>
  <button class="w-full max-w-xs py-3 bg-crimson-700 text-white rounded-lg font-medium flex items-center justify-center gap-2">
    <KeyRound class="w-5 h-5" />
    Create Account with Passkey
  </button>
</ExampleBox>

{@html renderGuideSection(`
### Discord

If you have a Discord account, tap the Discord button. You'll be redirected to Discord to authorise, then sent back to Archon with your account ready.
`)}

<ExampleBox>
  <button class="w-full max-w-xs py-3 bg-[#5865F2] text-white rounded-lg font-medium flex items-center justify-center gap-2">
    <DiscordIcon class="w-5 h-5" />
    Sign Up with Discord
  </button>
</ExampleBox>

{@html renderGuideSection(`
### Email

Enter your email address and tap the button below. You'll receive a magic link — click it to finish creating your account and set a password.
`)}

<ExampleBox>
  <div class="max-w-xs space-y-3">
    <input
      type="email"
      placeholder="Enter your email"
      class="w-full px-4 py-3 bg-dusk-900 border border-ash-700 rounded-lg text-bone-100 placeholder-ash-500"
      tabindex="-1"
    />
    <button class="w-full py-3 bg-ash-800 text-bone-100 rounded-lg font-medium flex items-center justify-center gap-2">
      <Mail class="w-5 h-5" />
      Continue with Email
    </button>
  </div>
</ExampleBox>

{@html renderGuideSection(`
## Logging In

If you already have an account, use the **Login** tab. Enter your email and password, or use one of the alternative sign-in methods:
`)}

<ExampleBox>
  <div class="max-w-xs space-y-4">
    <div class="space-y-3">
      <div>
        <label for="ex-email" class="block text-sm text-ash-400 mb-1">Email</label>
        <input id="ex-email" type="email" placeholder="you@example.com" class="w-full px-4 py-3 bg-dusk-900 border border-ash-700 rounded-lg text-bone-100 placeholder-ash-500" tabindex="-1" />
      </div>
      <div>
        <label for="ex-password" class="block text-sm text-ash-400 mb-1">Password</label>
        <input id="ex-password" type="password" placeholder="Enter your password" class="w-full px-4 py-3 bg-dusk-900 border border-ash-700 rounded-lg text-bone-100 placeholder-ash-500" tabindex="-1" />
      </div>
      <button class="w-full py-3 bg-crimson-700 text-white rounded-lg font-medium">
        Sign In
      </button>
    </div>
    <div class="text-center text-sm text-ash-400">Forgot password?</div>
    <div class="relative my-2">
      <div class="absolute inset-0 flex items-center"><div class="w-full border-t border-ash-700"></div></div>
      <div class="relative flex justify-center text-sm"><span class="px-2 bg-dusk-950 text-ash-500">or</span></div>
    </div>
    <button class="w-full py-3 bg-ash-800 text-bone-100 rounded-lg font-medium flex items-center justify-center gap-2">
      <KeyRound class="w-5 h-5" />
      Sign in with Passkey
    </button>
    <button class="w-full py-3 bg-[#5865F2] text-white rounded-lg font-medium flex items-center justify-center gap-2">
      <DiscordIcon class="w-5 h-5" />
      Continue with Discord
    </button>
  </div>
</ExampleBox>

{@html renderGuideSection(`
If you forgot your password, tap **Forgot password?** and enter your email. You'll receive a link to reset it.

## Claiming Your VEKN ID

After creating your account, go to your **Profile** page. To participate in official VEKN tournaments you need a VEKN ID linked to your account.

### New to VTES?

If you've never played in a VEKN-sanctioned tournament before, ask any existing VEKN member (or a tournament organiser) to **sponsor** you. They'll find your account in the Members page and click the Sponsor button:
`)}

<ExampleBox>
  <div class="bg-dusk-950 border border-ash-800 rounded-lg p-4 max-w-sm">
    <p class="text-sm text-ash-300 mb-3">No VEKN ID</p>
    <div class="flex flex-wrap gap-2">
      <button class="px-3 py-1.5 text-sm btn-emerald rounded flex items-center gap-1">
        <UserPlus class="w-3.5 h-3.5" />
        Sponsor
      </button>
      <button class="px-3 py-1.5 text-sm bg-ash-700 text-bone-100 rounded flex items-center gap-1">
        <Link class="w-3.5 h-3.5" />
        Link VEKN
      </button>
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(`
This will create a brand-new VEKN member number for you.

### Already have a VEKN ID?

If you already have a VEKN ID from a previous system, tap **Claim VEKN ID** on your profile and enter your number. This connects your tournament history to your new account.
`)}

<ExampleBox>
  <div class="flex justify-between items-center max-w-sm">
    <span class="text-ash-400">VEKN ID</span>
    <button class="px-3 py-1 text-sm bg-crimson-700 text-white rounded">
      Claim VEKN ID
    </button>
  </div>
</ExampleBox>

{@html renderGuideSection(`
A modal will open asking for your VEKN ID number:
`)}

<ExampleBox>
  <div class="bg-dusk-950 border border-ash-800 rounded-lg max-w-sm">
    <div class="p-4 border-b border-ash-800">
      <h3 class="text-lg font-medium text-bone-100">Claim VEKN ID</h3>
      <p class="mt-1 text-sm text-ash-400">Enter your VEKN ID to link it to your account. The ID must exist and not be claimed by another user.</p>
    </div>
    <div class="p-4 space-y-3">
      <div>
        <label for="ex-vekn-id" class="block text-sm font-medium text-ash-400 mb-1">VEKN ID</label>
        <input id="ex-vekn-id" type="text" placeholder="1234567" class="w-full px-3 py-2 border border-ash-600 rounded bg-dusk-950 text-ash-200" tabindex="-1" />
      </div>
      <div class="flex gap-2">
        <button class="flex-1 px-4 py-2 bg-crimson-700 text-white rounded font-medium">Claim</button>
        <button class="px-4 py-2 bg-ash-700 text-ash-200 rounded font-medium">Cancel</button>
      </div>
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(`
### Unlinking your VEKN ID

If you need to unlink your VEKN ID (e.g. you claimed the wrong number), tap the unlink icon next to your VEKN ID on your profile. This disassociates the ID from your account but preserves your tournament history.
`)}

<ExampleBox>
  <div class="flex justify-between items-center max-w-sm">
    <span class="text-ash-400">VEKN ID</span>
    <div class="flex items-center gap-2">
      <span class="text-bone-100 font-mono">1234567</span>
      <span class="p-1 text-ash-500">
        <Unlink class="w-4 h-4" />
      </span>
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(`
## Finding Tournaments

Browse the **Tournaments** page to see upcoming events. Use the filters to narrow by country, format, and date range.

Toggle between **Your Agenda** (tournaments you're registered for or organising) and **All Tournaments**:
`)}

<ExampleBox>
  <div class="space-y-3 max-w-sm">
    <div class="flex bg-dusk-900 rounded-lg p-1">
      <button class="flex-1 py-2 px-4 rounded-md text-sm font-medium bg-crimson-700 text-white">
        Your Agenda
      </button>
      <button class="flex-1 py-2 px-4 rounded-md text-sm font-medium text-ash-400 hover:text-ash-200">
        All Tournaments
      </button>
    </div>
    <div class="flex items-center gap-2">
      <Calendar class="h-4 w-4 text-ash-500 shrink-0" />
      <span class="text-xs text-ash-500">Subscribe:</span>
      <input type="text" readonly value="https://archon.vekn.net/api/calendar/..." class="flex-1 min-w-0 px-2 py-1.5 text-xs border border-ash-700 rounded bg-dusk-950 text-ash-400" tabindex="-1" />
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(`
**Calendar feed:** Tap the calendar icon below the toggle to subscribe to a personal iCal feed. Tournament dates will appear in your phone or desktop calendar app automatically.

## Registering

Once the organiser opens registration, a **Register** button appears on the tournament page. Tap it to sign up — your status changes to "Registered."
`)}

<ExampleBox>
  <div class="flex gap-3 items-center">
    <button class="px-4 py-2 text-sm font-medium btn-emerald rounded-lg">
      Register
    </button>
    <span class="text-xs text-ash-500">or, if you want out:</span>
    <button class="px-3 py-1.5 text-sm text-crimson-400 border border-crimson-800 rounded-lg">
      Unregister
    </button>
  </div>
</ExampleBox>

{@html renderGuideSection(`
To withdraw before check-in opens, tap **Unregister**. Once registration closes, only the organiser can remove you.

> **WARNING**
> Registering does **not** check you in. Before the first round starts, the organiser will open a check-in phase. You must check in separately or you will be marked as dropped for that round. See [Checking In](#checking-in) below.

## Uploading Your Decklist

On the tournament page, scroll down to the **Decks** section. You can upload a deck using one of three methods:
`)}

<ExampleBox>
  <div class="space-y-3 max-w-sm">
    <div class="flex gap-1">
      <button class="px-3 py-1.5 text-sm rounded-lg bg-crimson-600 text-white">
        Paste Deck
      </button>
      <button class="px-3 py-1.5 text-sm rounded-lg bg-ash-800 text-ash-300">
        From URL
      </button>
      <button class="px-3 py-1.5 text-sm rounded-lg bg-ash-800 text-ash-300">
        Scan QR
      </button>
    </div>
    <input
      type="url"
      placeholder="VDB, VTESDecks, or Amaranth URL"
      class="w-full px-3 py-2 text-sm bg-dusk-900 border border-ash-700 rounded-lg text-bone-100 placeholder-ash-500"
      tabindex="-1"
    />
    <button class="w-full py-2 text-sm font-medium btn-emerald rounded-lg">
      Upload Deck
    </button>
  </div>
</ExampleBox>

{@html renderGuideSection(`
- **Paste Deck** — paste the deck list text directly
- **From URL** — paste a link from VDB, VTESDecks, or Amaranth
- **Scan QR** — scan a VDB deck QR code with your camera

The deck is validated automatically: you'll see errors (illegal deck) or warnings (e.g. non-V5 cards in a V5 event) immediately.

### When can I change my deck?

- **Before the tournament starts** — you can replace or delete your deck freely.
- **During the tournament (single-deck)** — your deck is locked once any round has started. You cannot replace or delete it.
- **During the tournament (multideck)** — each round has its own deck slot. You can upload a new deck for an upcoming round, but slots for rounds already played are locked.
- **After the tournament** — if you never submitted a deck, you can still upload one (useful for the Tournament Winning Deck Archive). You cannot change an existing deck.

> **TIP**
> If the organiser has enabled "Decklist required," you'll see a warning badge until you upload a deck. Upload it before check-in to avoid a potential warning from the judges.

## Checking In

Before each round, the organiser opens a **check-in phase**. You check in by scanning the QR code displayed at the venue:
`)}

<ExampleBox>
  <button class="px-3 py-1.5 text-sm text-emerald-400 border border-emerald-800 rounded-lg flex items-center gap-1.5">
    <QrCode class="w-4 h-4" />
    Scan QR to Check In
  </button>
</ExampleBox>

{@html renderGuideSection(`
Point your camera at the organiser's QR code and you'll be checked in instantly. Alternatively the organiser may check you in from their player list.

**If you don't check in before a round starts, you do not play.** You are automatically marked as dropped from the tournament.

### Do I check in once, or every round?

It depends on how the organiser runs the tournament:

- **Single check-in** — some organisers check in everyone once at the start, then keep all players checked in between rounds. In this case you only need to scan the QR code before round 1. Your status will remain "Checked-in" automatically for later rounds.
- **Per-round check-in** — other organisers reopen check-in before each round (for example, to allow late drops or re-entries). In this case, you need to check in again each time.

### How do I know if I need to check in again?

Open the tournament page and look at your status:

- If you see the **Scan QR to Check In** button, the organiser has opened check-in and you need to act.
- If your status shows **Checked-in**, you're good — no action needed.
- If your status shows **Finished** or **Dropped** and a new round hasn't started yet, look for the check-in button — the organiser may have reopened check-in.

> **TIP**
> When in doubt, open the tournament page. If there's a check-in button visible, tap it. If there isn't, you're already checked in.

### What blocks check-in?

You cannot check in if you have an active **disqualification** or **suspension** sanction. The organiser cannot override this.

## During a Round

After a round starts, check the **Rounds** tab to see your **table assignment** and who you're playing with. Tables show player names in seating order (your predator is above you, your prey below).

### Reporting Results

Any player seated at a table can enter VP scores once the game finishes. Tap the VP dropdown next to each player and set their score. Once the scores are valid, the table is marked as finished.
`)}

<ExampleBox>
  <div class="bg-ash-900/50 rounded-lg p-4 max-w-sm">
    <div class="flex items-center justify-between mb-2">
      <h3 class="text-sm font-medium text-bone-100">Table 3</h3>
      <span class="text-xs px-2 py-0.5 rounded badge-amber">Playing</span>
    </div>
    <div class="divide-y divide-ash-800">
      {#each ["Alice", "Bob", "Charlie", "Diana"] as name, i}
        <div class="py-1.5 flex items-center justify-between text-sm">
          <span class="text-ash-300">{name}</span>
          <div class="flex items-center gap-2">
            <span class="text-ash-400 text-xs">VP:</span>
            <select
              class="bg-ash-800 text-bone-100 text-xs rounded px-1.5 py-0.5 border border-ash-700"
              tabindex="-1"
            >
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
If the organiser or judge has placed an **override** on your table, player scoring is locked — only the organiser can modify results.

### Calling a Judge

During an online tournament, tap the **Call Judge** button to alert organisers that your table needs assistance. This sends a real-time notification — it does not interrupt your game.
`)}

<ExampleBox>
  <button class="px-2 py-1 text-xs text-amber-400 border border-amber-800 rounded-lg flex items-center gap-1">
    <Gavel class="w-3 h-3" />
    Call Judge
  </button>
</ExampleBox>

{@html renderGuideSection(`
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

After a finished tournament, your **rating points (RtP)** are calculated and visible on the [Rankings](/rankings) page. Ratings are tracked separately by format (Constructed, Constructed Online, Limited, Limited Online). Your overall rating is based on your **best 8 tournaments** in the trailing 18 months. Per tournament: 5 base RtP + 4 per VP + 8 per GW, plus a finalist bonus scaled by event size and rank. See the [Hall of Fame](/halloffame) for players with 5+ tournament wins.

## Sanctions

If you receive a sanction during a tournament, it appears as a badge next to your name. Sanction levels:

- **Caution** — verbal warning, not formally tracked
- **Warning** — recorded on your profile, visible for 18 months
- **Standings Adjustment (SA)** — a −1 VP penalty applied to a specific round (see [How are scores computed?](#how-are-scores-computed))
- **Disqualification (DQ)** — removed from the event, blocks future check-in until lifted

Suspensions and bans are issued by the VEKN Ethics Committee, not tournament organisers.

## Offline Mode

When the organiser's device loses internet or they deliberately switch to offline mode, the tournament stops syncing with the server. You'll see a banner at the top of the tournament page:
`)}

<ExampleBox>
  <div class="bg-amber-900/30 border border-amber-800/50 rounded-lg p-3 flex items-center gap-2 max-w-sm">
    <svg class="w-5 h-5 text-amber-400 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="1" y1="1" x2="23" y2="23"/><path d="M16.72 11.06A10.94 10.94 0 0 1 19 12.55"/><path d="M5 12.55a10.94 10.94 0 0 1 5.17-2.39"/><path d="M10.71 5.05A16 16 0 0 1 22.56 9"/><path d="M1.42 9a15.91 15.91 0 0 1 4.7-2.88"/><path d="M8.53 16.11a6 6 0 0 1 6.95 0"/><line x1="12" y1="20" x2="12.01" y2="20"/></svg>
    <span class="text-amber-200 font-medium text-sm">OFFLINE MODE — Changes are stored locally</span>
  </div>
</ExampleBox>

{@html renderGuideSection(`
When a tournament is in offline mode, **nothing goes through the app from your point of view**. The organiser manages everything on their device — seatings, check-ins, VP scores, and standings are all handled locally and not pushed to your phone.

Do not rely on any data you see in the app during this time: table assignments, scores, and standings may be outdated or incomplete. Follow the organiser's verbal instructions and paper postings instead.

Once the organiser goes back online, all changes sync to the server and your app will update automatically.
`)}
