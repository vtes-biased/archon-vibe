<script lang="ts">
  import { onMount } from "svelte";
  import type { UserListItem } from "$lib/db";
  import { getFilteredUsers, warmUserIndex } from "$lib/db";
  import { getCountryFlag } from "$lib/geonames";
  import * as m from '$lib/paraglide/messages.js';

  let {
    mode = $bindable(),
    search = $bindable(),
    vekn = $bindable(),
    name = $bindable(),
    playerUid = '',
    playerName = '',
  }: {
    mode: 'self' | 'anonymous' | 'other';
    search: string;
    vekn: string;
    name: string;
    playerUid?: string;
    playerName?: string;
  } = $props();

  let results = $state<UserListItem[]>([]);
  let total = $state(0);
  let selectedIndex = $state(-1);
  const SEARCH_LIMIT = 10;
  // See UserPicker: guards against an earlier, slower query landing last.
  let searchSeq = 0;

  onMount(() => { warmUserIndex(); });

  async function searchUsers() {
    selectedIndex = -1;
    const seq = ++searchSeq;
    if (search.trim().length < 2) {
      results = [];
      total = 0;
      return;
    }
    const r = await getFilteredUsers(undefined, undefined, search.trim());
    if (seq !== searchSeq) return;
    total = r.length;
    results = r.slice(0, SEARCH_LIMIT);
  }

  function selectUser(user: UserListItem) {
    vekn = user.vekn_id || user.name;
    name = user.name;
    search = user.name + (user.vekn_id ? ` (${user.vekn_id})` : '');
    results = [];
  }

  function handleKeydown(e: KeyboardEvent) {
    if (!results.length) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      selectedIndex = Math.min(selectedIndex + 1, results.length - 1);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      selectedIndex = Math.max(selectedIndex - 1, 0);
    } else if (e.key === 'Enter' && selectedIndex >= 0) {
      e.preventDefault();
      const user = results[selectedIndex];
      if (user) selectUser(user);
    }
  }
</script>

<div class="flex items-center gap-3 text-sm flex-wrap mb-2">
  <span class="text-ink-muted">{m.deck_upload_attribution()}:</span>
  <label class="flex items-center gap-1 text-ink-bright">
    <input type="radio" bind:group={mode} value="self" class="accent-accent" />
    {playerUid ? m.deck_upload_attr_player({ name: playerName || '?' }) : m.deck_upload_attr_self()}
  </label>
  <label class="flex items-center gap-1 text-ink-bright">
    <input type="radio" bind:group={mode} value="anonymous" class="accent-accent" />
    {m.deck_upload_attr_anonymous()}
  </label>
  <label class="flex items-center gap-1 text-ink-bright">
    <input type="radio" bind:group={mode} value="other" class="accent-accent" />
    {m.deck_upload_attr_other()}
  </label>
</div>
{#if mode === 'other'}
  <div class="relative mb-2">
    <input
      type="text"
      bind:value={search}
      oninput={() => { vekn = search; name = ''; searchUsers(); }}
      onkeydown={handleKeydown}
      placeholder={m.deck_upload_attr_other_placeholder()}
      autocomplete="off"
      autocorrect="off"
      autocapitalize="off"
      spellcheck="false"
      class="w-full px-3 py-2 bg-surface-muted border border-line-strong rounded-lg text-ink-bright placeholder-ink-faint text-sm"
    />
    {#if results.length > 0}
      <div class="absolute z-10 mt-1 w-full bg-surface-card border border-line-strong rounded-lg divide-y divide-line max-h-48 overflow-y-auto shadow-lg">
        {#each results as user, i}
          <button
            onclick={() => selectUser(user)}
            class="w-full px-3 py-2 text-left text-sm text-ink-bright transition-colors {i === selectedIndex ? 'bg-surface-active' : 'hover:bg-surface-hover'}"
          >
            {#if user.country}<span class="mr-1">{getCountryFlag(user.country)}</span>{/if}{user.name}
            {#if user.vekn_id}
              <span class="text-ink-faint ml-2">({user.vekn_id})</span>
            {/if}
          </button>
        {/each}
        {#if total > SEARCH_LIMIT}
          <div class="px-3 py-2 text-xs text-ink-faint text-center">
            {m.add_player_more_results({ count: (total - SEARCH_LIMIT).toString() })}
          </div>
        {/if}
      </div>
    {/if}
  </div>
{/if}
