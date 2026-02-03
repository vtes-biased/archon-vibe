<script lang="ts">
  import type { Deck, VtesCard } from "$lib/types";
  import { getCards } from "$lib/cards";
  import { disciplineIcon, typeIcon } from "$lib/vtes-icons";

  let {
    deck,
  }: {
    deck: Deck;
  } = $props();

  let cards = $state<Map<number, VtesCard>>(new Map());
  let cardImageUrl = $state<string | null>(null);

  $effect(() => {
    getCards().then(c => cards = c);
  });

  interface DisplayEntry {
    id: number;
    count: number;
    card: VtesCard | undefined;
  }

  const cryptEntries = $derived.by(() => {
    const entries: DisplayEntry[] = [];
    for (const [idStr, count] of Object.entries(deck.cards)) {
      const id = parseInt(idStr);
      const card = cards.get(id);
      if (card?.kind === 'crypt') entries.push({ id, count, card });
    }
    return entries.sort((a, b) => (b.card?.capacity ?? 0) - (a.card?.capacity ?? 0) || (a.card?.name ?? '').localeCompare(b.card?.name ?? ''));
  });

  const libraryEntries = $derived.by(() => {
    const entries: DisplayEntry[] = [];
    for (const [idStr, count] of Object.entries(deck.cards)) {
      const id = parseInt(idStr);
      const card = cards.get(id);
      if (card?.kind === 'library') entries.push({ id, count, card });
    }
    return entries.sort((a, b) => {
      const ta = a.card?.types[0] ?? '';
      const tb = b.card?.types[0] ?? '';
      return ta.localeCompare(tb) || (a.card?.name ?? '').localeCompare(b.card?.name ?? '');
    });
  });

  const cryptCount = $derived(cryptEntries.reduce((s, e) => s + e.count, 0));
  const libraryCount = $derived(libraryEntries.reduce((s, e) => s + e.count, 0));

  // Group library by type
  const libraryByType = $derived.by(() => {
    const groups: Record<string, DisplayEntry[]> = {};
    for (const entry of libraryEntries) {
      const type = entry.card?.types[0] ?? 'Other';
      (groups[type] ??= []).push(entry);
    }
    return Object.entries(groups).sort(([a], [b]) => a.localeCompare(b));
  });

  function showCard(card: VtesCard | undefined) {
    if (!card) return;
    // Use krcg static URL pattern
    const normalized = card.name.toLowerCase().replace(/[^\w\d]/g, '') + '.jpg';
    cardImageUrl = `https://static.krcg.org/card/${normalized}`;
  }
</script>

{#if deck.name}
  <h4 class="text-sm font-semibold text-bone-200 mb-1">{deck.name}</h4>
{/if}
{#if deck.author}
  <p class="text-xs text-ash-400 mb-2">by {deck.author}</p>
{/if}

<div class="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
  <!-- Crypt -->
  <div>
    <h5 class="font-semibold text-ash-200 mb-1">Crypt ({cryptCount})</h5>
    <div class="space-y-0.5">
      {#each cryptEntries as entry}
        <button
          class="w-full text-left hover:bg-ash-800/50 px-1 rounded flex gap-2 items-baseline"
          onclick={() => showCard(entry.card)}
        >
          <span class="text-ash-400 w-4 text-right shrink-0">{entry.count}x</span>
          <span class="text-ash-200 flex-1 truncate">{entry.card?.name ?? `#${entry.id}`}</span>
          {#if entry.card?.capacity}
            <span class="text-ash-500 text-xs">{entry.card.capacity}</span>
          {/if}
          {#if entry.card?.disciplines.length}
            <span class="text-ash-400 text-sm" style="font-family: 'Ankha VTES'">{#each entry.card.disciplines as disc}{disciplineIcon(disc) ?? ''}{/each}</span>
          {/if}
        </button>
      {/each}
    </div>
  </div>

  <!-- Library -->
  <div>
    <h5 class="font-semibold text-ash-200 mb-1">Library ({libraryCount})</h5>
    {#each libraryByType as [type, entries]}
      <div class="mb-2">
        <p class="text-xs text-ash-500 font-medium">
          {#if typeIcon(type)}<span class="text-sm text-ash-400" style="font-family: 'Ankha VTES'">{typeIcon(type)}</span>{/if}
          {type} ({entries.reduce((s, e) => s + e.count, 0)})
        </p>
        <div class="space-y-0.5">
          {#each entries as entry}
            <button
              class="w-full text-left hover:bg-ash-800/50 px-1 rounded flex gap-2 items-baseline"
              onclick={() => showCard(entry.card)}
            >
              <span class="text-ash-400 w-4 text-right shrink-0">{entry.count}x</span>
              <span class="text-ash-200 flex-1 truncate">{entry.card?.name ?? `#${entry.id}`}</span>
            </button>
          {/each}
        </div>
      </div>
    {/each}
  </div>
</div>

<!-- Card image modal -->
{#if cardImageUrl}
  <div
    class="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4"
    onclick={() => cardImageUrl = null}
    onkeydown={(e) => e.key === 'Escape' && (cardImageUrl = null)}
    role="dialog"
    tabindex="-1"
  >
    <img
      src={cardImageUrl}
      alt="Card"
      class="max-h-[80vh] max-w-full rounded-lg shadow-xl"
      onerror={() => cardImageUrl = null}
    />
  </div>
{/if}
