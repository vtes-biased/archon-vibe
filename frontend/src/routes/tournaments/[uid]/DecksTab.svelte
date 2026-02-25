<script lang="ts">
  import type { Tournament, DeckObject, VtesCard } from "$lib/types";
  import { getDecksByTournamentGrouped } from "$lib/db";
  import DeckUpload from "$lib/components/DeckUpload.svelte";
  import DeckDisplay from "$lib/components/DeckDisplay.svelte";
  import { getAuthState } from "$lib/stores/auth.svelte";
  import { getCards } from "$lib/cards";
  import { ChevronDown, ChevronRight, Lock } from "lucide-svelte";
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

  // Load decks from IDB (separate store, not tournament.decks)
  let decksByUser = $state<Record<string, DeckObject[]>>({});

  $effect(() => {
    const tUid = tournament.uid;
    getDecksByTournamentGrouped(tUid).then(grouped => {
      decksByUser = grouped;
    });
  });

  const myDecks = $derived(decksByUser[myUid] ?? []);
  const isPlayer = $derived(tournament.players?.some(p => p.user_uid === myUid) ?? false);
  const isMultideck = $derived(!!tournament.multideck);
  const roundCount = $derived(tournament.rounds?.length ?? 0);
  const maxRounds = $derived(tournament.max_rounds ?? 0);

  // For multideck: how many slots to show (rounds played + 1 for upcoming, capped by max_rounds)
  const deckSlotCount = $derived.by(() => {
    if (!isMultideck) return 1;
    const slots = roundCount + 1;
    return maxRounds > 0 ? Math.min(slots, maxRounds) : slots;
  });

  let uploadingFor = $state<string | null>(null);
  let uploadingSlot = $state<number>(0);
  let expandedPlayer = $state<string | null>(null);
  let expandedDecks = $state<Set<string>>(new Set());
  let cardsDb = $state<Map<number, VtesCard>>(new Map());
  let deleteLoading = $state(false);

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
    // Reload decks from IDB after upload
    getDecksByTournamentGrouped(tournament.uid).then(grouped => {
      decksByUser = grouped;
    });
  }

  function isDeckLocked(index: number): boolean {
    return index < roundCount;
  }

  function canModifySlot(index: number): boolean {
    if (isOrganizer) return true;
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
    if (isOrganizer) return true;
    const s = tournament.state;
    if (s === 'Planned' || s === 'Registration' || s === 'Waiting') return true;
    if (s === 'Playing') return myDecks.length === 0;
    if (s === 'Finished') return myDecks.length === 0; // recovery
    return false;
  });

  // Can the player delete (single-deck mode)
  const canPlayerDelete = $derived.by(() => {
    if (isOrganizer) return true;
    const s = tournament.state;
    if (s === 'Planned' || s === 'Registration' || s === 'Waiting') return true;
    return false;
  });

  // Single-deck: player can edit before first round or after tournament ends
  const singleDeckEditable = $derived(roundCount === 0 || tournament.state === 'Finished');

  // Organizer deck visibility: hide contents until the round for this deck has started
  function isDeckVisibleToOrganizer(slotIdx: number): boolean {
    if (tournament.state === 'Finished') return true;
    return isMultideck ? slotIdx < roundCount : roundCount > 0;
  }

  async function deleteDeck(playerUid: string, deckIndex?: number) {
    deleteLoading = true;
    try {
      const token = (await import('$lib/stores/auth.svelte')).getAccessToken();
      const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
      const params = deckIndex !== undefined ? `?deck_index=${deckIndex}` : '';
      const resp = await fetch(`${API_URL}/api/tournaments/${tournament.uid}/decks/${playerUid}${params}`, {
        method: 'DELETE',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        console.error('Delete deck failed:', data.detail || resp.status);
      }
    } catch (e) {
      console.error('Delete deck error:', e);
    } finally {
      deleteLoading = false;
    }
  }

  // Winner info for nudges
  const winnerUid = $derived(tournament.winner ?? '');
  const winnerHasDeck = $derived(
    !!winnerUid && !!(decksByUser[winnerUid]?.length)
  );
  const isWinner = $derived(myUid === winnerUid);

  // Determine which decks are visible
  const visibleDecks = $derived.by(() => {
    if (Object.keys(decksByUser).length === 0) return {};
    if (isOrganizer) return decksByUser;
    // Players see their own deck always
    const result: Record<string, DeckObject[]> = {};
    if (myUid && decksByUser[myUid]) {
      result[myUid] = decksByUser[myUid];
    }
    if (tournament.state === 'Finished' && tournament.decklists_mode) {
      for (const [uid, decks] of Object.entries(decksByUser)) {
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

  <!-- Player's own deck(s) -->
  {#if isPlayer && !isOrganizer}
    {#if isMultideck}
      <!-- Multideck: per-round slots -->
      <div class="bg-ash-900/50 rounded-lg p-3 sm:p-4 space-y-4">
        <h3 class="text-sm font-semibold text-bone-200">{m.decks_my_decks()}</h3>
        {#each Array(deckSlotCount) as _, slotIdx}
          {@const deck = myDecks[slotIdx] ?? null}
          {@const locked = isDeckLocked(slotIdx)}
          {@const canModify = canModifySlot(slotIdx)}
          <div class="border-t border-ash-800 pt-3 first:border-0 first:pt-0">
            <div class="flex items-center gap-2 mb-2">
              <span class="text-xs font-medium text-ash-400">{m.decks_round_label({ n: String(slotIdx + 1) })}</span>
              {#if locked}
                <span class="inline-flex items-center gap-1 text-xs text-ash-500">
                  <Lock class="w-3 h-3" />
                  {m.decks_locked()}
                </span>
              {/if}
            </div>
            {#if uploadingFor === myUid && uploadingSlot === slotIdx}
              <DeckUpload tournamentUid={tournament.uid} onuploaded={onUploaded} />
            {:else if deck}
              <DeckDisplay
                {deck}
                editable={canModify}
                tournamentUid={tournament.uid}
                deckIndex={slotIdx}
                format={tournament.format}
                onreplace={canModify ? () => { uploadingFor = myUid; uploadingSlot = slotIdx; } : undefined}
                ondelete={canModify ? () => deleteDeck(myUid, slotIdx) : undefined}
              />
            {:else if canModify}
              <button
                onclick={() => { uploadingFor = myUid; uploadingSlot = slotIdx; }}
                class="px-3 py-1.5 text-sm font-medium text-ash-200 bg-ash-800 hover:bg-ash-700 rounded-lg transition-colors"
              >{m.decks_upload()}</button>
            {:else}
              <p class="text-sm text-ash-500">{m.decks_no_deck()}</p>
            {/if}
          </div>
        {/each}
      </div>
    {:else}
      <!-- Single-deck -->
      <div class="bg-ash-900/50 rounded-lg">
        {#if myDecks.length > 0 && myDecks[0] && uploadingFor !== myUid}
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
              <DeckDisplay deck={myDecks[0]} editable={singleDeckEditable} tournamentUid={tournament.uid} format={tournament.format} onreplace={singleDeckEditable ? () => uploadingFor = myUid : undefined} ondelete={singleDeckEditable ? () => deleteDeck(myUid) : undefined} />
            </div>
          {/if}
        {:else}
          <div class="p-3 sm:p-4">
            <h3 class="text-sm font-semibold text-bone-200 mb-3">{m.decks_my_deck()}</h3>
            {#if singleDeckEditable && (uploadingFor === myUid || myDecks.length === 0)}
              <DeckUpload tournamentUid={tournament.uid} onuploaded={onUploaded} />
            {:else if myDecks.length > 0 && myDecks[0]}
              <DeckDisplay deck={myDecks[0]} editable={singleDeckEditable} tournamentUid={tournament.uid} format={tournament.format} onreplace={singleDeckEditable ? () => uploadingFor = myUid : undefined} ondelete={singleDeckEditable ? () => deleteDeck(myUid) : undefined} />
            {:else}
              <p class="text-sm text-ash-400">{m.decks_no_deck_yet()}</p>
            {/if}
          </div>
        {/if}
      </div>
    {/if}
  {/if}

  <!-- Organizer: all player decks -->
  {#if isOrganizer}
    <div class="space-y-3">
      <div class="flex items-center justify-between">
        <h3 class="text-sm font-semibold text-bone-200">{m.decks_player_decks()}</h3>
        <span class="text-xs text-ash-500">
          {m.decks_submitted_count({ submitted: String(Object.keys(decksByUser).length), total: String(tournament.players?.length ?? 0) })}
        </span>
      </div>

      {#each tournament.players ?? [] as player}
        {@const uid = player.user_uid ?? ''}
        {@const decks = decksByUser[uid] ?? []}
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
              {:else if isMultideck}
                <!-- Multideck organizer: per-round display -->
                {#each Array(Math.max(deckSlotCount, decks.length)) as _, slotIdx}
                  {@const deck = decks[slotIdx] ?? null}
                  {@const locked = isDeckLocked(slotIdx)}
                  <div class="border-t border-ash-800 pt-2 first:border-0 first:pt-0">
                    <div class="flex items-center gap-2 mb-1">
                      <span class="text-xs font-medium text-ash-400">{m.decks_round_label({ n: String(slotIdx + 1) })}</span>
                      {#if locked}
                        <span class="inline-flex items-center gap-1 text-xs text-ash-500">
                          <Lock class="w-3 h-3" />
                        </span>
                      {/if}
                    </div>
                    {#if deck}
                      {#if isDeckVisibleToOrganizer(slotIdx)}
                        <DeckDisplay
                          {deck}
                          editable={true}
                          tournamentUid={tournament.uid}
                          playerUid={uid}
                          playerName={playerInfo[uid]?.name}
                          playerVekn={playerInfo[uid]?.vekn ?? undefined}
                          deckIndex={slotIdx}
                          format={tournament.format}
                          onreplace={() => { uploadingFor = uid; uploadingSlot = slotIdx; }}
                          ondelete={() => deleteDeck(uid, slotIdx)}
                        />
                      {:else}
                        <span class="inline-flex items-center gap-1.5 text-sm text-ash-400">
                          <Lock class="w-3.5 h-3.5" />
                          {m.decks_hidden_until_round()}
                        </span>
                      {/if}
                    {:else}
                      <button
                        onclick={() => { uploadingFor = uid; uploadingSlot = slotIdx; }}
                        class="px-3 py-1.5 text-sm font-medium text-ash-200 bg-ash-800 hover:bg-ash-700 rounded-lg transition-colors"
                      >{m.decks_upload()}</button>
                    {/if}
                  </div>
                {/each}
              {:else}
                {#each decks as deck, i}
                  {#if deck}
                    {#if isDeckVisibleToOrganizer(i)}
                      <DeckDisplay {deck} editable={true} tournamentUid={tournament.uid} playerUid={uid} playerName={playerInfo[uid]?.name} playerVekn={playerInfo[uid]?.vekn ?? undefined} deckIndex={i} format={tournament.format} onreplace={() => uploadingFor = uid} ondelete={() => deleteDeck(uid)} />
                    {:else}
                      <span class="inline-flex items-center gap-1.5 text-sm text-ash-400">
                        <Lock class="w-3.5 h-3.5" />
                        {m.decks_hidden_until_round()}
                      </span>
                    {/if}
                  {/if}
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
    {@const totalDecks = deckEntries.reduce((n, [, d]) => n + d.filter(Boolean).length, 0)}
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
                    for (let i = 0; i < decks.length; i++) {
                      if (decks[i]) all.add(`${uid}-${i}`);
                    }
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
            {#if deck}
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
                      {#if isMultideck}<span class="text-ash-500">{m.decks_round_label({ n: String(i + 1) })}</span> — {/if}
                      {deck.name || m.decks_unnamed()}
                    </span>
                  </div>
                  <span class="text-xs text-ash-500 shrink-0 whitespace-nowrap">
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
  {/if}
</div>
