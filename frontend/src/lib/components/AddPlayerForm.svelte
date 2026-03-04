<script lang="ts">
  import type { User, Tournament } from "$lib/types";
  import { getFilteredUsers, isUserCurrentlySanctioned } from "$lib/db";
  import { getCountryFlag } from "$lib/geonames";
  import { Ban, TriangleAlert } from "lucide-svelte";
  import * as m from '$lib/paraglide/messages.js';

  let {
    tournament,
    onadd,
    oncreate,
  }: {
    tournament: Tournament;
    onadd: (user: User) => void;
    oncreate?: () => void;
  } = $props();

  let playerSearch = $state("");
  let searchResults = $state<User[]>([]);
  let searchTotal = $state(0);
  let selectedIndex = $state(-1);
  let suspendedUids = $state<Set<string>>(new Set());
  const SEARCH_LIMIT = 10;

  async function searchPlayers() {
    selectedIndex = -1;
    if (playerSearch.trim().length < 2) {
      searchResults = [];
      searchTotal = 0;
      suspendedUids = new Set();
      return;
    }
    const results = await getFilteredUsers(undefined, undefined, playerSearch.trim());
    const registeredUids = new Set(tournament?.players?.map(p => p.user_uid) ?? []);
    const filtered = results.filter(u => !registeredUids.has(u.uid));
    searchTotal = filtered.length;
    searchResults = filtered.slice(0, SEARCH_LIMIT);
    // Check suspension status for displayed results
    const suspended = new Set<string>();
    await Promise.all(searchResults.map(async (u) => {
      if (await isUserCurrentlySanctioned(u.uid)) suspended.add(u.uid);
    }));
    suspendedUids = suspended;
  }

  function handleSearchKeydown(e: KeyboardEvent) {
    if (!searchResults.length) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      selectedIndex = Math.min(selectedIndex + 1, searchResults.length - 1);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      selectedIndex = Math.max(selectedIndex - 1, 0);
    } else if (e.key === "Enter" && selectedIndex >= 0) {
      e.preventDefault();
      const user = searchResults[selectedIndex];
      if (user && !suspendedUids.has(user.uid)) selectUser(user);
    }
  }

  function selectUser(user: User) {
    onadd(user);
    playerSearch = "";
    searchResults = [];
    suspendedUids = new Set();
  }
</script>

<div class="relative">
  <input
    id="player-search-input"
    type="text"
    bind:value={playerSearch}
    oninput={() => searchPlayers()}
    onkeydown={handleSearchKeydown}
    placeholder={m.add_player_search_placeholder()}
    autocomplete="off"
    autocorrect="off"
    autocapitalize="off"
    spellcheck="false"
    class="w-full px-3 py-2 text-sm bg-dusk-950 border border-ash-700 rounded-lg text-ash-200 focus:border-ash-500 focus:outline-none"
  />
  {#if searchResults.length > 0 || playerSearch.trim().length >= 2}
    <div class="absolute z-10 mt-1 w-full bg-dusk-950 border border-ash-700 rounded-lg divide-y divide-ash-800 max-h-48 overflow-y-auto shadow-lg">
      {#each searchResults as user, i}
        {@const isSuspended = suspendedUids.has(user.uid)}
        <button
          onclick={() => !isSuspended && selectUser(user)}
          disabled={isSuspended}
          class="w-full px-3 py-2 text-left text-sm transition-colors {isSuspended ? 'text-ash-500 cursor-not-allowed' : 'text-ash-200'} {i === selectedIndex && !isSuspended ? 'bg-ash-700' : isSuspended ? '' : 'hover:bg-ash-800'}"
        >
          <span class="inline-flex items-center gap-1">
            {#if user.country}<span class="mr-1">{getCountryFlag(user.country)}</span>{/if}{user.name}
            {#if user.vekn_id}
              <span class="text-ash-500 ml-2">({user.vekn_id})</span>
            {:else}
              <span class="inline-flex items-center gap-0.5 ml-2 text-xs text-amber-400">
                <TriangleAlert class="w-3 h-3" />
                {m.add_player_no_vekn_id()}
              </span>
            {/if}
            {#if isSuspended}
              <Ban class="w-3.5 h-3.5 text-crimson-400 ml-1" />
              <span class="text-xs text-crimson-400">{m.error_suspended_cannot_register()}</span>
            {/if}
          </span>
        </button>
      {/each}
      {#if searchTotal > SEARCH_LIMIT}
        <div class="px-3 py-2 text-xs text-ash-500 text-center">
          {m.add_player_more_results({ count: (searchTotal - SEARCH_LIMIT).toString() })}
        </div>
      {/if}
      {#if oncreate}
        <button
          onclick={() => oncreate?.()}
          class="w-full px-3 py-2 text-left text-sm text-amber-400 hover:text-amber-300 hover:bg-ash-800 transition-colors {searchResults.length === 0 ? 'font-medium' : ''}"
        >
          {m.add_player_not_on_archon()}
        </button>
      {/if}
    </div>
  {/if}
</div>
