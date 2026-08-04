<script lang="ts">
  import { toUserMessage } from '$lib/errors';
  import { untrack } from "svelte";
  import { getFilteredTournaments, getAgendaTournaments, getLeague } from "$lib/db";
  import { syncManager } from "$lib/sync";
  import { getCountries, getSortedCountries, getCountryFlag, getCountriesOnContinent } from "$lib/geonames";
  import { getAuthState, generateCalendarToken } from "$lib/stores/auth.svelte";
  import { canCreateTournament } from "$lib/engine";
  import { isBrowserOnline } from "$lib/stores/connectivity.svelte";
  import type { Tournament, TournamentFormat } from "$lib/types";
  import { getStateBadgeClass, translateTournamentState } from "$lib/tournament-utils";
  import { zonedDate } from "$lib/utils";
  import { syncQueryParams, currentParams, readPageParam, pageParam } from "$lib/url-filters";
  import { Loader2, Trophy, Calendar, Copy, Check } from "@lucide/svelte";
  import Button from '$lib/components/Button.svelte';
  import * as m from '$lib/paraglide/messages.js';

  const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
  // Subscription URLs get pasted into external calendar apps, so they must be
  // absolute — prod builds set VITE_API_URL='' (same-origin), leaving API_BASE empty.
  const CALENDAR_BASE = API_BASE || window.location.origin;

  let tournaments = $state<Tournament[]>([]);
  let totalCount = $state(0);
  let upcomingCount = $state(0);
  let loaded = $state(false);
  let showLoading = $state(false);
  // Delay showing spinner to avoid flash on fast IDB reads
  $effect(() => {
    if (loaded) { showLoading = false; return; }
    const timer = setTimeout(() => { showLoading = true; }, 200);
    return () => clearTimeout(timer);
  });
  let isSyncing = $state(!syncManager.isSynced);
  let showSyncing = $state(false);
  // Delay showing syncing spinner to avoid flash
  $effect(() => {
    if (!isSyncing) { showSyncing = false; return; }
    const timer = setTimeout(() => { showSyncing = true; }, 200);
    return () => clearTimeout(timer);
  });
  let error = $state<string | null>(null);

  // Filters and page live in the query string (see $lib/url-filters): coming
  // back from a tournament remounts this component, so anything held only in
  // local state is lost.
  const urlParams = currentParams();

  // View mode
  const auth = $derived(getAuthState());
  const canUseAgenda = $derived(auth.isAuthenticated && auth.user?.vekn_id && auth.user?.country);
  const urlView = urlParams.get("view");
  let viewMode = $state<"agenda" | "all">(urlView === "agenda" || urlView === "all" ? urlView : "all");

  // Default to the agenda once auth resolves — unless the URL already chose.
  $effect(() => {
    if (canUseAgenda && !urlView) {
      untrack(() => { viewMode = "agenda"; });
    }
  });

  // Filters
  let searchQuery = $state(urlParams.get("q") ?? "");
  // Debounced mirror of searchQuery: the search path scans the whole tournaments
  // table per query, so don't re-query on every keystroke (country/format filters
  // use narrower indexes and stay immediate).
  let debouncedSearch = $state(urlParams.get("q") ?? "");
  $effect(() => {
    const q = searchQuery;
    const timer = setTimeout(() => { debouncedSearch = q; }, 250);
    return () => clearTimeout(timer);
  });
  let ongoing = $state(urlParams.get("ongoing") === "true");
  let selectedCountry = $state<string>(urlParams.get("country") ?? "all");
  let selectedFormat = $state<string>(urlParams.get("format") ?? "all");
  let includeOnline = $state(urlParams.get("online") !== "false");

  // Calendar
  let calendarLoading = $state(false);
  let copied = $state(false);

  // Pagination
  let page = $state(readPageParam());
  const PAGE_SIZE = 50;

  const countries = getCountries();
  const sortedCountries = getSortedCountries();
  const formats: TournamentFormat[] = ["Standard", "V5", "Limited"];

  const totalPages = $derived(Math.ceil(totalCount / PAGE_SIZE));
  const canCreate = $derived(canCreateTournament(auth.user).allowed);

  // League names for display, plus parent meta-league (keyed by league_uid)
  let leagueNames = $state<Record<string, string>>({});
  let metaLeagues = $state<Record<string, { uid: string; name: string }>>({});
  $effect(() => {
    const uids = [...new Set(tournaments.map(t => t.league_uid).filter((u): u is string => !!u))];
    if (!uids.length) { leagueNames = {}; metaLeagues = {}; return; }
    Promise.all(uids.map(u => getLeague(u))).then(async leagues => {
      const map: Record<string, string> = {};
      const parentUids = new Set<string>();
      for (const l of leagues) { if (l) { map[l.uid] = l.name; if (l.parent_uid) parentUids.add(l.parent_uid); } }
      leagueNames = map;
      const parents = await Promise.all([...parentUids].map(p => getLeague(p)));
      const byUid = new Map(parents.filter(p => p && !p.deleted_at).map(p => [p!.uid, p!.name]));
      const mmap: Record<string, { uid: string; name: string }> = {};
      for (const l of leagues) {
        if (l?.parent_uid && byUid.has(l.parent_uid)) mmap[l.uid] = { uid: l.parent_uid, name: byUid.get(l.parent_uid)! };
      }
      metaLeagues = mmap;
    });
  });

  async function loadTournaments() {
    try {
      if (viewMode === "agenda" && canUseAgenda) {
        const user = auth.user!;
        const continentCountries = user.country ? getCountriesOnContinent(user.country) : [];
        const result = await getAgendaTournaments(
          user.uid,
          user.country!,
          continentCountries,
          { ongoing, includeOnline, format: selectedFormat, search: debouncedSearch },
          page,
          PAGE_SIZE,
        );
        tournaments = result.items;
        totalCount = result.total;
        upcomingCount = result.upcomingCount;
      } else {
        const result = await getFilteredTournaments(
          {
            ongoing,
            includeOnline,
            country: selectedCountry,
            format: selectedFormat,
            search: debouncedSearch,
            // Logged-out visitors see current + upcoming only, not past events.
            excludePast: !auth.isAuthenticated,
          },
          page,
          PAGE_SIZE,
        );
        tournaments = result.items;
        totalCount = result.total;
        upcomingCount = result.upcomingCount;
      }
    } catch (e) {
      error = toUserMessage(e, m.tournament_error_load_list());
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
      return zonedDate(t.start, t.timezone || "UTC").toLocaleDateString(undefined, opts);
    } catch {
      return t.start;
    }
  }

  // Re-query when filters or page change
  $effect(() => {
    const _s = debouncedSearch;
    const _o = ongoing;
    const _c = selectedCountry;
    const _f = selectedFormat;
    const _io = includeOnline;
    const _vm = viewMode;
    const _p = page;
    const _a = auth.isAuthenticated;
    untrack(() => loadTournaments());
  });

  const filterKey = $derived(
    [debouncedSearch, ongoing, selectedCountry, selectedFormat, includeOnline, viewMode].join("|"),
  );

  // Reset page when filters change. Comparing against the last key rather than
  // resetting on every run keeps the mount pass from discarding a page number
  // restored from the URL.
  let lastFilterKey = untrack(() => filterKey);
  $effect(() => {
    const key = filterKey;
    untrack(() => {
      if (key === lastFilterKey) return;
      lastFilterKey = key;
      page = 0;
    });
  });

  // A page restored from the URL can point past the end (fewer matches than when
  // the link was made). The list renders empty there, pagination controls and all,
  // so there would be no way back except editing the address bar.
  $effect(() => {
    if (!loaded) return;
    const last = Math.max(0, totalPages - 1);
    if (page > last) untrack(() => { page = last; });
  });

  // Mirror filters + page into the address bar so Back restores this view.
  $effect(() => {
    syncQueryParams({
      q: debouncedSearch,
      ongoing: ongoing ? "true" : null,
      country: selectedCountry === "all" ? null : selectedCountry,
      format: selectedFormat === "all" ? null : selectedFormat,
      online: includeOnline ? null : "false",
      view: canUseAgenda ? viewMode : null,
      page: pageParam(page),
    });
  });

  // SSE sync listener
  $effect(() => {
    const handleSyncEvent = (event: { type: string }) => {
      if (event.type === "syncing") {
        isSyncing = true;
      } else if (event.type === "sync_complete") {
        isSyncing = false;
        loadTournaments();
      } else if (event.type === "error" || event.type === "disconnected") {
        isSyncing = false;
      } else if (event.type === "tournament") {
        loadTournaments();
      }
    };
    syncManager.addEventListener(handleSyncEvent);
    return () => syncManager.removeEventListener(handleSyncEvent);
  });

  // Calendar helpers — the feed URL mirrors the ACTIVE screen filters so the
  // subscriber gets what the screen shows (format was silently dropped before).
  const calendarUrl = $derived.by(() => {
    if (viewMode === "agenda" && auth.user?.calendar_token) {
      const params = new URLSearchParams({ token: auth.user.calendar_token });
      if (!includeOnline) params.set("online", "false");
      return `${CALENDAR_BASE}/api/calendar/tournaments.ics?${params}`;
    }
    const params = new URLSearchParams();
    if (selectedCountry && selectedCountry !== "all") {
      params.set("country", selectedCountry);
    }
    if (selectedFormat && selectedFormat !== "all") {
      params.set("format", selectedFormat);
    }
    if (!includeOnline) {
      params.set("online", "false");
    }
    const qs = params.toString();
    return `${CALENDAR_BASE}/api/calendar/tournaments.ics${qs ? '?' + qs : ''}`;
  });

  // webcal:// opens the OS calendar's subscribe dialog directly.
  const webcalUrl = $derived(calendarUrl.replace(/^https?:\/\//, "webcal://"));

  // Feed-scope summary so the copied URL doesn't read as "everything".
  const calendarScope = $derived.by(() => {
    if (viewMode === "agenda" && auth.user?.calendar_token) {
      return m.tournaments_calendar_scope_agenda();
    }
    const parts: string[] = [];
    parts.push(selectedCountry !== "all" ? (countries[selectedCountry]?.name ?? selectedCountry) : m.rankings_all_countries());
    if (selectedFormat !== "all") parts.push(selectedFormat);
    if (includeOnline) parts.push(m.tournaments_calendar_scope_online());
    return parts.join(" · ");
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
      <h1 class="text-3xl font-semibold text-accent">{m.nav_tournaments()}</h1>

      {#if canCreate}
        <a
          href="/tournaments/new"
          class="px-4 py-2 text-sm font-medium btn-success rounded-lg transition-colors shadow-md"
        >
          {m.tournaments_new_btn()}
        </a>
      {/if}
    </div>

    <!-- View Mode Toggle -->
    {#if canUseAgenda}
      <div class="flex mb-4 bg-surface-card rounded-lg border border-line p-1 w-fit">
        <button
          onclick={() => viewMode = "agenda"}
          class="px-4 py-2 text-sm font-medium rounded-md transition-colors {viewMode === 'agenda' ? 'bg-accent-strong text-white' : 'text-ink-muted hover:text-ink-bright'}"
        >
          {m.tournaments_view_agenda()}
        </button>
        <button
          onclick={() => viewMode = "all"}
          class="px-4 py-2 text-sm font-medium rounded-md transition-colors {viewMode === 'all' ? 'bg-accent-strong text-white' : 'text-ink-muted hover:text-ink-bright'}"
        >
          {m.tournaments_view_all()}
        </button>
      </div>
    {/if}

    <!-- Filters -->
    <div class="bg-surface-card rounded-lg shadow p-4 mb-4 border border-line">
      <div class="flex flex-wrap gap-4 items-end">
        <!-- Search -->
        <div class="flex-1 min-w-[200px]">
          <label for="search" class="block text-sm font-medium text-ink-muted mb-1">{m.common_search()}</label>
          <input
            id="search"
            type="text"
            bind:value={searchQuery}
            placeholder={m.tournaments_search_placeholder()}
            class="w-full px-3 py-2 border border-line-strong rounded-lg bg-surface-card text-ink-bright placeholder:text-ink-faint"
          />
        </div>

        <!-- Format -->
        <div class="min-w-[130px]">
          <label for="format-filter" class="block text-sm font-medium text-ink-muted mb-1">{m.tournaments_format()}</label>
          <select
            id="format-filter"
            bind:value={selectedFormat}
            class="w-full px-3 py-2 border border-line-strong rounded-lg bg-surface-card text-ink-bright"
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
            <label for="country-filter" class="block text-sm font-medium text-ink-muted mb-1">{m.common_country()}</label>
            <select
              id="country-filter"
              bind:value={selectedCountry}
              class="w-full px-3 py-2 border border-line-strong rounded-lg bg-surface-card text-ink-bright"
            >
              <option value="all">{m.tournaments_all_countries()}</option>
              {#each sortedCountries as country}
                <option value={country.iso_code}>{country.name} {getCountryFlag(country.iso_code)}</option>
              {/each}
            </select>
          </div>
        {/if}

        <!-- Ongoing toggle -->
        <div class="flex items-center gap-3 pb-1">
          <label class="inline-flex items-center gap-2 cursor-pointer">
            <input type="checkbox" bind:checked={ongoing} class="sr-only peer" />
            <div class="relative w-11 h-6 bg-surface-active rounded-full peer-checked:bg-accent-strong transition-colors">
              <div class="absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform" class:translate-x-5={ongoing}></div>
            </div>
            <span class="text-sm text-ink">{m.tournaments_ongoing()}</span>
          </label>
        </div>

        <!-- Include online -->
        <div class="flex items-center gap-3 pb-1">
          <label class="inline-flex items-center gap-2 cursor-pointer">
            <input type="checkbox" bind:checked={includeOnline} class="sr-only peer" />
            <div class="relative w-11 h-6 bg-surface-active rounded-full peer-checked:bg-accent-strong transition-colors">
              <div class="absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform" class:translate-x-5={includeOnline}></div>
            </div>
            <span class="text-sm text-ink">{m.tournaments_include_online()}</span>
          </label>
        </div>
      </div>
    </div>

    <!-- Calendar Subscribe — hidden offline: token generation is an API call
         and webcal makes the OS calendar fetch the feed immediately -->
    {#if auth.isAuthenticated && isBrowserOnline()}
      <div class="mb-6 px-1">
        {#if viewMode === "agenda" && !auth.user?.calendar_token}
          <Button variant="primary" size="sm" loading={calendarLoading} onclick={handleGenerateCalendarToken}>
            {m.tournaments_calendar_generate()}
          </Button>
        {:else}
          <!-- The feed URL is never shown: the two actions cover both subscribe
               paths, so the raw .ics link is only a copy target. -->
          <div class="flex items-center gap-2 flex-wrap">
            <a href={webcalUrl}
               class="inline-flex items-center justify-center gap-1 px-2 py-1 text-xs rounded-lg border border-line-strong text-ink hover:bg-surface-hover/50 hover:text-ink-strong transition-colors">
              <Calendar class="h-3 w-3" aria-hidden="true" />
              {m.tournaments_calendar_webcal()}
            </a>
            <Button variant="ghost" size="sm" onclick={() => copyToClipboard(calendarUrl)}>
              {#if copied}
                <Check class="h-3 w-3" aria-hidden="true" />
                {m.tournaments_calendar_copied()}
              {:else}
                <Copy class="h-3 w-3" aria-hidden="true" />
                {m.tournaments_calendar_copy()}
              {/if}
            </Button>
          </div>
          <p class="mt-1.5 text-xs text-ink-faint">
            {m.tournaments_calendar_scope_label({ scope: calendarScope })}
          </p>
        {/if}
      </div>
    {/if}

    <!-- Error -->
    {#if error}
      <div class="bg-accent-soft/20 border border-accent-soft-border rounded-lg p-4 mb-6">
        <p class="text-link-soft">{error}</p>
      </div>
    {/if}

    <!-- Tournament List -->
    {#if tournaments.length > 0}
      <div class="bg-surface-card rounded-lg shadow overflow-hidden border border-line">
        <!-- Header (desktop) -->
        <div class="hidden sm:grid sm:grid-cols-12 gap-4 px-6 py-3 bg-surface-muted text-sm font-medium text-ink border-b border-line-strong">
          <div class="col-span-4">{m.tournaments_col_name()}</div>
          <div class="col-span-2">{m.tournaments_col_date()}</div>
          <div class="col-span-2">{m.tournaments_col_country()}</div>
          <div class="col-span-2">{m.tournaments_col_format()}</div>
          <div class="col-span-2">{m.tournaments_col_state()}</div>
        </div>

        <div class="divide-y divide-line">
          {#each tournaments as tournament, i (tournament.uid)}
            {#if i === upcomingCount - page * PAGE_SIZE}
              <div class="px-6 py-2 bg-surface-muted text-xs font-medium text-ink-faint uppercase tracking-wide">
                {m.tournaments_past_divider()}
              </div>
            {/if}
            <a
              href="/tournaments/{tournament.uid}"
              class="block px-6 py-4 hover:bg-surface-muted/50 transition-colors"
            >
              <!-- Mobile -->
              <div class="sm:hidden space-y-2">
                <div class="flex items-start justify-between">
                  <div>
                    <div class="font-semibold text-ink-strong">{tournament.name}</div>
                    <div class="text-sm text-ink-muted mt-1">
                      {formatDate(tournament)}
                      {#if tournament.country}
                        · {getCountryFlag(tournament.country)} {countries[tournament.country]?.name || tournament.country}
                      {/if}
                    </div>
                  </div>
                  <span class="px-2 py-1 rounded text-xs font-medium {getStateBadgeClass(tournament.state)}">
                    {translateTournamentState(tournament.state)}
                  </span>
                </div>
                <div class="flex gap-2 text-xs text-ink-faint flex-wrap">
                  <span>{tournament.format}</span>
                  {#if tournament.rank}
                    <span>· {tournament.rank}</span>
                  {/if}
                  {#if tournament.online}
                    <span>· {m.tournaments_online()}</span>
                  {/if}
                  {#if tournament.league_uid && leagueNames[tournament.league_uid]}
                    <span class="text-info/70">· {leagueNames[tournament.league_uid]}</span>
                  {/if}
                  {#if tournament.league_uid && metaLeagues[tournament.league_uid]}
                    <span class="text-warn/80" title={m.league_kind_meta()}>· {metaLeagues[tournament.league_uid]?.name}</span>
                  {/if}
                </div>
              </div>

              <!-- Desktop -->
              <div class="hidden sm:grid sm:grid-cols-12 gap-4 items-center">
                <div class="col-span-4">
                  <div class="font-semibold text-ink-strong">{tournament.name}</div>
                  {#if tournament.rank || (tournament.league_uid && leagueNames[tournament.league_uid])}
                    <div class="text-xs text-ink-faint truncate">
                      {#if tournament.rank}{tournament.rank}{/if}{#if tournament.rank && tournament.league_uid && leagueNames[tournament.league_uid]} · {/if}{#if tournament.league_uid && leagueNames[tournament.league_uid]}<span class="text-info/70">{leagueNames[tournament.league_uid]}</span>{/if}{#if tournament.league_uid && metaLeagues[tournament.league_uid]} · <span class="text-warn/80" title={m.league_kind_meta()}>{metaLeagues[tournament.league_uid]?.name}</span>{/if}
                    </div>
                  {/if}
                </div>
                <div class="col-span-2 text-sm text-ink-muted">
                  {formatDate(tournament)}
                </div>
                <div class="col-span-2 text-sm text-ink-muted">
                  {#if tournament.country}
                    {getCountryFlag(tournament.country)} {countries[tournament.country]?.name || tournament.country}
                  {:else if tournament.online}
                    {m.tournaments_online()}
                  {:else}
                    —
                  {/if}
                </div>
                <div class="col-span-2 text-sm text-ink-muted">
                  {tournament.format}
                </div>
                <div class="col-span-2">
                  <span class="px-2 py-1 rounded text-xs font-medium {getStateBadgeClass(tournament.state)}">
                    {translateTournamentState(tournament.state)}
                  </span>
                </div>
              </div>
            </a>
          {/each}
        </div>
      </div>

      <div class="mt-4 flex items-center justify-between text-sm text-ink-muted">
        <span>{m.tournaments_total_count({ count: totalCount.toString() })}</span>
        {#if totalPages > 1}
          <div class="flex items-center gap-2">
            <Button variant="secondary" size="md" disabled={page === 0} onclick={() => page = Math.max(0, page - 1)}>{m.tournaments_prev()}</Button>
            <span>{m.tournaments_page_info({ current: String(page + 1), total: String(totalPages) })}</span>
            <Button variant="secondary" size="md" disabled={page >= totalPages - 1} onclick={() => page = Math.min(totalPages - 1, page + 1)}>{m.common_next()}</Button>
          </div>
        {/if}
      </div>
    {:else if !loaded}
      {#if showLoading}
        <div class="text-center py-12">
          <div class="text-ink-faint mb-4">
            <Loader2 class="mx-auto h-12 w-12 animate-spin" />
          </div>
          <h3 class="text-lg font-medium text-ink-strong mb-2">{m.common_loading()}</h3>
          <p class="text-ink-muted">{m.tournaments_loading_from_storage()}</p>
        </div>
      {/if}
    {:else if showSyncing}
      <div class="text-center py-12">
        <div class="text-ink-faint mb-4">
          <Loader2 class="mx-auto h-12 w-12 animate-spin" />
        </div>
        <h3 class="text-lg font-medium text-ink-strong mb-2">{m.status_syncing()}</h3>
        <p class="text-ink-muted">{m.tournaments_loading_from_storage()}</p>
      </div>
    {:else}
      <div class="text-center py-12">
        <div class="text-ink-faint mb-4">
          <Trophy class="mx-auto h-12 w-12" />
        </div>
        <h3 class="text-lg font-medium text-ink-strong mb-2">{m.tournaments_no_results()}</h3>
        <p class="text-ink-muted">
          {#if searchQuery.trim() || selectedCountry !== "all" || selectedFormat !== "all"}
            {m.tournaments_adjust_filters()}
          {:else if viewMode === "agenda"}
            {m.tournaments_agenda_empty()}
          {:else}
            {m.tournaments_none_yet()}
          {/if}
        </p>
        {#if viewMode === "agenda" && !searchQuery.trim() && selectedFormat === "all"}
          <Button variant="secondary" size="md" class="mt-4" onclick={() => viewMode = "all"}>
            {m.tournaments_agenda_show_all()}
          </Button>
        {/if}
      </div>
    {/if}
  </div>
</div>
