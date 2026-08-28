<script lang="ts">
  import { renderGuideSection } from "$lib/markdown";
  import * as m from "$lib/paraglide/messages.js";
  import { formatScore } from "$lib/utils";
  import { getRoleTone } from "$lib/roles";
  import ExampleBox from "./ExampleBox.svelte";
  import Button from "$lib/components/Button.svelte";
  import Badge from "$lib/components/Badge.svelte";
  import VpInput from "$lib/components/VpInput.svelte";
  import CommunityLinkPills from "$lib/components/CommunityLinkPills.svelte";
  import { KeyRound, Mail, UserPlus, Link, Unlink, QrCode, Gavel, Calendar, Copy, RefreshCw, Trophy, Lock, Monitor, Sun, Moon, Bell, Users, ChevronDown } from "@lucide/svelte";
  import DiscordIcon from "$lib/components/DiscordIcon.svelte";
  import GithubIcon from "$lib/components/GithubIcon.svelte";

  const linkClass = "text-link hover:text-link-soft underline";
  const consentHtml = m.login_consent_html({
    terms: `<a href="/legal/terms" class="${linkClass}">${m.legal_terms_title()}</a>`,
    privacy: `<a href="/legal/privacy" class="${linkClass}">${m.legal_privacy_title()}</a>`,
  });
</script>

{#snippet vpChips(selected: number)}
  <VpInput value={selected} options={[0, 0.5, 1, 1.5, 2, 3, 4]} onchange={() => {}} />
{/snippet}

<!-- Segmented controls: the app fills the selected half with the primary Button and leaves the
     others as bare text on the group's own surface. -->
{#snippet unselectedTab(label: string)}
  <span class="flex-1 py-2 px-4 text-center text-sm font-medium text-ink-muted">{label}</span>
{/snippet}

{@html renderGuideSection(m.pg_intro())}

<ExampleBox>
  <div class="flex bg-surface-muted rounded-lg p-1 max-w-xs">
    {@render unselectedTab(m.login_tab_login())}
    <Button variant="primary" size="lg" class="flex-1 rounded-md">{m.login_tab_signup()}</Button>
  </div>
</ExampleBox>

{@html renderGuideSection(m.pg_signup_passkey())}

<ExampleBox>
  <div class="max-w-xs space-y-3">
    <!-- Gates every signup method. -->
    <div class="flex items-start gap-2 text-xs text-ink leading-snug">
      <input type="checkbox" class="mt-0.5 shrink-0 w-5 h-5 accent-accent-strong-hover" tabindex="-1" />
      <span>{@html consentHtml}</span>
    </div>
    <Button variant="primary" size="lg" block>
      <KeyRound class="w-5 h-5" />
      {m.login_passkey_signup()}
    </Button>
  </div>
</ExampleBox>

{@html renderGuideSection(m.pg_signup_discord())}

<ExampleBox>
  <button class="w-full max-w-xs py-3 bg-[#5865F2] hover:bg-[#4752C4] text-white rounded-lg font-medium transition-colors flex items-center justify-center gap-2">
    <DiscordIcon class="w-5 h-5" />
    {m.login_discord_signup()}
  </button>
</ExampleBox>

{@html renderGuideSection(m.pg_signup_email())}

<ExampleBox>
  <div class="max-w-xs space-y-3">
    <input
      type="email"
      placeholder={m.login_placeholder_signup_email()}
      class="w-full px-4 py-3 bg-surface-muted border border-line-strong rounded-lg text-ink-strong placeholder-ink-faint"
      tabindex="-1"
    />
    <Button variant="secondary" size="lg" block>
      <Mail class="w-5 h-5" />
      {m.login_email_signup()}
    </Button>
  </div>
</ExampleBox>

{@html renderGuideSection(m.pg_login())}

<ExampleBox>
  <div class="max-w-xs space-y-4">
    <div class="space-y-3">
      <div>
        <label for="ex-email" class="block text-sm text-ink-muted mb-1">{m.common_email()}</label>
        <input id="ex-email" type="email" placeholder={m.login_placeholder_email()} class="w-full px-4 py-3 bg-surface-muted border border-line-strong rounded-lg text-ink-strong placeholder-ink-faint" tabindex="-1" />
      </div>
      <div>
        <label for="ex-password" class="block text-sm text-ink-muted mb-1">{m.common_password()}</label>
        <input id="ex-password" type="password" placeholder={m.login_placeholder_password()} class="w-full px-4 py-3 bg-surface-muted border border-line-strong rounded-lg text-ink-strong placeholder-ink-faint" tabindex="-1" />
      </div>
      <Button variant="primary" size="lg" block>{m.login_sign_in()}</Button>
    </div>
    <button class="w-full text-sm text-ink-muted hover:text-ink-bright">{m.login_forgot_password()}</button>
    <div class="relative my-2">
      <div class="absolute inset-0 flex items-center"><div class="w-full border-t border-line-strong"></div></div>
      <div class="relative flex justify-center text-sm"><span class="px-2 bg-surface-card text-ink-faint">{m.common_or()}</span></div>
    </div>
    <Button variant="secondary" size="lg" block>
      <KeyRound class="w-5 h-5" />
      {m.login_passkey_login()}
    </Button>
    <button class="w-full py-3 bg-[#5865F2] hover:bg-[#4752C4] text-white rounded-lg font-medium transition-colors flex items-center justify-center gap-2">
      <DiscordIcon class="w-5 h-5" />
      {m.login_discord_login()}
    </button>
  </div>
</ExampleBox>

{@html renderGuideSection(m.pg_login_reset())}

<ExampleBox>
  <div class="bg-surface-card border border-line rounded-lg p-4 max-w-sm">
    <p class="text-sm text-ink mb-3">{m.vekn_no_id()}</p>
    <div class="flex flex-wrap gap-2">
      <Button variant="primary" size="md">
        <UserPlus class="w-3.5 h-3.5" />
        {m.vekn_sponsor()}
      </Button>
      <Button variant="secondary" size="md">
        <Link class="w-3.5 h-3.5" />
        {m.vekn_link_btn()}
      </Button>
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(m.pg_vekn_new())}

<ExampleBox>
  <div class="flex justify-between items-center max-w-sm">
    <span class="text-ink-muted">{m.add_player_vekn_id_label()}</span>
    <Button variant="primary" size="md">{m.profile_claim_vekn_title()}</Button>
  </div>
</ExampleBox>

{@html renderGuideSection(m.pg_vekn_claim_modal())}

<ExampleBox>
  <div class="bg-surface-card border border-line rounded-lg shadow-xl max-w-sm">
    <div class="p-6 border-b border-line">
      <h3 class="text-xl font-medium text-ink-strong">{m.profile_claim_vekn_title()}</h3>
      <p class="mt-2 text-sm text-ink-muted">{m.profile_claim_vekn_description()}</p>
    </div>
    <div class="p-6 space-y-4">
      <div>
        <label for="ex-vekn-id" class="block text-sm font-medium text-ink-muted mb-1">{m.add_player_vekn_id_label()}</label>
        <input id="ex-vekn-id" type="text" placeholder="1234567" class="w-full px-3 py-2 border border-line-strong rounded bg-surface-card text-ink-bright" tabindex="-1" />
      </div>
      <div class="flex gap-2">
        <Button variant="primary" size="lg" class="flex-1">{m.profile_claim_btn()}</Button>
        <Button variant="secondary" size="lg">{m.common_cancel()}</Button>
      </div>
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(m.pg_vekn_unlink())}

<ExampleBox>
  <div class="flex justify-between items-center max-w-sm">
    <span class="text-ink-muted">{m.add_player_vekn_id_label()}</span>
    <div class="flex items-center gap-2">
      <span class="text-ink-strong font-mono">1234567</span>
      <button class="p-1 text-ink-faint hover:text-link transition-colors" title={m.profile_abandon_vekn_tooltip()}>
        <Unlink class="w-4 h-4" />
      </button>
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(m.pg_profile_settings())}

<ExampleBox>
  <div class="max-w-sm space-y-4">
    <div class="space-y-2">
      <span class="block text-sm text-ink-muted">{m.profile_theme_label()}</span>
      <div class="flex gap-2">
        <Button variant="secondary" size="md"><Monitor class="w-4 h-4" /> {m.theme_system()}</Button>
        <Button variant="secondary" size="md"><Sun class="w-4 h-4" /> {m.theme_light()}</Button>
        <Button variant="primary" size="md"><Moon class="w-4 h-4" /> {m.theme_dark()}</Button>
      </div>
    </div>
    <div class="space-y-2">
      <span class="block text-sm text-ink-muted">{m.profile_language_label()}</span>
      <div class="flex gap-2 flex-wrap">
        <Button variant="primary" size="md"><span>🇬🇧</span>EN</Button>
        <Button variant="secondary" size="md"><span>🇫🇷</span>FR</Button>
        <Button variant="secondary" size="md"><span>🇪🇸</span>ES</Button>
        <Button variant="secondary" size="md"><span>🇵🇹</span>PT</Button>
        <Button variant="secondary" size="md"><span>🇮🇹</span>IT</Button>
      </div>
    </div>
    <div class="space-y-2">
      <span class="block text-sm text-ink-muted">{m.notifications_label()}</span>
      <Button variant="primary" size="md">
        <Bell class="w-4 h-4" />
        {m.notifications_enable()}
      </Button>
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(m.pg_profile_accounts())}

<ExampleBox>
  <div class="max-w-md space-y-4">
    <h3 class="text-sm font-medium text-ink-muted uppercase tracking-wide">{m.profile_linked_accounts()}</h3>
    <div class="flex items-center justify-between gap-3">
      <div class="flex items-center gap-3 min-w-0">
        <Mail class="w-5 h-5 text-ink-muted shrink-0" />
        <div class="min-w-0">
          <p class="text-ink-strong">{m.profile_email_password()}</p>
          <p class="text-sm text-ink-muted">{m.profile_passkey_not_setup()}</p>
        </div>
      </div>
      <Button variant="secondary" size="lg" class="shrink-0">{m.profile_email_setup()}</Button>
    </div>
    <div class="flex items-center justify-between gap-3">
      <div class="flex items-center gap-3 min-w-0">
        <DiscordIcon class="w-5 h-5 text-[#5865F2] shrink-0" />
        <div class="min-w-0">
          <p class="text-ink-strong">Discord</p>
          <p class="text-sm text-ink-muted">janedoe</p>
        </div>
      </div>
      <span class="shrink-0 px-3 py-1 text-sm rounded badge-success">{m.profile_linked()}</span>
    </div>
    <div class="flex items-center justify-between gap-3">
      <div class="flex items-center gap-3 min-w-0">
        <GithubIcon class="w-5 h-5 text-ink-strong shrink-0" />
        <div class="min-w-0">
          <p class="text-ink-strong">GitHub</p>
          <p class="text-sm text-ink-muted">{m.profile_github_hint()}</p>
        </div>
      </div>
      <button class="shrink-0 px-4 py-2 bg-[#24292e] hover:bg-[#1b1f23] text-white rounded font-medium transition-colors">{m.profile_link()}</button>
    </div>
    <div class="flex items-center justify-between gap-3">
      <div class="flex items-center gap-3 min-w-0">
        <KeyRound class="w-5 h-5 text-ink-muted shrink-0" />
        <div class="min-w-0">
          <p class="text-ink-strong">Passkey</p>
          <p class="text-sm text-ink-muted">{m.profile_passkey_configured()}</p>
        </div>
      </div>
      <span class="shrink-0 px-3 py-1 text-sm rounded badge-success">{m.profile_passkey_active()}</span>
    </div>

    <div class="pt-4 border-t border-line space-y-4">
      <h3 class="text-sm font-medium text-ink-muted uppercase tracking-wide">{m.profile_data()}</h3>
      <div class="flex items-center justify-between gap-3">
        <div class="min-w-0">
          <p class="text-ink-strong">{m.profile_resync_title()}</p>
          <p class="text-sm text-ink-muted">{m.profile_resync_description()}</p>
        </div>
        <Button variant="primary" size="lg" class="shrink-0">
          <RefreshCw class="w-4 h-4" />
          {m.profile_resync_btn()}
        </Button>
      </div>
      <Button variant="secondary" size="lg" block>{m.profile_sign_out()}</Button>
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(m.pg_install())}

{@html renderGuideSection(m.pg_community())}

<ExampleBox>
  <div class="max-w-md">
    <div class="bg-surface-card rounded-lg shadow border border-line overflow-hidden">
      <button class="w-full flex items-center justify-between p-4 text-left">
        <div class="flex items-center gap-2">
          <span class="text-lg">🇫🇷</span>
          <span class="font-medium text-ink-strong">France</span>
          <span class="px-2 py-0.5 text-xs rounded bg-accent-soft/40 text-link">{m.community_your_country()}</span>
          <span class="text-xs text-ink-faint">(3)</span>
        </div>
        <ChevronDown class="w-5 h-5 text-ink-faint" />
      </button>
      <div class="border-t border-line divide-y divide-line/50">
        <div class="p-4 space-y-2">
          <h3 class="text-sm font-medium text-ink-strong">{m.community_card_pinned()}</h3>
          <CommunityLinkPills links={[{ type: "discord", url: "https://discord.gg/vtes-france", label: "VTES France", moderation: "national" }]} />
        </div>
        <div class="p-4 space-y-2">
          <h3 class="text-sm font-medium text-ink-strong">{m.community_card_officials()}</h3>
          <div class="flex items-center gap-2 flex-wrap">
            <span class="font-medium text-ink-strong">Jane Doe</span>
            <Badge tone={getRoleTone("NC")}>NC</Badge>
          </div>
          <div class="text-sm text-ink-muted">Paris</div>
          <div class="flex flex-wrap gap-3 text-xs text-ink-muted">
            <span class="text-link">jane.doe@example.com</span>
            <span class="text-link">janedoe</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(m.pg_leagues())}

<ExampleBox>
  <div class="max-w-md">
    <h3 class="text-xl font-medium text-ink-strong mb-1">{m.league_col_standings()}</h3>
    <p class="text-sm text-ink-muted mb-3">
      <span class="font-medium text-ink">{m.league_standings_rtp()}</span>
      — {m.league_mode_hint_rtp()}
    </p>
    <div class="bg-surface-card rounded-lg shadow overflow-hidden border border-line divide-y divide-line">
      <div class="flex items-center gap-3 px-4 py-3 ring-1 ring-inset ring-accent/40 bg-accent-soft/10">
        <span class="w-6 shrink-0 text-right text-sm font-medium text-ink-muted">1</span>
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-1.5 min-w-0">
            <span class="truncate text-sm text-ink-strong">Alice</span>
            <span class="shrink-0 px-1.5 py-0.5 rounded text-xs badge-slate">{m.league_standings_you()}</span>
          </div>
          <div class="mt-0.5 flex items-center gap-3 text-xs text-ink-faint">
            <span class="whitespace-nowrap">{formatScore(3, 11, 198)}</span>
            <span class="inline-flex items-center gap-1"><Trophy class="w-3 h-3" />4</span>
          </div>
        </div>
        <div class="shrink-0 text-right">
          <div class="text-sm font-semibold text-ink-strong leading-tight">75</div>
          <div class="text-[10px] uppercase tracking-wide text-ink-faint">{m.league_points_rtp()}</div>
        </div>
      </div>
      <div class="flex items-center gap-3 px-4 py-3">
        <span class="w-6 shrink-0 text-right text-sm font-medium text-ink-muted">2</span>
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-1.5 min-w-0">
            <span class="truncate text-sm text-ink-strong">Bob</span>
          </div>
          <div class="mt-0.5 flex items-center gap-3 text-xs text-ink-faint">
            <span class="whitespace-nowrap">{formatScore(2, 9, 174)}</span>
            <span class="inline-flex items-center gap-1"><Trophy class="w-3 h-3" />4</span>
          </div>
        </div>
        <div class="shrink-0 text-right">
          <div class="text-sm font-semibold text-ink-strong leading-tight">60</div>
          <div class="text-[10px] uppercase tracking-wide text-ink-faint">{m.league_points_rtp()}</div>
        </div>
      </div>
      <div class="flex items-center gap-3 px-4 py-3">
        <span class="w-6 shrink-0 text-right text-sm font-medium text-ink-muted">3</span>
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-1.5 min-w-0">
            <span class="truncate text-sm text-ink-strong">Charlie</span>
          </div>
          <div class="mt-0.5 flex items-center gap-3 text-xs text-ink-faint">
            <span class="whitespace-nowrap">{formatScore(1, 8, 156)}</span>
            <span class="inline-flex items-center gap-1"><Trophy class="w-3 h-3" />3</span>
          </div>
        </div>
        <div class="shrink-0 text-right">
          <div class="text-sm font-semibold text-ink-strong leading-tight">48</div>
          <div class="text-[10px] uppercase tracking-wide text-ink-faint">{m.league_points_rtp()}</div>
        </div>
      </div>
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(m.pg_finding_tournaments())}

<ExampleBox>
  <div class="space-y-3 max-w-sm">
    <div class="flex bg-surface-card rounded-lg border border-line p-1 w-fit">
      <Button variant="primary" size="lg" class="rounded-md">{m.tournaments_view_agenda()}</Button>
      {@render unselectedTab(m.tournaments_view_all())}
    </div>
    <!-- Two moments, in order: generate the feed once, then subscribe either way. -->
    <Button variant="primary" size="sm">{m.tournaments_calendar_generate()}</Button>
    <div class="border-t border-line pt-3 space-y-1.5">
      <div class="flex items-center gap-2 flex-wrap">
        <Button variant="ghost" size="sm" href="/api/calendar/tournaments.ics" tabindex="-1">
          <Calendar class="h-3 w-3" />
          {m.tournaments_calendar_webcal()}
        </Button>
        <Button variant="ghost" size="sm">
          <Copy class="h-3 w-3" />
          {m.tournaments_calendar_copy()}
        </Button>
      </div>
      <p class="text-xs text-ink-faint">{m.tournaments_calendar_scope_label({ scope: m.tournaments_calendar_scope_agenda() })}</p>
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(m.pg_calendar_feed())}

<ExampleBox>
  <Button variant="primary" size="lg">{m.tournament_register_btn()}</Button>
</ExampleBox>

{@html renderGuideSection(m.pg_registration_warning())}

<ExampleBox>
  <div class="space-y-3 max-w-sm">
    <div class="flex gap-2 flex-wrap">
      <Button variant="primary" size="md">{m.deck_upload_from_url()}</Button>
      <Button variant="secondary" size="md">{m.deck_upload_paste()}</Button>
      <Button variant="secondary" size="md">{m.deck_upload_scan_qr()}</Button>
    </div>
    <input
      type="text"
      placeholder={m.deck_upload_name_placeholder()}
      class="w-full px-3 py-2 text-sm bg-surface-muted border border-line-strong rounded-lg text-ink-bright placeholder-ink-faint"
      tabindex="-1"
    />
    <input
      type="url"
      placeholder={m.deck_upload_url_placeholder()}
      class="w-full px-3 py-2 text-sm bg-surface-muted border border-line-strong rounded-lg text-ink-bright placeholder-ink-faint"
      tabindex="-1"
    />
    <p class="text-xs text-ink-faint">{m.deck_upload_supported_sites()}</p>
    <div class="flex items-center gap-3 text-sm flex-wrap">
      <span class="text-ink-muted">{m.deck_upload_attribution()}:</span>
      <label class="flex items-center gap-1 text-ink-bright">
        <input type="radio" name="ex-attribution" checked class="accent-accent" tabindex="-1" />
        {m.deck_upload_attr_self()}
      </label>
      <label class="flex items-center gap-1 text-ink-bright">
        <input type="radio" name="ex-attribution" class="accent-accent" tabindex="-1" />
        {m.deck_upload_attr_anonymous()}
      </label>
      <label class="flex items-center gap-1 text-ink-bright">
        <input type="radio" name="ex-attribution" class="accent-accent" tabindex="-1" />
        {m.deck_upload_attr_other()}
      </label>
    </div>
    <Button variant="primary" size="lg">{m.deck_upload_submit()}</Button>
  </div>
</ExampleBox>

{@html renderGuideSection(m.pg_deck_methods())}

<ExampleBox>
  <Button variant="ghost" size="md">
    <QrCode class="w-4 h-4" />
    {m.checkin_qr_scan_btn()}
  </Button>
</ExampleBox>

{@html renderGuideSection(m.pg_checkin_details())}

<ExampleBox>
  <div class="max-w-sm border-t border-line pt-4">
    <div class="flex items-center justify-between mb-2">
      <h3 class="text-sm font-medium text-ink-strong">{m.tournament_your_table({ label: m.rounds_table_n({ n: "3" }) })}</h3>
      <span class="text-xs px-2 py-0.5 rounded badge-pending">{m.table_state_in_progress()}</span>
    </div>
    <div class="space-y-1.5">
      <div class="px-2.5 -mx-2.5 py-2 rounded-md">
        <div class="flex items-center justify-between gap-2 mb-1.5 text-sm">
          <span class="min-w-0 inline-flex items-center gap-1.5">
            <span class="text-ink-faint text-xs tabular-nums shrink-0">{m.tournament_seat_n({ n: "1" })}</span>
            <span class="text-ink truncate min-w-0">Alice</span>
            <span class="shrink-0 px-1.5 py-0.5 rounded text-xs badge-slate">{m.tournament_seat_predator()}</span>
          </span>
          <span class="text-ink-faint text-xs shrink-0">0GW 42TP</span>
        </div>
        {@render vpChips(1)}
      </div>
      <div class="px-2.5 -mx-2.5 py-2 rounded-md ring-1 ring-inset ring-accent/40 bg-accent-soft/10">
        <div class="flex items-center justify-between gap-2 mb-1.5 text-sm">
          <span class="min-w-0 inline-flex items-center gap-1.5">
            <span class="text-ink-faint text-xs tabular-nums shrink-0">{m.tournament_seat_n({ n: "2" })}</span>
            <span class="text-ink truncate min-w-0">Bob</span>
            <span class="shrink-0 px-1.5 py-0.5 rounded text-xs badge-slate">{m.tournament_seat_you()}</span>
          </span>
          <span class="text-ink-faint text-xs shrink-0">1GW 60TP</span>
        </div>
        {@render vpChips(2)}
      </div>
      <div class="px-2.5 -mx-2.5 py-2 rounded-md">
        <div class="flex items-center justify-between gap-2 mb-1.5 text-sm">
          <span class="min-w-0 inline-flex items-center gap-1.5">
            <span class="text-ink-faint text-xs tabular-nums shrink-0">{m.tournament_seat_n({ n: "3" })}</span>
            <span class="text-ink truncate min-w-0">Charlie</span>
            <span class="shrink-0 px-1.5 py-0.5 rounded text-xs badge-slate">{m.tournament_seat_prey()}</span>
          </span>
          <span class="text-ink-faint text-xs shrink-0">0GW 24TP</span>
        </div>
        {@render vpChips(0)}
      </div>
      <div class="px-2.5 -mx-2.5 py-2 rounded-md">
        <div class="flex items-center justify-between gap-2 mb-1.5 text-sm">
          <span class="min-w-0 inline-flex items-center gap-1.5">
            <span class="text-ink-faint text-xs tabular-nums shrink-0">{m.tournament_seat_n({ n: "4" })}</span>
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
  <Button variant="primary" size="lg" block class="max-w-sm min-h-[44px]">
    <Gavel class="w-5 h-5" />
    {m.judge_call_btn()}
  </Button>
</ExampleBox>

{@html renderGuideSection(m.pg_self_organize())}

<ExampleBox>
  <div class="max-w-sm border-t border-line pt-4 space-y-2">
    <div class="flex items-start gap-2">
      <Users class="w-4 h-4 mt-0.5 text-link shrink-0" />
      <div class="min-w-0">
        <h3 class="text-sm font-medium text-ink-strong">{m.self_organize_title()}</h3>
        <p class="text-xs text-ink-muted mt-0.5">{m.self_organize_tip()}</p>
      </div>
    </div>
    <Button variant="primary" size="lg" block class="min-h-[44px]">{m.self_organize_start_btn()}</Button>
  </div>
</ExampleBox>

{@html renderGuideSection(m.pg_standings())}

<!-- pg_standings ends by pointing at "a banner at the top of the tournament page" — this must stay
     immediately after it. This is the LOCKED-BY-ANOTHER-DEVICE banner; the loud OFFLINE MODE one only shows on the organizer's own device. -->
<ExampleBox>
  <div class="bg-surface-muted/50 border border-line-strong rounded-lg p-4 max-w-sm">
    <div class="flex items-center gap-2">
      <Lock class="w-5 h-5 text-ink-muted shrink-0" />
      <span class="text-ink text-sm">{m.offline_locked_banner()}</span>
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(m.pg_offline_details())}
