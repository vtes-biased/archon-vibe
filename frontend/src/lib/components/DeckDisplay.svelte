<script lang="ts">
  import type { Deck, VtesCard, User } from "$lib/types";
  import { getCards } from "$lib/cards";
  import { getFilteredUsers } from "$lib/db";
  import { getCountryFlag } from "$lib/geonames";
  import { disciplineIcon, typeIcon } from "$lib/vtes-icons";
  import { validateDeck, type ValidationError } from "$lib/engine";
  import CardSearch from "./CardSearch.svelte";
  import { CircleX, TriangleAlert } from "lucide-svelte";
  import * as m from '$lib/paraglide/messages.js';

  let {
    deck,
    editable = false,
    tournamentUid = '',
    playerUid = '',
    playerName = undefined,
    playerVekn = undefined,
    deckIndex = 0,
    format = '',
    onsaved,
    onreplace,
    ondelete,
  }: {
    deck: Deck;
    editable?: boolean;
    tournamentUid?: string;
    playerUid?: string;
    playerName?: string;
    playerVekn?: string;
    deckIndex?: number;
    format?: string;
    onsaved?: () => void;
    onreplace?: () => void;
    ondelete?: () => void;
  } = $props();

  let cards = $state<Map<number, VtesCard>>(new Map());
  let cardImageUrl = $state<string | null>(null);
  let editedCards = $state<Record<string, number>>({});
  let editedName = $state('');
  let attrMode = $state<'self' | 'anonymous' | 'other'>('self');
  let attributionSearch = $state('');
  let attributionVekn = $state('');
  let attributionName = $state('');
  let attrResults = $state<User[]>([]);
  let attrTotal = $state(0);
  let attrSelectedIndex = $state(-1);
  const ATTR_SEARCH_LIMIT = 10;
  let editing = $state(false);
  let saving = $state(false);
  let saveError = $state<string | null>(null);
  let validationErrors = $state<ValidationError[]>([]);

  $effect(() => {
    getCards().then(c => cards = c);
  });

  // Validate deck reactively
  $effect(() => {
    const cardsToValidate = editing ? editedCards : deck.cards;
    if (!format || !Object.keys(cardsToValidate).length) {
      validationErrors = [];
      return;
    }
    validateDeck({ cards: cardsToValidate, name: deck.name }, format).then(errors => {
      validationErrors = errors;
    });
  });

  function startEditing() {
    editedCards = { ...deck.cards };
    editedName = deck.name;
    // Determine attribution mode from current deck
    if (deck.attribution === null) {
      attrMode = 'anonymous';
    } else if (deck.attribution) {
      attrMode = 'other';
      attributionVekn = deck.attribution;
      attributionName = deck.author || '';
      attributionSearch = deck.author || '';
    } else {
      attrMode = 'self';
    }
    editing = true;
    saveError = null;
  }

  function cancelEditing() {
    editing = false;
    editedCards = {};
    editedName = '';
    attrResults = [];
    saveError = null;
  }

  async function searchAttribution() {
    attrSelectedIndex = -1;
    if (attributionSearch.trim().length < 2) {
      attrResults = [];
      attrTotal = 0;
      return;
    }
    const results = await getFilteredUsers(undefined, undefined, attributionSearch.trim());
    attrTotal = results.length;
    attrResults = results.slice(0, ATTR_SEARCH_LIMIT);
  }

  function selectAttrUser(user: User) {
    attributionVekn = user.vekn_id || user.name;
    attributionName = user.name;
    attributionSearch = user.name + (user.vekn_id ? ` (${user.vekn_id})` : '');
    attrResults = [];
  }

  function handleAttrKeydown(e: KeyboardEvent) {
    if (!attrResults.length) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      attrSelectedIndex = Math.min(attrSelectedIndex + 1, attrResults.length - 1);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      attrSelectedIndex = Math.max(attrSelectedIndex - 1, 0);
    } else if (e.key === 'Enter' && attrSelectedIndex >= 0) {
      e.preventDefault();
      const user = attrResults[attrSelectedIndex];
      if (user) selectAttrUser(user);
    }
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
      const { tournamentAction } = await import('$lib/api');
      const auth = (await import('$lib/stores/auth.svelte')).getAuthState();
      const targetUid = playerUid || auth.user?.uid;

      // Compute attribution and author from attrMode
      let attrValue: string | null | undefined = undefined;
      let authorValue = deck.author;
      if (attrMode === 'anonymous') {
        attrValue = null;
      } else if (attrMode === 'self') {
        const selfVekn = playerVekn || auth.user?.vekn_id;
        const selfName = playerName || auth.user?.name;
        attrValue = selfVekn || selfName || null;
        if (selfName) authorValue = selfName;
      } else if (attrMode === 'other') {
        const val = attributionVekn.trim() || attributionSearch.trim();
        if (val) {
          attrValue = val;
          authorValue = attributionName || attributionSearch.trim();
        }
      }

      const deckData: Record<string, unknown> = {
        name: editedName,
        author: authorValue,
        comments: deck.comments,
        cards: editedCards,
      };
      if (attrValue !== undefined) deckData.attribution = attrValue;

      await tournamentAction(tournamentUid, 'UpsertDeck', {
        player_uid: targetUid,
        deck: deckData,
        multideck: false,
      });

      editing = false;
      editedCards = {};
      editedName = '';
      attrResults = [];
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

{#if editing}
  <!-- Editable name -->
  <input
    type="text"
    bind:value={editedName}
    placeholder={m.deck_upload_name_placeholder()}
    class="w-full px-3 py-2 mb-2 bg-ash-900 border border-ash-700 rounded-lg text-ash-200 placeholder-ash-500 text-sm"
  />

  <!-- Attribution -->
  <div class="flex items-center gap-3 text-sm flex-wrap mb-2">
    <span class="text-ash-400">{m.deck_upload_attribution()}:</span>
    <label class="flex items-center gap-1 text-ash-200">
      <input type="radio" bind:group={attrMode} value="self" class="accent-crimson-500" />
      {playerUid ? m.deck_upload_attr_player({ name: playerName || '?' }) : m.deck_upload_attr_self()}
    </label>
    <label class="flex items-center gap-1 text-ash-200">
      <input type="radio" bind:group={attrMode} value="anonymous" class="accent-crimson-500" />
      {m.deck_upload_attr_anonymous()}
    </label>
    <label class="flex items-center gap-1 text-ash-200">
      <input type="radio" bind:group={attrMode} value="other" class="accent-crimson-500" />
      {m.deck_upload_attr_other()}
    </label>
  </div>
  {#if attrMode === 'other'}
    <div class="relative mb-2">
      <input
        type="text"
        bind:value={attributionSearch}
        oninput={() => { attributionVekn = attributionSearch; attributionName = ''; searchAttribution(); }}
        onkeydown={handleAttrKeydown}
        placeholder={m.deck_upload_attr_other_placeholder()}
        class="w-full px-3 py-2 bg-ash-900 border border-ash-700 rounded-lg text-ash-200 placeholder-ash-500 text-sm"
      />
      {#if attrResults.length > 0}
        <div class="absolute z-10 mt-1 w-full bg-dusk-950 border border-ash-700 rounded-lg divide-y divide-ash-800 max-h-48 overflow-y-auto shadow-lg">
          {#each attrResults as user, i}
            <button
              onclick={() => selectAttrUser(user)}
              class="w-full px-3 py-2 text-left text-sm text-ash-200 transition-colors {i === attrSelectedIndex ? 'bg-ash-700' : 'hover:bg-ash-800'}"
            >
              {#if user.country}<span class="mr-1">{getCountryFlag(user.country)}</span>{/if}{user.name}
              {#if user.vekn_id}
                <span class="text-ash-500 ml-2">({user.vekn_id})</span>
              {/if}
            </button>
          {/each}
          {#if attrTotal > ATTR_SEARCH_LIMIT}
            <div class="px-3 py-2 text-xs text-ash-500 text-center">
              {m.add_player_more_results({ count: (attrTotal - ATTR_SEARCH_LIMIT).toString() })}
            </div>
          {/if}
        </div>
      {/if}
    </div>
  {/if}

  <div class="mb-3">
    <CardSearch onselect={addCard} />
    <p class="text-xs text-ash-500 mt-1">{m.deck_edit_search_hint()}</p>
  </div>
{:else}
  {#if deck.name}
    <h4 class="text-sm font-semibold text-bone-200 mb-1">{deck.name}</h4>
  {/if}
  {#if deck.author}
    <p class="text-xs text-ash-400 mb-2">{m.deck_by_author({ author: deck.author })}</p>
  {/if}

  {#if editable || onreplace || ondelete}
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

{#if validationErrors.length > 0}
  <div class="mt-3 space-y-1">
    {#each validationErrors as err}
      <p class="text-sm {err.severity === 'error' ? 'text-crimson-400' : 'text-amber-400'}">
        {#if err.severity === 'error'}<CircleX class="w-4 h-4 inline mr-1" />{:else}<TriangleAlert class="w-4 h-4 inline mr-1" />{/if}
        {err.message}
      </p>
    {/each}
  </div>
{/if}

{#if editing}
  {#if saveError}
    <p class="text-sm text-red-400 mt-2">{saveError}</p>
  {/if}
  <div class="flex gap-2 mt-3">
    <button
      onclick={saveDeck}
      disabled={saving}
      class="px-4 py-2 text-sm font-medium text-white bg-crimson-600 hover:bg-crimson-500 disabled:bg-ash-800 disabled:text-ash-500 rounded-lg transition-colors"
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
