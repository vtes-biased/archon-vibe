<script lang="ts">
  import { renderGuideSection } from "$lib/markdown";
  import * as m from "$lib/paraglide/messages.js";
  import ExampleBox from "./ExampleBox.svelte";
  import { KeyRound, Mail, UserPlus, Link, Unlink, QrCode, Gavel, Calendar, Copy, RefreshCw, Trophy, Lock, Monitor, Sun, Moon, Bell, Users, ChevronDown } from "@lucide/svelte";
  import DiscordIcon from "$lib/components/DiscordIcon.svelte";
  import GithubIcon from "$lib/components/GithubIcon.svelte";
</script>

<!-- VpInput is chips, not a dropdown. -->
{#snippet vpChips(selected: number)}
  <div class="flex flex-wrap items-center gap-1">
    {#each [0, 1, 2, 3, 4] as opt}
      <button
        class="h-11 min-w-11 px-2 rounded-lg border text-sm font-semibold tabular-nums transition-colors
          {opt === selected
            ? 'bg-accent-strong text-white border-accent-strong-hover ring-2 ring-accent'
            : 'bg-surface-hover text-ink-strong border-line-strong'}"
      >{opt}</button>
    {/each}
    <button class="h-11 min-w-11 px-2 ml-1 rounded-lg border text-sm font-semibold tabular-nums transition-colors bg-surface-hover text-ink-strong border-line-strong">+½</button>
  </div>
{/snippet}

{@html renderGuideSection(m.pg_intro())}

<ExampleBox>
  <div class="flex bg-surface-muted rounded-lg p-1 max-w-xs">
    <button class="flex-1 py-2 px-4 rounded-md text-sm font-medium text-ink-muted hover:text-ink-bright">
      Login
    </button>
    <button class="flex-1 py-2 px-4 rounded-md text-sm font-medium bg-accent-strong text-white">
      Sign Up
    </button>
  </div>
</ExampleBox>

{@html renderGuideSection(m.pg_signup_passkey())}

<ExampleBox>
  <div class="max-w-xs space-y-3">
    <!-- Gates every signup method. -->
    <div class="flex items-start gap-2 text-xs text-ink leading-snug">
      <input type="checkbox" class="mt-0.5 shrink-0 w-5 h-5 accent-accent-strong-hover" tabindex="-1" />
      <span>
        I agree to the <span class="text-link underline">Terms of Service</span> and
        <span class="text-link underline">Privacy Policy</span>. I am 16 or older, or a parent or
        guardian consenting on behalf of a younger player.
      </span>
    </div>
    <button class="inline-flex w-full items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-medium bg-accent-strong hover:bg-accent-strong-hover text-white transition-colors">
      <KeyRound class="w-5 h-5" />
      Create Account with Passkey
    </button>
  </div>
</ExampleBox>

{@html renderGuideSection(m.pg_signup_discord())}

<ExampleBox>
  <button class="w-full max-w-xs py-3 bg-[#5865F2] hover:bg-[#4752C4] text-white rounded-lg font-medium transition-colors flex items-center justify-center gap-2">
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
      class="w-full px-4 py-3 bg-surface-muted border border-line-strong rounded-lg text-ink-strong placeholder-ink-faint"
      tabindex="-1"
    />
    <button class="inline-flex w-full items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-medium bg-surface-hover text-ink-bright transition-colors">
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
        <label for="ex-email" class="block text-sm text-ink-muted mb-1">Email</label>
        <input id="ex-email" type="email" placeholder="you@example.com" class="w-full px-4 py-3 bg-surface-muted border border-line-strong rounded-lg text-ink-strong placeholder-ink-faint" tabindex="-1" />
      </div>
      <div>
        <label for="ex-password" class="block text-sm text-ink-muted mb-1">Password</label>
        <input id="ex-password" type="password" placeholder="Enter your password" class="w-full px-4 py-3 bg-surface-muted border border-line-strong rounded-lg text-ink-strong placeholder-ink-faint" tabindex="-1" />
      </div>
      <button class="inline-flex w-full items-center justify-center rounded-lg px-4 py-2 text-sm font-medium bg-accent-strong hover:bg-accent-strong-hover text-white transition-colors">
        Sign In
      </button>
    </div>
    <button class="w-full text-sm text-ink-muted hover:text-ink-bright">Forgot password?</button>
    <div class="relative my-2">
      <div class="absolute inset-0 flex items-center"><div class="w-full border-t border-line-strong"></div></div>
      <div class="relative flex justify-center text-sm"><span class="px-2 bg-surface-card text-ink-faint">or</span></div>
    </div>
    <button class="inline-flex w-full items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-medium bg-surface-hover text-ink-bright transition-colors">
      <KeyRound class="w-5 h-5" />
      Sign in with Passkey
    </button>
    <button class="w-full py-3 bg-[#5865F2] hover:bg-[#4752C4] text-white rounded-lg font-medium transition-colors flex items-center justify-center gap-2">
      <DiscordIcon class="w-5 h-5" />
      Continue with Discord
    </button>
  </div>
</ExampleBox>

{@html renderGuideSection(m.pg_login_reset())}

<ExampleBox>
  <div class="bg-surface-card border border-line rounded-lg p-4 max-w-sm">
    <p class="text-sm text-ink mb-3">No VEKN ID</p>
    <div class="flex flex-wrap gap-2">
      <button class="inline-flex items-center justify-center gap-1.5 rounded-lg px-3 py-1.5 text-sm bg-accent-strong hover:bg-accent-strong-hover text-white transition-colors">
        <UserPlus class="w-3.5 h-3.5" />
        Sponsor
      </button>
      <button class="inline-flex items-center justify-center gap-1.5 rounded-lg px-3 py-1.5 text-sm bg-surface-hover text-ink-bright transition-colors">
        <Link class="w-3.5 h-3.5" />
        Link VEKN
      </button>
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(m.pg_vekn_new())}

<ExampleBox>
  <div class="flex justify-between items-center max-w-sm">
    <span class="text-ink-muted">VEKN ID</span>
    <button class="inline-flex items-center justify-center rounded-lg px-3 py-1.5 text-sm bg-accent-strong hover:bg-accent-strong-hover text-white transition-colors">
      Claim VEKN ID
    </button>
  </div>
</ExampleBox>

{@html renderGuideSection(m.pg_vekn_claim_modal())}

<ExampleBox>
  <div class="bg-surface-card border border-line rounded-lg shadow-xl max-w-sm">
    <div class="p-6 border-b border-line">
      <h3 class="text-xl font-medium text-ink-strong">Claim VEKN ID</h3>
      <p class="mt-2 text-sm text-ink-muted">Enter your VEKN ID to link it to your account. The ID must exist and not be claimed by another user.</p>
    </div>
    <div class="p-6 space-y-4">
      <div>
        <label for="ex-vekn-id" class="block text-sm font-medium text-ink-muted mb-1">VEKN ID</label>
        <input id="ex-vekn-id" type="text" placeholder="1234567" class="w-full px-3 py-2 border border-line-strong rounded bg-surface-card text-ink-bright" tabindex="-1" />
      </div>
      <div class="flex gap-2">
        <button class="flex-1 inline-flex items-center justify-center rounded-lg px-4 py-2 text-sm font-medium bg-accent-strong hover:bg-accent-strong-hover text-white transition-colors">Claim</button>
        <button class="inline-flex items-center justify-center rounded-lg px-4 py-2 text-sm font-medium bg-surface-hover text-ink-bright transition-colors">Cancel</button>
      </div>
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(m.pg_vekn_unlink())}

<ExampleBox>
  <div class="flex justify-between items-center max-w-sm">
    <span class="text-ink-muted">VEKN ID</span>
    <div class="flex items-center gap-2">
      <span class="text-ink-strong font-mono">1234567</span>
      <button class="p-1 text-ink-faint hover:text-link transition-colors" aria-label="Unlink VEKN ID">
        <Unlink class="w-4 h-4" />
      </button>
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(m.pg_profile_settings())}

<ExampleBox>
  <div class="max-w-sm space-y-4">
    <div class="space-y-2">
      <span class="block text-sm text-ink-muted">Theme</span>
      <div class="flex gap-2">
        <button class="flex items-center gap-2 px-3 py-2 rounded text-sm bg-surface-hover text-ink hover:bg-surface-active">
          <Monitor class="w-4 h-4" />
          Auto
        </button>
        <button class="flex items-center gap-2 px-3 py-2 rounded text-sm bg-surface-hover text-ink hover:bg-surface-active">
          <Sun class="w-4 h-4" />
          Light
        </button>
        <button class="flex items-center gap-2 px-3 py-2 rounded text-sm bg-accent-strong text-white">
          <Moon class="w-4 h-4" />
          Dark
        </button>
      </div>
    </div>
    <div class="space-y-2">
      <span class="block text-sm text-ink-muted">Language</span>
      <div class="flex gap-2 flex-wrap">
        <button class="flex items-center gap-1.5 px-3 py-2 rounded text-sm bg-accent-strong text-white"><span>🇬🇧</span>EN</button>
        <button class="flex items-center gap-1.5 px-3 py-2 rounded text-sm bg-surface-hover text-ink hover:bg-surface-active"><span>🇫🇷</span>FR</button>
        <button class="flex items-center gap-1.5 px-3 py-2 rounded text-sm bg-surface-hover text-ink hover:bg-surface-active"><span>🇪🇸</span>ES</button>
        <button class="flex items-center gap-1.5 px-3 py-2 rounded text-sm bg-surface-hover text-ink hover:bg-surface-active"><span>🇵🇹</span>PT</button>
        <button class="flex items-center gap-1.5 px-3 py-2 rounded text-sm bg-surface-hover text-ink hover:bg-surface-active"><span>🇮🇹</span>IT</button>
      </div>
    </div>
    <div class="space-y-2">
      <span class="block text-sm text-ink-muted">Push notifications</span>
      <button class="inline-flex items-center justify-center gap-1.5 rounded-lg px-3 py-1.5 text-sm bg-accent-strong hover:bg-accent-strong-hover text-white transition-colors">
        <Bell class="w-4 h-4" />
        Enable
      </button>
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(m.pg_profile_accounts())}

<ExampleBox>
  <div class="max-w-md space-y-4">
    <h3 class="text-sm font-medium text-ink-muted uppercase tracking-wide">Linked Accounts</h3>
    <div class="flex items-center justify-between gap-3">
      <div class="flex items-center gap-3 min-w-0">
        <Mail class="w-5 h-5 text-ink-muted shrink-0" />
        <div class="min-w-0">
          <p class="text-ink-strong">Email &amp; Password</p>
          <p class="text-sm text-ink-muted">Not set up</p>
        </div>
      </div>
      <button class="inline-flex shrink-0 items-center justify-center rounded-lg px-4 py-2 text-sm font-medium bg-surface-hover text-ink-bright transition-colors">Set up</button>
    </div>
    <div class="flex items-center justify-between gap-3">
      <div class="flex items-center gap-3 min-w-0">
        <DiscordIcon class="w-5 h-5 text-[#5865F2] shrink-0" />
        <div class="min-w-0">
          <p class="text-ink-strong">Discord</p>
          <p class="text-sm text-ink-muted">janedoe</p>
        </div>
      </div>
      <span class="shrink-0 px-3 py-1 text-sm rounded badge-success">Linked</span>
    </div>
    <div class="flex items-center justify-between gap-3">
      <div class="flex items-center gap-3 min-w-0">
        <GithubIcon class="w-5 h-5 text-ink-strong shrink-0" />
        <div class="min-w-0">
          <p class="text-ink-strong">GitHub</p>
          <p class="text-sm text-ink-muted">Link so we can mention you on your feedback issues</p>
        </div>
      </div>
      <button class="shrink-0 px-4 py-2 bg-[#24292e] hover:bg-[#1b1f23] text-white rounded font-medium transition-colors">Link</button>
    </div>
    <div class="flex items-center justify-between gap-3">
      <div class="flex items-center gap-3 min-w-0">
        <KeyRound class="w-5 h-5 text-ink-muted shrink-0" />
        <div class="min-w-0">
          <p class="text-ink-strong">Passkey</p>
          <p class="text-sm text-ink-muted">Face ID, Touch ID, or security key</p>
        </div>
      </div>
      <span class="shrink-0 px-3 py-1 text-sm rounded badge-success">Active</span>
    </div>

    <div class="pt-4 border-t border-line space-y-4">
      <h3 class="text-sm font-medium text-ink-muted uppercase tracking-wide">Data</h3>
      <div class="flex items-center justify-between gap-3">
        <div class="min-w-0">
          <p class="text-ink-strong">Resync local data</p>
          <p class="text-sm text-ink-muted">Clear local database and re-download all data from server</p>
        </div>
        <button class="inline-flex shrink-0 items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-medium bg-accent-strong hover:bg-accent-strong-hover text-white transition-colors">
          <RefreshCw class="w-4 h-4" />
          Resync
        </button>
      </div>
      <button class="inline-flex w-full items-center justify-center rounded-lg px-4 py-2 text-sm font-medium bg-surface-hover text-ink-bright transition-colors">Sign Out</button>
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(m.pg_install())}

{@html renderGuideSection(m.pg_community())}

<ExampleBox>
  <div class="max-w-md space-y-3">
    <div class="flex items-center gap-2">
      <Users class="w-5 h-5 text-accent" />
      <h3 class="text-lg font-medium text-ink-strong">Officials Directory</h3>
    </div>
    <div class="bg-surface-card rounded-lg shadow border border-line overflow-hidden">
      <button class="w-full flex items-center justify-between p-4 text-left">
        <div class="flex items-center gap-2">
          <span class="text-lg">🇫🇷</span>
          <span class="font-medium text-ink-strong">France</span>
          <span class="px-2 py-0.5 text-xs rounded bg-accent-soft/40 text-link">Your country</span>
          <span class="text-xs text-ink-faint">(2)</span>
        </div>
        <ChevronDown class="w-5 h-5 text-ink-faint" />
      </button>
      <div class="border-t border-line p-4">
        <div class="flex items-center gap-2 flex-wrap">
          <span class="font-medium text-ink-strong">Jane Doe</span>
          <span class="inline-flex items-center gap-1 rounded text-xs font-medium px-2 py-0.5 badge-crimson">NC</span>
        </div>
        <div class="text-sm text-ink-muted mt-0.5">Paris</div>
        <div class="flex flex-wrap gap-3 mt-2 text-xs text-ink-muted">
          <span class="text-link">jane.doe@example.com</span>
          <span class="text-link">janedoe</span>
        </div>
      </div>
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(m.pg_leagues())}

<ExampleBox>
  <div class="max-w-md">
    <h3 class="text-xl font-medium text-ink-strong mb-1">Standings</h3>
    <p class="text-sm text-ink-muted mb-3">
      <span class="font-medium text-ink">Rating Points</span>
      — VEKN rating points earned at each event, summed across ALL league events — unlike profile ratings, the season total has no best-8 or 18-month cap.
    </p>
    <div class="bg-surface-card rounded-lg shadow overflow-hidden border border-line divide-y divide-line">
      <div class="flex items-center gap-3 px-4 py-3 ring-1 ring-inset ring-accent/40 bg-accent-soft/10">
        <span class="w-6 shrink-0 text-right text-sm font-medium text-ink-muted">1</span>
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-1.5 min-w-0">
            <span class="truncate text-sm text-ink-strong">Alice</span>
            <span class="shrink-0 px-1.5 py-0.5 rounded text-xs badge-slate">You</span>
          </div>
          <div class="mt-0.5 flex items-center gap-3 text-xs text-ink-faint">
            <span class="whitespace-nowrap">3GW 11VP 198TP</span>
            <span class="inline-flex items-center gap-1"><Trophy class="w-3 h-3" />4</span>
          </div>
        </div>
        <div class="shrink-0 text-right">
          <div class="text-sm font-semibold text-ink-strong leading-tight">75</div>
          <div class="text-[10px] uppercase tracking-wide text-ink-faint">RtP</div>
        </div>
      </div>
      <div class="flex items-center gap-3 px-4 py-3">
        <span class="w-6 shrink-0 text-right text-sm font-medium text-ink-muted">2</span>
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-1.5 min-w-0">
            <span class="truncate text-sm text-ink-strong">Bob</span>
          </div>
          <div class="mt-0.5 flex items-center gap-3 text-xs text-ink-faint">
            <span class="whitespace-nowrap">2GW 9VP 174TP</span>
            <span class="inline-flex items-center gap-1"><Trophy class="w-3 h-3" />4</span>
          </div>
        </div>
        <div class="shrink-0 text-right">
          <div class="text-sm font-semibold text-ink-strong leading-tight">60</div>
          <div class="text-[10px] uppercase tracking-wide text-ink-faint">RtP</div>
        </div>
      </div>
      <div class="flex items-center gap-3 px-4 py-3">
        <span class="w-6 shrink-0 text-right text-sm font-medium text-ink-muted">3</span>
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-1.5 min-w-0">
            <span class="truncate text-sm text-ink-strong">Charlie</span>
          </div>
          <div class="mt-0.5 flex items-center gap-3 text-xs text-ink-faint">
            <span class="whitespace-nowrap">1GW 8VP 156TP</span>
            <span class="inline-flex items-center gap-1"><Trophy class="w-3 h-3" />3</span>
          </div>
        </div>
        <div class="shrink-0 text-right">
          <div class="text-sm font-semibold text-ink-strong leading-tight">48</div>
          <div class="text-[10px] uppercase tracking-wide text-ink-faint">RtP</div>
        </div>
      </div>
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(m.pg_finding_tournaments())}

<ExampleBox>
  <div class="space-y-3 max-w-sm">
    <div class="flex bg-surface-card rounded-lg border border-line p-1 w-fit">
      <button class="px-4 py-2 text-sm font-medium rounded-md bg-accent-strong text-white">
        Your Agenda
      </button>
      <button class="px-4 py-2 text-sm font-medium rounded-md text-ink-muted hover:text-ink-bright">
        All Tournaments
      </button>
    </div>
    <!-- Two moments, in order: generate the feed once, then subscribe either way. -->
    <button class="inline-flex items-center justify-center gap-1 rounded-lg px-2 py-1 text-xs bg-accent-strong hover:bg-accent-strong-hover text-white transition-colors">
      Generate link
    </button>
    <div class="border-t border-line pt-3 space-y-1.5">
      <div class="flex items-center gap-2 flex-wrap">
        <a href="/api/calendar/tournaments.ics" tabindex="-1" class="inline-flex items-center justify-center gap-1 px-2 py-1 text-xs rounded-lg border border-line-strong text-ink hover:bg-surface-hover/50 hover:text-ink-strong transition-colors">
          <Calendar class="h-3 w-3" />
          Open in calendar app
        </a>
        <button class="inline-flex items-center justify-center gap-1 rounded-lg px-2 py-1 text-xs border border-line-strong text-ink hover:bg-surface-hover/50 hover:text-ink-strong transition-colors">
          <Copy class="h-3 w-3" />
          Copy link
        </button>
      </div>
      <p class="text-xs text-ink-faint">Calendar for: your personal agenda</p>
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(m.pg_calendar_feed())}

<ExampleBox>
  <button class="inline-flex items-center justify-center rounded-lg px-4 py-2 text-sm font-medium bg-accent-strong hover:bg-accent-strong-hover text-white transition-colors">
    Register
  </button>
</ExampleBox>

{@html renderGuideSection(m.pg_registration_warning())}

<ExampleBox>
  <div class="space-y-3 max-w-sm">
    <div class="flex gap-2 flex-wrap">
      <button class="px-3 py-1.5 text-sm rounded-lg bg-accent-strong-hover text-white transition-colors">
        From URL
      </button>
      <button class="px-3 py-1.5 text-sm rounded-lg bg-surface-hover text-ink transition-colors">
        Paste Deck
      </button>
      <button class="px-3 py-1.5 text-sm rounded-lg bg-surface-hover text-ink transition-colors">
        Scan QR
      </button>
    </div>
    <input
      type="text"
      placeholder="Deck name (optional)"
      class="w-full px-3 py-2 text-sm bg-surface-muted border border-line-strong rounded-lg text-ink-bright placeholder-ink-faint"
      tabindex="-1"
    />
    <input
      type="url"
      placeholder="VDB, VTESDecks, or Amaranth URL"
      class="w-full px-3 py-2 text-sm bg-surface-muted border border-line-strong rounded-lg text-ink-bright placeholder-ink-faint"
      tabindex="-1"
    />
    <p class="text-xs text-ink-faint">Supported: vdb.im, vtesdecks.com, amaranth.vtes.co.nz</p>
    <div class="flex items-center gap-3 text-sm flex-wrap">
      <span class="text-ink-muted">Attribution:</span>
      <label class="flex items-center gap-1 text-ink-bright">
        <input type="radio" name="ex-attribution" checked class="accent-accent" tabindex="-1" />
        Your deck
      </label>
      <label class="flex items-center gap-1 text-ink-bright">
        <input type="radio" name="ex-attribution" class="accent-accent" tabindex="-1" />
        Anonymous
      </label>
      <label class="flex items-center gap-1 text-ink-bright">
        <input type="radio" name="ex-attribution" class="accent-accent" tabindex="-1" />
        Other
      </label>
    </div>
    <button class="inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-medium bg-accent-strong hover:bg-accent-strong-hover text-white transition-colors">
      Upload Deck
    </button>
  </div>
</ExampleBox>

{@html renderGuideSection(m.pg_deck_methods())}

<ExampleBox>
  <button class="inline-flex items-center justify-center gap-1.5 rounded-lg px-3 py-1.5 text-sm border border-line-strong text-ink hover:bg-surface-hover/50 hover:text-ink-strong transition-colors">
    <QrCode class="w-4 h-4" />
    Scan QR to Check In
  </button>
</ExampleBox>

{@html renderGuideSection(m.pg_checkin_details())}

<ExampleBox>
  <div class="max-w-sm border-t border-line pt-4">
    <div class="flex items-center justify-between mb-2">
      <h3 class="text-sm font-medium text-ink-strong">Your Table (Table 3)</h3>
      <span class="text-xs px-2 py-0.5 rounded badge-pending">In Progress</span>
    </div>
    <div class="space-y-1.5">
      <div class="px-2.5 -mx-2.5 py-2 rounded-md">
        <div class="flex items-center justify-between gap-2 mb-1.5 text-sm">
          <span class="min-w-0 inline-flex items-center gap-1.5">
            <span class="text-ink-faint text-xs tabular-nums shrink-0">Seat 1</span>
            <span class="text-ink truncate min-w-0">Alice</span>
            <span class="shrink-0 px-1.5 py-0.5 rounded text-xs badge-slate">Predator</span>
          </span>
          <span class="text-ink-faint text-xs shrink-0">0GW 42TP</span>
        </div>
        {@render vpChips(1)}
      </div>
      <div class="px-2.5 -mx-2.5 py-2 rounded-md ring-1 ring-inset ring-accent/40 bg-accent-soft/10">
        <div class="flex items-center justify-between gap-2 mb-1.5 text-sm">
          <span class="min-w-0 inline-flex items-center gap-1.5">
            <span class="text-ink-faint text-xs tabular-nums shrink-0">Seat 2</span>
            <span class="text-ink truncate min-w-0">Bob</span>
            <span class="shrink-0 px-1.5 py-0.5 rounded text-xs badge-slate">You</span>
          </span>
          <span class="text-ink-faint text-xs shrink-0">1GW 60TP</span>
        </div>
        {@render vpChips(2)}
      </div>
      <div class="px-2.5 -mx-2.5 py-2 rounded-md">
        <div class="flex items-center justify-between gap-2 mb-1.5 text-sm">
          <span class="min-w-0 inline-flex items-center gap-1.5">
            <span class="text-ink-faint text-xs tabular-nums shrink-0">Seat 3</span>
            <span class="text-ink truncate min-w-0">Charlie</span>
            <span class="shrink-0 px-1.5 py-0.5 rounded text-xs badge-slate">Prey</span>
          </span>
          <span class="text-ink-faint text-xs shrink-0">0GW 24TP</span>
        </div>
        {@render vpChips(0)}
      </div>
      <div class="px-2.5 -mx-2.5 py-2 rounded-md">
        <div class="flex items-center justify-between gap-2 mb-1.5 text-sm">
          <span class="min-w-0 inline-flex items-center gap-1.5">
            <span class="text-ink-faint text-xs tabular-nums shrink-0">Seat 4</span>
            <span class="text-ink truncate min-w-0">Diana</span>
          </span>
          <span class="text-ink-faint text-xs shrink-0">0GW 42TP</span>
        </div>
        {@render vpChips(1)}
      </div>
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(m.pg_override_judge())}

<ExampleBox>
  <button class="inline-flex w-full max-w-sm items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-medium min-h-[44px] bg-accent-strong hover:bg-accent-strong-hover text-white transition-colors">
    <Gavel class="w-5 h-5" />
    Call Judge
  </button>
</ExampleBox>

{@html renderGuideSection(m.pg_self_organize())}

<ExampleBox>
  <div class="max-w-sm border-t border-line pt-4 space-y-2">
    <div class="flex items-start gap-2">
      <Users class="w-4 h-4 mt-0.5 text-link shrink-0" />
      <div class="min-w-0">
        <h3 class="text-sm font-medium text-ink-strong">Self-organize a round</h3>
        <p class="text-xs text-ink-muted mt-0.5">Gather 4 or 5 registered players and start your own table — no organizer needed.</p>
      </div>
    </div>
    <button class="inline-flex w-full items-center justify-center rounded-lg px-4 py-2 text-sm font-medium min-h-[44px] bg-accent-strong hover:bg-accent-strong-hover text-white transition-colors">
      Self-organize a round
    </button>
  </div>
</ExampleBox>

{@html renderGuideSection(m.pg_standings())}

<!-- pg_standings ends by introducing Offline Mode and pointing at this banner
     ("you'll see a banner at the top of the tournament page:"), so nothing may
     be rendered between the two. This is the LOCKED-BY-ANOTHER-DEVICE banner —
     the loud "OFFLINE MODE" one is gated on this device holding the offline
     lock, so only the organizer's device ever shows it. -->
<ExampleBox>
  <div class="bg-surface-muted/50 border border-line-strong rounded-lg p-4 max-w-sm">
    <div class="flex items-center gap-2">
      <Lock class="w-5 h-5 text-ink-muted shrink-0" />
      <span class="text-ink text-sm">This tournament is offline on another device. Updates will resume when the organizer goes back online.</span>
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(m.pg_offline_details())}
