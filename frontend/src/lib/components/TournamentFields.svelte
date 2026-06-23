<script lang="ts">
  import type { TournamentFormat, TournamentRank, StandingsMode, DeckListsMode, League } from "$lib/types";
  import type { VenueInfo } from "$lib/db";
  import { getCountries, getCountryFlag } from "$lib/geonames";
  import { getAllLeagues } from "$lib/db";
  import { getAuthState } from "$lib/stores/auth.svelte";
  import VenueAutocomplete from "./VenueAutocomplete.svelte";
  import { Info } from "@lucide/svelte";
  import * as m from '$lib/paraglide/messages.js';

  export interface TournamentFieldValues {
    name: string;
    format: TournamentFormat;
    rank: TournamentRank;
    open_rounds: boolean;
    max_rounds: number;
    self_organized_rounds: boolean;
    online: boolean;
    country: string;
    venue: string;
    venue_url: string;
    address: string;
    map_url: string;
    start: string;
    finish: string;
    timezone: string;
    description: string;
    standings_mode: StandingsMode;
    decklists_mode: DeckListsMode;
    proxies: boolean;
    multideck: boolean;
    decklist_required: boolean;
    league_uid: string;
    round_time: number;
    finals_time: number;
  }

  let {
    values = $bindable(),
    onchange,
    onvenueselect,
    disabled = false,
    disabledFields = new Set<string>(),
    idPrefix = "",
  }: {
    values: TournamentFieldValues;
    onchange?: (field: string, value: any) => void;
    onvenueselect?: (fields: Record<string, string>) => void;
    disabled?: boolean;
    disabledFields?: Set<string>;
    idPrefix?: string;
  } = $props();

  const countries = getCountries();
  const timezones = Intl.supportedValuesOf("timeZone");
  const auth = $derived(getAuthState());
  const veknPush = import.meta.env.VITE_VEKN_PUSH === "true";

  let allActiveLeagues = $state<League[]>([]);
  $effect(() => {
    getAllLeagues().then(all => {
      allActiveLeagues = all
        .filter(l => !l.deleted_at && (!l.finish || new Date(l.finish) >= new Date()))
        .sort((a, b) => a.name.localeCompare(b.name));
    });
  });

  // Leagues where the current user is an organizer (selectable)
  const myLeagues = $derived(
    allActiveLeagues.filter(l => l.organizers_uids?.includes(auth.user?.uid ?? ""))
  );
  // Leagues where the user is NOT an organizer (shown disabled with explanation)
  const otherLeagues = $derived(
    allActiveLeagues.filter(l => !l.organizers_uids?.includes(auth.user?.uid ?? ""))
  );

  function id(name: string) {
    return idPrefix ? `${idPrefix}-${name}` : name;
  }

  function handleInput(field: string, value: any) {
    (values as any)[field] = value;
    onchange?.(field, value);
  }

  function handleOpenRoundsToggle(checked: boolean) {
    if (!checked) {
      // Back to a standard tournament: self-organize is open-rounds-only. The VEKN
      // build needs a valid 2–4 round count; house tournaments accept any cap, keep it.
      values.self_organized_rounds = false;
      if (veknPush && !(values.max_rounds >= 2 && values.max_rounds <= 4)) {
        values.max_rounds = 3;
      }
    }
    // Persist open_rounds last so ConfigTab can read the coerced sibling fields.
    handleInput("open_rounds", checked);
  }

  function handleVenueSelect(venue: VenueInfo) {
    values.venue = venue.venue;
    values.venue_url = venue.venue_url;
    values.address = venue.address;
    values.map_url = venue.map_url;
    onvenueselect?.({
      venue: venue.venue,
      venue_url: venue.venue_url,
      address: venue.address,
      map_url: venue.map_url,
    });
  }
</script>

<!-- Name -->
<div>
  <label class="block text-sm text-ink-muted mb-1" for={id("name")}>{m.tfield_name_label()} <span class="text-link text-xs">({m.common_required()})</span></label>
  <input
    id={id("name")}
    type="text"
    required
    value={values.name}
    {disabled}
    oninput={(e) => handleInput("name", (e.target as HTMLInputElement).value)}
    class="w-full px-3 py-2 text-sm bg-surface-card border rounded-lg text-ink-bright focus:outline-none {values.name.trim() ? 'border-line-strong focus:border-line-strong' : 'border-accent-strong/50 focus:border-accent'}"
    placeholder={m.tfield_name_placeholder()}
  />
</div>

<!-- Format & Rank -->
<div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
  <div>
    <label class="block text-sm text-ink-muted mb-1" for={id("format")}>{m.tfield_format()}</label>
    <select
      id={id("format")}
      value={values.format}
      {disabled}
      onchange={(e) => handleInput("format", (e.target as HTMLSelectElement).value)}
      class="w-full px-3 py-2 min-h-[44px] text-sm bg-surface-card border border-line-strong rounded-lg text-ink-bright"
    >
      <option value="Standard">Standard</option>
      <option value="V5">V5</option>
      <option value="Limited">Limited</option>
    </select>
  </div>
  <div>
    <label class="block text-sm text-ink-muted mb-1" for={id("rank")}>{m.tfield_rank()}</label>
    <select
      id={id("rank")}
      value={values.rank}
      {disabled}
      onchange={(e) => handleInput("rank", (e.target as HTMLSelectElement).value)}
      class="w-full px-3 py-2 min-h-[44px] text-sm bg-surface-card border border-line-strong rounded-lg text-ink-bright"
    >
      <option value="">{m.tfield_rank_basic()}</option>
      <option value="National Championship">National Championship</option>
      <option value="Continental Championship">Continental Championship</option>
    </select>
  </div>
</div>

<!-- League -->
{#if allActiveLeagues.length > 0}
  <div>
    <label class="block text-sm text-ink-muted mb-1" for={id("league")}>{m.tfield_league()}</label>
    <select
      id={id("league")}
      value={values.league_uid}
      {disabled}
      onchange={(e) => handleInput("league_uid", (e.target as HTMLSelectElement).value)}
      class="w-full px-3 py-2 min-h-[44px] text-sm bg-surface-card border border-line-strong rounded-lg text-ink-bright"
    >
      <option value="">{m.common_none()}</option>
      {#each myLeagues as league}
        <option value={league.uid}>{league.name}</option>
      {/each}
      {#each otherLeagues as league}
        <option value={league.uid} disabled>{league.name} — {m.tfield_league_not_organizer()}</option>
      {/each}
    </select>
  </div>
{/if}

<!-- Rounds: open-rounds opt-in + round count / per-player cap (always shown) -->
<fieldset class="border-0 p-0 m-0">
  <legend class="sr-only">{m.tfield_round_settings()}</legend>
  <label class="flex items-center gap-3 cursor-pointer">
    <input
      type="checkbox"
      checked={values.open_rounds}
      disabled={disabled || disabledFields.has("open_rounds")}
      onchange={(e) => handleOpenRoundsToggle((e.target as HTMLInputElement).checked)}
      class="w-5 h-5 rounded border-line-strong bg-surface-card text-accent focus:ring-accent"
    />
    <span class="text-sm text-ink-bright">{m.tfield_open_rounds()}</span>
  </label>
  {#if values.open_rounds}
    <div class="banner-warn flex items-start gap-2 rounded-lg p-2 mt-1 ml-8 text-xs">
      <Info class="w-4 h-4 shrink-0 mt-px" aria-hidden="true" />
      <span>{m.tfield_open_rounds_warning()}</span>
    </div>
  {:else}
    <p class="text-xs text-ink-faint mt-1 ml-8">{m.tfield_open_rounds_desc()}</p>
  {/if}

  <!-- Round count (standard) / per-player cap (open rounds) — always visible; the
       VEKN-push build constrains a standard tournament to 2–4 (the count it reports). -->
  <div class="mt-2 ml-8">
    <label class="block text-sm text-ink-muted mb-1" for={id("max-rounds")}>
      {values.open_rounds ? m.tfield_round_cap() : m.tfield_round_count()}
    </label>
    <select
      id={id("max-rounds")}
      value={String(values.max_rounds)}
      disabled={disabled || disabledFields.has("max_rounds")}
      onchange={(e) => {
        const mr = parseInt((e.target as HTMLSelectElement).value);
        handleInput("max_rounds", mr);
        // Self-organize needs a cap (>0); clear it if the cap is lifted.
        if (mr === 0 && values.self_organized_rounds) handleInput("self_organized_rounds", false);
      }}
      class="w-full px-3 py-2 min-h-[44px] text-sm bg-surface-card border border-line-strong rounded-lg text-ink-bright"
    >
      {#if !values.open_rounds && veknPush}
        <option value="2">2</option>
        <option value="3">3</option>
        <option value="4">4</option>
      {:else}
        <option value="0">{m.tfield_max_rounds_no_limit()}</option>
        <option value="1">1</option>
        <option value="2">2</option>
        <option value="3">3</option>
        <option value="4">4</option>
        <option value="5">5</option>
      {/if}
    </select>
    {#if disabledFields.has("max_rounds")}
      <p class="text-xs text-ink-faint mt-1">{m.tfield_rounds_locked_hint()}</p>
    {/if}
  </div>

  {#if values.open_rounds && values.online && values.max_rounds > 0}
    <div class="mt-3 ml-8">
      <label class="flex items-center gap-3 cursor-pointer">
        <input
          type="checkbox"
          checked={values.self_organized_rounds}
          {disabled}
          onchange={(e) => handleInput("self_organized_rounds", (e.target as HTMLInputElement).checked)}
          class="w-5 h-5 rounded border-line-strong bg-surface-card text-accent focus:ring-accent"
        />
        <span class="text-sm text-ink-bright">{m.tfield_self_organized_rounds()}</span>
      </label>
      <p class="text-xs text-ink-faint mt-1 ml-8">{m.tfield_self_organized_rounds_desc()}</p>
    </div>
  {/if}
</fieldset>

<!-- Dates & Timezone -->
<div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
  <div>
    <label class="block text-sm text-ink-muted mb-1" for={id("start")}>{m.tfield_start()} <span class="text-link text-xs">({m.common_required()})</span></label>
    <input
      id={id("start")}
      type="datetime-local"
      required
      value={values.start}
      {disabled}
      onchange={(e) => handleInput("start", (e.target as HTMLInputElement).value)}
      class="w-full px-3 py-2 text-sm bg-surface-card border rounded-lg text-ink-bright focus:outline-none {values.start ? 'border-line-strong focus:border-line-strong' : 'border-accent-strong/50 focus:border-accent'}"
    />
  </div>
  <div>
    <label class="block text-sm text-ink-muted mb-1" for={id("finish")}>{m.tfield_finish()}</label>
    <input
      id={id("finish")}
      type="datetime-local"
      value={values.finish}
      {disabled}
      onchange={(e) => handleInput("finish", (e.target as HTMLInputElement).value)}
      class="w-full px-3 py-2 text-sm bg-surface-card border border-line-strong rounded-lg text-ink-bright focus:border-line-strong focus:outline-none"
    />
  </div>
  <div>
    <label class="block text-sm text-ink-muted mb-1" for={id("timezone")}>{m.tfield_timezone()}</label>
    <select
      id={id("timezone")}
      value={values.timezone}
      {disabled}
      onchange={(e) => handleInput("timezone", (e.target as HTMLSelectElement).value)}
      class="w-full px-3 py-2 min-h-[44px] text-sm bg-surface-card border border-line-strong rounded-lg text-ink-bright"
    >
      {#each timezones as tz}
        <option value={tz}>{tz.replace(/_/g, " ")}</option>
      {/each}
    </select>
  </div>
</div>

<!-- Online toggle -->
<label class="flex items-center gap-3 cursor-pointer">
  <input
    type="checkbox"
    checked={values.online}
    {disabled}
    onchange={(e) => {
      const checked = (e.target as HTMLInputElement).checked;
      handleInput("online", checked);
      if (checked) {
        handleInput("proxies", false);
      }
      if (checked && !values.venue) {
        handleInput("venue", "VEKN Discord");
        handleInput("venue_url", "https://discord.com/invite/vampire-the-eternal-struggle-official-887471681277399091");
      }
    }}
    class="w-5 h-5 rounded border-line-strong bg-surface-card text-accent focus:ring-accent"
  />
  <span class="text-sm text-ink-bright">{m.tfield_online()}</span>
</label>

<!-- Location fields (hidden when online) -->
{#if !values.online}
  <div>
    <label class="block text-sm text-ink-muted mb-1" for={id("country")}>{m.common_country()} <span class="text-link text-xs">({m.common_required()})</span></label>
    <select
      id={id("country")}
      required
      value={values.country}
      {disabled}
      onchange={(e) => handleInput("country", (e.target as HTMLSelectElement).value)}
      class="w-full px-3 py-2 text-sm bg-surface-card border rounded-lg text-ink-bright {values.country ? 'border-line-strong' : 'border-accent-strong/50'}"
    >
      <option value="">{m.tfield_select_country()}</option>
      {#each Object.entries(countries) as [code, c]}
        <option value={code}>{c.name} {getCountryFlag(code)}</option>
      {/each}
    </select>
  </div>
{/if}

<!-- Venue (always shown) -->
<div>
  <label class="block text-sm text-ink-muted mb-1" for={id("venue")}>{m.tfield_venue()}</label>
  <VenueAutocomplete
    id={id("venue")}
    bind:value={values.venue}
    country={values.country}
    {disabled}
    onselect={handleVenueSelect}
    oninput={() => onchange?.("venue", values.venue)}
  />
</div>

<!-- Venue URL (always shown) -->
<div>
  <label class="block text-sm text-ink-muted mb-1" for={id("venue-url")}>{m.tfield_venue_url()}</label>
  <input
    id={id("venue-url")}
    type="url"
    value={values.venue_url}
    {disabled}
    oninput={(e) => handleInput("venue_url", (e.target as HTMLInputElement).value)}
    class="w-full px-3 py-2 text-sm bg-surface-card border border-line-strong rounded-lg text-ink-bright focus:border-line-strong focus:outline-none"
    placeholder="https://..."
  />
</div>

{#if !values.online}
  <!-- Address -->
  <div>
    <label class="block text-sm text-ink-muted mb-1" for={id("address")}>{m.tfield_address()}</label>
    <input
      id={id("address")}
      type="text"
      value={values.address}
      {disabled}
      oninput={(e) => handleInput("address", (e.target as HTMLInputElement).value)}
      class="w-full px-3 py-2 text-sm bg-surface-card border border-line-strong rounded-lg text-ink-bright focus:border-line-strong focus:outline-none"
      placeholder={m.tfield_address_placeholder()}
    />
  </div>

  <!-- Map URL -->
  <div>
    <label class="block text-sm text-ink-muted mb-1" for={id("map-url")}>{m.tfield_map_url()}</label>
    <input
      id={id("map-url")}
      type="url"
      value={values.map_url}
      {disabled}
      oninput={(e) => handleInput("map_url", (e.target as HTMLInputElement).value)}
      class="w-full px-3 py-2 text-sm bg-surface-card border border-line-strong rounded-lg text-ink-bright focus:border-line-strong focus:outline-none"
      placeholder="https://..."
    />
  </div>
{/if}

<!-- Standings & Decklists -->
<div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
  <div>
    <label class="block text-sm text-ink-muted mb-1" for={id("standings")}>{m.tfield_standings_visibility()}</label>
    <select
      id={id("standings")}
      value={values.standings_mode}
      {disabled}
      onchange={(e) => handleInput("standings_mode", (e.target as HTMLSelectElement).value)}
      class="w-full px-3 py-2 min-h-[44px] text-sm bg-surface-card border border-line-strong rounded-lg text-ink-bright"
    >
      <option value="Private">{m.tournament_standings_private()}</option>
      <option value="Cutoff">{m.tfield_standings_cutoff()}</option>
      <option value="Top 10">{m.tournament_standings_top10()}</option>
      <option value="Public">{m.tournament_standings_public()}</option>
    </select>
  </div>
  <div>
    <label class="block text-sm text-ink-muted mb-1" for={id("decklists")}>{m.tfield_decklists_visibility()}</label>
    <select
      id={id("decklists")}
      value={values.decklists_mode}
      {disabled}
      onchange={(e) => handleInput("decklists_mode", (e.target as HTMLSelectElement).value)}
      class="w-full px-3 py-2 min-h-[44px] text-sm bg-surface-card border border-line-strong rounded-lg text-ink-bright"
    >
      <option value="Winner">{m.tfield_decklists_winner()}</option>
      <option value="Finalists">{m.tfield_decklists_finalists()}</option>
      <option value="All">{m.tfield_decklists_all()}</option>
    </select>
  </div>
</div>

<!-- Boolean toggles -->
<div class="space-y-3">
  {#if !values.online}
    <label class="flex items-center gap-3 cursor-pointer">
      <input
        type="checkbox"
        checked={values.proxies}
        {disabled}
        onchange={(e) => handleInput("proxies", (e.target as HTMLInputElement).checked)}
        class="w-5 h-5 rounded border-line-strong bg-surface-card text-accent focus:ring-accent"
      />
      <span class="text-sm text-ink-bright">{m.tfield_allow_proxies()}</span>
    </label>
  {/if}
  <label class="flex items-center gap-3 cursor-pointer">
    <input
      type="checkbox"
      checked={values.multideck}
      {disabled}
      onchange={(e) => handleInput("multideck", (e.target as HTMLInputElement).checked)}
      class="w-5 h-5 rounded border-line-strong bg-surface-card text-accent focus:ring-accent"
    />
    <span class="text-sm text-ink-bright">{m.tfield_multideck()}</span>
  </label>
  <label class="flex items-center gap-3 cursor-pointer">
    <input
      type="checkbox"
      checked={values.decklist_required}
      {disabled}
      onchange={(e) => handleInput("decklist_required", (e.target as HTMLInputElement).checked)}
      class="w-5 h-5 rounded border-line-strong bg-surface-card text-accent focus:ring-accent"
    />
    <span class="text-sm text-ink-bright">{m.tfield_decklist_required()}</span>
  </label>
</div>

<!-- Timer Configuration -->
<div class="border-t border-line pt-4">
  <h3 class="text-sm font-medium text-ink-strong mb-3">{m.timer_config_heading()}</h3>
  <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
    <div>
      <label class="block text-sm text-ink-muted mb-1" for={id("round-time")}>{m.timer_round_time()}</label>
      <select
        id={id("round-time")}
        value={String(values.round_time ?? 0)}
        {disabled}
        onchange={(e) => handleInput("round_time", parseInt((e.target as HTMLSelectElement).value))}
        class="w-full px-3 py-2 min-h-[44px] text-sm bg-surface-card border border-line-strong rounded-lg text-ink-bright"
      >
        <option value="0">{m.timer_no_timer()}</option>
        <option value="7200">2h</option>
        <option value="8100">2h15</option>
        <option value="9000">2h30</option>
        <option value="9900">2h45</option>
        <option value="10800">3h</option>
      </select>
    </div>
    <div>
      <label class="block text-sm text-ink-muted mb-1" for={id("finals-time")}>{m.timer_finals_time()}</label>
      <select
        id={id("finals-time")}
        value={String(values.finals_time ?? 0)}
        {disabled}
        onchange={(e) => handleInput("finals_time", parseInt((e.target as HTMLSelectElement).value))}
        class="w-full px-3 py-2 min-h-[44px] text-sm bg-surface-card border border-line-strong rounded-lg text-ink-bright"
      >
        <option value="0">{m.timer_same_as_round()}</option>
        <option value="7200">2h</option>
        <option value="8100">2h15</option>
        <option value="9000">2h30</option>
        <option value="9900">2h45</option>
        <option value="10800">3h</option>
      </select>
    </div>
  </div>
</div>

<!-- Description -->
<div>
  <label class="block text-sm text-ink-muted mb-1" for={id("description")}>{m.common_description()}</label>
  <span class="text-xs text-ink-faint mb-1 block">
    {@html m.tfield_markdown_support({ link: '<a href="https://www.markdownguide.org/basic-syntax/" target="_blank" rel="noopener noreferrer" class="underline text-ink-muted hover:text-ink-bright">Markdown</a>' })}
  </span>
  <textarea
    id={id("description")}
    value={values.description}
    {disabled}
    oninput={(e) => handleInput("description", (e.target as HTMLTextAreaElement).value)}
    rows="10"
    class="w-full px-3 py-2 text-sm bg-surface-card border border-line-strong rounded-lg text-ink-bright focus:border-line-strong focus:outline-none resize-y"
    placeholder={m.tfield_description_placeholder()}
  ></textarea>
</div>
