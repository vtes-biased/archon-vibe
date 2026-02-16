<script lang="ts">
  import { untrack } from "svelte";
  import { getAllLeagues } from "$lib/db";
  import { syncManager } from "$lib/sync";
  import { getCountries, getCountryFlag } from "$lib/geonames";
  import { hasAnyRole } from "$lib/stores/auth.svelte";
  import { normalizeSearch } from "$lib/utils";
  import type { League, LeagueStandingsMode } from "$lib/types";
  import Icon from "@iconify/svelte";
  import * as m from '$lib/paraglide/messages.js';

  let leagues = $state<League[]>([]);
  let loaded = $state(false);

  // Filters
  let searchQuery = $state("");
  let selectedCountry = $state<string>("all");
  let showPast = $state(false);

  const countries = getCountries();
  const canCreate = $derived(hasAnyRole("IC", "NC"));

  function standingsModeLabel(mode: LeagueStandingsMode): string {
    switch (mode) {
      case "RTP": return m.league_standings_rtp();
      case "Score": return m.league_standings_score();
      case "GP": return m.league_standings_gp();
      default: return mode;
    }
  }

  function formatDateRange(league: League): string {
    if (!league.start) return "—";
    try {
      const tz = league.timezone || "UTC";
      const opts: Intl.DateTimeFormatOptions = { year: "numeric", month: "short", day: "numeric", timeZone: tz };
      const start = new Date(league.start).toLocaleDateString(undefined, opts);
      if (league.finish) {
        const end = new Date(league.finish).toLocaleDateString(undefined, opts);
        return `${start} – ${end}`;
      }
      return `${start} – ${m.league_ongoing()}`;
    } catch {
      return league.start;
    }
  }

  function isActive(league: League): boolean {
    if (!league.finish) return true;
    return new Date(league.finish) >= new Date();
  }

  async function loadLeagues() {
    try {
      let all = await getAllLeagues();
      // Exclude soft-deleted
      all = all.filter(l => !l.deleted_at);
      // Filter past
      if (!showPast) {
        all = all.filter(l => isActive(l));
      }
      // Filter by country
      if (selectedCountry !== "all") {
        all = all.filter(l => l.country === selectedCountry);
      }
      // Filter by search
      if (searchQuery.trim()) {
        const q = normalizeSearch(searchQuery.trim());
        all = all.filter(l => normalizeSearch(l.name).includes(q));
      }
      // Sort: active first (by start desc), then finished (by finish desc)
      all.sort((a, b) => {
        const da = a.start || a.modified;
        const db_ = b.start || b.modified;
        return db_.localeCompare(da);
      });
      leagues = all;
    } finally {
      loaded = true;
    }
  }

  // Re-query when filters change
  $effect(() => {
    const _s = searchQuery;
    const _c = selectedCountry;
    const _p = showPast;
    untrack(() => loadLeagues());
  });

  // SSE sync listener
  $effect(() => {
    const handleSyncEvent = (event: { type: string }) => {
      if (event.type === "league" || event.type === "sync_complete") {
        loadLeagues();
      }
    };
    syncManager.addEventListener(handleSyncEvent);
    return () => syncManager.removeEventListener(handleSyncEvent);
  });
</script>

<svelte:head>
  <title>{m.leagues_title()} - Archon</title>
</svelte:head>

<div class="p-4 sm:p-8">
  <div class="max-w-6xl mx-auto">
    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-3xl font-light text-crimson-500">{m.leagues_title()}</h1>

      {#if canCreate}
        <a
          href="/leagues/new"
          class="px-4 py-2 text-sm font-medium text-white bg-emerald-700 hover:bg-emerald-600 rounded-lg transition-colors shadow-md"
        >
          {m.league_new_btn()}
        </a>
      {/if}
    </div>

    <!-- Filters -->
    <div class="bg-dusk-950 rounded-lg shadow p-4 mb-6 border border-ash-800">
      <div class="flex flex-wrap gap-4 items-end">
        <!-- Search -->
        <div class="flex-1 min-w-[200px]">
          <label for="search" class="block text-sm font-medium text-ash-400 mb-1">{m.common_search()}</label>
          <input
            id="search"
            type="text"
            bind:value={searchQuery}
            placeholder={m.league_search_placeholder()}
            class="w-full px-3 py-2 border border-ash-600 rounded-lg bg-dusk-950 text-ash-200 placeholder:text-ash-600"
          />
        </div>

        <!-- Country -->
        <div class="min-w-[180px]">
          <label for="country-filter" class="block text-sm font-medium text-ash-400 mb-1">{m.common_country()}</label>
          <select
            id="country-filter"
            bind:value={selectedCountry}
            class="w-full px-3 py-2 border border-ash-600 rounded-lg bg-dusk-950 text-ash-200"
          >
            <option value="all">{m.league_all_countries()}</option>
            {#each Object.entries(countries) as [code, country]}
              <option value={code}>{country.name} {getCountryFlag(code)}</option>
            {/each}
          </select>
        </div>

        <!-- Show past -->
        <label class="flex items-center gap-2 text-sm text-ash-400 cursor-pointer py-2">
          <input
            type="checkbox"
            bind:checked={showPast}
            class="rounded border-ash-600 bg-dusk-950 text-crimson-500"
          />
          {m.league_show_past()}
        </label>
      </div>
    </div>

    <!-- League List -->
    {#if leagues.length > 0}
      <div class="bg-dusk-950 rounded-lg shadow overflow-hidden border border-ash-800">
        <!-- Header (desktop) -->
        <div class="hidden sm:grid sm:grid-cols-12 gap-4 px-6 py-3 bg-ash-900 text-sm font-medium text-ash-300 border-b border-ash-700">
          <div class="col-span-4">{m.common_name()}</div>
          <div class="col-span-3">{m.league_col_dates()}</div>
          <div class="col-span-2">{m.common_country()}</div>
          <div class="col-span-2">{m.league_col_standings()}</div>
          <div class="col-span-1">{m.league_col_kind()}</div>
        </div>

        <div class="divide-y divide-ash-800">
          {#each leagues as league (league.uid)}
            <a
              href="/leagues/{league.uid}"
              class="block px-6 py-4 hover:bg-ash-900/50 transition-colors"
            >
              <!-- Mobile -->
              <div class="sm:hidden space-y-2">
                <div class="flex items-start justify-between">
                  <div>
                    <div class="font-semibold text-bone-100">{league.name}</div>
                    <div class="text-sm text-ash-400 mt-1">
                      {formatDateRange(league)}
                    </div>
                  </div>
                  <span class="px-2 py-1 rounded text-xs font-medium {isActive(league) ? 'bg-emerald-900/50 text-emerald-300' : 'bg-ash-800 text-ash-400'}">
                    {isActive(league) ? m.league_status_active() : m.league_status_finished()}
                  </span>
                </div>
                <div class="flex gap-2 text-xs text-ash-500">
                  <span>{standingsModeLabel(league.standings_mode)}</span>
                  {#if league.format}
                    <span>· {league.format}</span>
                  {/if}
                  {#if league.country}
                    <span>· {getCountryFlag(league.country)}</span>
                  {/if}
                  {#if league.kind === "Meta-League"}
                    <span>· Meta</span>
                  {/if}
                </div>
              </div>

              <!-- Desktop -->
              <div class="hidden sm:grid sm:grid-cols-12 gap-4 items-center">
                <div class="col-span-4">
                  <div class="font-semibold text-bone-100">{league.name}</div>
                  {#if league.format}
                    <div class="text-xs text-ash-500">{league.format}</div>
                  {/if}
                </div>
                <div class="col-span-3 text-sm text-ash-400">
                  {formatDateRange(league)}
                </div>
                <div class="col-span-2 text-sm text-ash-400">
                  {#if league.country}
                    {getCountryFlag(league.country)} {countries[league.country]?.name || league.country}
                  {:else}
                    {m.league_worldwide()}
                  {/if}
                </div>
                <div class="col-span-2 text-sm text-ash-400">
                  {standingsModeLabel(league.standings_mode)}
                </div>
                <div class="col-span-1">
                  {#if league.kind === "Meta-League"}
                    <span class="px-2 py-1 rounded text-xs font-medium bg-violet-900/50 text-violet-300">Meta</span>
                  {/if}
                </div>
              </div>
            </a>
          {/each}
        </div>
      </div>

      <div class="mt-4 text-sm text-ash-400">
        {m.league_total_count({ count: String(leagues.length) })}
      </div>
    {:else if !loaded}
      <div class="text-center py-12">
        <div class="text-ash-500 mb-4">
          <Icon icon="lucide:loader-2" class="mx-auto h-12 w-12 animate-spin" />
        </div>
        <h3 class="text-lg font-medium text-bone-100 mb-2">{m.common_loading()}</h3>
        <p class="text-ash-400">{m.league_loading_hint()}</p>
      </div>
    {:else}
      <div class="text-center py-12">
        <div class="text-ash-600 mb-4">
          <Icon icon="lucide:bar-chart-3" class="mx-auto h-12 w-12" />
        </div>
        <h3 class="text-lg font-medium text-bone-100 mb-2">{m.league_no_results()}</h3>
        <p class="text-ash-400">
          {#if searchQuery.trim() || selectedCountry !== "all"}
            {m.league_adjust_filters()}
          {:else if !showPast}
            {m.league_no_active()}
          {:else}
            {m.league_none_yet()}
          {/if}
        </p>
      </div>
    {/if}
  </div>
</div>
