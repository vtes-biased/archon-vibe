<script lang="ts">
  import { toUserMessage } from '$lib/errors';
  import type { DeckAttribution, DeckObject, VtesCard } from "$lib/types";
  import { creditName, isSettableCredit } from "$lib/deck-credit";
  import { getAuthState } from "$lib/stores/auth.svelte";
  import { getCards } from "$lib/cards";
  import { normalizeSearch } from "$lib/utils";
  import { disciplineIcon, typeIcon } from "$lib/vtes-icons";
  import AttributionPicker from "./AttributionPicker.svelte";
  import { getLibraryTypeOrder, validateDeck, type ValidationError } from "$lib/engine";
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
    organizer = false,
    multideck = false,
    format = '',
    onsaved,
    onreplace,
    ondelete,
  }: {
    deck: DeckObject;
    editable?: boolean;
    tournamentUid?: string;
    organizer?: boolean;
    multideck?: boolean;
    format?: string;
    onsaved?: () => void;
    onreplace?: () => void;
    ondelete?: () => void;
  } = $props();

  let cards = $state<Map<number, VtesCard>>(new Map());
  let cardImageUrl = $state<string | null>(null);
  let editedCards = $state<Record<string, number>>({});
  let editedName = $state('');
  let editedComments = $state('');
  let editing = $state(false);
  let editingCredit = $state(false);
  let editedAttribution = $state<DeckAttribution>({ kind: 'Anonymous', vekn_id: '', name: '' });
  let credit = $state('');
  let creditError = $state<string | null>(null);
  const myUid = $derived(getAuthState().user?.uid);
  const ownsDeck = $derived(!!tournamentUid && !!myUid && deck.user_uid === myUid);
  const anonymous = $derived(deck.attribution.kind === 'Anonymous');
  const canSetPrivate = $derived(!!tournamentUid && (ownsDeck || organizer));
  let privacyError = $state<string | null>(null);

  $effect(() => {
    creditName(deck.attribution).then(n => credit = n);
  });
  let saving = $state(false);
  let saveError = $state<string | null>(null);
  let validationErrors = $state<ValidationError[] | null>([]);

  $effect(() => {
    getCards().then(c => cards = c);
  });

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
    editedComments = deck.comments;
    editing = true;
    saveError = null;
  }

  function startEditingCredit() {
    editedAttribution = deck.attribution;
    editingCredit = true;
    creditError = null;
  }

  async function saveCredit() {
    creditError = null;
    try {
      const { tournamentAction } = await import('$lib/tournament-actions');
      await tournamentAction(tournamentUid, 'SetDeckAttribution', {
        player_uid: deck.user_uid,
        round: deck.round,
        attribution: editedAttribution,
      });
      editingCredit = false;
      onsaved?.();
    } catch (e: any) {
      creditError = toUserMessage(e, m.deck_error_save());
    }
  }

  async function setPrivate(e: Event) {
    const box = e.currentTarget as HTMLInputElement;
    privacyError = null;
    try {
      const { tournamentAction } = await import('$lib/tournament-actions');
      await tournamentAction(tournamentUid, 'SetDeckPrivate', {
        player_uid: deck.user_uid,
        round: deck.round,
        private: box.checked,
      });
      onsaved?.();
    } catch (err: any) {
      box.checked = deck.private ?? false;
      privacyError = toUserMessage(err, m.deck_error_save());
    }
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
      const targetUid = deck.user_uid;

      const deckData: Record<string, unknown> = {
        name: editedName,
        comments: editedComments,
        cards: editedCards,
        round: deck.round,
      };

      await tournamentAction(tournamentUid, 'UpsertDeck', {
        player_uid: targetUid,
        deck: deckData,
        multideck,
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

  const libraryByType = $derived.by(() => {
    const groups: Record<string, DisplayEntry[]> = {};
    for (const entry of libraryEntries) {
      const type = entry.card?.types[0] ?? 'Other';
      (groups[type] ??= []).push(entry);
    }
    const order = getLibraryTypeOrder();
    return Object.entries(groups).sort(([a], [b]) => {
      const ai = order.indexOf(a);
      const bi = order.indexOf(b);
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
    const normalized = normalizeSearch(card.full_name).replace(/[^a-z0-9]/g, '') + '.jpg';
    cardImageUrl = `https://static.krcg.org/card/${normalized}`;
  }
</script>

{#if editing}
  <input
    type="text"
    bind:value={editedName}
    placeholder={m.deck_upload_name_placeholder()}
    class="w-full px-3 py-2 mb-2 bg-surface-muted border border-line-strong rounded-lg text-ink-bright placeholder-ink-faint text-sm"
  />
  <textarea
    bind:value={editedComments}
    rows="3"
    placeholder={m.deck_comments_placeholder()}
    class="w-full px-3 py-2 mb-2 bg-surface-muted border border-line-strong rounded-lg text-ink-bright placeholder-ink-faint text-sm"
  ></textarea>

  <div class="mb-3">
    <CardSearch onselect={addCard} />
    <p class="text-xs text-ink-faint mt-1">{m.deck_edit_search_hint()}</p>
  </div>
{:else}
  {#if deck.name}
    <h4 class="text-sm font-semibold text-ink-strong mb-1">{deck.name}</h4>
  {/if}
  {#if deck.comments}
    <p class="text-sm text-ink whitespace-pre-line break-words mb-2">{deck.comments}</p>
  {/if}
  {#if editingCredit}
    <AttributionPicker bind:attribution={editedAttribution} />
    <div class="flex gap-2 mb-2">
      <Button variant="primary" size="lg" disabled={!isSettableCredit(editedAttribution)} onclick={saveCredit}>{m.common_save()}</Button>
      <Button variant="secondary" size="lg" onclick={() => editingCredit = false}>{m.common_cancel()}</Button>
    </div>
    {#if creditError}
      <p class="text-sm text-link mb-2">{creditError}</p>
    {/if}
  {:else if credit || anonymous || ownsDeck}
    <p class="text-xs text-ink-muted mb-2">
      {#if credit}{m.deck_by_author({ author: credit })}{:else if anonymous}{m.deck_credit_none()}{/if}
      {#if ownsDeck}
        <button class="text-link underline ml-1" onclick={startEditingCredit}>{m.deck_credit_edit()}</button>
      {/if}
    </p>
  {/if}

  {#if canSetPrivate}
    <label class="flex items-center gap-3 min-h-11 cursor-pointer">
      <input
        type="checkbox"
        checked={deck.private}
        onchange={setPrivate}
        class="w-5 h-5 rounded border-line-strong bg-surface-card text-accent focus:ring-accent"
      />
      <span class="text-sm text-ink-bright">{m.deck_private_label()}</span>
    </label>
    <p class="text-xs text-ink-faint mb-2">{m.deck_private_hint()}</p>
    {#if privacyError}
      <p class="text-sm text-link mb-2">{privacyError}</p>
    {/if}
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
