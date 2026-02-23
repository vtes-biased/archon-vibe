<script lang="ts">
  import type { Deck, VtesCard } from "$lib/types";
  import { getCards } from "$lib/cards";
  import { disciplineIcon, typeIcon } from "$lib/vtes-icons";
  import CardSearch from "./CardSearch.svelte";
  import * as m from '$lib/paraglide/messages.js';

  let {
    deck,
    editable = false,
    tournamentUid = '',
    playerUid = '',
    deckIndex = 0,
    onsaved,
    onreplace,
    ondelete,
  }: {
    deck: Deck;
    editable?: boolean;
    tournamentUid?: string;
    playerUid?: string;
    deckIndex?: number;
    onsaved?: () => void;
    onreplace?: () => void;
    ondelete?: () => void;
  } = $props();

  let cards = $state<Map<number, VtesCard>>(new Map());
  let cardImageUrl = $state<string | null>(null);
  let editedCards = $state<Record<string, number>>({});
  let editing = $state(false);
  let saving = $state(false);
  let saveError = $state<string | null>(null);

  $effect(() => {
    getCards().then(c => cards = c);
  });

  function startEditing() {
    editedCards = { ...deck.cards };
    editing = true;
    saveError = null;
  }

  function cancelEditing() {
    editing = false;
    editedCards = {};
    saveError = null;
  }

  function adjustCount(idStr: string, delta: number) {
    const current = editedCards[idStr] ?? 0;
    const next = current + delta;
    if (next <= 0) {
      delete editedCards[idStr];
      editedCards = { ...editedCards };
    } else {
      editedCards = { ...editedCards, [idStr]: next };
    }
  }

  function addCard(card: VtesCard) {
    const idStr = card.id.toString();
    editedCards = { ...editedCards, [idStr]: (editedCards[idStr] ?? 0) + 1 };
  }

  async function saveDeck() {
    saving = true;
    saveError = null;
    try {
      const token = (await import('$lib/stores/auth.svelte')).getAccessToken();
      const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
      const endpoint = playerUid
        ? `${API_URL}/api/tournaments/${tournamentUid}/decks/${playerUid}?deck_index=${deckIndex}`
        : `${API_URL}/api/tournaments/${tournamentUid}/decks`;
      const method = playerUid ? 'PUT' : 'POST';

      const resp = await fetch(endpoint, {
        method,
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          name: deck.name,
          author: deck.author,
          comments: deck.comments,
          text: Object.entries(editedCards)
            .map(([id, count]) => {
              const card = cards.get(parseInt(id));
              return `${count}x ${card?.name ?? id}`;
            })
            .join('\n'),
        }),
      });

      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `Save failed (${resp.status})`);
      }

      editing = false;
      editedCards = {};
      onsaved?.();
    } catch (e: any) {
      saveError = e.message || 'Save failed';
    } finally {
      saving = false;
    }
  }

  interface DisplayEntry {
    id: number;
    count: number;
    card: VtesCard | undefined;
  }

  const activeCards = $derived(editing ? editedCards : deck.cards);

  const cryptEntries = $derived.by(() => {
    const entries: DisplayEntry[] = [];
    for (const [idStr, count] of Object.entries(activeCards)) {
      const id = parseInt(idStr);
      const card = cards.get(id);
      if (card?.kind === 'crypt') entries.push({ id, count, card });
    }
    return entries.sort((a, b) => (b.card?.capacity ?? 0) - (a.card?.capacity ?? 0) || (a.card?.name ?? '').localeCompare(b.card?.name ?? ''));
  });

  const libraryEntries = $derived.by(() => {
    const entries: DisplayEntry[] = [];
    for (const [idStr, count] of Object.entries(activeCards)) {
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

  // Standard TWDA library type ordering (from krcg config)
  const LIBRARY_TYPE_ORDER = [
    'Master', 'Conviction', 'Action', 'Action/Combat', 'Action/Reaction',
    'Ally', 'Equipment', 'Political Action', 'Retainer', 'Power',
    'Action Modifier', 'Action Modifier/Combat', 'Action Modifier/Reaction',
    'Reaction', 'Combat', 'Combat/Reaction', 'Event',
  ];

  // Group library by type
  const libraryByType = $derived.by(() => {
    const groups: Record<string, DisplayEntry[]> = {};
    for (const entry of libraryEntries) {
      const type = entry.card?.types[0] ?? 'Other';
      (groups[type] ??= []).push(entry);
    }
    return Object.entries(groups).sort(([a], [b]) => {
      const ai = LIBRARY_TYPE_ORDER.indexOf(a);
      const bi = LIBRARY_TYPE_ORDER.indexOf(b);
      return (ai === -1 ? 999 : ai) - (bi === -1 ? 999 : bi);
    });
  });

  function showCard(card: VtesCard | undefined) {
    if (!card) return;
    const normalized = card.name.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^\w\d]/g, '') + '.jpg';
    cardImageUrl = `https://static.krcg.org/card/${normalized}`;
  }
</script>

{#if deck.name}
  <h4 class="text-sm font-semibold text-bone-200 mb-1">{deck.name}</h4>
{/if}
{#if deck.author}
  <p class="text-xs text-ash-400 mb-2">{m.deck_by_author({ author: deck.author })}</p>
{/if}

{#if (editable || onreplace || ondelete) && !editing}
  <div class="flex gap-2 mb-3">
    {#if editable}
      <button
        onclick={startEditing}
        class="px-3 py-1.5 text-sm font-medium text-ash-200 bg-ash-800 hover:bg-ash-700 rounded-lg transition-colors"
      >{m.deck_edit()}</button>
    {/if}
    {#if onreplace}
      <button
        onclick={onreplace}
        class="px-3 py-1.5 text-sm font-medium text-ash-200 bg-ash-800 hover:bg-ash-700 rounded-lg transition-colors"
      >{m.decks_replace()}</button>
    {/if}
    {#if ondelete}
      <button
        onclick={ondelete}
        class="px-3 py-1.5 text-sm font-medium text-crimson-400 bg-ash-800 hover:bg-ash-700 rounded-lg transition-colors"
      >{m.decks_delete()}</button>
    {/if}
  </div>
{/if}

{#if editing}
  <div class="mb-3">
    <CardSearch onselect={addCard} />
    <p class="text-xs text-ash-500 mt-1">{m.deck_edit_search_hint()}</p>
  </div>
{/if}

<div class="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
  <!-- Crypt -->
  <div>
    <h5 class="font-semibold text-ash-200 mb-1">{m.deck_crypt_count({ count: cryptCount.toString() })}</h5>
    <div class="space-y-0.5">
      {#each cryptEntries as entry}
        <div class="flex gap-2 items-center hover:bg-ash-800/50 px-1 rounded min-h-[28px]">
          {#if editing}
            <button
              onclick={() => adjustCount(entry.id.toString(), -1)}
              class="w-5 h-5 flex items-center justify-center rounded bg-ash-700 text-ash-300 hover:bg-ash-600 text-xs shrink-0"
            >-</button>
          {/if}
          <button
            class="flex-1 text-left flex gap-2 items-baseline min-w-0"
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
          {#if editing}
            <button
              onclick={() => adjustCount(entry.id.toString(), 1)}
              class="w-5 h-5 flex items-center justify-center rounded bg-ash-700 text-ash-300 hover:bg-ash-600 text-xs shrink-0"
            >+</button>
          {/if}
        </div>
      {/each}
    </div>
  </div>

  <!-- Library -->
  <div>
    <h5 class="font-semibold text-ash-200 mb-1">{m.deck_library_count({ count: libraryCount.toString() })}</h5>
    {#each libraryByType as [type, entries]}
      <div class="mb-2">
        <p class="text-xs text-ash-500 font-medium">
          {#if typeIcon(type)}<span class="text-sm text-ash-400" style="font-family: 'Ankha VTES'">{typeIcon(type)}</span>{/if}
          {type} ({entries.reduce((s, e) => s + e.count, 0)})
        </p>
        <div class="space-y-0.5">
          {#each entries as entry}
            <div class="flex gap-2 items-center hover:bg-ash-800/50 px-1 rounded min-h-[28px]">
              {#if editing}
                <button
                  onclick={() => adjustCount(entry.id.toString(), -1)}
                  class="w-5 h-5 flex items-center justify-center rounded bg-ash-700 text-ash-300 hover:bg-ash-600 text-xs shrink-0"
                >-</button>
              {/if}
              <button
                class="flex-1 text-left flex gap-2 items-baseline min-w-0"
                onclick={() => showCard(entry.card)}
              >
                <span class="text-ash-400 w-4 text-right shrink-0">{entry.count}x</span>
                <span class="text-ash-200 flex-1 truncate">{entry.card?.name ?? `#${entry.id}`}</span>
              </button>
              {#if editing}
                <button
                  onclick={() => adjustCount(entry.id.toString(), 1)}
                  class="w-5 h-5 flex items-center justify-center rounded bg-ash-700 text-ash-300 hover:bg-ash-600 text-xs shrink-0"
                >+</button>
              {/if}
            </div>
          {/each}
        </div>
      </div>
    {/each}
  </div>
</div>

{#if editing}
  {#if saveError}
    <p class="text-sm text-red-400 mt-2">{saveError}</p>
  {/if}
  <div class="flex gap-2 mt-3">
    <button
      onclick={saveDeck}
      disabled={saving}
      class="px-4 py-2 text-sm font-medium text-white bg-crimson-600 hover:bg-crimson-500 disabled:bg-ash-700 disabled:text-ash-500 rounded-lg transition-colors"
    >{saving ? m.common_saving() : m.deck_save_changes()}</button>
    <button
      onclick={cancelEditing}
      class="px-4 py-2 text-sm text-ash-300 bg-ash-800 hover:bg-ash-700 rounded-lg transition-colors"
    >{m.common_cancel()}</button>
  </div>
{/if}

<!-- Card image modal -->
{#if cardImageUrl}
  <div
    class="fixed inset-0 z-[60] bg-black/80 flex items-center justify-center p-4"
    onclick={() => cardImageUrl = null}
    onkeydown={(e) => e.key === 'Escape' && (cardImageUrl = null)}
    role="dialog"
    tabindex="-1"
  >
    <img
      src={cardImageUrl}
      alt={m.deck_card_image_alt()}
      class="max-h-[80vh] max-w-full rounded-lg shadow-xl"
      onerror={() => cardImageUrl = null}
    />
  </div>
{/if}
