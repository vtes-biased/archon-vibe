<script lang="ts">
  import { getAllUsers, getSuspendedUserUids } from "$lib/db";
  import { getAuthState } from "$lib/stores/auth.svelte";
  import { syncManager } from "$lib/sync";
  import { getCountries, getSortedCountries, getCountryFlag } from "$lib/geonames";
  import DeceasedIcon from "$lib/components/DeceasedIcon.svelte";
  import Button from "$lib/components/Button.svelte";
  import type { User, RatingCategory } from "$lib/types";
  import { Trophy, Loader2, ChevronLeft, ChevronRight } from "@lucide/svelte";
  import { goto } from "$app/navigation";
  import { untrack } from "svelte";
  import { syncQueryParams, currentParams, readPageParam, pageParam } from "$lib/url-filters";
  import * as m from '$lib/paraglide/messages.js';

  type Tab = RatingCategory | "halloffame";
  const TAB_VALUES: Tab[] = ["constructed_offline", "constructed_online", "limited_offline", "limited_online", "halloffame"];

  // Single exclusion policy: straight suspensions are hidden from every tab; probations stay visible.
  let users = $state<User[]>([]);
  let suspendedUids = $state<Set<string>>(new Set());
  let isSyncing = $state(!syncManager.isSynced);

  // Filters. Tab is deep-linkable (?tab=halloffame — the guide and the profile
  // HoF chip land there); country and page ride along so Back restores the view.
  const urlParams = currentParams();
  const urlTab = urlParams.get("tab") as Tab | null;
  let activeTab = $state<Tab>(urlTab && TAB_VALUES.includes(urlTab) ? urlTab : "constructed_offline");
  let selectedCountry = $state<string>(urlParams.get("country") ?? "all");
  let page = $state(readPageParam());

  // Ratings and wins are member-level, so every tab is necessarily empty when
  // signed out — "no results" would read as "the Hall of Fame is empty".
  const auth = $derived(getAuthState());

  const isHof = $derived(activeTab === "halloffame");
  const pageSize = $derived(isHof ? 100 : 50);

  const tabs: { value: Tab; labelFn: () => string; captionFn: () => string }[] = [
    { value: "constructed_offline", labelFn: () => m.rankings_cat_constructed(), captionFn: () => m.rankings_cat_constructed_desc() },
    { value: "constructed_online", labelFn: () => m.rankings_cat_constructed_online(), captionFn: () => m.rankings_cat_constructed_online_desc() },
    { value: "limited_offline", labelFn: () => m.rankings_cat_limited(), captionFn: () => m.rankings_cat_limited_desc() },
    { value: "limited_online", labelFn: () => m.rankings_cat_limited_online(), captionFn: () => m.rankings_cat_limited_online_desc() },
    { value: "halloffame", labelFn: () => m.hof_page_title(), captionFn: () => m.hof_description() },
  ];

  const countries = getCountries();
  const countryList = getSortedCountries();

  let filtered = $derived.by(() => {
    if (isHof) {
      let result = users.filter(u => {
        if ((u.wins?.length ?? 0) < 5) return false;
        if (suspendedUids.has(u.uid)) return false;
        if (selectedCountry !== "all" && u.country !== selectedCountry) return false;
        return true;
      });
      result.sort((a, b) => (b.wins?.length ?? 0) - (a.wins?.length ?? 0));
      return result;
    }

    const cat = activeTab as RatingCategory;
    let result = users.filter(u => {
      if (suspendedUids.has(u.uid)) return false;
      const c = u[cat];
      return c && c.total > 0;
    });
    if (selectedCountry !== "all") {
      result = result.filter(u => u.country === selectedCountry);
    }
    result.sort((a, b) => (b[cat]?.total ?? 0) - (a[cat]?.total ?? 0));
    return result;
  });

  let totalPages = $derived(Math.ceil(filtered.length / pageSize));
  let paged = $derived(filtered.slice(page * pageSize, (page + 1) * pageSize));

  async function loadData() {
    const [allUsers, suspended] = await Promise.all([
      getAllUsers(),
      getSuspendedUserUids(),
    ]);
    users = allUsers;
    suspendedUids = suspended;
  }

  // Reset page on tab/filter change — but not on the mount pass, which would
  // discard a page number restored from the URL.
  const filterKey = $derived(`${activeTab}|${selectedCountry}`);
  let lastFilterKey = untrack(() => filterKey);
  $effect(() => {
    const key = filterKey;
    untrack(() => {
      if (key === lastFilterKey) return;
      lastFilterKey = key;
      page = 0;
    });
  });

  // A page restored from the URL can point past the end — clamp once the data
  // is in, or the list renders empty with no controls to get back.
  $effect(() => {
    if (!users.length) return;
    const last = Math.max(0, totalPages - 1);
    if (page > last) untrack(() => { page = last; });
  });

  // Mirror filters + page into the address bar so Back restores this view.
  $effect(() => {
    syncQueryParams({
      tab: activeTab === "constructed_offline" ? null : activeTab,
      country: selectedCountry === "all" ? null : selectedCountry,
      page: pageParam(page),
    });
  });

  $effect(() => {
    loadData();

    const handleSyncEvent = (event: { type: string }) => {
      if (event.type === "user" || event.type === "sanction" || event.type === "sync_complete") {
        loadData();
        if (event.type === "sync_complete") isSyncing = false;
      }
    };

    syncManager.addEventListener(handleSyncEvent);
    return () => syncManager.removeEventListener(handleSyncEvent);
  });
</script>

<svelte:head>
  <title>{m.rankings_page_title()} - Archon</title>
</svelte:head>

<div class="p-4 sm:p-8">
  <div class="max-w-6xl mx-auto">
    <h1 class="text-3xl font-semibold text-accent mb-6">{m.rankings_page_title()}</h1>

    <!-- Tabs: rating categories + Hall of Fame -->
    <div class="flex flex-wrap gap-y-1 mb-6 bg-surface-card rounded-lg border border-line p-1 w-fit max-w-full">
      {#each tabs as tab}
        <button
          onclick={() => { activeTab = tab.value; }}
          class="px-4 py-2 text-sm font-medium rounded-md whitespace-nowrap transition-colors {activeTab === tab.value ? 'bg-accent-strong text-white' : 'text-ink-muted hover:text-ink-bright'}"
        >
          {tab.labelFn()}
        </button>
      {/each}
    </div>

    <!-- One-line caption per tab: what the Points column means on this ranking -->
    <p class="text-ink-muted text-sm mb-6">{tabs.find(t => t.value === activeTab)?.captionFn()}</p>

    <!-- Country filter -->
    <div class="mb-4">
      <label for="ranking-country" class="sr-only">{m.common_country()}</label>
      <select
        id="ranking-country"
        bind:value={selectedCountry}
        class="bg-surface-card border border-line rounded-lg px-3 py-2 text-sm text-ink-bright w-full sm:w-64"
      >
        <option value="all">{m.rankings_all_countries()}</option>
        {#each countryList as c}
          <option value={c.iso_code}>{c.name} {getCountryFlag(c.iso_code)}</option>
        {/each}
      </select>
    </div>

    <!-- Table -->
    {#if !auth.isLoading && !auth.isAuthenticated}
      <div class="p-4 rounded-lg bg-surface-muted border border-line-strong text-sm text-ink">
        {m.rankings_login_prompt()}
        <a href="/login" class="underline text-link hover:text-link-soft ml-1">{m.community_sign_in()}</a>
      </div>
    {:else if isSyncing && users.length === 0}
      <div class="text-center text-ink-muted py-8">
        <Loader2 class="w-6 h-6 animate-spin inline-block" />
        <span class="ml-2">{isHof ? m.hof_loading() : m.rankings_loading()}</span>
      </div>
    {:else if filtered.length === 0}
      <div class="text-center text-ink-faint py-8">
        {isHof ? m.hof_no_results() : m.rankings_no_results()}
        <!-- The country filter can come back with the view the nav menu restored,
             so an empty table needs a visible way out of it. -->
        {#if selectedCountry !== "all"}
          <div>
            <Button variant="secondary" size="md" class="mt-4" onclick={() => selectedCountry = "all"}>
              {m.filters_clear()}
            </Button>
          </div>
        {/if}
      </div>
    {:else}
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b border-line text-ink-muted">
              <th class="py-2 px-3 text-left w-12">{m.rankings_col_rank()}</th>
              <th class="py-2 px-3 text-left">{m.rankings_col_player()}</th>
              <!-- Flag-only on phones (DESIGN.md mobile reflow rule) — the name column
                   is what pushes ~360px viewports into side-scroll. -->
              <th class="py-2 px-3 text-left"><span class="sr-only sm:not-sr-only">{m.common_country()}</span></th>
              <th class="py-2 px-3 text-right">{isHof ? m.hof_col_wins() : m.rankings_col_points()}</th>
            </tr>
          </thead>
          <tbody>
            {#each paged as user, i}
              {@const rank = page * pageSize + i + 1}
              {@const value = isHof ? (user.wins?.length ?? 0) : (user[activeTab as RatingCategory]?.total ?? 0)}
              <!-- Whole row navigates; the name <a> keeps keyboard focus + cmd-click new-tab,
                   so the row onclick is a mouse-only enhancement (skips clicks on the link). -->
              <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_noninteractive_element_interactions -->
              <tr class="border-b border-line/50 hover:bg-surface-hover/20 cursor-pointer"
                  onclick={(e) => { if (!(e.target as HTMLElement).closest('a')) goto(`/users/${user.uid}`); }}>
                <td class="py-2 px-3 text-ink-muted">{rank}</td>
                <td class="py-2 px-3">
                  <a href="/users/{user.uid}" class="text-ink-strong hover:text-link">
                    <DeceasedIcon deceased={user.deceased_at} />{user.name}
                  </a>
                </td>
                <td class="py-2 px-3 text-ink">
                  {#if user.country}
                    <span title={countries[user.country]?.name ?? user.country}>{getCountryFlag(user.country)}</span>
                    <span class="hidden sm:inline">{countries[user.country]?.name ?? user.country}</span>
                  {/if}
                </td>
                <td class="py-2 px-3 text-right font-medium text-ink-strong">
                  {#if isHof}
                    <Trophy class="w-4 h-4 inline mr-1 text-highlight" />
                  {/if}
                  {value}
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>

      <!-- Pagination -->
      {#if totalPages > 1}
        <div class="flex items-center justify-center gap-2 mt-4">
          <button
            class="px-3 py-1 rounded text-sm {page > 0 ? 'text-ink-bright hover:bg-surface-hover/50' : 'text-ink-faint'}"
            disabled={page === 0}
            onclick={() => { page = Math.max(0, page - 1); }}
          >
            <ChevronLeft class="w-4 h-4 inline" />
          </button>
          <span class="text-sm text-ink-muted">
            {m.rankings_page_info({ current: String(page + 1), total: String(totalPages) })}
          </span>
          <button
            class="px-3 py-1 rounded text-sm {page < totalPages - 1 ? 'text-ink-bright hover:bg-surface-hover/50' : 'text-ink-faint'}"
            disabled={page >= totalPages - 1}
            onclick={() => { page = Math.min(totalPages - 1, page + 1); }}
          >
            <ChevronRight class="w-4 h-4 inline" />
          </button>
        </div>
      {/if}
    {/if}
  </div>
</div>
