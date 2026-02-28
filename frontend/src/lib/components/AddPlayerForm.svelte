<script lang="ts">
  import type { User, Tournament } from "$lib/types";
  import { getFilteredUsers } from "$lib/db";
  import { getCountryFlag } from "$lib/geonames";
  import * as m from '$lib/paraglide/messages.js';

  let {
    tournament,
    onadd,
  }: {
    tournament: Tournament;
    onadd: (user: User) => void;
  } = $props();

  let playerSearch = $state("");
  let searchResults = $state<User[]>([]);
  let searchTotal = $state(0);
  let selectedIndex = $state(-1);
  const SEARCH_LIMIT = 10;

  async function searchPlayers() {
    selectedIndex = -1;
    if (playerSearch.trim().length < 2) {
      searchResults = [];
      searchTotal = 0;
      return;
    }
    const results = await getFilteredUsers(undefined, undefined, playerSearch.trim());
    const registeredUids = new Set(tournament?.players?.map(p => p.user_uid) ?? []);
    const filtered = results.filter(u => !registeredUids.has(u.uid));
    searchTotal = filtered.length;
    searchResults = filtered.slice(0, SEARCH_LIMIT);
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
      if (user) selectUser(user);
    }
  }

  function selectUser(user: User) {
    onadd(user);
    playerSearch = "";
    searchResults = [];
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
  {#if searchResults.length > 0}
    <div class="absolute z-10 mt-1 w-full bg-dusk-950 border border-ash-700 rounded-lg divide-y divide-ash-800 max-h-48 overflow-y-auto shadow-lg">
      {#each searchResults as user, i}
        <button
          onclick={() => selectUser(user)}
          class="w-full px-3 py-2 text-left text-sm text-ash-200 transition-colors {i === selectedIndex ? 'bg-ash-700' : 'hover:bg-ash-800'}"
        >
          {#if user.country}<span class="mr-1">{getCountryFlag(user.country)}</span>{/if}{user.name}
          {#if user.vekn_id}
            <span class="text-ash-500 ml-2">({user.vekn_id})</span>
          {/if}
        </button>
      {/each}
      {#if searchTotal > SEARCH_LIMIT}
        <div class="px-3 py-2 text-xs text-ash-500 text-center">
          {m.add_player_more_results({ count: (searchTotal - SEARCH_LIMIT).toString() })}
        </div>
      {/if}
    </div>
  {/if}
</div>
