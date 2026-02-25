<script lang="ts">
  import type { User } from "$lib/types";
  import { getFilteredUsers, getUser } from "$lib/db";
  import { getCountryFlag } from "$lib/geonames";
  import { showToast } from "$lib/stores/toast.svelte";
  import { X } from "lucide-svelte";
  import * as m from '$lib/paraglide/messages.js';

  let {
    organizerUids,
    onadd,
    onremove,
  }: {
    organizerUids: string[];
    onadd: (userUid: string) => Promise<void>;
    onremove: (userUid: string) => Promise<void>;
  } = $props();

  let organizers = $state<Record<string, User | null>>({});
  let search = $state("");
  let searchResults = $state<User[]>([]);
  let searchTotal = $state(0);
  let loading = $state(false);
  let selectedIndex = $state(-1);
  const SEARCH_LIMIT = 8;

  // Load organizer details
  async function loadOrganizers() {
    const result: Record<string, User | null> = {};
    for (const uid of organizerUids) {
      result[uid] = (await getUser(uid)) ?? null;
    }
    organizers = result;
  }

  $effect(() => {
    const _uids = organizerUids;
    loadOrganizers();
  });

  async function doSearch() {
    selectedIndex = -1;
    if (search.trim().length < 2) {
      searchResults = [];
      searchTotal = 0;
      return;
    }
    const results = await getFilteredUsers(undefined, undefined, search.trim());
    const existing = new Set(organizerUids);
    const filtered = results.filter(u => !existing.has(u.uid));
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
      if (user) handleAdd(user);
    }
  }

  async function handleAdd(user: User) {
    loading = true;
    try {
      await onadd(user.uid);
      search = "";
      searchResults = [];
      showToast({ type: "success", message: m.organizers_added() });
    } catch {
      // Error already shown by apiRequest
    } finally {
      loading = false;
    }
  }

  async function handleRemove(uid: string) {
    if (organizerUids.length <= 1) {
      showToast({ type: "error", message: m.organizers_last_warning() });
      return;
    }
    const name = organizers[uid]?.name || uid.slice(0, 8);
    if (!confirm(m.organizers_remove_confirm({ name }))) return;
    loading = true;
    try {
      await onremove(uid);
      showToast({ type: "success", message: m.organizers_removed() });
    } catch {
      // Error already shown by apiRequest
    } finally {
      loading = false;
    }
  }
</script>

<div class="space-y-3">
  <!-- Current organizers -->
  <div class="flex flex-wrap gap-2">
    {#each organizerUids as uid (uid)}
      {@const user = organizers[uid]}
      <span class="inline-flex items-center gap-1.5 px-3 py-1.5 bg-ash-800 rounded-lg text-sm text-bone-100">
        {#if user?.country}
          <span>{getCountryFlag(user.country)}</span>
        {/if}
        {user?.name || uid.slice(0, 8)}
        {#if organizerUids.length > 1}
          <button
            onclick={() => handleRemove(uid)}
            disabled={loading}
            class="ml-1 text-ash-500 hover:text-crimson-400 transition-colors"
            title={m.common_delete()}
          >
            <X class="w-3.5 h-3.5" />
          </button>
        {/if}
      </span>
    {/each}
  </div>

  <!-- Search to add -->
  <div class="relative">
    <input
      type="text"
      bind:value={search}
      oninput={() => doSearch()}
      onkeydown={handleKeydown}
      placeholder={m.organizers_search_placeholder()}
      class="w-full px-3 py-2 text-sm bg-dusk-950 border border-ash-700 rounded-lg text-ash-200 focus:border-ash-500 focus:outline-none"
    />
    {#if searchResults.length > 0}
      <div class="absolute z-10 mt-1 w-full bg-dusk-950 border border-ash-700 rounded-lg divide-y divide-ash-800 max-h-48 overflow-y-auto shadow-lg">
        {#each searchResults as user, i}
          <button
            onclick={() => handleAdd(user)}
            disabled={loading}
            class="w-full px-3 py-2 text-left text-sm text-ash-200 transition-colors {i === selectedIndex ? 'bg-ash-700' : 'hover:bg-ash-800'}"
          >
            {#if user.country}
              <span class="mr-1">{getCountryFlag(user.country)}</span>
            {/if}
            {user.name}
            {#if user.vekn_id}
              <span class="text-ash-500 ml-2">#{user.vekn_id}</span>
            {/if}
          </button>
        {/each}
        {#if searchTotal > SEARCH_LIMIT}
          <div class="px-3 py-2 text-xs text-ash-500 text-center">
            {m.add_player_more_results({ count: (searchTotal - SEARCH_LIMIT).toString() })}
          </div>
        {/if}
      </div>
    {:else if search.trim().length >= 2 && searchResults.length === 0}
      <div class="absolute z-10 mt-1 w-full bg-dusk-950 border border-ash-700 rounded-lg p-3 text-center text-sm text-ash-500 shadow-lg">
        {m.organizers_no_results()}
      </div>
    {/if}
  </div>
</div>
