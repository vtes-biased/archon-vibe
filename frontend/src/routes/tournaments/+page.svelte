<script lang="ts">
  import { toUserMessage } from '$lib/errors';
  import { untrack } from "svelte";
  import { getFilteredTournaments, getAgendaTournaments, getLeague, type TournamentListItem, type TournamentStateFilter } from "$lib/db";
  import { syncManager } from "$lib/sync";
  import { getCountries, getSortedCountries, getCountryFlag, getCountriesOnContinent } from "$lib/geonames";
  import { getAuthState, generateCalendarToken } from "$lib/stores/auth.svelte";
  import { canCreateTournament } from "$lib/engine";
  import { isBrowserOnline } from "$lib/stores/connectivity.svelte";
  import type { TournamentFormat, TournamentRank } from "$lib/types";
  import { getStateTone, translateTournamentState, rankBadgeLabel } from "$lib/tournament-utils";
  import Badge from "$lib/components/Badge.svelte";
  import { zonedDate } from "$lib/utils";
  import { syncQueryParams, currentParams, readPageParam, pageParam } from "$lib/url-filters";
  import { Loader2, Trophy, Calendar, Copy, Check, Plus, SlidersHorizontal, X } from "@lucide/svelte";
  import Button from '$lib/components/Button.svelte';
  import * as m from '$lib/paraglide/messages.js';

  const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
  // Subscription URLs get pasted into external calendar apps, so they must be
  // absolute — prod builds set VITE_API_URL='' (same-origin), leaving API_BASE empty.
  const CALENDAR_BASE = API_BASE || window.location.origin;

  let tournaments = $state<TournamentListItem[]>([]);
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

  // Filters and page live in the query string ($lib/url-filters): returning
  // from a tournament remounts this component, discarding anything held only
  // in local state.
  const urlParams = currentParams();

  // Agenda-vs-all is a display preference, not a filter: it outlives the tab
  // via localStorage like the theme, while filters below only get the
  // short-lived nav-menu memory ($lib/last-view).
  const VIEW_PREF_KEY = "archon:tournaments-view";
  const auth = $derived(getAuthState());
  const canUseAgenda = $derived(auth.isAuthenticated && auth.user?.vekn_id && auth.user?.country);
  const urlView = urlParams.get("view");
  const storedView = localStorage.getItem(VIEW_PREF_KEY);
  const initialView = [urlView, storedView].find(v => v === "agenda" || v === "all");
  let viewMode = $state<"agenda" | "all">((initialView as "agenda" | "all") ?? "all");

  // Default to the agenda once auth resolves — unless the URL or a remembered
  // preference already chose.
  $effect(() => {
    if (canUseAgenda && !initialView) {
      untrack(() => { viewMode = "agenda"; });
    }
  });

  // Only remember the choice once the agenda is actually reachable: before auth
  // resolves every viewer reads as "all", which would overwrite a stored agenda.
  $effect(() => {
    if (canUseAgenda) localStorage.setItem(VIEW_PREF_KEY, viewMode);
  });

  let searchQuery = $state(urlParams.get("q") ?? "");
  // Debounced: search normalizes every projected name per query, so don't
  // re-query every keystroke.
  let debouncedSearch = $state(urlParams.get("q") ?? "");
  $effect(() => {
    const q = searchQuery;
    const timer = setTimeout(() => { debouncedSearch = q; }, 250);
    return () => clearTimeout(timer);
  });
  const STATE_FILTERS: TournamentStateFilter[] = ["all", "upcoming", "ongoing", "finished"];
  const urlState = urlParams.get("state");
  let selectedState = $state<TournamentStateFilter>(
    STATE_FILTERS.includes(urlState as TournamentStateFilter) ? (urlState as TournamentStateFilter) : "all",
  );
  let selectedCountry = $state<string>(urlParams.get("country") ?? "all");
  let selectedFormat = $state<string>(urlParams.get("format") ?? "all");
  const RANK_FILTERS: TournamentRank[] = ["National Championship", "Continental Championship"];
  const urlRank = urlParams.get("rank");
  let selectedRank = $state<string>(
    RANK_FILTERS.includes(urlRank as TournamentRank) ? (urlRank as string) : "all",
  );
  let includeOnline = $state(urlParams.get("online") !== "false");

  let calendarLoading = $state(false);
  let copied = $state(false);
  let filtersOpen = $state(false);

  function focusOnMount(node: HTMLElement) {
    node.focus();
  }

  let page = $state(readPageParam());
  const PAGE_SIZE = 50;

  const countries = getCountries();
  const sortedCountries = getSortedCountries();
  const formats: TournamentFormat[] = ["Standard", "V5", "Limited", "Storyline"];
  // Finished is authenticated-only: logged-out viewers are restricted to
  // current + upcoming (excludePast below), so it would always come up empty.
  const stateOptions = $derived<{ value: TournamentStateFilter; label: string }[]>([
    { value: "all", label: m.tournaments_all_states() },
    { value: "upcoming", label: m.tournaments_state_upcoming() },
    { value: "ongoing", label: m.tournaments_ongoing() },
    ...(auth.isAuthenticated ? [{ value: "finished" as const, label: m.state_finished() }] : []),
  ]);

  const totalPages = $derived(Math.ceil(totalCount / PAGE_SIZE));
  const canCreate = $derived(canCreateTournament(auth.user).allowed);

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
          { state: selectedState, includeOnline, format: selectedFormat, rank: selectedRank, search: debouncedSearch },
          page,
          PAGE_SIZE,
        );
        tournaments = result.items;
        totalCount = result.total;
        upcomingCount = result.upcomingCount;
      } else {
        const result = await getFilteredTournaments(
          {
            state: selectedState,
            includeOnline,
            country: selectedCountry,
            format: selectedFormat,
            rank: selectedRank,
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

  function formatDate(t: TournamentListItem): string {
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

  $effect(() => {
    const _s = debouncedSearch;
    const _o = selectedState;
    const _c = selectedCountry;
    const _f = selectedFormat;
    const _r = selectedRank;
    const _io = includeOnline;
    const _vm = viewMode;
    const _p = page;
    const _a = auth.isAuthenticated;
    untrack(() => loadTournaments());
  });

  const filterKey = $derived(
    [debouncedSearch, selectedState, selectedCountry, selectedFormat, selectedRank, includeOnline, viewMode].join("|"),
  );

  // The badge counts what the sheet holds: search sits outside it, and the
  // country select is absent in agenda mode.
  const activeFilterCount = $derived(
    (selectedState !== "all" ? 1 : 0)
      + (viewMode !== "agenda" && selectedCountry !== "all" ? 1 : 0)
      + (selectedFormat !== "all" ? 1 : 0)
      + (selectedRank !== "all" ? 1 : 0)
      + (includeOnline ? 0 : 1),
  );

  // includeOnline counts: it hides data like any other filter, so an empty list
  // under it must read as filtered, not as "no tournaments yet".
  const hasFilters = $derived(
    !!searchQuery.trim() || selectedState !== "all" || selectedCountry !== "all"
      || selectedFormat !== "all" || selectedRank !== "all" || !includeOnline,
  );

  function clearFilters() {
    searchQuery = "";
    selectedState = "all";
    selectedCountry = "all";
    selectedFormat = "all";
    selectedRank = "all";
    includeOnline = true;
  }

  // Reset page on filter change; comparing against the last key (not resetting
  // every run) keeps the mount pass from discarding a page number restored
  // from the URL.
  let lastFilterKey = untrack(() => filterKey);
  $effect(() => {
    const key = filterKey;
    untrack(() => {
      if (key === lastFilterKey) return;
      lastFilterKey = key;
      page = 0;
    });
  });

  // A page restored from the URL can point past the end (fewer matches now);
  // clamp once loaded, or the list renders empty with no way back but the
  // address bar.
  $effect(() => {
    if (!loaded) return;
    const last = Math.max(0, totalPages - 1);
    if (page > last) untrack(() => { page = last; });
  });

  $effect(() => {
    syncQueryParams({
      q: debouncedSearch,
      state: selectedState === "all" ? null : selectedState,
      country: selectedCountry === "all" ? null : selectedCountry,
      format: selectedFormat === "all" ? null : selectedFormat,
      rank: selectedRank === "all" ? null : selectedRank,
      online: includeOnline ? null : "false",
      view: canUseAgenda ? viewMode : null,
      page: pageParam(page),
    });
  });

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

  // The feed URL mirrors the active screen filters, so the subscriber gets
  // what the screen shows.
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
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-3xl font-semibold text-accent">{m.nav_tournaments()}</h1>

      {#if canCreate}
        <Button variant="create" size="lg" href="/tournaments/new">
          <Plus class="w-4 h-4" aria-hidden="true" />
          {m.tournaments_new_btn()}
        </Button>
      {/if}
    </div>

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

    <div class="flex items-center gap-2 mb-4">
      <input
        id="search"
        type="text"
        bind:value={searchQuery}
        aria-label={m.common_search()}
        placeholder={m.tournaments_search_placeholder()}
        class="flex-1 min-w-0 px-3 py-2 border border-line-strong rounded-lg bg-surface-card text-ink-bright placeholder:text-ink-faint"
      />
      <Button
        variant="ghost"
        size="lg"
        onclick={() => (filtersOpen = true)}
        aria-label={activeFilterCount > 0
          ? m.filters_active_count({ count: String(activeFilterCount) })
          : m.filters_title()}
      >
        <SlidersHorizontal class="w-4 h-4" aria-hidden="true" />
        {m.filters_title()}
        {#if activeFilterCount > 0}
          <span class="rounded-full bg-accent-strong px-1.5 text-xs text-white" aria-hidden="true">{activeFilterCount}</span>
        {/if}
      </Button>
    </div>

    <!-- Hidden offline: token generation is an API call, and webcal makes the
         OS calendar fetch the feed immediately. -->
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

    {#if error}
      <div class="bg-accent-soft/20 border border-accent-soft-border rounded-lg p-4 mb-6">
        <p class="text-link-soft">{error}</p>
      </div>
    {/if}

    {#if tournaments.length > 0}
      <div class="bg-surface-card rounded-lg shadow overflow-hidden border border-line">
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
                  <Badge kind="status" tone={getStateTone(tournament.state)}>
                    {translateTournamentState(tournament.state)}
                  </Badge>
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
                  <Badge kind="status" tone={getStateTone(tournament.state)}>
                    {translateTournamentState(tournament.state)}
                  </Badge>
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
          {#if hasFilters}
            {m.tournaments_adjust_filters()}
          {:else if viewMode === "agenda"}
            {m.tournaments_agenda_empty()}
          {:else}
            {m.tournaments_none_yet()}
          {/if}
        </p>
        <!-- A view restored by the nav menu can come up empty on filters the
             viewer didn't just set, so clearing them is one click, not a hunt. -->
        {#if hasFilters}
          <Button variant="secondary" size="md" class="mt-4" onclick={clearFilters}>
            {m.filters_clear()}
          </Button>
        {/if}
        {#if viewMode === "agenda" && !searchQuery.trim() && selectedFormat === "all"}
          <Button variant="secondary" size="md" class="mt-4" onclick={() => viewMode = "all"}>
            {m.tournaments_agenda_show_all()}
          </Button>
        {/if}
      </div>
    {/if}
  </div>
</div>

{#if filtersOpen}
  <div class="fixed inset-0 z-50 flex items-end sm:items-center justify-center">
    <button type="button" class="absolute inset-0 bg-black/50 backdrop-blur-sm" aria-label={m.common_close()} onclick={() => (filtersOpen = false)}></button>

    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="filters-title"
      tabindex="-1"
      use:focusOnMount
      onkeydown={(e) => { if (e.key === "Escape") filtersOpen = false; }}
      class="relative flex max-h-[85dvh] w-full flex-col overflow-hidden rounded-t-2xl border border-line bg-surface-card shadow-xl pb-safe-b sm:pb-0 sm:max-w-md sm:rounded-2xl"
    >
      <div class="flex items-center justify-between border-b border-line px-4 py-3">
        <h2 id="filters-title" class="text-sm font-semibold text-ink-strong">{m.filters_title()}</h2>
        <button type="button" onclick={() => (filtersOpen = false)} aria-label={m.common_close()} class="rounded-lg p-1.5 text-ink-muted hover:bg-surface-hover hover:text-ink-bright">
          <X class="w-5 h-5" aria-hidden="true" />
        </button>
      </div>

      <div class="min-h-0 flex-1 overflow-y-auto p-4 space-y-4">
        <div>
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

        <div>
          <label for="rank-filter" class="block text-sm font-medium text-ink-muted mb-1">{m.tfield_rank()}</label>
          <select
            id="rank-filter"
            bind:value={selectedRank}
            class="w-full px-3 py-2 border border-line-strong rounded-lg bg-surface-card text-ink-bright"
          >
            <option value="all">{m.tournaments_all_ranks()}</option>
            {#each RANK_FILTERS as r}
              <option value={r}>{rankBadgeLabel(r)}</option>
            {/each}
          </select>
        </div>

        {#if viewMode !== "agenda"}
          <div>
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

        <div>
          <label for="state-filter" class="block text-sm font-medium text-ink-muted mb-1">{m.tournaments_col_state()}</label>
          <select
            id="state-filter"
            bind:value={selectedState}
            class="w-full px-3 py-2 border border-line-strong rounded-lg bg-surface-card text-ink-bright"
          >
            {#each stateOptions as option}
              <option value={option.value}>{option.label}</option>
            {/each}
          </select>
        </div>

        <label class="inline-flex items-center gap-2 cursor-pointer">
          <input type="checkbox" bind:checked={includeOnline} class="sr-only peer" />
          <div class="relative w-11 h-6 bg-surface-active rounded-full peer-checked:bg-accent-strong transition-colors">
            <div class="absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform" class:translate-x-5={includeOnline}></div>
          </div>
          <span class="text-sm text-ink">{m.tournaments_include_online()}</span>
        </label>
      </div>

      <div class="flex items-center justify-between gap-2 border-t border-line px-4 py-3">
        <Button variant="ghost" size="md" disabled={!hasFilters} onclick={clearFilters}>
          {m.filters_clear()}
        </Button>
        <Button variant="primary" size="md" onclick={() => (filtersOpen = false)}>
          {m.common_close()}
        </Button>
      </div>
    </div>
  </div>
{/if}
