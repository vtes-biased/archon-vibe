<script lang="ts">
  import { onMount } from "svelte";
  import type { UserListItem } from "$lib/db";
  import { getFilteredUsers, warmUserIndex } from "$lib/db";
  import { getCountryFlag } from "$lib/geonames";
  import type { DeckAttribution } from "$lib/types";
  import * as m from '$lib/paraglide/messages.js';

  let {
    attribution = $bindable(),
    playerUid = '',
    playerName = '',
  }: {
    attribution: DeckAttribution;
    playerUid?: string;
    playerName?: string;
  } = $props();

  let results = $state<UserListItem[]>([]);
  let total = $state(0);
  let selectedIndex = $state(-1);
  let search = $state(attribution.kind === 'Member' ? attribution.vekn_id : '');
  const SEARCH_LIMIT = 10;
  // See UserPicker: guards against an earlier, slower query landing last.
  let searchSeq = 0;

  onMount(() => { warmUserIndex(); });

  // A deck holding a past Archive credit keeps it until the owner picks one of these.
  const kinds = ['Owner', 'Anonymous', 'Member'] as const;

  function pick(kind: (typeof kinds)[number]) {
    attribution = { kind, vekn_id: '', name: '' };
    results = [];
    search = '';
  }

  async function searchUsers() {
    selectedIndex = -1;
    attribution = { kind: 'Member', vekn_id: '', name: '' };
    const seq = ++searchSeq;
    if (search.trim().length < 2) {
      results = [];
      total = 0;
      return;
    }
    const r = (await getFilteredUsers(undefined, undefined, search.trim())).filter(u => u.vekn_id);
    if (seq !== searchSeq) return;
    total = r.length;
    results = r.slice(0, SEARCH_LIMIT);
  }

  function selectUser(user: UserListItem) {
    attribution = { kind: 'Member', vekn_id: user.vekn_id ?? '', name: '' };
    search = `${user.name} (${user.vekn_id})`;
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
      const user = results[selectedIndex];
      if (user) {
        e.preventDefault();
        selectUser(user);
      }
    }
  }

  const label = {
    Owner: () => playerUid ? m.deck_upload_attr_player({ name: playerName || '?' }) : m.deck_upload_attr_self(),
    Anonymous: () => m.deck_upload_attr_anonymous(),
    Member: () => m.deck_upload_attr_member(),
  };
</script>

<div class="flex items-center gap-3 text-sm flex-wrap mb-2">
  <span class="text-ink-muted">{m.deck_upload_attribution()}:</span>
  {#each kinds as kind}
    <label class="flex items-center gap-1 text-ink-bright">
      <input
        type="radio"
        name="attribution-kind"
        checked={attribution.kind === kind}
        onchange={() => pick(kind)}
        class="accent-accent"
      />
      {label[kind]()}
    </label>
  {/each}
</div>
{#if attribution.kind === 'Member'}
  <div class="relative mb-2">
    <input
      type="text"
      bind:value={search}
      oninput={searchUsers}
      onkeydown={handleKeydown}
      placeholder={m.deck_upload_attr_member_placeholder()}
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
            <span class="text-ink-faint ml-2">({user.vekn_id})</span>
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
