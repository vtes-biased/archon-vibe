<script lang="ts">
  import { untrack } from "svelte";
  import { getAllLeagues } from "$lib/db";
  import { syncManager } from "$lib/sync";
  import { getCountries, getCountryFlag } from "$lib/geonames";
  import { hasAnyRole } from "$lib/stores/auth.svelte";
  import { normalizeSearch } from "$lib/utils";
  import type { League, LeagueStandingsMode } from "$lib/types";
  import { Loader2, BarChart3 } from "@lucide/svelte";
  import * as m from '$lib/paraglide/messages.js';

  let leagues = $state<League[]>([]);
  // Parent meta-league name, keyed by child league uid
  let metaLeagueNames = $state<Record<string, string>>({});
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
      const opts: Intl.DateTimeFormatOptions = { year: "numeric", month: "short", day: "numeric" };
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
      // Resolve parent meta-league names from the full (unfiltered) set
      const byUid = new Map(all.filter(l => !l.deleted_at).map(l => [l.uid, l.name]));
      const metaMap: Record<string, string> = {};
      for (const l of all) {
        if (!l.deleted_at && l.parent_uid && byUid.has(l.parent_uid)) metaMap[l.uid] = byUid.get(l.parent_uid)!;
      }
      metaLeagueNames = metaMap;
      // Exclude soft-deleted
      all = all.filter(l => !l.deleted_at);
      // Filter past
      if (!showPast) {
        all = all.filter(l => isActive(l));
      }
      // Filter by country
      if (selectedCountry !== "all") {
        all = all.filter(l => !l.country || l.country === selectedCountry);
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
      <h1 class="text-3xl font-semibold text-accent">{m.leagues_title()}</h1>

      {#if canCreate}
        <a
          href="/leagues/new"
          class="px-4 py-2 text-sm font-medium btn-success rounded-lg transition-colors shadow-md"
        >
          {m.league_new_btn()}
        </a>
      {/if}
    </div>

    <!-- Filters -->
    <div class="bg-surface-card rounded-lg shadow p-4 mb-6 border border-line">
      <div class="flex flex-wrap gap-4 items-end">
        <!-- Search -->
        <div class="flex-1 min-w-[200px]">
          <label for="search" class="block text-sm font-medium text-ink-muted mb-1">{m.common_search()}</label>
          <input
            id="search"
            type="text"
            bind:value={searchQuery}
            placeholder={m.league_search_placeholder()}
            class="w-full px-3 py-2 border border-line-strong rounded-lg bg-surface-card text-ink-bright placeholder:text-ink-faint"
          />
        </div>

        <!-- Country -->
        <div class="min-w-[180px]">
          <label for="country-filter" class="block text-sm font-medium text-ink-muted mb-1">{m.common_country()}</label>
          <select
            id="country-filter"
            bind:value={selectedCountry}
            class="w-full px-3 py-2 border border-line-strong rounded-lg bg-surface-card text-ink-bright"
          >
            <option value="all">{m.league_all_countries()}</option>
            {#each Object.entries(countries) as [code, country]}
              <option value={code}>{country.name} {getCountryFlag(code)}</option>
            {/each}
          </select>
        </div>

        <!-- Show past -->
        <div class="flex items-center gap-3 pb-1">
          <label class="inline-flex items-center gap-2 cursor-pointer">
            <input type="checkbox" bind:checked={showPast} class="sr-only peer" />
            <div class="relative w-11 h-6 bg-surface-active rounded-full peer-checked:bg-accent-strong transition-colors">
              <div class="absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform" class:translate-x-5={showPast}></div>
            </div>
            <span class="text-sm text-ink">{m.league_show_past()}</span>
          </label>
        </div>
      </div>
    </div>

    <!-- League List -->
    {#if leagues.length > 0}
      <div class="bg-surface-card rounded-lg shadow overflow-hidden border border-line">
        <!-- Header (desktop) -->
        <div class="hidden sm:grid sm:grid-cols-12 gap-4 px-6 py-3 bg-surface-muted text-sm font-medium text-ink border-b border-line-strong">
          <div class="col-span-5">{m.common_name()}</div>
          <div class="col-span-3">{m.league_col_dates()}</div>
          <div class="col-span-2">{m.common_country()}</div>
          <div class="col-span-2">{m.league_col_standings()}</div>
        </div>

        <div class="divide-y divide-line">
          {#each leagues as league (league.uid)}
            <a
              href="/leagues/{league.uid}"
              class="block px-6 py-4 hover:bg-surface-muted/50 transition-colors"
            >
              <!-- Mobile -->
              <div class="sm:hidden space-y-2">
                <div class="flex items-start justify-between">
                  <div>
                    <div class="font-semibold text-ink-strong">{league.name}</div>
                    <div class="text-sm text-ink-muted mt-1">
                      {formatDateRange(league)}
                    </div>
                  </div>
                  <span class="px-2 py-1 rounded text-xs font-medium {isActive(league) ? 'badge-success' : 'bg-surface-hover text-ink-muted'}">
                    {isActive(league) ? m.league_status_active() : m.league_status_finished()}
                  </span>
                </div>
                <div class="flex gap-2 text-xs text-ink-faint">
                  <span>{standingsModeLabel(league.standings_mode)}</span>
                  {#if league.format}
                    <span>· {league.format}</span>
                  {/if}
                  {#if league.country}
                    <span>· {getCountryFlag(league.country)}</span>
                  {/if}
                  {#if league.kind === "Meta-League"}
                    <span>· {m.league_meta_badge()}</span>
                  {/if}
                  {#if metaLeagueNames[league.uid]}
                    <span class="text-warn/80" title={m.league_kind_meta()}>· {metaLeagueNames[league.uid]}</span>
                  {/if}
                </div>
              </div>

              <!-- Desktop -->
              <div class="hidden sm:grid sm:grid-cols-12 gap-4 items-center">
                <div class="col-span-5">
                  <div class="font-semibold text-ink-strong">
                    {league.name}
                    {#if league.kind === "Meta-League"}
                      <span class="ml-2 px-2 py-0.5 rounded text-xs font-medium badge-amethyst">{m.league_meta_badge()}</span>
                    {/if}
                    {#if metaLeagueNames[league.uid]}
                      <span class="ml-2 px-2 py-0.5 rounded text-xs font-medium badge-amethyst" title={m.league_kind_meta()}>{metaLeagueNames[league.uid]}</span>
                    {/if}
                  </div>
                  {#if league.format}
                    <div class="text-xs text-ink-faint">{league.format}</div>
                  {/if}
                </div>
                <div class="col-span-3 text-sm text-ink-muted">
                  {formatDateRange(league)}
                </div>
                <div class="col-span-2 text-sm text-ink-muted">
                  {#if league.country}
                    {getCountryFlag(league.country)} {countries[league.country]?.name || league.country}
                  {:else}
                    {m.league_worldwide()}
                  {/if}
                </div>
                <div class="col-span-2 text-sm text-ink-muted">
                  {standingsModeLabel(league.standings_mode)}
                </div>
              </div>
            </a>
          {/each}
        </div>
      </div>

      <div class="mt-4 text-sm text-ink-muted">
        {m.league_total_count({ count: String(leagues.length) })}
      </div>
    {:else if !loaded}
      <div class="text-center py-12">
        <div class="text-ink-faint mb-4">
          <Loader2 class="mx-auto h-12 w-12 animate-spin" />
        </div>
        <h3 class="text-lg font-medium text-ink-strong mb-2">{m.common_loading()}</h3>
        <p class="text-ink-muted">{m.league_loading_hint()}</p>
      </div>
    {:else}
      <div class="text-center py-12">
        <div class="text-ink-faint mb-4">
          <BarChart3 class="mx-auto h-12 w-12" />
        </div>
        <h3 class="text-lg font-medium text-ink-strong mb-2">{m.league_no_results()}</h3>
        <p class="text-ink-muted">
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
