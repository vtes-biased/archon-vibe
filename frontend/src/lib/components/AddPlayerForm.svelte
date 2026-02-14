<script lang="ts">
  import type { User, Tournament } from "$lib/types";
  import { getFilteredUsers, getUserByVeknId } from "$lib/db";
  import * as m from '$lib/paraglide/messages.js';

  let {
    tournament,
    onadd,
    onaddvekn,
  }: {
    tournament: Tournament;
    onadd: (user: User) => void;
    onaddvekn: (veknId: string) => void;
  } = $props();

  let playerSearch = $state("");
  let playerVeknId = $state("");
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
    const registeredUids = new Set(tournament?.players.map(p => p.user_uid) ?? []);
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

<div class="bg-ash-900/50 rounded-lg p-4 space-y-3">
  <div>
    <label class="block text-sm text-ash-400 mb-1" for="player-search-input">{m.add_player_search_label()}</label>
    <input
      id="player-search-input"
      type="text"
      bind:value={playerSearch}
      oninput={() => searchPlayers()}
      onkeydown={handleSearchKeydown}
      placeholder={m.add_player_search_placeholder()}
      class="w-full px-3 py-2 text-sm bg-dusk-950 border border-ash-700 rounded-lg text-ash-200 focus:border-ash-500 focus:outline-none"
    />
    {#if searchResults.length > 0}
      <div class="mt-1 bg-dusk-950 border border-ash-700 rounded-lg divide-y divide-ash-800 max-h-48 overflow-y-auto">
        {#each searchResults as user, i}
          <button
            onclick={() => selectUser(user)}
            class="w-full px-3 py-2 text-left text-sm text-ash-200 transition-colors {i === selectedIndex ? 'bg-ash-700' : 'hover:bg-ash-800'}"
          >
            {user.name}
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
  <div class="text-center text-ash-500 text-sm">{m.add_player_or_separator()}</div>
  <div>
    <label class="block text-sm text-ash-400 mb-1" for="vekn-id-input">{m.add_player_vekn_id_label()}</label>
    <div class="flex gap-2">
      <input
        id="vekn-id-input"
        type="text"
        bind:value={playerVeknId}
        placeholder="1234567"
        class="flex-1 px-3 py-2 text-sm bg-dusk-950 border border-ash-700 rounded-lg text-ash-200 focus:border-ash-500 focus:outline-none"
      />
      <button
        onclick={() => { onaddvekn(playerVeknId.trim()); playerVeknId = ""; }}
        disabled={!playerVeknId.trim()}
        class="px-4 py-2 text-sm font-medium text-bone-100 bg-emerald-700 hover:bg-emerald-600 disabled:bg-ash-700 rounded-lg transition-colors"
      >
        {m.common_add()}
      </button>
    </div>
  </div>
</div>
