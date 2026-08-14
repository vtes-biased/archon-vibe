<script lang="ts">
  // Single-select user typeahead: IndexedDB search, min 2 chars, keyboard
  // nav, flag + #vekn_id rows. The one search box — organizers, promos, …
  import { onMount } from "svelte";
  import type { User } from "$lib/types";
  import { getFilteredUsers, warmUserIndex } from "$lib/db";
  import { getCountryFlag } from "$lib/geonames";
  import * as m from '$lib/paraglide/messages.js';

  let {
    onselect,
    placeholder = m.user_picker_placeholder(),
    excludeUids = [],
    membersOnly = true,
    inputId,
  }: {
    onselect: (user: User) => void;
    placeholder?: string;
    excludeUids?: string[];
    // Default on: everything a user gets picked FOR here — organizing, holding
    // promo stock — is member-only, so opting out is the deliberate act. The
    // one exception is merging a duplicate account, which is usually the
    // account that never got a VEKN id.
    membersOnly?: boolean;
    inputId?: string;
  } = $props();

  let search = $state("");
  let searchResults = $state<User[]>([]);
  let searchTotal = $state(0);
  let selectedIndex = $state(-1);
  const SEARCH_LIMIT = 8;
  // Keystrokes race: the first one pays for building the member index while
  // later ones resolve straight from it, so without this the earliest (broadest)
  // query can land last and overwrite the results for what was actually typed.
  let searchSeq = 0;

  onMount(() => { warmUserIndex(); });

  async function doSearch() {
    selectedIndex = -1;
    const seq = ++searchSeq;
    if (search.trim().length < 2) {
      searchResults = [];
      searchTotal = 0;
      return;
    }
    const results = await getFilteredUsers(undefined, undefined, search.trim());
    if (seq !== searchSeq) return;
    const excluded = new Set(excludeUids);
    const filtered = results.filter(
      (u) => !excluded.has(u.uid) && (!membersOnly || !!u.vekn_id),
    );
    searchTotal = filtered.length;
    searchResults = filtered.slice(0, SEARCH_LIMIT);
  }

  function handleKeydown(e: KeyboardEvent) {
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
      if (user) pick(user);
    }
  }

  function pick(user: User) {
    search = "";
    searchResults = [];
    searchTotal = 0;
    onselect(user);
  }
</script>

<div class="relative">
  <input
    id={inputId}
    type="text"
    bind:value={search}
    oninput={() => doSearch()}
    onkeydown={handleKeydown}
    {placeholder}
    class="w-full px-3 py-2 min-h-[44px] text-sm bg-surface-card border border-line-strong rounded-lg text-ink-bright focus:ring-2 focus:ring-accent focus:border-transparent"
  />
  {#if searchResults.length > 0}
    <div class="absolute z-10 mt-1 w-full bg-surface-card border border-line-strong rounded-lg divide-y divide-line max-h-48 overflow-y-auto shadow-lg">
      {#each searchResults as user, i (user.uid)}
        <button
          type="button"
          onclick={() => pick(user)}
          class="w-full px-3 py-2 min-h-[44px] text-left text-sm text-ink-bright transition-colors {i === selectedIndex ? 'bg-surface-active' : 'hover:bg-surface-hover'}"
        >
          {#if user.country}
            <span class="mr-1">{getCountryFlag(user.country)}</span>
          {/if}
          {user.name}
          {#if user.vekn_id}
            <span class="text-ink-faint ml-2">#{user.vekn_id}</span>
          {/if}
        </button>
      {/each}
      {#if searchTotal > SEARCH_LIMIT}
        <div class="px-3 py-2 text-xs text-ink-faint text-center">
          {m.add_player_more_results({ count: (searchTotal - SEARCH_LIMIT).toString() })}
        </div>
      {/if}
    </div>
  {:else if search.trim().length >= 2}
    <div class="absolute z-10 mt-1 w-full bg-surface-card border border-line-strong rounded-lg p-3 text-center text-sm text-ink-faint shadow-lg">
      {m.user_picker_no_results()}
    </div>
  {/if}
</div>
