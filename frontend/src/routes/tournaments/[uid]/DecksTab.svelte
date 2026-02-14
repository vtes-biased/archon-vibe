<script lang="ts">
  import type { Tournament, Deck } from "$lib/types";
  import DeckUpload from "$lib/components/DeckUpload.svelte";
  import DeckDisplay from "$lib/components/DeckDisplay.svelte";
  import { getAuthState } from "$lib/stores/auth.svelte";

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
      >Download Report (Text)</a>
      <a
        href="{API_URL}/api/tournaments/{tournament.uid}/report?format=json"
        class="px-3 py-1.5 text-sm bg-ash-800 text-ash-200 hover:bg-ash-700 rounded-lg transition-colors"
        download
      >Download Report (JSON)</a>
    </div>
  {/if}

  <!-- Decklist required reminder -->
  {#if tournament.decklist_required && (tournament.state === 'Registration' || tournament.state === 'Waiting')}
    <div class="bg-amber-900/30 border border-amber-700/50 rounded-lg p-3 text-sm text-amber-200">
      {#if isOrganizer}
        Decklists are required. Players checking in without a decklist will receive a warning.
      {:else if isPlayer && myDecks.length === 0}
        A decklist is required for this tournament. Please upload your deck before check-in to avoid a warning sanction.
      {:else if isPlayer}
        Decklist submitted. You can replace it until the tournament starts.
      {:else}
        Decklists are required for this tournament.
      {/if}
    </div>
  {/if}

  <!-- Winner's deck nudge (post-tournament) -->
  {#if tournament.state === 'Finished' && winnerUid && !winnerHasDeck}
    {#if isWinner}
      <div class="bg-crimson-900/30 border border-crimson-700/50 rounded-lg p-3 text-sm text-crimson-200">
        Congratulations on your win! Your decklist is missing — please upload it so it can be preserved in the tournament records.
      </div>
    {:else if isOrganizer}
      <div class="bg-amber-900/30 border border-amber-700/50 rounded-lg p-3 text-sm text-amber-200">
        Winner's decklist is missing. Please remind {playerInfo[winnerUid]?.name ?? 'the winner'} to upload their deck.
      </div>
    {/if}
  {/if}

  <!-- Player's own deck upload -->
  {#if isPlayer && !isOrganizer}
    <div class="bg-ash-900/50 rounded-lg p-4">
      <h3 class="text-sm font-semibold text-bone-200 mb-3">My Deck</h3>
      {#if myDecks.length > 0 && myDecks[0]}
        <DeckDisplay deck={myDecks[0]} editable={canPlayerUpload} tournamentUid={tournament.uid} />
        {#if canPlayerUpload}
          <div class="mt-3">
            <button
              onclick={() => uploadingFor = myUid}
              class="text-sm text-crimson-400 hover:text-crimson-300"
            >Replace deck</button>
          </div>
        {/if}
      {:else}
        <p class="text-sm text-ash-400 mb-3">No deck uploaded yet</p>
      {/if}
      {#if canPlayerUpload && (uploadingFor === myUid || myDecks.length === 0)}
        <DeckUpload tournamentUid={tournament.uid} onuploaded={onUploaded} />
      {/if}
    </div>
  {/if}

  <!-- Organizer: all player decks -->
  {#if isOrganizer}
    <div class="space-y-3">
      <div class="flex items-center justify-between">
        <h3 class="text-sm font-semibold text-bone-200">Player Decks</h3>
        <span class="text-xs text-ash-500">
          {Object.keys(tournament.decks ?? {}).length} / {tournament.players?.length ?? 0} submitted
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
              {decks.length ? `${decks.length} deck(s)` : tournament.decklist_required ? 'Missing!' : 'No deck'}
            </span>
          </button>

          {#if expandedPlayer === uid}
            <div class="mt-3 space-y-3">
              {#each decks as deck}
                <DeckDisplay {deck} editable={true} tournamentUid={tournament.uid} playerUid={uid} />
              {/each}
              <button
                onclick={() => uploadingFor = uid}
                class="text-sm text-crimson-400 hover:text-crimson-300"
              >{decks.length ? 'Replace deck' : 'Upload deck'}</button>
              {#if uploadingFor === uid}
                <DeckUpload tournamentUid={tournament.uid} playerUid={uid} onuploaded={onUploaded} />
              {/if}
            </div>
          {/if}
        </div>
      {/each}
    </div>
  {/if}

  <!-- Visible decks (post-tournament or own) -->
  {#if !isOrganizer}
    {#each Object.entries(visibleDecks) as [uid, decks]}
      {#if uid !== myUid}
        <div class="bg-ash-900/50 rounded-lg p-4">
          <h3 class="text-sm font-semibold text-bone-200 mb-2">
            {playerInfo[uid]?.name ?? uid}'s Deck
          </h3>
          {#each decks as deck}
            <DeckDisplay {deck} />
          {/each}
        </div>
      {/if}
    {/each}
  {/if}
</div>
