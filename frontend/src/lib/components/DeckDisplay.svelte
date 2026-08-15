<script lang="ts">
  import { toUserMessage } from '$lib/errors';
  import type { Deck, VtesCard } from "$lib/types";
  import { getCards } from "$lib/cards";
  import { disciplineIcon, typeIcon } from "$lib/vtes-icons";
  import AttributionPicker from "./AttributionPicker.svelte";
  import { validateDeck, type ValidationError } from "$lib/engine";
  import CardSearch from "./CardSearch.svelte";
  import CardName from "./CardName.svelte";
  import { CircleX, TriangleAlert } from "@lucide/svelte";
  import Button from '$lib/components/Button.svelte';
  import * as m from '$lib/paraglide/messages.js';
  import { dialogPanel } from "$lib/actions/dialog";

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
  let editing = $state(false);
  let saving = $state(false);
  let saveError = $state<string | null>(null);
  let validationErrors = $state<ValidationError[] | null>([]);

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
      const { tournamentAction } = await import('$lib/tournament-actions');
      const auth = (await import('$lib/stores/auth.svelte')).getAuthState();
      const targetUid = playerUid || auth.user?.uid;

      // Compute attribution and author from attrMode
      let attrValue: string | null | undefined = undefined;
      let authorValue = deck.author;
      if (attrMode === 'anonymous') {
        attrValue = null;
        authorValue = ''; // anonymous: never persist a designer name
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
      onsaved?.();
    } catch (e: any) {
      saveError = toUserMessage(e, m.deck_error_save());
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
    return entries.sort((a, b) => (b.card?.capacity ?? 0) - (a.card?.capacity ?? 0) || (a.card?.unique_name ?? '').localeCompare(b.card?.unique_name ?? ''));
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
      return ta.localeCompare(tb) || (a.card?.unique_name ?? '').localeCompare(b.card?.unique_name ?? '');
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
    if (card.img) {
      cardImageUrl = card.img;
      return;
    }
    // Fallback for stale IndexedDB card data predating the img field. krcg's image
    // filename derives from the full (group/advanced-suffixed) name, not the bare one.
    const normalized = card.full_name.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^\w\d]/g, '') + '.jpg';
    cardImageUrl = `https://static.krcg.org/card/${normalized}`;
  }
</script>

{#if editing}
  <!-- Editable name -->
  <input
    type="text"
    bind:value={editedName}
    placeholder={m.deck_upload_name_placeholder()}
    class="w-full px-3 py-2 mb-2 bg-surface-muted border border-line-strong rounded-lg text-ink-bright placeholder-ink-faint text-sm"
  />

  <!-- Attribution -->
  <AttributionPicker
    bind:mode={attrMode}
    bind:search={attributionSearch}
    bind:vekn={attributionVekn}
    bind:name={attributionName}
    {playerUid}
    {playerName}
  />

  <div class="mb-3">
    <CardSearch onselect={addCard} />
    <p class="text-xs text-ink-faint mt-1">{m.deck_edit_search_hint()}</p>
  </div>
{:else}
  {#if deck.name}
    <h4 class="text-sm font-semibold text-ink-strong mb-1">{deck.name}</h4>
  {/if}
  {#if deck.author && deck.attribution !== null}
    <p class="text-xs text-ink-muted mb-2">{m.deck_by_author({ author: deck.author })}</p>
  {/if}

  {#if editable || onreplace || ondelete}
    <div class="flex gap-2 mb-3">
      {#if editable}
        <Button variant="secondary" size="lg" onclick={startEditing}>{m.deck_edit()}</Button>
      {/if}
      {#if onreplace}
        <Button variant="secondary" size="lg" onclick={onreplace}>{m.decks_replace()}</Button>
      {/if}
      {#if ondelete}
        <Button variant="secondary" size="lg" onclick={ondelete}>{m.decks_delete()}</Button>
      {/if}
    </div>
  {/if}
{/if}

<div class="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
  <!-- Crypt -->
  <div>
    <h5 class="font-semibold text-ink-bright mb-1">{m.deck_crypt_count({ count: cryptCount.toString() })}</h5>
    <div class="space-y-0.5">
      {#each cryptEntries as entry}
        <div class="flex gap-2 items-center hover:bg-surface-hover/50 px-1 rounded min-h-[28px]">
          {#if editing}
            <button
              onclick={() => adjustCount(entry.id.toString(), -1)}
              class="w-8 h-8 flex items-center justify-center rounded bg-surface-active text-ink hover:bg-surface-active text-sm shrink-0"
            >-</button>
          {/if}
          <button
            class="flex-1 text-left flex gap-2 items-baseline min-w-0"
            onclick={() => showCard(entry.card)}
          >
            <span class="text-ink-muted w-4 text-right shrink-0">{entry.count}x</span>
            {#if entry.card}
              <CardName card={entry.card} class="text-ink-bright flex-1" />
            {:else}
              <span class="text-ink-bright flex-1 truncate">#{entry.id}</span>
            {/if}
            {#if entry.card?.capacity}
              <span class="text-ink-faint text-xs">{entry.card.capacity}</span>
            {/if}
            {#if entry.card?.disciplines.length}
              <span class="text-ink-muted text-sm" style="font-family: 'Ankha VTES'">{#each entry.card.disciplines as disc}{disciplineIcon(disc) ?? ''}{/each}</span>
            {/if}
          </button>
          {#if editing}
            <button
              onclick={() => adjustCount(entry.id.toString(), 1)}
              class="w-8 h-8 flex items-center justify-center rounded bg-surface-active text-ink hover:bg-surface-active text-sm shrink-0"
            >+</button>
          {/if}
        </div>
      {/each}
    </div>
  </div>

  <!-- Library -->
  <div>
    <h5 class="font-semibold text-ink-bright mb-1">{m.deck_library_count({ count: libraryCount.toString() })}</h5>
    {#each libraryByType as [type, entries]}
      <div class="mb-2">
        <p class="text-xs text-ink-faint font-medium">
          {#if typeIcon(type)}<span class="text-sm text-ink-muted" style="font-family: 'Ankha VTES'">{typeIcon(type)}</span>{/if}
          {type} ({entries.reduce((s, e) => s + e.count, 0)})
        </p>
        <div class="space-y-0.5">
          {#each entries as entry}
            <div class="flex gap-2 items-center hover:bg-surface-hover/50 px-1 rounded min-h-[28px]">
              {#if editing}
                <button
                  onclick={() => adjustCount(entry.id.toString(), -1)}
                  class="w-8 h-8 flex items-center justify-center rounded bg-surface-active text-ink hover:bg-surface-active text-sm shrink-0"
                >-</button>
              {/if}
              <button
                class="flex-1 text-left flex gap-2 items-baseline min-w-0"
                onclick={() => showCard(entry.card)}
              >
                <span class="text-ink-muted w-4 text-right shrink-0">{entry.count}x</span>
                {#if entry.card}
                  <CardName card={entry.card} class="text-ink-bright flex-1" />
                {:else}
                  <span class="text-ink-bright flex-1 truncate">#{entry.id}</span>
                {/if}
              </button>
              {#if editing}
                <button
                  onclick={() => adjustCount(entry.id.toString(), 1)}
                  class="w-8 h-8 flex items-center justify-center rounded bg-surface-active text-ink hover:bg-surface-active text-sm shrink-0"
                >+</button>
              {/if}
            </div>
          {/each}
        </div>
      </div>
    {/each}
  </div>
</div>

{#if validationErrors === null}
  <p class="mt-3 text-sm text-ink-muted">
    <TriangleAlert class="w-4 h-4 inline mr-1" />
    {m.deck_validation_unavailable()}
  </p>
{:else if validationErrors.length > 0}
  <div class="mt-3 space-y-1">
    {#each validationErrors as err}
      <p class="text-sm {err.severity === 'error' ? 'text-link' : 'text-warn'}">
        {#if err.severity === 'error'}<CircleX class="w-4 h-4 inline mr-1" />{:else}<TriangleAlert class="w-4 h-4 inline mr-1" />{/if}
        {err.message}
      </p>
    {/each}
  </div>
{/if}

{#if editing}
  {#if saveError}
    <p class="text-sm text-link mt-2">{saveError}</p>
  {/if}
  <div class="flex gap-2 mt-3">
    <Button variant="primary" size="lg" loading={saving} onclick={saveDeck}>{saving ? m.common_saving() : m.deck_save_changes()}</Button>
    <Button variant="secondary" size="lg" onclick={cancelEditing}>{m.common_cancel()}</Button>
  </div>
{/if}

<!-- Card image modal -->
{#if cardImageUrl}
  <div
    class="fixed inset-0 z-[60] bg-black/80 flex items-center justify-center p-4"
    onclick={() => cardImageUrl = null}
    onkeydown={(e) => e.key === 'Escape' && (cardImageUrl = null)}
    use:dialogPanel={() => cardImageUrl = null}
    role="dialog"
    tabindex="-1"
  >
    <img
      src={cardImageUrl}
      alt={m.deck_card_image_alt()}
      class="max-h-[80dvh] max-w-full rounded-lg shadow-xl"
      onerror={() => cardImageUrl = null}
    />
  </div>
{/if}
