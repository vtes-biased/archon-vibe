<script lang="ts">
  import { getAllUsers, getSuspendedUserUids } from "$lib/db";
  import { syncManager } from "$lib/sync";
  import { getCountries, getCountryFlag } from "$lib/geonames";
  import type { User, RatingCategory } from "$lib/types";
  import { Trophy, Loader2, ChevronLeft, ChevronRight } from "lucide-svelte";
  import * as m from '$lib/paraglide/messages.js';

  let users = $state<User[]>([]);
  let suspendedUids = $state<Set<string>>(new Set());
  let isSyncing = $state(!syncManager.isSynced);

  // Filters
  let selectedCategory = $state<RatingCategory>("constructed_offline");
  let selectedCountry = $state<string>("all");
  let page = $state(0);
  const PAGE_SIZE = 50;

  const categories: { value: RatingCategory; labelFn: () => string }[] = [
    { value: "constructed_offline", labelFn: () => m.rankings_cat_constructed() },
    { value: "constructed_online", labelFn: () => m.rankings_cat_constructed_online() },
    { value: "limited_offline", labelFn: () => m.rankings_cat_limited() },
    { value: "limited_online", labelFn: () => m.rankings_cat_limited_online() },
  ];

  const countries = getCountries();
  const countryList = $derived(
    Object.entries(countries)
      .map(([code, c]) => ({ code, name: c.name }))
      .sort((a, b) => a.name.localeCompare(b.name))
  );

  let filtered = $derived(() => {
    let result = users.filter(u => {
      if (suspendedUids.has(u.uid)) return false;
      const cat = u[selectedCategory];
      return cat && cat.total > 0;
    });

    if (selectedCountry !== "all") {
      result = result.filter(u => u.country === selectedCountry);
    }

    // Sort by total desc
    result.sort((a, b) => {
      const ta = a[selectedCategory]?.total ?? 0;
      const tb = b[selectedCategory]?.total ?? 0;
      return tb - ta;
    });

    return result;
  });

  let totalPages = $derived(Math.ceil(filtered().length / PAGE_SIZE));
  let paged = $derived(filtered().slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE));

  async function loadData() {
    const [allUsers, suspended] = await Promise.all([
      getAllUsers(),
      getSuspendedUserUids(),
    ]);
    users = allUsers;
    suspendedUids = suspended;
  }

  // Reset page on filter change
  $effect(() => {
    selectedCategory;
    selectedCountry;
    page = 0;
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

<div class="max-w-4xl mx-auto p-4 sm:p-8">
  <div class="flex items-center justify-between mb-4">
    <h1 class="text-2xl font-bold text-ash-100">{m.rankings_page_title()}</h1>
    <a href="/halloffame" class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg badge-amber hover:opacity-80 transition-colors text-sm font-medium">
      <Trophy class="w-4 h-4" />
      {m.rankings_hall_of_fame_link()}
    </a>
  </div>

  <!-- Category tabs -->
  <div class="flex gap-1 mb-4 overflow-x-auto">
    {#each categories as cat}
      <button
        class="px-4 py-2 rounded-lg text-sm font-medium whitespace-nowrap transition-colors
          {selectedCategory === cat.value
            ? 'bg-crimson-900/60 text-crimson-300'
            : 'bg-dusk-950 text-ash-400 hover:text-ash-200 hover:bg-ash-800/50'}"
        onclick={() => { selectedCategory = cat.value; }}
      >
        {cat.labelFn()}
      </button>
    {/each}
  </div>

  <!-- Country filter -->
  <div class="mb-4">
    <label for="ranking-country" class="sr-only">{m.common_country()}</label>
    <select
      id="ranking-country"
      bind:value={selectedCountry}
      class="bg-dusk-950 border border-ash-800 rounded-lg px-3 py-2 text-sm text-ash-200 w-full sm:w-64"
    >
      <option value="all">{m.rankings_all_countries()}</option>
      {#each countryList as c}
        <option value={c.code}>{c.name} {getCountryFlag(c.code)}</option>
      {/each}
    </select>
  </div>

  <!-- Table -->
  {#if isSyncing && users.length === 0}
    <div class="text-center text-ash-400 py-8">
      <Loader2 class="w-6 h-6 animate-spin inline-block" />
      <span class="ml-2">{m.rankings_loading()}</span>
    </div>
  {:else if filtered().length === 0}
    <div class="text-center text-ash-500 py-8">{m.rankings_no_results()}</div>
  {:else}
    <div class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead>
          <tr class="border-b border-ash-800 text-ash-400">
            <th class="py-2 px-3 text-left w-12">{m.rankings_col_rank()}</th>
            <th class="py-2 px-3 text-left">{m.rankings_col_player()}</th>
            <th class="py-2 px-3 text-left">{m.common_country()}</th>
            <th class="py-2 px-3 text-right">{m.rankings_col_points()}</th>
          </tr>
        </thead>
        <tbody>
          {#each paged as user, i}
            {@const rank = page * PAGE_SIZE + i + 1}
            {@const total = user[selectedCategory]?.total ?? 0}
            <tr class="border-b border-ash-800/50 hover:bg-ash-800/20">
              <td class="py-2 px-3 text-ash-400">{rank}</td>
              <td class="py-2 px-3">
                <a href="/users/{user.uid}" class="text-ash-100 hover:text-crimson-400">
                  {user.name}
                </a>
              </td>
              <td class="py-2 px-3 text-ash-300">
                {#if user.country}
                  {getCountryFlag(user.country)}
                  {countries[user.country]?.name ?? user.country}
                {/if}
              </td>
              <td class="py-2 px-3 text-right font-medium text-ash-100">{total}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>

    <!-- Pagination -->
    {#if totalPages > 1}
      <div class="flex items-center justify-center gap-2 mt-4">
        <button
          class="px-3 py-1 rounded text-sm {page > 0 ? 'text-ash-200 hover:bg-ash-800/50' : 'text-ash-600 cursor-default'}"
          disabled={page === 0}
          onclick={() => { page = Math.max(0, page - 1); }}
        >
          <ChevronLeft class="w-4 h-4 inline" />
        </button>
        <span class="text-sm text-ash-400">
          {m.rankings_page_info({ current: String(page + 1), total: String(totalPages) })}
        </span>
        <button
          class="px-3 py-1 rounded text-sm {page < totalPages - 1 ? 'text-ash-200 hover:bg-ash-800/50' : 'text-ash-600 cursor-default'}"
          disabled={page >= totalPages - 1}
          onclick={() => { page = Math.min(totalPages - 1, page + 1); }}
        >
          <ChevronRight class="w-4 h-4 inline" />
        </button>
      </div>
    {/if}
  {/if}
</div>
