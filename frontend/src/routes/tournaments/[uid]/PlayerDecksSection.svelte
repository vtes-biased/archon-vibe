<script lang="ts">
  import type { Tournament, DeckObject, VtesCard } from "$lib/types";
  import type { PlayerInfoMap } from "$lib/tournament-utils";
  import { roundsPlayed, seatDisplay } from "$lib/tournament-utils";
  import { getDecksByTournamentGrouped } from "$lib/db";
  import DeckUpload from "$lib/components/DeckUpload.svelte";
  import DeckDisplay from "$lib/components/DeckDisplay.svelte";
  import { getAuthState } from "$lib/stores/auth.svelte";
  import { tournamentAction } from "$lib/tournament-actions";
  import { showToast } from "$lib/stores/toast.svelte";
  import { toUserMessage } from "$lib/errors";
  import { getCards } from "$lib/cards";
  import { ChevronDown, ChevronRight, CircleCheck, Lock, Trash2, Trophy } from "@lucide/svelte";
  import { slide } from "svelte/transition";
  import DeckAccordion from "$lib/components/DeckAccordion.svelte";
  import Button from '$lib/components/Button.svelte';
  import * as m from '$lib/paraglide/messages.js';

  let {
    tournament,
    playerInfo,
    decksByUser: decksByUserProp,
  }: {
    tournament: Tournament;
    playerInfo: PlayerInfoMap;
    decksByUser?: Record<string, DeckObject[]>;
  } = $props();

  const auth = $derived(getAuthState());
  const myUid = $derived(auth.user?.uid ?? '');

  // Use parent-provided decksByUser if available, otherwise load locally
  let localDecks = $state<Record<string, DeckObject[]>>({});

  $effect(() => {
    if (!decksByUserProp) {
      getDecksByTournamentGrouped(tournament.uid).then(grouped => {
        localDecks = grouped;
      });
    }
  });

  const decksByUser = $derived(decksByUserProp ?? localDecks);

  const myDecks = $derived(decksByUser[myUid] ?? []);
  const myDecksByRound = $derived(new Map(myDecks.map(d => [d.round ?? 0, d])));
  const isPlayer = $derived(tournament.players?.some(p => p.user_uid === myUid) ?? false);
  const isMultideck = $derived(!!tournament.multideck);
  const maxRounds = $derived(tournament.max_rounds ?? 0);
  // Per-player rounds played (open rounds: each player progresses through the pool independently).
  const myRoundsPlayed = $derived(roundsPlayed(tournament, myUid));

  // For multideck: how many slots to show (this player's rounds played + 1 upcoming, capped by max_rounds)
  const deckSlotCount = $derived.by(() => {
    if (!isMultideck) return 1;
    const slots = myRoundsPlayed + 1;
    return maxRounds > 0 ? Math.min(slots, maxRounds) : slots;
  });

  let uploadingFor = $state<string | null>(null);
  let uploadingSlot = $state<number>(0);
  let expandedRoundIdx = $state<number | null>(null);
  let confirmDeleteSlot = $state<number | null>(null);
  let expandedDecks = $state<Set<string>>(new Set());
  let cardsDb = $state<Map<number, VtesCard>>(new Map());
  $effect(() => { getCards().then(c => cardsDb = c); });

  function toggleDeck(key: string) {
    const next = new Set(expandedDecks);
    if (next.has(key)) next.delete(key); else next.add(key);
    expandedDecks = next;
  }

  function deckCounts(deck: DeckObject): { crypt: number; library: number } {
    let crypt = 0, library = 0;
    for (const [idStr, count] of Object.entries(deck.cards)) {
      const card = cardsDb.get(parseInt(idStr));
      if (card?.kind === 'crypt') crypt += count; else library += count;
    }
    return { crypt, library };
  }

  function onUploaded() {
    uploadingFor = null;
    // Reload local decks from IDB after upload (when not using parent prop)
    if (!decksByUserProp) {
      getDecksByTournamentGrouped(tournament.uid).then(grouped => {
        localDecks = grouped;
      });
    }
  }

  function isDeckLocked(index: number): boolean {
    // Per-player (mirrors engine is_deck_locked): slot i locks once this player has played round i.
    return index < myRoundsPlayed;
  }

  function canModifySlot(index: number): boolean {
    const s = tournament.state;
    if (s === 'Finished') return false;
    if (s === 'Playing') {
      return isMultideck ? !isDeckLocked(index) : false;
    }
    // Planned, Registration, Waiting: always allowed
    return s === 'Planned' || s === 'Registration' || s === 'Waiting';
  }

  // Can the player upload (single-deck mode or first deck)
  const canPlayerUpload = $derived.by(() => {
    const s = tournament.state;
    if (s === 'Planned' || s === 'Registration' || s === 'Waiting') return true;
    if (s === 'Playing') return myDecks.length === 0;
    if (s === 'Finished') return myDecks.length === 0; // recovery
    return false;
  });

  // Can the player delete (single-deck mode)
  const canPlayerDelete = $derived.by(() => {
    const s = tournament.state;
    if (s === 'Planned' || s === 'Registration' || s === 'Waiting') return true;
    return false;
  });

  // Single-deck: player can edit before they've played any round or after the tournament ends
  const singleDeckEditable = $derived(myRoundsPlayed === 0 || tournament.state === 'Finished');

  async function deleteDeck(playerUid: string, deckIndex?: number) {
    try {
      await tournamentAction(tournament.uid, 'DeleteDeck', {
        player_uid: playerUid,
        deck_index: deckIndex ?? null,
        multideck: isMultideck,
      });
    } catch (e) {
      // Surface to the user (not console-only): tournamentAction's server-only
      // fallback no longer toasts, so this is the delete's error surface.
      console.error('Delete deck error:', e);
      showToast({ type: 'error', message: toUserMessage(e, m.tournament_error_action()) });
    }
  }

  // Winner info for nudges
  const winnerUid = $derived(tournament.winner ?? '');
  const winnerHasDeck = $derived(
    !!winnerUid && !!(decksByUser[winnerUid]?.length)
  );
  const isWinner = $derived(myUid === winnerUid);

  // Determine which decks are visible
  // IDB already has role-appropriate data (organizers see all, members see public+own).
  // Only client filter needed: decklists_mode for "visible decks" section post-tournament.
  const visibleDecks = $derived.by(() => {
    if (Object.keys(decksByUser).length === 0) return {};
    if (tournament.state !== 'Finished') return {};
    const mode = tournament.decklists_mode;
    if (!mode || mode === 'All') return decksByUser;
    const result: Record<string, DeckObject[]> = {};
    if (myUid && decksByUser[myUid]) result[myUid] = decksByUser[myUid];
    for (const [uid, decks] of Object.entries(decksByUser)) {
      if (uid === myUid) continue;
      if (mode === 'Winner' && uid === tournament.winner) result[uid] = decks;
      else if (mode === 'Finalists') {
        if (tournament.players?.find(p => p.user_uid === uid)?.finalist) result[uid] = decks;
      }
    }
    return result;
  });

  // Visible decks: entries for other players + total count (used in template)
  const deckEntries = $derived(Object.entries(visibleDecks).filter(([uid]) => uid !== myUid));
  const totalVisibleDecks = $derived(deckEntries.reduce((n, [, d]) => n + d.filter(Boolean).length, 0));
</script>

<div class="space-y-6">
  <!-- Decklist required reminder -->
  {#if tournament.decklist_required && tournament.state === 'Registration'}
    <div class="banner-warn border rounded-lg p-3 text-sm">
      {#if isPlayer && myDecks.length === 0}
        {m.decks_required_player_hint()}
      {:else if isPlayer}
        {m.decks_required_submitted()}
      {:else}
        {m.decks_required_notice()}
      {/if}
    </div>
  {:else if tournament.decklist_required && tournament.state === 'Waiting'}
    <!-- Check-in window: the loud message is "check in" (PlayerView banner). A
         present deck is the happy path → quiet note, not an amber warning. The
         no-deck penalty warning lives beside the check-in CTA in PlayerView. -->
    {#if isPlayer && myDecks.length > 0}
      <p class="text-xs text-ink-muted">{m.decks_submitted_note()}</p>
    {:else if !isPlayer}
      <div class="banner-warn border rounded-lg p-3 text-sm">{m.decks_required_notice()}</div>
    {/if}
  {/if}

  <!-- Winner's deck nudge (post-tournament) -->
  {#if tournament.state === 'Finished' && winnerUid && !winnerHasDeck}
    {#if isWinner}
      <div class="bg-accent-soft/30 border border-accent-strong/50 rounded-lg p-3 text-sm text-link-soft">
        {m.decks_winner_nudge_self()}
      </div>
    {/if}
  {/if}

  <!-- Player's own deck(s) -->
  {#if isPlayer}
    {#if isMultideck}
      <!-- Multideck: per-round slots (accordion) -->
      <div class="bg-surface-muted/50 rounded-lg p-3 sm:p-4 space-y-2">
        <h3 class="text-sm font-semibold text-ink-strong">{m.decks_my_decks()}</h3>
        {#each Array(deckSlotCount) as _, slotIdx}
          {@const deck = myDecksByRound.get(slotIdx) ?? null}
          {@const locked = isDeckLocked(slotIdx)}
          {@const canModify = canModifySlot(slotIdx)}
          {@const isExpanded = expandedRoundIdx === slotIdx}
          <DeckAccordion
            expanded={isExpanded}
            ontoggle={() => expandedRoundIdx = isExpanded ? null : slotIdx}
            roundLabel={m.decks_round_label({ n: String(slotIdx + 1) })}
            bgClass="bg-surface-muted/30"
          >
            {#snippet headerExtra()}
              {#if locked}
                <Lock class="w-3 h-3 text-ink-faint" />
              {/if}
              {#if deck}
                <CircleCheck class="w-3.5 h-3.5 text-info" />
              {:else}
                <span class="text-ink-faint truncate">{m.decks_no_deck()}</span>
              {/if}
            {/snippet}
            {#if uploadingFor === myUid && uploadingSlot === slotIdx}
              <DeckUpload tournamentUid={tournament.uid} round={slotIdx} onuploaded={onUploaded} />
            {:else if deck}
              <DeckDisplay
                {deck}
                editable={canModify}
                tournamentUid={tournament.uid}
                deckIndex={slotIdx}
                format={tournament.format}
                onreplace={canModify ? () => { uploadingFor = myUid; uploadingSlot = slotIdx; } : undefined}
                ondelete={canModify ? () => { confirmDeleteSlot = slotIdx; } : undefined}
              />
              {#if confirmDeleteSlot === slotIdx}
                <div class="mt-2 bg-accent-soft/20 border border-accent-soft-border/50 rounded-lg p-3 space-y-2">
                  <p class="text-sm text-link-soft font-medium">{m.decks_delete_confirm_title()}</p>
                  <p class="text-xs text-ink-muted">{m.decks_delete_confirm_msg()}</p>
                  <div class="flex gap-2">
                    <Button
                      variant="danger"
                      size="lg"
                      onclick={() => { deleteDeck(myUid, slotIdx); confirmDeleteSlot = null; }}
                    ><Trash2 class="w-4 h-4" aria-hidden="true" />{m.decks_delete_confirm_yes()}</Button>
                    <Button
                      variant="secondary"
                      onclick={() => confirmDeleteSlot = null}
                    >{m.common_cancel()}</Button>
                  </div>
                </div>
              {/if}
              {#if !canModify}
                <p class="text-sm text-ink-faint">{m.decks_locked()}</p>
              {/if}
            {:else if canModify}
              <Button
                variant="secondary"
                size="lg"
                onclick={() => { uploadingFor = myUid; uploadingSlot = slotIdx; }}
              >{m.decks_upload()}</Button>
            {:else}
              <p class="text-sm text-ink-faint">{m.decks_no_deck()}</p>
            {/if}
          </DeckAccordion>
        {/each}
      </div>
    {:else}
      <!-- Single-deck -->
      <div class="bg-surface-muted/50 rounded-lg">
        {#if myDecks.length > 0 && myDecks[0]}
          <!-- Folded by default and never auto-expanded: keeps a nearby opponent
               from inadvertently glancing at the player's own decklist. The
               check-in "Fix your deck" CTA scrolls here but deliberately leaves
               it collapsed. -->
          <button
            class="w-full flex items-center gap-3 p-3 sm:p-4 text-left min-h-[44px]"
            onclick={() => { const next = new Set(expandedDecks); if (next.has('my')) next.delete('my'); else next.add('my'); expandedDecks = next; }}
            aria-expanded={expandedDecks.has('my')}
          >
            <span class="text-ink-muted shrink-0">
              {#if expandedDecks.has('my')}<ChevronDown class="w-4 h-4" />{:else}<ChevronRight class="w-4 h-4" />{/if}
            </span>
            <span class="text-sm font-semibold text-ink-strong">{m.decks_my_deck()}</span>
          </button>
          {#if expandedDecks.has('my')}
            <div class="px-3 pb-3 sm:px-4 sm:pb-4" transition:slide={{ duration: 150 }}>
              {#if uploadingFor === myUid && singleDeckEditable}
                <DeckUpload tournamentUid={tournament.uid} onuploaded={onUploaded} />
              {:else}
                <DeckDisplay deck={myDecks[0]} editable={singleDeckEditable} tournamentUid={tournament.uid} format={tournament.format} onreplace={singleDeckEditable ? () => uploadingFor = myUid : undefined} ondelete={singleDeckEditable ? () => { confirmDeleteSlot = -1; } : undefined} />
                {#if confirmDeleteSlot === -1}
                  <div class="mt-2 bg-accent-soft/20 border border-accent-soft-border/50 rounded-lg p-3 space-y-2">
                    <p class="text-sm text-link-soft font-medium">{m.decks_delete_confirm_title()}</p>
                    <p class="text-xs text-ink-muted">{m.decks_delete_confirm_msg()}</p>
                    <div class="flex gap-2">
                      <Button
                        variant="danger"
                        size="lg"
                        onclick={() => { deleteDeck(myUid); confirmDeleteSlot = null; }}
                      ><Trash2 class="w-4 h-4" aria-hidden="true" />{m.decks_delete_confirm_yes()}</Button>
                      <Button
                        variant="secondary"
                        onclick={() => confirmDeleteSlot = null}
                      >{m.common_cancel()}</Button>
                    </div>
                  </div>
                {/if}
              {/if}
            </div>
          {/if}
        {:else if singleDeckEditable}
          <!-- The uploader is a screenful, so it waits behind its own button. -->
          {@const uploading = uploadingFor === myUid}
          <div class="p-3 sm:p-4 space-y-3">
            <div class="flex items-center justify-between gap-2">
              <h3 class="text-sm font-semibold text-ink-strong">{m.decks_my_deck()}</h3>
              <Button
                variant={uploading ? "secondary" : "primary"}
                onclick={() => (uploadingFor = uploading ? null : myUid)}
              >{uploading ? m.common_cancel() : m.decks_upload()}</Button>
            </div>
            {#if uploading}
              <DeckUpload tournamentUid={tournament.uid} onuploaded={onUploaded} />
            {/if}
          </div>
        {:else}
          <p class="p-3 sm:p-4 text-sm text-ink-muted">{m.decks_no_deck_yet()}</p>
        {/if}
      </div>
    {/if}
  {/if}

  <!-- Visible decks (post-tournament, collapsible) -->
  {#if deckEntries.length > 0}
    <div class="space-y-2">
      <div class="flex items-center justify-between">
        <h3 class="text-sm font-semibold text-ink-strong">{m.decks_visible_heading()}</h3>
        {#if totalVisibleDecks >= 5}
          <button
            class="text-xs text-ink-muted hover:text-ink-bright transition-colors"
            onclick={() => {
              if (expandedDecks.size >= totalVisibleDecks) {
                expandedDecks = new Set();
              } else {
                const all = new Set<string>();
                for (const [uid, decks] of deckEntries) {
                  for (let i = 0; i < decks.length; i++) {
                    if (decks[i]) all.add(`${uid}-${i}`);
                  }
                }
                expandedDecks = all;
              }
            }}
          >
            {expandedDecks.size >= totalVisibleDecks ? m.decks_collapse_all() : m.decks_expand_all()}
          </button>
        {/if}
      </div>
        {#each deckEntries as [uid, decks]}
          {#each decks as deck, i}
            {#if deck}
              {@const key = `${uid}-${i}`}
              {@const expanded = expandedDecks.has(key)}
              {@const counts = deckCounts(deck)}
              {@const showIdentity = tournament.decklists_mode !== 'All' || uid === winnerUid}
              {@const isWinnerDeck = uid === winnerUid}
              <div class="bg-surface-muted/50 rounded-lg">
                <button
                  class="w-full flex items-center gap-3 p-3 sm:p-4 text-left min-h-[44px]"
                  onclick={() => toggleDeck(key)}
                  aria-expanded={expanded}
                >
                  <span class="text-ink-muted shrink-0">
                    {#if expanded}<ChevronDown class="w-4 h-4" />{:else}<ChevronRight class="w-4 h-4" />{/if}
                  </span>
                  <div class="flex-1 min-w-0">
                    {#if showIdentity}
                      {#if isWinnerDeck}
                        <span class="text-sm font-semibold text-highlight truncate flex items-center gap-1.5">
                          <Trophy class="w-3.5 h-3.5 shrink-0" aria-hidden="true" />
                          <span class="truncate">{seatDisplay(uid, playerInfo, tournament.online)}</span>
                          <span class="text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded badge-highlight shrink-0">{m.tournament_winner()}</span>
                        </span>
                      {:else}
                        <span class="text-sm text-ink-bright truncate block">{seatDisplay(uid, playerInfo, tournament.online)}</span>
                      {/if}
                    {/if}
                    <span class="text-ink-muted truncate block {showIdentity ? 'text-xs' : 'text-sm'}">
                      {#if isMultideck}<span class="text-ink-faint">{m.decks_round_label({ n: String(i + 1) })}</span> — {/if}
                      {deck.name || m.decks_unnamed()}
                    </span>
                  </div>
                  <span class="text-xs text-ink-faint shrink-0 whitespace-nowrap">
                    {counts.crypt}/{counts.library}
                  </span>
                </button>
                {#if expanded}
                  <div class="px-3 pb-3 sm:px-4 sm:pb-4" transition:slide={{ duration: 150 }}>
                    <DeckDisplay {deck} format={tournament.format} />
                  </div>
                {/if}
              </div>
            {/if}
          {/each}
        {/each}
      </div>
    {/if}
</div>
