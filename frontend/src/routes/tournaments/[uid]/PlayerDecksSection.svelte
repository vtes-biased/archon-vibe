<script lang="ts">
  import type { Tournament, DeckObject, VtesCard } from "$lib/types";
  import type { PlayerInfoMap } from "$lib/tournament-utils";
  import { roundsPlayed, seatDisplay } from "$lib/tournament-utils";
  import { getDecksByTournamentGrouped } from "$lib/db";
  import DeckUpload from "$lib/components/DeckUpload.svelte";
  import DeckDisplay from "$lib/components/DeckDisplay.svelte";
  import { getAuthState } from "$lib/stores/auth.svelte";
  import { tournamentAction } from "$lib/tournament-actions";
  import { toUserMessage } from "$lib/errors";
  import { getCards } from "$lib/cards";
  import { ChevronDown, ChevronRight, CircleCheck, Lock, Trash2, Trophy } from "@lucide/svelte";
  import { slide } from "svelte/transition";
  import FoldableSection from "$lib/components/FoldableSection.svelte";
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
  const isPlayer = $derived(tournament.players?.some(p => p.user_uid === myUid) ?? false);
  const isMultideck = $derived(!!tournament.multideck);
  const maxRounds = $derived(tournament.max_rounds ?? 0);
  // Per-player rounds played (open rounds: each player progresses through the pool independently).
  const myRoundsPlayed = $derived(roundsPlayed(tournament, myUid));
  const roundCount = $derived(tournament.rounds?.length ?? 0);

  const myStamped = $derived(
    myDecks.filter(d => d.round !== null).sort((a, b) => (a.round ?? 0) - (b.round ?? 0)),
  );
  const myPending = $derived(myDecks.find(d => d.round === null) ?? null);
  const showPendingSlot = $derived(
    !!myPending || maxRounds === 0 || myRoundsPlayed < maxRounds,
  );

  // Accordion key: a stamped deck's round, or PENDING for the not-yet-played one.
  const PENDING = -1;
  let uploadingFor = $state<string | null>(null);
  let expandedRoundIdx = $state<number | null>(null);
  let confirmDeletePending = $state(false);
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
    if (!decksByUserProp) {
      getDecksByTournamentGrouped(tournament.uid).then(grouped => {
        localDecks = grouped;
      });
    }
  }

  // Only a format switch can have left a deck on a Storyline event, and the
  // engine freezes it: UpsertDeck refuses.
  const isStoryline = $derived(tournament.format === 'Storyline');
  const canModifyPending = $derived(tournament.state !== 'Finished' && !isStoryline);

  // Post-tournament recovery aside, a single-deck event's registered deck is
  // frozen once play starts — the engine's own rule.
  const singleDeckEditable = $derived(
    isStoryline
      ? false
      : tournament.state === 'Playing'
        ? false
        : tournament.state !== 'Finished' || myDecks.length === 0,
  );

  function roundLabel(round: number | null): string {
    if (round === null) return m.decks_next_round();
    if (round >= roundCount) return m.tournament_finals_heading();
    return m.decks_round_label({ n: String(round + 1) });
  }

  let deleteError = $state<string | null>(null);

  async function deleteDeck(playerUid: string) {
    deleteError = null;
    try {
      await tournamentAction(tournament.uid, 'DeleteDeck', {
        player_uid: playerUid,
        deck_index: null,
        multideck: isMultideck,
      });
    } catch (e) {
      deleteError = toUserMessage(e, m.tournament_error_action());
    }
  }

  const winnerUid = $derived(tournament.winner ?? '');
  const winnerHasDeck = $derived(
    !!winnerUid && !!(decksByUser[winnerUid]?.length)
  );
  const isWinner = $derived(myUid === winnerUid);

  // IDB already has role-appropriate data (organizers see all, members see
  // public+own); only decklists_mode needs a client filter, for the
  // post-tournament visible-decks section.
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

  const deckEntries = $derived(Object.entries(visibleDecks).filter(([uid]) => uid !== myUid));
  const totalVisibleDecks = $derived(deckEntries.reduce((n, [, d]) => n + d.filter(Boolean).length, 0));
</script>

<div class="space-y-6">
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
    <!-- The loud message here is check-in (PlayerView banner); a deck present is
         the happy path, so this stays a quiet note. The no-deck penalty warning
         lives beside the check-in CTA in PlayerView. -->
    {#if isPlayer && myDecks.length > 0}
      <p class="text-xs text-ink-muted">{m.decks_submitted_note()}</p>
    {:else if !isPlayer}
      <div class="banner-warn border rounded-lg p-3 text-sm">{m.decks_required_notice()}</div>
    {/if}
  {/if}

  {#if !isStoryline && tournament.state === 'Finished' && winnerUid && !winnerHasDeck}
    {#if isWinner}
      <div class="bg-accent-soft/30 border border-accent-strong/50 rounded-lg p-3 text-sm text-link-soft">
        {m.decks_winner_nudge_self()}
      </div>
    {/if}
  {/if}

  {#if isPlayer && (!isStoryline || myDecks.length > 0)}
    {#if isMultideck}
      <div class="bg-surface-muted/50 rounded-lg p-3 sm:p-4 space-y-2">
        <h3 class="text-sm font-semibold text-ink-strong">{m.decks_my_decks()}</h3>
        {#each myStamped as deck (deck.uid)}
          {@const isExpanded = expandedRoundIdx === deck.round}
          <FoldableSection
            open={isExpanded}
            ontoggle={() => expandedRoundIdx = isExpanded ? null : deck.round}
            title={roundLabel(deck.round)}
          >
            {#snippet header()}
              <Lock class="w-3 h-3 text-ink-faint" />
              <CircleCheck class="w-3.5 h-3.5 text-info" />
            {/snippet}
            <DeckDisplay {deck} tournamentUid={tournament.uid} format={tournament.format} />
            <p class="text-sm text-ink-faint">{m.decks_locked()}</p>
          </FoldableSection>
        {/each}
        {#if showPendingSlot}
          {@const isExpanded = expandedRoundIdx === PENDING}
          <FoldableSection
            open={isExpanded}
            ontoggle={() => expandedRoundIdx = isExpanded ? null : PENDING}
            title={m.decks_next_round()}
          >
            {#snippet header()}
              {#if myPending}
                <CircleCheck class="w-3.5 h-3.5 text-info" />
              {:else}
                <span class="text-ink-faint truncate">{m.decks_no_deck()}</span>
              {/if}
            {/snippet}
            {#if uploadingFor === myUid}
              <DeckUpload tournamentUid={tournament.uid} multideck onuploaded={onUploaded} />
            {:else if myPending}
              <DeckDisplay
                deck={myPending}
                editable={canModifyPending}
                tournamentUid={tournament.uid}
                multideck
                format={tournament.format}
                onreplace={canModifyPending ? () => { uploadingFor = myUid; } : undefined}
                ondelete={canModifyPending ? () => { confirmDeletePending = true; } : undefined}
              />
              {#if confirmDeletePending}
                <div class="mt-2 bg-accent-soft/20 border border-accent-soft-border/50 rounded-lg p-3 space-y-2">
                  <p class="text-sm text-link-soft font-medium">{m.decks_delete_confirm_title()}</p>
                  <p class="text-xs text-ink-muted">{m.decks_delete_confirm_msg()}</p>
                  <div class="flex gap-2">
                    <Button
                      variant="danger"
                      size="lg"
                      onclick={() => { deleteDeck(myUid); confirmDeletePending = false; }}
                    ><Trash2 class="w-4 h-4" aria-hidden="true" />{m.decks_delete_confirm_yes()}</Button>
                    <Button
                      variant="secondary"
                      onclick={() => confirmDeletePending = false}
                    >{m.common_cancel()}</Button>
                  </div>
                </div>
              {/if}
              {#if deleteError}
                <div class="mt-2 bg-accent-soft/20 border border-accent-soft-border rounded-lg p-3">
                  <p class="text-link-soft text-sm">{deleteError}</p>
                </div>
              {/if}
              {#if !canModifyPending}
                <p class="text-sm text-ink-faint">{m.decks_locked()}</p>
              {/if}
            {:else if canModifyPending}
              <Button
                variant="secondary"
                size="lg"
                onclick={() => { uploadingFor = myUid; }}
              >{m.decks_upload()}</Button>
            {:else}
              <p class="text-sm text-ink-faint">{m.decks_no_deck()}</p>
            {/if}
          </FoldableSection>
        {/if}
      </div>
    {:else}
      <div>
        {#if myDecks.length > 0 && myDecks[0]}
          <!-- Folded by default, never auto-expanded: keeps a nearby opponent
               from glancing at the decklist. The check-in "Fix your deck" CTA
               scrolls here but leaves it collapsed. -->
          <FoldableSection
            title={m.decks_my_deck()}
            open={expandedDecks.has('my')}
            ontoggle={() => toggleDeck('my')}
          >
            <div>
              {#if uploadingFor === myUid && singleDeckEditable}
                <DeckUpload tournamentUid={tournament.uid} onuploaded={onUploaded} />
              {:else}
                <DeckDisplay deck={myDecks[0]} editable={singleDeckEditable} tournamentUid={tournament.uid} format={tournament.format} onreplace={singleDeckEditable ? () => uploadingFor = myUid : undefined} ondelete={singleDeckEditable ? () => { confirmDeletePending = true; } : undefined} />
                {#if confirmDeletePending}
                  <div class="mt-2 bg-accent-soft/20 border border-accent-soft-border/50 rounded-lg p-3 space-y-2">
                    <p class="text-sm text-link-soft font-medium">{m.decks_delete_confirm_title()}</p>
                    <p class="text-xs text-ink-muted">{m.decks_delete_confirm_msg()}</p>
                    <div class="flex gap-2">
                      <Button
                        variant="danger"
                        size="lg"
                        onclick={() => { deleteDeck(myUid); confirmDeletePending = false; }}
                      ><Trash2 class="w-4 h-4" aria-hidden="true" />{m.decks_delete_confirm_yes()}</Button>
                      <Button
                        variant="secondary"
                        onclick={() => confirmDeletePending = false}
                      >{m.common_cancel()}</Button>
                    </div>
                  </div>
                {/if}
                {#if deleteError}
                  <div class="mt-2 bg-accent-soft/20 border border-accent-soft-border rounded-lg p-3">
                    <p class="text-link-soft text-sm">{deleteError}</p>
                  </div>
                {/if}
              {/if}
            </div>
          </FoldableSection>
        {:else if singleDeckEditable}
          <!-- The uploader is a screenful, so it waits behind its own button. -->
          {@const uploading = uploadingFor === myUid}
          <div class="bg-surface-muted/50 rounded-lg p-3 sm:p-4 space-y-3">
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
          <p class="bg-surface-muted/50 rounded-lg p-3 sm:p-4 text-sm text-ink-muted">{m.decks_no_deck_yet()}</p>
        {/if}
      </div>
    {/if}
  {/if}

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
                      {#if isMultideck}<span class="text-ink-faint">{roundLabel(deck.round)}</span> — {/if}
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
