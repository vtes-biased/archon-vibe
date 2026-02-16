<script lang="ts">
  import type { TournamentFormat, TournamentRank, StandingsMode, DeckListsMode, League } from "$lib/types";
  import { getCountries, getCountryFlag } from "$lib/geonames";
  import { getAllLeagues } from "$lib/db";
  import { getAuthState } from "$lib/stores/auth.svelte";
  import * as m from '$lib/paraglide/messages.js';

  export interface TournamentFieldValues {
    name: string;
    format: TournamentFormat;
    rank: TournamentRank;
    open_rounds: boolean;
    max_rounds: number;
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
  }

  let {
    values = $bindable(),
    onchange,
    disabled = false,
    disabledFields = new Set<string>(),
    idPrefix = "",
  }: {
    values: TournamentFieldValues;
    onchange?: (field: string, value: any) => void;
    disabled?: boolean;
    disabledFields?: Set<string>;
    idPrefix?: string;
  } = $props();

  const countries = getCountries();
  const timezones = Intl.supportedValuesOf("timeZone");
  const auth = $derived(getAuthState());

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
</script>

<!-- Name -->
<div>
  <label class="block text-sm text-ash-400 mb-1" for={id("name")}>{m.tfield_name_label()}</label>
  <input
    id={id("name")}
    type="text"
    value={values.name}
    {disabled}
    oninput={(e) => handleInput("name", (e.target as HTMLInputElement).value)}
    class="w-full px-3 py-2 text-sm bg-dusk-950 border border-ash-700 rounded-lg text-ash-200 focus:border-ash-500 focus:outline-none"
    placeholder={m.tfield_name_placeholder()}
  />
</div>

<!-- Format & Rank -->
<div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
  <div>
    <label class="block text-sm text-ash-400 mb-1" for={id("format")}>{m.tfield_format()}</label>
    <select
      id={id("format")}
      value={values.format}
      {disabled}
      onchange={(e) => handleInput("format", (e.target as HTMLSelectElement).value)}
      class="w-full px-3 py-2 text-sm bg-dusk-950 border border-ash-700 rounded-lg text-ash-200"
    >
      <option value="Standard">Standard</option>
      <option value="V5">V5</option>
      <option value="Limited">Limited</option>
    </select>
  </div>
  <div>
    <label class="block text-sm text-ash-400 mb-1" for={id("rank")}>{m.tfield_rank()}</label>
    <select
      id={id("rank")}
      value={values.rank}
      {disabled}
      onchange={(e) => handleInput("rank", (e.target as HTMLSelectElement).value)}
      class="w-full px-3 py-2 text-sm bg-dusk-950 border border-ash-700 rounded-lg text-ash-200"
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
    <label class="block text-sm text-ash-400 mb-1" for={id("league")}>{m.tfield_league()}</label>
    <select
      id={id("league")}
      value={values.league_uid}
      {disabled}
      onchange={(e) => handleInput("league_uid", (e.target as HTMLSelectElement).value)}
      class="w-full px-3 py-2 text-sm bg-dusk-950 border border-ash-700 rounded-lg text-ash-200"
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

<!-- Open Rounds -->
<div>
  <label class="flex items-center gap-3 cursor-pointer">
    <input
      type="checkbox"
      checked={values.open_rounds}
      disabled={disabled || disabledFields.has("open_rounds")}
      onchange={(e) => {
        const checked = (e.target as HTMLInputElement).checked;
        handleInput("open_rounds", checked);
        if (!checked) {
          handleInput("max_rounds", 0);
        }
      }}
      class="w-5 h-5 rounded border-ash-700 bg-dusk-950 text-emerald-600 focus:ring-emerald-500"
    />
    <span class="text-sm text-ash-200">{m.tfield_open_rounds()}</span>
  </label>
  <p class="text-xs text-ash-500 mt-1 ml-8">{m.tfield_open_rounds_desc()}</p>
  {#if values.open_rounds}
    <div class="mt-2 ml-8">
      <label class="block text-sm text-ash-400 mb-1" for={id("max-rounds")}>{m.tfield_max_rounds()}</label>
      <select
        id={id("max-rounds")}
        value={String(values.max_rounds)}
        disabled={disabled || disabledFields.has("max_rounds")}
        onchange={(e) => handleInput("max_rounds", parseInt((e.target as HTMLSelectElement).value))}
        class="w-full px-3 py-2 text-sm bg-dusk-950 border border-ash-700 rounded-lg text-ash-200"
      >
        <option value="0">{m.tfield_max_rounds_no_limit()}</option>
        <option value="1">1</option>
        <option value="2">2</option>
        <option value="3">3</option>
        <option value="4">4</option>
        <option value="5">5</option>
      </select>
    </div>
  {/if}
</div>

<!-- Dates & Timezone -->
<div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
  <div>
    <label class="block text-sm text-ash-400 mb-1" for={id("start")}>{m.tfield_start()}</label>
    <input
      id={id("start")}
      type="datetime-local"
      value={values.start}
      {disabled}
      onchange={(e) => handleInput("start", (e.target as HTMLInputElement).value)}
      class="w-full px-3 py-2 text-sm bg-dusk-950 border border-ash-700 rounded-lg text-ash-200 focus:border-ash-500 focus:outline-none"
    />
  </div>
  <div>
    <label class="block text-sm text-ash-400 mb-1" for={id("finish")}>{m.tfield_finish()}</label>
    <input
      id={id("finish")}
      type="datetime-local"
      value={values.finish}
      {disabled}
      onchange={(e) => handleInput("finish", (e.target as HTMLInputElement).value)}
      class="w-full px-3 py-2 text-sm bg-dusk-950 border border-ash-700 rounded-lg text-ash-200 focus:border-ash-500 focus:outline-none"
    />
  </div>
  <div>
    <label class="block text-sm text-ash-400 mb-1" for={id("timezone")}>{m.tfield_timezone()}</label>
    <select
      id={id("timezone")}
      value={values.timezone}
      {disabled}
      onchange={(e) => handleInput("timezone", (e.target as HTMLSelectElement).value)}
      class="w-full px-3 py-2 text-sm bg-dusk-950 border border-ash-700 rounded-lg text-ash-200"
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
    onchange={(e) => handleInput("online", (e.target as HTMLInputElement).checked)}
    class="w-5 h-5 rounded border-ash-700 bg-dusk-950 text-emerald-600 focus:ring-emerald-500"
  />
  <span class="text-sm text-ash-200">{m.tfield_online()}</span>
</label>

<!-- Location fields (hidden when online) -->
{#if !values.online}
  <div>
    <label class="block text-sm text-ash-400 mb-1" for={id("country")}>{m.common_country()}</label>
    <select
      id={id("country")}
      value={values.country}
      {disabled}
      onchange={(e) => handleInput("country", (e.target as HTMLSelectElement).value)}
      class="w-full px-3 py-2 text-sm bg-dusk-950 border border-ash-700 rounded-lg text-ash-200"
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
  <label class="block text-sm text-ash-400 mb-1" for={id("venue")}>{m.tfield_venue()}</label>
  <input
    id={id("venue")}
    type="text"
    value={values.venue}
    {disabled}
    oninput={(e) => handleInput("venue", (e.target as HTMLInputElement).value)}
    class="w-full px-3 py-2 text-sm bg-dusk-950 border border-ash-700 rounded-lg text-ash-200 focus:border-ash-500 focus:outline-none"
    placeholder={m.tfield_venue_placeholder()}
  />
</div>

<!-- Venue URL (always shown) -->
<div>
  <label class="block text-sm text-ash-400 mb-1" for={id("venue-url")}>{m.tfield_venue_url()}</label>
  <input
    id={id("venue-url")}
    type="url"
    value={values.venue_url}
    {disabled}
    oninput={(e) => handleInput("venue_url", (e.target as HTMLInputElement).value)}
    class="w-full px-3 py-2 text-sm bg-dusk-950 border border-ash-700 rounded-lg text-ash-200 focus:border-ash-500 focus:outline-none"
    placeholder="https://..."
  />
</div>

{#if !values.online}
  <!-- Address -->
  <div>
    <label class="block text-sm text-ash-400 mb-1" for={id("address")}>{m.tfield_address()}</label>
    <input
      id={id("address")}
      type="text"
      value={values.address}
      {disabled}
      oninput={(e) => handleInput("address", (e.target as HTMLInputElement).value)}
      class="w-full px-3 py-2 text-sm bg-dusk-950 border border-ash-700 rounded-lg text-ash-200 focus:border-ash-500 focus:outline-none"
      placeholder={m.tfield_address_placeholder()}
    />
  </div>

  <!-- Map URL -->
  <div>
    <label class="block text-sm text-ash-400 mb-1" for={id("map-url")}>{m.tfield_map_url()}</label>
    <input
      id={id("map-url")}
      type="url"
      value={values.map_url}
      {disabled}
      oninput={(e) => handleInput("map_url", (e.target as HTMLInputElement).value)}
      class="w-full px-3 py-2 text-sm bg-dusk-950 border border-ash-700 rounded-lg text-ash-200 focus:border-ash-500 focus:outline-none"
      placeholder="https://..."
    />
  </div>
{/if}

<!-- Description -->
<div>
  <label class="block text-sm text-ash-400 mb-1" for={id("description")}>{m.common_description()}</label>
  <span class="text-xs text-ash-500 mb-1 block">
    {@html m.tfield_markdown_support({ link: '<a href="https://www.markdownguide.org/basic-syntax/" target="_blank" rel="noopener noreferrer" class="underline text-ash-400 hover:text-ash-200">Markdown</a>' })}
  </span>
  <textarea
    id={id("description")}
    value={values.description}
    {disabled}
    oninput={(e) => handleInput("description", (e.target as HTMLTextAreaElement).value)}
    rows="3"
    class="w-full px-3 py-2 text-sm bg-dusk-950 border border-ash-700 rounded-lg text-ash-200 focus:border-ash-500 focus:outline-none resize-none"
    placeholder={m.tfield_description_placeholder()}
  ></textarea>
</div>

<!-- Standings & Decklists -->
<div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
  <div>
    <label class="block text-sm text-ash-400 mb-1" for={id("standings")}>{m.tfield_standings_visibility()}</label>
    <select
      id={id("standings")}
      value={values.standings_mode}
      {disabled}
      onchange={(e) => handleInput("standings_mode", (e.target as HTMLSelectElement).value)}
      class="w-full px-3 py-2 text-sm bg-dusk-950 border border-ash-700 rounded-lg text-ash-200"
    >
      <option value="Private">Private</option>
      <option value="Cutoff">Cutoff (Top 5)</option>
      <option value="Top 10">Top 10</option>
      <option value="Public">Public</option>
    </select>
  </div>
  <div>
    <label class="block text-sm text-ash-400 mb-1" for={id("decklists")}>{m.tfield_decklists_visibility()}</label>
    <select
      id={id("decklists")}
      value={values.decklists_mode}
      {disabled}
      onchange={(e) => handleInput("decklists_mode", (e.target as HTMLSelectElement).value)}
      class="w-full px-3 py-2 text-sm bg-dusk-950 border border-ash-700 rounded-lg text-ash-200"
    >
      <option value="Winner">Winner Only</option>
      <option value="Finalists">Finalists</option>
      <option value="All">All</option>
    </select>
  </div>
</div>

<!-- Boolean toggles -->
<div class="space-y-3">
  <label class="flex items-center gap-3 cursor-pointer">
    <input
      type="checkbox"
      checked={values.proxies}
      {disabled}
      onchange={(e) => handleInput("proxies", (e.target as HTMLInputElement).checked)}
      class="w-5 h-5 rounded border-ash-700 bg-dusk-950 text-emerald-600 focus:ring-emerald-500"
    />
    <span class="text-sm text-ash-200">{m.tfield_allow_proxies()}</span>
  </label>
  <label class="flex items-center gap-3 cursor-pointer">
    <input
      type="checkbox"
      checked={values.multideck}
      {disabled}
      onchange={(e) => handleInput("multideck", (e.target as HTMLInputElement).checked)}
      class="w-5 h-5 rounded border-ash-700 bg-dusk-950 text-emerald-600 focus:ring-emerald-500"
    />
    <span class="text-sm text-ash-200">{m.tfield_multideck()}</span>
  </label>
  <label class="flex items-center gap-3 cursor-pointer">
    <input
      type="checkbox"
      checked={values.decklist_required}
      {disabled}
      onchange={(e) => handleInput("decklist_required", (e.target as HTMLInputElement).checked)}
      class="w-5 h-5 rounded border-ash-700 bg-dusk-950 text-emerald-600 focus:ring-emerald-500"
    />
    <span class="text-sm text-ash-200">{m.tfield_decklist_required()}</span>
  </label>
</div>
