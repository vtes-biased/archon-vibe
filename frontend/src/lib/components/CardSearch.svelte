<script lang="ts">
  import type { VtesCard } from "$lib/types";
  import { searchCards } from "$lib/cards";

  let {
    onselect,
  }: {
    onselect: (card: VtesCard) => void;
  } = $props();

  let query = $state('');
  let results = $state<VtesCard[]>([]);
  let selectedIndex = $state(-1);
  let debounceTimer: ReturnType<typeof setTimeout>;

  function onInput() {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(async () => {
      selectedIndex = -1;
      results = await searchCards(query, 15);
    }, 200);
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
    placeholder="Search cards..."
    class="w-full px-3 py-2 bg-ash-900 border border-ash-700 rounded-lg text-ash-200 placeholder-ash-500 text-sm"
  />

  {#if results.length > 0}
    <div class="absolute z-40 top-full mt-1 w-full bg-ash-900 border border-ash-700 rounded-lg shadow-xl max-h-60 overflow-y-auto">
      {#each results as card, i}
        <button
          class="w-full text-left px-3 py-1.5 text-sm flex items-center gap-2 transition-colors {i === selectedIndex ? 'bg-ash-700 text-bone-100' : 'text-ash-200 hover:bg-ash-800'}"
          onclick={() => select(card)}
        >
          <span class="flex-1 truncate">{card.name}</span>
          <span class="text-xs text-ash-500">{card.types.join('/')}</span>
          {#if card.kind === 'crypt' && card.capacity}
            <span class="text-xs text-ash-500">{card.capacity}</span>
          {/if}
        </button>
      {/each}
    </div>
  {/if}
</div>
