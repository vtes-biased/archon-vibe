<script lang="ts">
  import { untrack } from "svelte";
  import { getFilteredTournaments } from "$lib/db";
  import { syncManager } from "$lib/sync";
  import { getCountries, getCountryFlag } from "$lib/geonames";
  import { hasAnyRole, getAuthState } from "$lib/stores/auth.svelte";
  import type { Tournament, TournamentState, TournamentFormat } from "$lib/types";
  import { getStateBadgeClass } from "$lib/tournament-utils";
  import { Loader2, Trophy } from "lucide-svelte";
  import * as m from '$lib/paraglide/messages.js';

  let tournaments = $state<Tournament[]>([]);
  let totalCount = $state(0);
  let loaded = $state(false);
  let error = $state<string | null>(null);

  // Filters
  let searchQuery = $state("");
  let selectedState = $state<string>("all");
  let selectedCountry = $state<string>("all");
  let selectedFormat = $state<string>("all");
  let sortBy = $state<"date" | "name" | "state">("date");

  // Pagination
  let page = $state(0);
  const PAGE_SIZE = 50;

  const countries = getCountries();
  const states: TournamentState[] = ["Planned", "Registration", "Waiting", "Playing", "Finished"];
  const formats: TournamentFormat[] = ["Standard", "V5", "Limited"];

  const totalPages = $derived(Math.ceil(totalCount / PAGE_SIZE));

  const canCreate = $derived(hasAnyRole("IC", "NC", "Prince"));
  const auth = $derived(getAuthState());

  async function loadTournaments() {
    try {
      const result = await getFilteredTournaments(
        {
          state: selectedState,
          country: selectedCountry,
          format: selectedFormat,
          search: searchQuery,
        },
        sortBy,
        page,
        PAGE_SIZE,
      );
      tournaments = result.items;
      totalCount = result.total;
    } catch (e) {
      error = e instanceof Error ? e.message : "Failed to load tournaments";
    } finally {
      loaded = true;
    }
  }

  function formatDate(t: Tournament): string {
    if (!t.start) return "—";
    try {
      const tz = t.online ? undefined : t.timezone || "UTC";
      const opts: Intl.DateTimeFormatOptions = {
        year: "numeric",
        month: "short",
        day: "numeric",
        ...(tz ? { timeZone: tz } : {}),
      };
      return new Date(t.start).toLocaleDateString(undefined, opts);
    } catch {
      return t.start;
    }
  }

  // Re-query when filters, sort, or page change
  $effect(() => {
    // Track reactive dependencies
    const _s = searchQuery;
    const _st = selectedState;
    const _c = selectedCountry;
    const _f = selectedFormat;
    const _sb = sortBy;
    const _p = page;
    untrack(() => loadTournaments());
  });

  // Reset page when filters change
  $effect(() => {
    const _s = searchQuery;
    const _st = selectedState;
    const _c = selectedCountry;
    const _f = selectedFormat;
    const _sb = sortBy;
    untrack(() => { page = 0; });
  });

  // SSE sync listener (separate from filter effect)
  $effect(() => {
    const handleSyncEvent = (event: { type: string }) => {
      if (event.type === "tournament" || event.type === "sync_complete") {
        loadTournaments();
      }
    };

    syncManager.addEventListener(handleSyncEvent);
    return () => syncManager.removeEventListener(handleSyncEvent);
  });
</script>

<svelte:head>
  <title>{m.tournaments_page_title()} - Archon</title>
</svelte:head>

<div class="p-4 sm:p-8">
  <div class="max-w-6xl mx-auto">
    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-3xl font-light text-crimson-500">{m.nav_tournaments()}</h1>

      {#if canCreate}
        <a
          href="/tournaments/new"
          class="px-4 py-2 text-sm font-medium text-white bg-emerald-700 hover:bg-emerald-600 rounded-lg transition-colors shadow-md"
        >
          {m.tournaments_new_btn()}
        </a>
      {/if}
    </div>

    <!-- Filters -->
    <div class="bg-dusk-950 rounded-lg shadow p-4 mb-6 border border-ash-800">
      <div class="flex flex-wrap gap-4">
        <!-- Search -->
        <div class="flex-1 min-w-[200px]">
          <label for="search" class="block text-sm font-medium text-ash-400 mb-1">{m.common_search()}</label>
          <input
            id="search"
            type="text"
            bind:value={searchQuery}
            placeholder={m.tournaments_search_placeholder()}
            class="w-full px-3 py-2 border border-ash-600 rounded-lg bg-dusk-950 text-ash-200 placeholder:text-ash-600"
          />
        </div>

        <!-- State -->
        <div class="min-w-[150px]">
          <label for="state-filter" class="block text-sm font-medium text-ash-400 mb-1">{m.tournaments_state()}</label>
          <select
            id="state-filter"
            bind:value={selectedState}
            class="w-full px-3 py-2 border border-ash-600 rounded-lg bg-dusk-950 text-ash-200"
          >
            <option value="all">{m.tournaments_all_states()}</option>
            {#each states as s}
              <option value={s}>{s}</option>
            {/each}
          </select>
        </div>

        <!-- Format -->
        <div class="min-w-[130px]">
          <label for="format-filter" class="block text-sm font-medium text-ash-400 mb-1">{m.tournaments_format()}</label>
          <select
            id="format-filter"
            bind:value={selectedFormat}
            class="w-full px-3 py-2 border border-ash-600 rounded-lg bg-dusk-950 text-ash-200"
          >
            <option value="all">{m.tournaments_all_formats()}</option>
            {#each formats as f}
              <option value={f}>{f}</option>
            {/each}
          </select>
        </div>

        <!-- Country -->
        <div class="min-w-[180px]">
          <label for="country-filter" class="block text-sm font-medium text-ash-400 mb-1">{m.common_country()}</label>
          <select
            id="country-filter"
            bind:value={selectedCountry}
            class="w-full px-3 py-2 border border-ash-600 rounded-lg bg-dusk-950 text-ash-200"
          >
            <option value="all">{m.tournaments_all_countries()}</option>
            {#each Object.entries(countries) as [code, country]}
              <option value={code}>{country.name} {getCountryFlag(code)}</option>
            {/each}
          </select>
        </div>

        <!-- Sort -->
        <div class="min-w-[130px]">
          <label for="sort" class="block text-sm font-medium text-ash-400 mb-1">{m.tournaments_sort_by()}</label>
          <select
            id="sort"
            bind:value={sortBy}
            class="w-full px-3 py-2 border border-ash-600 rounded-lg bg-dusk-950 text-ash-200"
          >
            <option value="date">{m.tournaments_sort_date()}</option>
            <option value="name">{m.tournaments_sort_name()}</option>
            <option value="state">{m.tournaments_sort_state()}</option>
          </select>
        </div>
      </div>
    </div>

    <!-- Error -->
    {#if error}
      <div class="bg-crimson-900/20 border border-crimson-800 rounded-lg p-4 mb-6">
        <p class="text-crimson-300">{error}</p>
      </div>
    {/if}

    <!-- Tournament List -->
    {#if tournaments.length > 0}
      <div class="bg-dusk-950 rounded-lg shadow overflow-hidden border border-ash-800">
        <!-- Header (desktop) -->
        <div class="hidden sm:grid sm:grid-cols-12 gap-4 px-6 py-3 bg-ash-900 text-sm font-medium text-ash-300 border-b border-ash-700">
          <div class="col-span-4">{m.tournaments_col_name()}</div>
          <div class="col-span-2">{m.tournaments_col_date()}</div>
          <div class="col-span-2">{m.tournaments_col_country()}</div>
          <div class="col-span-2">{m.tournaments_col_format()}</div>
          <div class="col-span-2">{m.tournaments_col_state()}</div>
        </div>

        <div class="divide-y divide-ash-800">
          {#each tournaments as tournament (tournament.uid)}
            <a
              href="/tournaments/{tournament.uid}"
              class="block px-6 py-4 hover:bg-ash-900/50 transition-colors"
            >
              <!-- Mobile -->
              <div class="sm:hidden space-y-2">
                <div class="flex items-start justify-between">
                  <div>
                    <div class="font-semibold text-bone-100">{tournament.name}</div>
                    <div class="text-sm text-ash-400 mt-1">
                      {formatDate(tournament)}
                      {#if tournament.country}
                        · {getCountryFlag(tournament.country)} {countries[tournament.country]?.name || tournament.country}
                      {/if}
                    </div>
                  </div>
                  <span class="px-2 py-1 rounded text-xs font-medium {getStateBadgeClass(tournament.state)}">
                    {tournament.state}
                  </span>
                </div>
                <div class="flex gap-2 text-xs text-ash-500">
                  <span>{tournament.format}</span>
                  {#if tournament.rank}
                    <span>· {tournament.rank}</span>
                  {/if}
                  {#if tournament.online}
                    <span>· {m.tournaments_online()}</span>
                  {/if}
                </div>
              </div>

              <!-- Desktop -->
              <div class="hidden sm:grid sm:grid-cols-12 gap-4 items-center">
                <div class="col-span-4">
                  <div class="font-semibold text-bone-100">{tournament.name}</div>
                  {#if tournament.rank}
                    <div class="text-xs text-ash-500">{tournament.rank}</div>
                  {/if}
                </div>
                <div class="col-span-2 text-sm text-ash-400">
                  {formatDate(tournament)}
                </div>
                <div class="col-span-2 text-sm text-ash-400">
                  {#if tournament.country}
                    {getCountryFlag(tournament.country)} {countries[tournament.country]?.name || tournament.country}
                  {:else if tournament.online}
                    {m.tournaments_online()}
                  {:else}
                    —
                  {/if}
                </div>
                <div class="col-span-2 text-sm text-ash-400">
                  {tournament.format}
                </div>
                <div class="col-span-2">
                  <span class="px-2 py-1 rounded text-xs font-medium {getStateBadgeClass(tournament.state)}">
                    {tournament.state}
                  </span>
                </div>
              </div>
            </a>
          {/each}
        </div>
      </div>

      <div class="mt-4 flex items-center justify-between text-sm text-ash-400">
        <span>{m.tournaments_total_count({ count: totalCount.toString() })}</span>
        {#if totalPages > 1}
          <div class="flex items-center gap-2">
            <button
              onclick={() => page = Math.max(0, page - 1)}
              disabled={page === 0}
              class="px-3 py-1 rounded bg-ash-800 hover:bg-ash-700 disabled:opacity-40 disabled:cursor-not-allowed text-ash-200"
            >{m.tournaments_prev()}</button>
            <span>{m.tournaments_page_info({ current: String(page + 1), total: String(totalPages) })}</span>
            <button
              onclick={() => page = Math.min(totalPages - 1, page + 1)}
              disabled={page >= totalPages - 1}
              class="px-3 py-1 rounded bg-ash-800 hover:bg-ash-700 disabled:opacity-40 disabled:cursor-not-allowed text-ash-200"
            >{m.common_next()}</button>
          </div>
        {/if}
      </div>
    {:else if !loaded}
      <div class="text-center py-12">
        <div class="text-ash-500 mb-4">
          <Loader2 class="mx-auto h-12 w-12 animate-spin" />
        </div>
        <h3 class="text-lg font-medium text-bone-100 mb-2">{m.common_loading()}</h3>
        <p class="text-ash-400">{m.tournaments_loading_from_storage()}</p>
      </div>
    {:else}
      <div class="text-center py-12">
        <div class="text-ash-600 mb-4">
          <Trophy class="mx-auto h-12 w-12" />
        </div>
        <h3 class="text-lg font-medium text-bone-100 mb-2">{m.tournaments_no_results()}</h3>
        <p class="text-ash-400">
          {#if searchQuery.trim() || selectedState !== "all" || selectedCountry !== "all" || selectedFormat !== "all"}
            {m.tournaments_adjust_filters()}
          {:else}
            {m.tournaments_none_yet()}
          {/if}
        </p>
      </div>
    {/if}
  </div>
</div>
