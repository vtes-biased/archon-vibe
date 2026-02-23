<script lang="ts">
  import { getAllUsers, getSanctionsForUser } from "$lib/db";
  import { syncManager } from "$lib/sync";
  import { getCountries, getCountryFlag } from "$lib/geonames";
  import type { User, Sanction } from "$lib/types";
  import { ArrowLeft, Loader2, Trophy, ChevronLeft, ChevronRight } from "lucide-svelte";
  import * as m from '$lib/paraglide/messages.js';

  let users = $state<User[]>([]);
  let excludedUids = $state<Set<string>>(new Set());
  let isSyncing = $state(!syncManager.isSynced);

  let selectedCountry = $state<string>("all");
  let page = $state(0);
  const PAGE_SIZE = 100;

  const countries = getCountries();
  const countryList = $derived(
    Object.entries(countries)
      .map(([code, c]) => ({ code, name: c.name }))
      .sort((a, b) => a.name.localeCompare(b.name))
  );

  function isActiveSanction(s: Sanction): boolean {
    if (s.deleted_at || s.lifted_at) return false;
    if (s.level !== 'suspension' && s.level !== 'probation') return false;
    if (s.expires_at && new Date(s.expires_at) < new Date()) return false;
    return true;
  }

  let filtered = $derived(() => {
    let result = users.filter(u => {
      if ((u.wins?.length ?? 0) < 5) return false;
      if (excludedUids.has(u.uid)) return false;
      if (selectedCountry !== "all" && u.country !== selectedCountry) return false;
      return true;
    });
    result.sort((a, b) => (b.wins?.length ?? 0) - (a.wins?.length ?? 0));
    return result;
  });

  let totalPages = $derived(Math.ceil(filtered().length / PAGE_SIZE));
  let paged = $derived(filtered().slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE));

  async function loadData() {
    const allUsers = await getAllUsers();
    // Only keep users with 5+ wins for sanction checking
    users = allUsers;

    const excluded = new Set<string>();
    for (const u of allUsers) {
      if ((u.wins?.length ?? 0) < 5) continue;
      const sanctions = await getSanctionsForUser(u.uid);
      if (sanctions.some(isActiveSanction)) {
        excluded.add(u.uid);
      }
    }
    excludedUids = excluded;
  }

  $effect(() => {
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
  <title>{m.hof_page_title()} - Archon</title>
</svelte:head>

<div class="max-w-4xl mx-auto p-4 sm:p-8">
  <div class="flex items-center justify-between mb-4">
    <h1 class="text-2xl font-bold text-ash-100">{m.hof_page_title()}</h1>
    <a href="/rankings" class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-dusk-950 text-ash-300 hover:text-ash-100 hover:bg-ash-800/50 transition-colors text-sm font-medium border border-ash-800">
      <ArrowLeft class="w-4 h-4" />
      {m.hof_back_to_rankings()}
    </a>
  </div>
  <p class="text-ash-400 text-sm mb-6">{m.hof_description()}</p>

  <!-- Country filter -->
  <div class="mb-4">
    <label for="hof-country" class="sr-only">{m.common_country()}</label>
    <select
      id="hof-country"
      bind:value={selectedCountry}
      class="bg-dusk-950 border border-ash-800 rounded-lg px-3 py-2 text-sm text-ash-200 w-full sm:w-64"
    >
      <option value="all">{m.hof_all_countries()}</option>
      {#each countryList as c}
        <option value={c.code}>{c.name} {getCountryFlag(c.code)}</option>
      {/each}
    </select>
  </div>

  {#if isSyncing && users.length === 0}
    <div class="text-center text-ash-400 py-8">
      <Loader2 class="w-6 h-6 animate-spin inline-block" />
      <span class="ml-2">{m.hof_loading()}</span>
    </div>
  {:else if filtered().length === 0}
    <div class="text-center text-ash-500 py-8">{m.hof_no_results()}</div>
  {:else}
    <div class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead>
          <tr class="border-b border-ash-800 text-ash-400">
            <th class="py-2 px-3 text-left w-12">{m.rankings_col_rank()}</th>
            <th class="py-2 px-3 text-left">{m.rankings_col_player()}</th>
            <th class="py-2 px-3 text-left">{m.common_country()}</th>
            <th class="py-2 px-3 text-right">{m.hof_col_wins()}</th>
          </tr>
        </thead>
        <tbody>
          {#each paged as user, i}
            {@const rank = page * PAGE_SIZE + i + 1}
            {@const winsCount = user.wins?.length ?? 0}
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
              <td class="py-2 px-3 text-right font-medium text-ash-100">
                <Trophy class="w-4 h-4 inline mr-1 text-amber-400" />
                {winsCount}
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
