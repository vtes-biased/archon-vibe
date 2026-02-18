<script lang="ts">
  import type { Tournament, Deck, VtesCard } from "$lib/types";
  import DeckUpload from "$lib/components/DeckUpload.svelte";
  import DeckDisplay from "$lib/components/DeckDisplay.svelte";
  import { getAuthState } from "$lib/stores/auth.svelte";
  import { getCards } from "$lib/cards";
  import { ChevronDown, ChevronRight } from "lucide-svelte";
  import { slide } from "svelte/transition";
  import * as m from '$lib/paraglide/messages.js';

  let {
    tournament,
    playerInfo,
    isOrganizer = false,
  }: {
    tournament: Tournament;
    playerInfo: Record<string, { name: string; nickname: string | null; vekn: string | null }>;
    isOrganizer?: boolean;
  } = $props();

  const auth = $derived(getAuthState());
  const myUid = $derived(auth.user?.uid ?? '');
  const myDecks = $derived(tournament.decks?.[myUid] ?? []);
  const isPlayer = $derived(tournament.players?.some(p => p.user_uid === myUid) ?? false);

  let uploadingFor = $state<string | null>(null);
  let expandedPlayer = $state<string | null>(null);
  let expandedDecks = $state<Set<string>>(new Set());
  let cardsDb = $state<Map<number, VtesCard>>(new Map());

  $effect(() => { getCards().then(c => cardsDb = c); });

  function toggleDeck(key: string) {
    const next = new Set(expandedDecks);
    if (next.has(key)) next.delete(key); else next.add(key);
    expandedDecks = next;
  }

  function deckCounts(deck: Deck): { crypt: number; library: number } {
    let crypt = 0, library = 0;
    for (const [idStr, count] of Object.entries(deck.cards)) {
      const card = cardsDb.get(parseInt(idStr));
      if (card?.kind === 'crypt') crypt += count; else library += count;
    }
    return { crypt, library };
  }

  function onUploaded() {
    uploadingFor = null;
  }

  // Can the player modify their deck in the current state?
  const canPlayerUpload = $derived.by(() => {
    if (isOrganizer) return true;
    const s = tournament.state;
    if (s === 'Planned' || s === 'Registration' || s === 'Waiting') return true;
    if (s === 'Playing') return myDecks.length === 0; // only if no deck yet (multideck handled separately)
    if (s === 'Finished') return myDecks.length === 0; // recovery: missing deck only
    return false;
  });

  // Winner info for nudges
  const winnerUid = $derived(tournament.winner ?? '');
  const winnerHasDeck = $derived(
    !!winnerUid && !!(tournament.decks?.[winnerUid]?.length)
  );
  const isWinner = $derived(myUid === winnerUid);

  // Determine which decks are visible
  const visibleDecks = $derived.by(() => {
    if (!tournament.decks) return {};
    if (isOrganizer) return tournament.decks;
    // Players see their own deck always
    const result: Record<string, Deck[]> = {};
    if (myUid && tournament.decks[myUid]) {
      result[myUid] = tournament.decks[myUid];
    }
    // Post-tournament: visible per decklists_mode
    if (tournament.state === 'Finished' && tournament.decklists_mode) {
      for (const [uid, decks] of Object.entries(tournament.decks)) {
        if (uid === myUid) continue;
        if (tournament.decklists_mode === 'All') {
          result[uid] = decks;
        } else if (tournament.decklists_mode === 'Winner' && uid === tournament.winner) {
          result[uid] = decks;
        } else if (tournament.decklists_mode === 'Finalists') {
          const player = tournament.players?.find(p => p.user_uid === uid);
          if (player?.finalist) result[uid] = decks;
        }
      }
    }
    return result;
  });
</script>

<div class="space-y-6">
  <!-- Download Report (organizer, finished tournament) -->
  {#if isOrganizer && tournament.state === 'Finished'}
    {@const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'}
    <div class="flex gap-2">
      <a
        href="{API_URL}/api/tournaments/{tournament.uid}/report?format=text"
        class="px-3 py-1.5 text-sm bg-ash-800 text-ash-200 hover:bg-ash-700 rounded-lg transition-colors"
        download
      >{m.decks_download_report_text()}</a>
      <a
        href="{API_URL}/api/tournaments/{tournament.uid}/report?format=json"
        class="px-3 py-1.5 text-sm bg-ash-800 text-ash-200 hover:bg-ash-700 rounded-lg transition-colors"
        download
      >{m.decks_download_report_json()}</a>
    </div>
  {/if}

  <!-- Decklist required reminder -->
  {#if tournament.decklist_required && (tournament.state === 'Registration' || tournament.state === 'Waiting')}
    <div class="banner-amber border rounded-lg p-3 text-sm">
      {#if isOrganizer}
        {m.decks_required_organizer_hint()}
      {:else if isPlayer && myDecks.length === 0}
        {m.decks_required_player_hint()}
      {:else if isPlayer}
        {m.decks_required_submitted()}
      {:else}
        {m.decks_required_notice()}
      {/if}
    </div>
  {/if}

  <!-- Winner's deck nudge (post-tournament) -->
  {#if tournament.state === 'Finished' && winnerUid && !winnerHasDeck}
    {#if isWinner}
      <div class="bg-crimson-900/30 border border-crimson-700/50 rounded-lg p-3 text-sm text-crimson-200">
        {m.decks_winner_nudge_self()}
      </div>
    {:else if isOrganizer}
      <div class="banner-amber border rounded-lg p-3 text-sm">
        {m.decks_winner_nudge_organizer({ name: playerInfo[winnerUid]?.name ?? 'the winner' })}
      </div>
    {/if}
  {/if}

  <!-- Player's own deck -->
  {#if isPlayer && !isOrganizer}
    <div class="bg-ash-900/50 rounded-lg">
      {#if myDecks.length > 0 && myDecks[0] && !canPlayerUpload && uploadingFor !== myUid}
        <!-- Collapsible when deck exists and not editing -->
        <button
          class="w-full flex items-center gap-3 p-3 sm:p-4 text-left min-h-[44px]"
          onclick={() => { const next = new Set(expandedDecks); if (next.has('my')) next.delete('my'); else next.add('my'); expandedDecks = next; }}
          aria-expanded={expandedDecks.has('my')}
        >
          <span class="text-ash-400 shrink-0">
            {#if expandedDecks.has('my')}<ChevronDown class="w-4 h-4" />{:else}<ChevronRight class="w-4 h-4" />{/if}
          </span>
          <span class="text-sm font-semibold text-bone-200">{m.decks_my_deck()}</span>
        </button>
        {#if expandedDecks.has('my')}
          <div class="px-3 pb-3 sm:px-4 sm:pb-4" transition:slide={{ duration: 150 }}>
            <DeckDisplay deck={myDecks[0]} editable={canPlayerUpload} tournamentUid={tournament.uid} onreplace={canPlayerUpload ? () => uploadingFor = myUid : undefined} />
          </div>
        {/if}
      {:else}
        <!-- Always expanded when uploading or no deck yet -->
        <div class="p-3 sm:p-4">
          <h3 class="text-sm font-semibold text-bone-200 mb-3">{m.decks_my_deck()}</h3>
          {#if canPlayerUpload && (uploadingFor === myUid || myDecks.length === 0)}
            <DeckUpload tournamentUid={tournament.uid} onuploaded={onUploaded} />
          {:else if myDecks.length > 0 && myDecks[0]}
            <DeckDisplay deck={myDecks[0]} editable={canPlayerUpload} tournamentUid={tournament.uid} onreplace={canPlayerUpload ? () => uploadingFor = myUid : undefined} />
          {:else}
            <p class="text-sm text-ash-400">{m.decks_no_deck_yet()}</p>
          {/if}
        </div>
      {/if}
    </div>
  {/if}

  <!-- Organizer: all player decks -->
  {#if isOrganizer}
    <div class="space-y-3">
      <div class="flex items-center justify-between">
        <h3 class="text-sm font-semibold text-bone-200">{m.decks_player_decks()}</h3>
        <span class="text-xs text-ash-500">
          {m.decks_submitted_count({ submitted: String(Object.keys(tournament.decks ?? {}).length), total: String(tournament.players?.length ?? 0) })}
        </span>
      </div>

      {#each tournament.players ?? [] as player}
        {@const uid = player.user_uid ?? ''}
        {@const decks = tournament.decks?.[uid] ?? []}
        {@const info = playerInfo[uid]}
        <div class="bg-ash-900/50 rounded-lg p-3">
          <button
            class="w-full flex items-center justify-between text-left"
            onclick={() => expandedPlayer = expandedPlayer === uid ? null : uid}
          >
            <span class="text-sm text-ash-200">{info?.name ?? uid}</span>
            <span class="text-xs {decks.length ? 'text-emerald-400' : tournament.decklist_required ? 'text-amber-400' : 'text-ash-500'}">
              {decks.length ? m.decks_deck_count({ count: String(decks.length) }) : tournament.decklist_required ? m.decks_missing() : m.decks_no_deck()}
            </span>
          </button>

          {#if expandedPlayer === uid}
            <div class="mt-3 space-y-3">
              {#if uploadingFor === uid}
                <DeckUpload tournamentUid={tournament.uid} playerUid={uid} playerName={info?.name} playerVekn={info?.vekn ?? undefined} onuploaded={onUploaded} />
              {:else}
                {#each decks as deck}
                  <DeckDisplay {deck} editable={true} tournamentUid={tournament.uid} playerUid={uid} onreplace={() => uploadingFor = uid} />
                {/each}
                {#if !decks.length}
                  <button
                    onclick={() => uploadingFor = uid}
                    class="px-3 py-1.5 text-sm font-medium text-ash-200 bg-ash-800 hover:bg-ash-700 rounded-lg transition-colors"
                  >{m.decks_upload()}</button>
                {/if}
              {/if}
            </div>
          {/if}
        </div>
      {/each}
    </div>
  {/if}

  <!-- Visible decks (post-tournament, collapsible) -->
  {#if !isOrganizer}
    {@const deckEntries = Object.entries(visibleDecks).filter(([uid]) => uid !== myUid)}
    {@const totalDecks = deckEntries.reduce((n, [, d]) => n + d.length, 0)}
    {#if deckEntries.length > 0}
      <div class="space-y-2">
        <div class="flex items-center justify-between">
          <h3 class="text-sm font-semibold text-bone-200">{m.decks_visible_heading()}</h3>
          {#if totalDecks >= 5}
            <button
              class="text-xs text-ash-400 hover:text-ash-200 transition-colors"
              onclick={() => {
                if (expandedDecks.size >= totalDecks) {
                  expandedDecks = new Set();
                } else {
                  const all = new Set<string>();
                  for (const [uid, decks] of deckEntries) {
                    for (let i = 0; i < decks.length; i++) all.add(`${uid}-${i}`);
                  }
                  expandedDecks = all;
                }
              }}
            >
              {expandedDecks.size >= totalDecks ? m.decks_collapse_all() : m.decks_expand_all()}
            </button>
          {/if}
        </div>
        {#each deckEntries as [uid, decks]}
          {#each decks as deck, i}
            {@const key = `${uid}-${i}`}
            {@const expanded = expandedDecks.has(key)}
            {@const counts = deckCounts(deck)}
            {@const showIdentity = tournament.decklists_mode !== 'All'}
            <div class="bg-ash-900/50 rounded-lg">
              <button
                class="w-full flex items-center gap-3 p-3 sm:p-4 text-left min-h-[44px]"
                onclick={() => toggleDeck(key)}
                aria-expanded={expanded}
              >
                <span class="text-ash-400 shrink-0">
                  {#if expanded}<ChevronDown class="w-4 h-4" />{:else}<ChevronRight class="w-4 h-4" />{/if}
                </span>
                <div class="flex-1 min-w-0">
                  {#if showIdentity}
                    <span class="text-sm text-ash-200 truncate block">{playerInfo[uid]?.name ?? uid}</span>
                  {/if}
                  <span class="text-ash-400 truncate block {showIdentity ? 'text-xs' : 'text-sm'}">
                    {deck.name || m.decks_unnamed()}
                  </span>
                </div>
                <span class="text-xs text-ash-500 shrink-0 whitespace-nowrap">
                  {counts.crypt}/{counts.library}
                </span>
              </button>
              {#if expanded}
                <div class="px-3 pb-3 sm:px-4 sm:pb-4" transition:slide={{ duration: 150 }}>
                  <DeckDisplay {deck} />
                </div>
              {/if}
            </div>
          {/each}
        {/each}
      </div>
    {/if}
  {/if}
</div>
