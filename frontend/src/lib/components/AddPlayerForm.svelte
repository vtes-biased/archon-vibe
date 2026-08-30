<script lang="ts">
  import { onMount } from "svelte";
  import type { Tournament } from "$lib/types";
  import type { UserListItem } from "$lib/db";
  import { getFilteredUsers, getRegistrationBarredUids, warmUserIndex } from "$lib/db";
  import { getCountryFlag } from "$lib/geonames";
  import { Ban, TriangleAlert, Flower2, UserCheck } from "@lucide/svelte";
  import * as m from '$lib/paraglide/messages.js';
  import { dialogPanel } from "$lib/actions/dialog";

  let {
    tournament,
    onadd,
    oncreate,
  }: {
    tournament: Tournament;
    onadd: (user: UserListItem) => void;
    oncreate?: () => void;
  } = $props();

  let playerSearch = $state("");
  let searchResults = $state<UserListItem[]>([]);
  let searchTotal = $state(0);
  let selectedIndex = $state(-1);
  let suspendedUids = $state<Set<string>>(new Set());
  let pendingDeceased = $state<UserListItem | null>(null);
  const registeredUids = $derived(new Set(tournament?.players?.map(p => p.user_uid) ?? []));
  const SEARCH_LIMIT = 10;
  const dropdownOpen = $derived(searchResults.length > 0 || playerSearch.trim().length >= 2);
  // See UserPicker: the index build makes early keystrokes slower than later ones,
  // so results can arrive out of order without a sequence guard.
  let searchSeq = 0;

  onMount(() => { warmUserIndex(); });

  async function searchPlayers() {
    selectedIndex = -1;
    const seq = ++searchSeq;
    if (playerSearch.trim().length < 2) {
      searchResults = [];
      searchTotal = 0;
      suspendedUids = new Set();
      return;
    }
    const results = await getFilteredUsers(undefined, undefined, playerSearch.trim());
    if (seq !== searchSeq) return;
    // One scan for the whole page of results, rather than a lookup per row on
    // the path to first paint.
    const barred = await getRegistrationBarredUids();
    if (seq !== searchSeq) return;
    searchTotal = results.length;
    searchResults = results.slice(0, SEARCH_LIMIT);
    suspendedUids = barred;
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
      if (user && !suspendedUids.has(user.uid) && !registeredUids.has(user.uid)) chooseUser(user);
    }
  }

  // Deceased members are warned, not blocked: backfilling a past (finished)
  // event can legitimately add a member who has since passed away.
  function chooseUser(user: UserListItem) {
    if (user.deceased_at) {
      pendingDeceased = user;
      return;
    }
    selectUser(user);
  }

  function confirmDeceased() {
    if (pendingDeceased) selectUser(pendingDeceased);
    pendingDeceased = null;
  }

  function selectUser(user: UserListItem) {
    onadd(user);
    playerSearch = "";
    searchResults = [];
    suspendedUids = new Set();
    pendingDeceased = null;
  }
</script>

<div class="relative flex-1 min-w-0 max-w-md">
  <input
    id="player-search-input"
    type="text"
    role="combobox"
    aria-expanded={dropdownOpen}
    aria-controls="player-search-listbox"
    aria-autocomplete="list"
    aria-activedescendant={selectedIndex >= 0 ? `player-search-option-${selectedIndex}` : undefined}
    bind:value={playerSearch}
    oninput={() => searchPlayers()}
    onkeydown={handleSearchKeydown}
    placeholder={m.add_player_search_placeholder()}
    autocomplete="off"
    autocorrect="off"
    autocapitalize="off"
    spellcheck="false"
    class="w-full px-3 py-2 text-sm bg-surface-card border border-line-strong rounded-lg text-ink-bright focus:border-line-strong focus:outline-none"
  />
  {#if dropdownOpen}
    <div id="player-search-listbox" role="listbox" class="absolute z-10 mt-1 w-full bg-surface-card border border-line-strong rounded-lg divide-y divide-line max-h-48 overflow-y-auto shadow-lg">
      {#each searchResults as user, i}
        {@const isRegistered = registeredUids.has(user.uid)}
        {@const isSuspended = !isRegistered && suspendedUids.has(user.uid)}
        {@const isBlocked = isRegistered || isSuspended}
        <button
          id="player-search-option-{i}"
          role="option"
          aria-selected={i === selectedIndex}
          aria-disabled={isBlocked}
          onclick={() => !isBlocked && chooseUser(user)}
          disabled={isBlocked}
          class="w-full px-3 py-2 text-left text-sm transition-colors {isBlocked ? 'text-ink-faint cursor-not-allowed' : 'text-ink-bright'} {i === selectedIndex && !isBlocked ? 'bg-surface-active' : isBlocked ? '' : 'hover:bg-surface-hover'}"
        >
          <span class="inline-flex items-center gap-1">
            {#if user.country}<span class="mr-1">{getCountryFlag(user.country)}</span>{/if}{user.name}
            {#if user.deceased_at}
              <Flower2 class="w-3.5 h-3.5 text-ink-muted ml-1" />
            {/if}
            {#if user.vekn_id}
              <span class="text-ink-faint ml-2">({user.vekn_id})</span>
            {:else}
              <span class="inline-flex items-center gap-0.5 ml-2 text-xs text-warn">
                <TriangleAlert class="w-3 h-3" />
                {m.add_player_no_vekn_id()}
              </span>
            {/if}
            {#if isRegistered}
              <UserCheck class="w-3.5 h-3.5 text-ink-muted ml-1" />
              <span class="text-xs text-ink-muted">{m.err_tournament_already_registered()}</span>
            {/if}
            {#if isSuspended}
              <Ban class="w-3.5 h-3.5 text-link ml-1" />
              <span class="text-xs text-link">{m.error_suspended_cannot_register()}</span>
            {/if}
          </span>
        </button>
      {/each}
      {#if searchTotal > SEARCH_LIMIT}
        <div class="px-3 py-2 text-xs text-ink-faint text-center">
          {m.add_player_more_results({ count: (searchTotal - SEARCH_LIMIT).toString() })}
        </div>
      {/if}
      {#if oncreate}
        <button
          role="option"
          aria-selected="false"
          onclick={() => oncreate?.()}
          class="w-full px-3 py-2 text-left text-sm text-warn hover:opacity-80 hover:bg-surface-hover transition-colors {searchResults.length === 0 ? 'font-medium' : ''}"
        >
          {m.add_player_not_on_archon()}
        </button>
      {/if}
    </div>
  {/if}
</div>

{#if pendingDeceased}
  <div
    role="presentation"
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
    onclick={(e) => { e.stopPropagation(); if (e.target === e.currentTarget) pendingDeceased = null; }}
  >
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="deceased-warn-title"
      use:dialogPanel={() => pendingDeceased = null}
      class="bg-surface-card rounded-lg shadow-xl border border-line w-full max-w-md mx-4 max-h-[85dvh] overflow-y-auto"
    >
      <div class="p-6 border-b border-line">
        <h2 id="deceased-warn-title" class="text-xl font-medium text-ink-strong inline-flex items-center gap-2">
          <Flower2 class="w-5 h-5 text-ink-muted" aria-hidden="true" />
          {m.deceased_badge()}
        </h2>
      </div>
      <div class="p-6">
        <p class="text-ink mb-4">
          {m.add_player_deceased_warn({ name: pendingDeceased.name })}
        </p>
        <div class="flex gap-2">
          <button
            onclick={confirmDeceased}
            class="flex-1 px-4 py-2 bg-surface-active hover:bg-surface-active text-ink-strong rounded font-medium transition-colors"
          >
            {m.add_player_deceased_confirm()}
          </button>
          <button
            onclick={() => (pendingDeceased = null)}
            class="px-4 py-2 bg-surface-active hover:bg-surface-active text-ink-bright rounded font-medium transition-colors"
          >
            {m.common_cancel()}
          </button>
        </div>
      </div>
    </div>
  </div>
{/if}
