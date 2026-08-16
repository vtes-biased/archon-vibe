<script lang="ts">
  import { onMount } from 'svelte';
  import type { VtesCard } from "$lib/types";
  import { searchCards, getCards } from "$lib/cards";
  import CardName from "$lib/components/CardName.svelte";
  import * as m from '$lib/paraglide/messages.js';

  let {
    onselect,
  }: {
    onselect: (card: VtesCard) => void;
  } = $props();

  let query = $state('');
  let results = $state<VtesCard[]>([]);
  let selectedIndex = $state(-1);
  // Searching is sub-millisecond against the token cache, so there is nothing left to debounce — this
  // sequence guard replaces the debounce timer's old race-guard role: the first query builds the card cache and can otherwise resolve after later ones it should have preceded.
  let searchSeq = 0;

  onMount(() => { getCards(); });

  async function onInput() {
    selectedIndex = -1;
    const seq = ++searchSeq;
    const found = await searchCards(query, 15);
    if (seq !== searchSeq) return;
    results = found;
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
      const card = results[selectedIndex];
      if (card) select(card);
    }
  }

  function select(card: VtesCard) {
    onselect(card);
    query = '';
    results = [];
  }
</script>

<div class="relative">
  <input
    type="text"
    bind:value={query}
    oninput={onInput}
    onkeydown={handleKeydown}
    placeholder={m.card_search_placeholder()}
    class="w-full px-3 py-2 bg-surface-muted border border-line-strong rounded-lg text-ink-bright placeholder-ink-faint text-sm"
  />

  {#if results.length > 0}
    <div class="absolute z-40 top-full mt-1 w-full bg-surface-muted border border-line-strong rounded-lg shadow-xl max-h-60 overflow-y-auto">
      {#each results as card, i}
        <button
          class="w-full text-left px-3 py-1.5 text-sm flex items-center gap-2 transition-colors {i === selectedIndex ? 'bg-surface-active text-ink-strong' : 'text-ink-bright hover:bg-surface-hover'}"
          onclick={() => select(card)}
        >
          <CardName {card} class="flex-1" />
          <span class="text-xs text-ink-faint">{card.types.join('/')}</span>
          {#if card.kind === 'crypt' && card.capacity}
            <span class="text-xs text-ink-faint">{card.capacity}</span>
          {/if}
        </button>
      {/each}
    </div>
  {/if}
</div>
