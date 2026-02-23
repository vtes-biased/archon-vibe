<script lang="ts">
  import { untrack } from "svelte";
  import { getFilteredTournaments, getAgendaTournaments } from "$lib/db";
  import { syncManager } from "$lib/sync";
  import { getCountries, getCountryFlag, getCountriesOnContinent } from "$lib/geonames";
  import { hasAnyRole, getAuthState, generateCalendarToken } from "$lib/stores/auth.svelte";
  import type { Tournament, TournamentFormat } from "$lib/types";
  import { getStateBadgeClass } from "$lib/tournament-utils";
  import { Loader2, Trophy, Calendar, Copy, Check } from "lucide-svelte";
  import * as m from '$lib/paraglide/messages.js';

  const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

  let tournaments = $state<Tournament[]>([]);
  let totalCount = $state(0);
  let loaded = $state(false);
  let showLoading = $state(false);
  // Delay showing spinner to avoid flash on fast IDB reads
  $effect(() => {
    if (loaded) { showLoading = false; return; }
    const timer = setTimeout(() => { showLoading = true; }, 200);
    return () => clearTimeout(timer);
  });
  let error = $state<string | null>(null);

  // View mode
  const auth = $derived(getAuthState());
  const canUseAgenda = $derived(auth.isAuthenticated && auth.user?.vekn_id && auth.user?.country);
  let viewMode = $state<"agenda" | "all">("all");

  // Set initial view mode based on auth
  $effect(() => {
    if (canUseAgenda) {
      untrack(() => { viewMode = "agenda"; });
    }
  });

  // Filters
  let searchQuery = $state("");
  let ongoing = $state(false);
  let selectedCountry = $state<string>("all");
  let selectedFormat = $state<string>("all");
  let includeOnline = $state(true);

  // Calendar
  let calendarLoading = $state(false);
  let copied = $state(false);

  // Pagination
  let page = $state(0);
  const PAGE_SIZE = 50;

  const countries = getCountries();
  const formats: TournamentFormat[] = ["Standard", "V5", "Limited"];

  const totalPages = $derived(Math.ceil(totalCount / PAGE_SIZE));
  const canCreate = $derived(hasAnyRole("IC", "NC", "Prince"));

  async function loadTournaments() {
    try {
      if (viewMode === "agenda" && canUseAgenda) {
        const user = auth.user!;
        const continentCountries = user.country ? getCountriesOnContinent(user.country) : [];
        const result = await getAgendaTournaments(
          user.uid,
          user.country!,
          continentCountries,
          { ongoing, includeOnline, format: selectedFormat, search: searchQuery },
          page,
          PAGE_SIZE,
        );
        tournaments = result.items;
        totalCount = result.total;
      } else {
        const result = await getFilteredTournaments(
          {
            ongoing,
            includeOnline,
            country: selectedCountry,
            format: selectedFormat,
            search: searchQuery,
          },
          page,
          PAGE_SIZE,
        );
        tournaments = result.items;
        totalCount = result.total;
      }
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

  // Re-query when filters or page change
  $effect(() => {
    const _s = searchQuery;
    const _o = ongoing;
    const _c = selectedCountry;
    const _f = selectedFormat;
    const _io = includeOnline;
    const _vm = viewMode;
    const _p = page;
    untrack(() => loadTournaments());
  });

  // Reset page when filters change
  $effect(() => {
    const _s = searchQuery;
    const _o = ongoing;
    const _c = selectedCountry;
    const _f = selectedFormat;
    const _io = includeOnline;
    const _vm = viewMode;
    untrack(() => { page = 0; });
  });

  // SSE sync listener
  $effect(() => {
    const handleSyncEvent = (event: { type: string }) => {
      if (event.type === "tournament" || event.type === "sync_complete") {
        loadTournaments();
      }
    };
    syncManager.addEventListener(handleSyncEvent);
    return () => syncManager.removeEventListener(handleSyncEvent);
  });

  // Calendar helpers
  const calendarUrl = $derived.by(() => {
    if (viewMode === "agenda" && auth.user?.calendar_token) {
      return `${API_BASE}/api/calendar/tournaments.ics?token=${auth.user.calendar_token}`;
    }
    const params = new URLSearchParams();
    if (selectedCountry && selectedCountry !== "all") {
      params.set("country", selectedCountry);
    }
    if (!includeOnline) {
      params.set("online", "false");
    }
    const qs = params.toString();
    return `${API_BASE}/api/calendar/tournaments.ics${qs ? '?' + qs : ''}`;
  });

  async function handleGenerateCalendarToken() {
    calendarLoading = true;
    try {
      await generateCalendarToken();
    } finally {
      calendarLoading = false;
    }
  }

  async function copyToClipboard(url: string) {
    try {
      await navigator.clipboard.writeText(url);
      copied = true;
      setTimeout(() => { copied = false; }, 2000);
    } catch { /* noop */ }
  }
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
          class="px-4 py-2 text-sm font-medium btn-emerald rounded-lg transition-colors shadow-md"
        >
          {m.tournaments_new_btn()}
        </a>
      {/if}
    </div>

    <!-- View Mode Toggle -->
    {#if canUseAgenda}
      <div class="flex mb-4 bg-dusk-950 rounded-lg border border-ash-800 p-1 w-fit">
        <button
          onclick={() => viewMode = "agenda"}
          class="px-4 py-2 text-sm font-medium rounded-md transition-colors {viewMode === 'agenda' ? 'bg-crimson-700 text-white' : 'text-ash-400 hover:text-ash-200'}"
        >
          {m.tournaments_view_agenda()}
        </button>
        <button
          onclick={() => viewMode = "all"}
          class="px-4 py-2 text-sm font-medium rounded-md transition-colors {viewMode === 'all' ? 'bg-crimson-700 text-white' : 'text-ash-400 hover:text-ash-200'}"
        >
          {m.tournaments_view_all()}
        </button>
      </div>
    {/if}

    <!-- Filters -->
    <div class="bg-dusk-950 rounded-lg shadow p-4 mb-4 border border-ash-800">
      <div class="flex flex-wrap gap-4 items-end">
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

        <!-- Country (hidden in agenda mode) -->
        {#if viewMode !== "agenda"}
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
        {/if}

        <!-- Ongoing toggle -->
        <div class="flex items-center gap-3 pb-1">
          <label class="inline-flex items-center gap-2 cursor-pointer">
            <input type="checkbox" bind:checked={ongoing} class="sr-only peer" />
            <div class="relative w-11 h-6 bg-ash-700 rounded-full peer-checked:bg-crimson-700 transition-colors">
              <div class="absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform" class:translate-x-5={ongoing}></div>
            </div>
            <span class="text-sm text-ash-300">{m.tournaments_ongoing()}</span>
          </label>
        </div>

        <!-- Include online -->
        <div class="flex items-center gap-3 pb-1">
          <label class="inline-flex items-center gap-2 cursor-pointer">
            <input type="checkbox" bind:checked={includeOnline} class="sr-only peer" />
            <div class="relative w-11 h-6 bg-ash-700 rounded-full peer-checked:bg-crimson-700 transition-colors">
              <div class="absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform" class:translate-x-5={includeOnline}></div>
            </div>
            <span class="text-sm text-ash-300">{m.tournaments_include_online()}</span>
          </label>
        </div>
      </div>
    </div>

    <!-- Calendar Subscribe -->
    {#if auth.isAuthenticated}
      <div class="flex items-center gap-2 flex-wrap mb-6 px-1">
        <Calendar class="h-4 w-4 text-ash-500 shrink-0" />
        <span class="text-xs text-ash-500">{m.tournaments_calendar_subscribe()}:</span>
        {#if viewMode === "agenda" && !auth.user?.calendar_token}
          <button
            onclick={handleGenerateCalendarToken}
            disabled={calendarLoading}
            class="px-3 py-1.5 text-xs rounded bg-crimson-700 hover:bg-crimson-600 text-white disabled:opacity-50 transition-colors"
          >
            {#if calendarLoading}
              <Loader2 class="inline h-3 w-3 animate-spin mr-1" />
            {/if}
            {m.tournaments_calendar_generate()}
          </button>
        {:else}
          <input
            type="text"
            readonly
            value={calendarUrl}
            class="flex-1 min-w-0 px-2 py-1.5 text-xs border border-ash-700 rounded bg-dusk-950 text-ash-400 select-all"
          />
          <button
            onclick={() => copyToClipboard(calendarUrl)}
            class="px-2 py-1.5 text-xs rounded bg-ash-800 hover:bg-ash-700 text-ash-200 flex items-center gap-1 shrink-0"
          >
            {#if copied}
              <Check class="h-3 w-3" />
              {m.tournaments_calendar_copied()}
            {:else}
              <Copy class="h-3 w-3" />
              {m.tournaments_calendar_copy()}
            {/if}
          </button>
        {/if}
      </div>
    {/if}

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
      {#if showLoading}
        <div class="text-center py-12">
          <div class="text-ash-500 mb-4">
            <Loader2 class="mx-auto h-12 w-12 animate-spin" />
          </div>
          <h3 class="text-lg font-medium text-bone-100 mb-2">{m.common_loading()}</h3>
          <p class="text-ash-400">{m.tournaments_loading_from_storage()}</p>
        </div>
      {/if}
    {:else}
      <div class="text-center py-12">
        <div class="text-ash-600 mb-4">
          <Trophy class="mx-auto h-12 w-12" />
        </div>
        <h3 class="text-lg font-medium text-bone-100 mb-2">{m.tournaments_no_results()}</h3>
        <p class="text-ash-400">
          {#if searchQuery.trim() || selectedCountry !== "all" || selectedFormat !== "all"}
            {m.tournaments_adjust_filters()}
          {:else}
            {m.tournaments_none_yet()}
          {/if}
        </p>
      </div>
    {/if}
  </div>
</div>
