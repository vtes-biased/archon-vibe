<script lang="ts">
  import type { TournamentFormat, TournamentRank, StandingsMode, DeckListsMode, League } from "$lib/types";
  import { getCountries, getCountryFlag } from "$lib/geonames";
  import { getAllLeagues } from "$lib/db";

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

  let leagues = $state<League[]>([]);
  $effect(() => {
    getAllLeagues().then(all => {
      leagues = all
        .filter(l => !l.deleted_at && (!l.finish || new Date(l.finish) >= new Date()))
        .sort((a, b) => a.name.localeCompare(b.name));
    });
  });

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
  <label class="block text-sm text-ash-400 mb-1" for={id("name")}>Name *</label>
  <input
    id={id("name")}
    type="text"
    value={values.name}
    {disabled}
    oninput={(e) => handleInput("name", (e.target as HTMLInputElement).value)}
    class="w-full px-3 py-2 text-sm bg-dusk-950 border border-ash-700 rounded-lg text-ash-200 focus:border-ash-500 focus:outline-none"
    placeholder="Tournament name"
  />
</div>

<!-- Format & Rank -->
<div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
  <div>
    <label class="block text-sm text-ash-400 mb-1" for={id("format")}>Format</label>
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
    <label class="block text-sm text-ash-400 mb-1" for={id("rank")}>Rank</label>
    <select
      id={id("rank")}
      value={values.rank}
      {disabled}
      onchange={(e) => handleInput("rank", (e.target as HTMLSelectElement).value)}
      class="w-full px-3 py-2 text-sm bg-dusk-950 border border-ash-700 rounded-lg text-ash-200"
    >
      <option value="">Basic</option>
      <option value="National Championship">National Championship</option>
      <option value="Continental Championship">Continental Championship</option>
    </select>
  </div>
</div>

<!-- League -->
{#if leagues.length > 0}
  <div>
    <label class="block text-sm text-ash-400 mb-1" for={id("league")}>League</label>
    <select
      id={id("league")}
      value={values.league_uid}
      {disabled}
      onchange={(e) => handleInput("league_uid", (e.target as HTMLSelectElement).value)}
      class="w-full px-3 py-2 text-sm bg-dusk-950 border border-ash-700 rounded-lg text-ash-200"
    >
      <option value="">None</option>
      {#each leagues as league}
        <option value={league.uid}>{league.name}</option>
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
    <span class="text-sm text-ash-200">Open Rounds</span>
  </label>
  <p class="text-xs text-ash-500 mt-1 ml-8">Players participate in up to a maximum number of rounds among all scheduled rounds.</p>
  {#if values.open_rounds}
    <div class="mt-2 ml-8">
      <label class="block text-sm text-ash-400 mb-1" for={id("max-rounds")}>Max Rounds</label>
      <select
        id={id("max-rounds")}
        value={String(values.max_rounds)}
        disabled={disabled || disabledFields.has("max_rounds")}
        onchange={(e) => handleInput("max_rounds", parseInt((e.target as HTMLSelectElement).value))}
        class="w-full px-3 py-2 text-sm bg-dusk-950 border border-ash-700 rounded-lg text-ash-200"
      >
        <option value="0">No limit</option>
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
    <label class="block text-sm text-ash-400 mb-1" for={id("start")}>Start</label>
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
    <label class="block text-sm text-ash-400 mb-1" for={id("finish")}>Finish</label>
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
    <label class="block text-sm text-ash-400 mb-1" for={id("timezone")}>Timezone</label>
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
  <span class="text-sm text-ash-200">Online Tournament</span>
</label>

<!-- Location fields (hidden when online) -->
{#if !values.online}
  <div>
    <label class="block text-sm text-ash-400 mb-1" for={id("country")}>Country</label>
    <select
      id={id("country")}
      value={values.country}
      {disabled}
      onchange={(e) => handleInput("country", (e.target as HTMLSelectElement).value)}
      class="w-full px-3 py-2 text-sm bg-dusk-950 border border-ash-700 rounded-lg text-ash-200"
    >
      <option value="">Select country</option>
      {#each Object.entries(countries) as [code, c]}
        <option value={code}>{c.name} {getCountryFlag(code)}</option>
      {/each}
    </select>
  </div>
{/if}

<!-- Venue (always shown) -->
<div>
  <label class="block text-sm text-ash-400 mb-1" for={id("venue")}>Venue</label>
  <input
    id={id("venue")}
    type="text"
    value={values.venue}
    {disabled}
    oninput={(e) => handleInput("venue", (e.target as HTMLInputElement).value)}
    class="w-full px-3 py-2 text-sm bg-dusk-950 border border-ash-700 rounded-lg text-ash-200 focus:border-ash-500 focus:outline-none"
    placeholder="Venue name"
  />
</div>

<!-- Venue URL (always shown) -->
<div>
  <label class="block text-sm text-ash-400 mb-1" for={id("venue-url")}>Venue URL</label>
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
    <label class="block text-sm text-ash-400 mb-1" for={id("address")}>Address</label>
    <input
      id={id("address")}
      type="text"
      value={values.address}
      {disabled}
      oninput={(e) => handleInput("address", (e.target as HTMLInputElement).value)}
      class="w-full px-3 py-2 text-sm bg-dusk-950 border border-ash-700 rounded-lg text-ash-200 focus:border-ash-500 focus:outline-none"
      placeholder="Street address"
    />
  </div>

  <!-- Map URL -->
  <div>
    <label class="block text-sm text-ash-400 mb-1" for={id("map-url")}>Map URL</label>
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
  <label class="block text-sm text-ash-400 mb-1" for={id("description")}>Description</label>
  <span class="text-xs text-ash-500 mb-1 block">
    Supports <a href="https://www.markdownguide.org/basic-syntax/" target="_blank" rel="noopener noreferrer" class="underline text-ash-400 hover:text-ash-200">Markdown</a> formatting
  </span>
  <textarea
    id={id("description")}
    value={values.description}
    {disabled}
    oninput={(e) => handleInput("description", (e.target as HTMLTextAreaElement).value)}
    rows="3"
    class="w-full px-3 py-2 text-sm bg-dusk-950 border border-ash-700 rounded-lg text-ash-200 focus:border-ash-500 focus:outline-none resize-none"
    placeholder="Optional description"
  ></textarea>
</div>

<!-- Standings & Decklists -->
<div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
  <div>
    <label class="block text-sm text-ash-400 mb-1" for={id("standings")}>Standings Visibility</label>
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
    <label class="block text-sm text-ash-400 mb-1" for={id("decklists")}>Decklists Visibility</label>
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
    <span class="text-sm text-ash-200">Allow Proxies</span>
  </label>
  <label class="flex items-center gap-3 cursor-pointer">
    <input
      type="checkbox"
      checked={values.multideck}
      {disabled}
      onchange={(e) => handleInput("multideck", (e.target as HTMLInputElement).checked)}
      class="w-5 h-5 rounded border-ash-700 bg-dusk-950 text-emerald-600 focus:ring-emerald-500"
    />
    <span class="text-sm text-ash-200">Multideck</span>
  </label>
  <label class="flex items-center gap-3 cursor-pointer">
    <input
      type="checkbox"
      checked={values.decklist_required}
      {disabled}
      onchange={(e) => handleInput("decklist_required", (e.target as HTMLInputElement).checked)}
      class="w-5 h-5 rounded border-ash-700 bg-dusk-950 text-emerald-600 focus:ring-emerald-500"
    />
    <span class="text-sm text-ash-200">Decklist Required</span>
  </label>
</div>
