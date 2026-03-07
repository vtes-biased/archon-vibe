<script lang="ts">
  import { renderGuideSection } from "$lib/markdown";
  import * as m from "$lib/paraglide/messages.js";
  import ExampleBox from "./ExampleBox.svelte";
  import { KeyRound, Mail, UserPlus, Link, Unlink, QrCode, Gavel, Calendar } from "lucide-svelte";
  import DiscordIcon from "$lib/components/DiscordIcon.svelte";
</script>

{@html renderGuideSection(m.pg_intro())}

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

{@html renderGuideSection(m.pg_signup_passkey())}

<ExampleBox>
  <button class="w-full max-w-xs py-3 bg-crimson-700 text-white rounded-lg font-medium flex items-center justify-center gap-2">
    <KeyRound class="w-5 h-5" />
    Create Account with Passkey
  </button>
</ExampleBox>

{@html renderGuideSection(m.pg_signup_discord())}

<ExampleBox>
  <button class="w-full max-w-xs py-3 bg-[#5865F2] text-white rounded-lg font-medium flex items-center justify-center gap-2">
    <DiscordIcon class="w-5 h-5" />
    Sign Up with Discord
  </button>
</ExampleBox>

{@html renderGuideSection(m.pg_signup_email())}

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

{@html renderGuideSection(m.pg_login())}

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

{@html renderGuideSection(m.pg_login_reset())}

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

{@html renderGuideSection(m.pg_vekn_new())}

<ExampleBox>
  <div class="flex justify-between items-center max-w-sm">
    <span class="text-ash-400">VEKN ID</span>
    <button class="px-3 py-1 text-sm bg-crimson-700 text-white rounded">
      Claim VEKN ID
    </button>
  </div>
</ExampleBox>

{@html renderGuideSection(m.pg_vekn_claim_modal())}

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

{@html renderGuideSection(m.pg_vekn_unlink())}

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

{@html renderGuideSection(m.pg_finding_tournaments())}

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

{@html renderGuideSection(m.pg_calendar_feed())}

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

{@html renderGuideSection(m.pg_registration_warning())}

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

{@html renderGuideSection(m.pg_deck_methods())}

<ExampleBox>
  <button class="px-3 py-1.5 text-sm text-emerald-400 border border-emerald-800 rounded-lg flex items-center gap-1.5">
    <QrCode class="w-4 h-4" />
    Scan QR to Check In
  </button>
</ExampleBox>

{@html renderGuideSection(m.pg_checkin_details())}

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

{@html renderGuideSection(m.pg_override_judge())}

<ExampleBox>
  <button class="px-2 py-1 text-xs text-amber-400 border border-amber-800 rounded-lg flex items-center gap-1">
    <Gavel class="w-3 h-3" />
    Call Judge
  </button>
</ExampleBox>

{@html renderGuideSection(m.pg_standings())}

<ExampleBox>
  <div class="bg-amber-900/30 border border-amber-800/50 rounded-lg p-3 flex items-center gap-2 max-w-sm">
    <svg class="w-5 h-5 text-amber-400 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="1" y1="1" x2="23" y2="23"/><path d="M16.72 11.06A10.94 10.94 0 0 1 19 12.55"/><path d="M5 12.55a10.94 10.94 0 0 1 5.17-2.39"/><path d="M10.71 5.05A16 16 0 0 1 22.56 9"/><path d="M1.42 9a15.91 15.91 0 0 1 4.7-2.88"/><path d="M8.53 16.11a6 6 0 0 1 6.95 0"/><line x1="12" y1="20" x2="12.01" y2="20"/></svg>
    <span class="text-amber-200 font-medium text-sm">OFFLINE MODE — Changes are stored locally</span>
  </div>
</ExampleBox>

{@html renderGuideSection(m.pg_offline_details())}
