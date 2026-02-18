<script lang="ts">
  import type { Tournament, User, Player, Deck, Sanction } from "$lib/types";
  import { formatScore } from "$lib/utils";
  import AddPlayerForm from "$lib/components/AddPlayerForm.svelte";
  import DeckDisplay from "$lib/components/DeckDisplay.svelte";
  import DeckUpload from "$lib/components/DeckUpload.svelte";
  import SanctionIndicator from "$lib/components/SanctionIndicator.svelte";
  import TournamentSanctionModal from "$lib/components/TournamentSanctionModal.svelte";
  import { UserPlus, Dice3, CircleCheck, TriangleAlert, CircleX, FileX, X } from "lucide-svelte";
  import { validateDeck, computeRatingPoints, type ValidationError } from "$lib/engine";
  import { top5HasTies as top5HasTiesFn, translatePlayerState, type StandingEntry } from "$lib/tournament-utils";
  import * as m from '$lib/paraglide/messages.js';

  let {
    tournament,
    playerInfo,
    standings,
    isOrganizer,
    actionLoading,
    doAction,
    tournamentSanctions,
    isOfflineMode = false,
  }: {
    tournament: Tournament;
    playerInfo: Record<string, { name: string; nickname: string | null; vekn: string | null }>;
    standings: StandingEntry[];
    isOrganizer: boolean;
    actionLoading: boolean;
    doAction: (action: string, body?: any) => Promise<void>;
    tournamentSanctions?: Sanction[];
    isOfflineMode?: boolean;
  } = $props();

  // Sanction modal state
  let sanctionTarget = $state<{ uid: string; name: string } | null>(null);

  // Build a map of player uid → their sanctions for this tournament
  const playerSanctionsMap = $derived.by(() => {
    const map: Record<string, Sanction[]> = {};
    for (const s of tournamentSanctions ?? []) {
      (map[s.user_uid] ??= []).push(s);
    }
    return map;
  });

  // Current round for pre-filling sanction modal
  const currentRound = $derived.by(() => {
    const numRounds = tournament.rounds?.length ?? 0;
    if (numRounds === 0) return null;
    if (tournament.state === "Playing") return numRounds - 1;
    return numRounds - 1; // default to last round
  });

  let tossInputs = $state<Record<string, string>>({});
  // svelte-ignore state_referenced_locally — intentionally captures initial value
  let playerSort = $state<'standings' | 'name' | 'vekn'>(standings.length > 0 ? 'standings' : 'name');
  let standingsInitialized = false;
  let paymentFilter = $state<'all' | 'Pending' | 'Paid'>('all');

  const paidCount = $derived(tournament.players?.filter(p => p.payment_status === 'Paid').length ?? 0);
  const totalPlayers = $derived(tournament.players?.length ?? 0);

  // Deck expansion state
  let expandedPlayer = $state<string | null>(null);
  let uploadingFor = $state<string | null>(null);
  let validationCache = $state<Record<string, ValidationError[]>>({});

  function togglePlayer(uid: string) {
    expandedPlayer = expandedPlayer === uid ? null : uid;
    uploadingFor = null;
  }

  function onUploaded() {
    uploadingFor = null;
  }

  // Get player's deck
  function getPlayerDeck(uid: string): Deck | null {
    const decks = tournament.decks?.[uid];
    return decks?.[0] ?? null;
  }

  // Compute deck status for a player
  type DeckStatus = 'valid' | 'warning' | 'error' | 'none';
  function getDeckStatus(uid: string): DeckStatus {
    const deck = getPlayerDeck(uid);
    if (!deck) return 'none';
    const errors = validationCache[uid];
    if (!errors) return 'valid'; // Not validated yet, assume valid
    const hasError = errors.some(e => e.severity === 'error');
    const hasWarning = errors.some(e => e.severity === 'warning');
    if (hasError) return 'error';
    if (hasWarning) return 'warning';
    return 'valid';
  }

  // Validate decks when they change
  $effect(() => {
    const decks = tournament.decks;
    const format = tournament.format;
    if (!decks) return;

    for (const [uid, playerDecks] of Object.entries(decks)) {
      if (playerDecks.length > 0 && playerDecks[0] && !validationCache[uid]) {
        // Validate asynchronously
        validateDeck(playerDecks[0], format).then(errors => {
          validationCache = { ...validationCache, [uid]: errors };
        });
      }
    }
  });

  $effect(() => {
    // Auto-switch to standings only on first availability, not on every change
    if (standings.length > 0 && !standingsInitialized) {
      standingsInitialized = true;
      playerSort = 'standings';
    }
  });

  const hasRounds = $derived((tournament?.rounds?.length ?? 0) > 0);
  const standingsMap = $derived(new Map(standings.map(s => [s.user_uid, s])));

  const sortedPlayers = $derived.by(() => {
    const players = [...(tournament.players ?? [])];
    const sort = playerSort;
    if (sort === 'standings' && standings.length > 0) {
      const rankMap = new Map(standings.map(s => [s.user_uid, s.rank]));
      players.sort((a, b) => (rankMap.get(a.user_uid!) ?? 9999) - (rankMap.get(b.user_uid!) ?? 9999));
    } else if (sort === 'vekn') {
      players.sort((a, b) => {
        const va = parseInt(playerInfo[a.user_uid ?? '']?.vekn ?? '9999999', 10);
        const vb = parseInt(playerInfo[b.user_uid ?? '']?.vekn ?? '9999999', 10);
        return va - vb;
      });
    } else {
      players.sort((a, b) => {
        const na = playerInfo[a.user_uid ?? '']?.name ?? '';
        const nb = playerInfo[b.user_uid ?? '']?.name ?? '';
        return na.localeCompare(nb);
      });
    }
    return players;
  });

  const filteredPlayers = $derived.by(() => {
    if (!isOrganizer || paymentFilter === 'all') return sortedPlayers;
    return sortedPlayers.filter(p => p.payment_status === paymentFilter);
  });

  async function addPlayerByUser(user: User) {
    await doAction("AddPlayer", { user_uid: user.uid });
  }

  async function removePlayer(userUid: string) {
    await doAction("RemovePlayer", { user_uid: userUid });
  }

  async function dropPlayer(playerUid: string) {
    await doAction("DropOut", { player_uid: playerUid });
  }

  async function setToss(playerUid: string) {
    const val = parseInt(tossInputs[playerUid] ?? "0", 10);
    if (isNaN(val) || val < 0) return;
    await doAction("SetToss", { player_uid: playerUid, toss: val });
    tossInputs[playerUid] = "";
  }

  async function randomToss() {
    await doAction("RandomToss");
  }

  const isFinished = $derived(tournament.state === "Finished");

  function getRatingPts(entry: StandingEntry): number {
    if (!isFinished) return 0;
    const finalistPos = entry.user_uid === tournament.winner ? 1
      : (tournament.finals?.seating.some(s => s.player_uid === entry.user_uid) ? 2 : 0);
    return computeRatingPoints(entry.vp, entry.gw, finalistPos, standings.length, tournament.rank);
  }

  const hasFinalsCandidate = $derived(standings.length >= 5 && (tournament?.rounds?.length ?? 0) >= 2);
  const hasFinals = $derived(standings.some(e => e.finals));
  const finishedPlayerCount = $derived(tournament?.players?.filter(p => p.state === "Finished").length ?? 0);

  // Offline player registration
  let showOfflinePlayerForm = $state(false);
  let offlinePlayerName = $state('');
  let offlinePlayerVeknId = $state('');
  let offlinePlayerEmail = $state('');

  async function addOfflinePlayerAction() {
    if (!offlinePlayerName.trim()) return;
    const tempUid = crypto.randomUUID();
    const { addOfflinePlayer } = await import('$lib/stores/offline.svelte');
    await addOfflinePlayer(tournament.uid, {
      temp_uid: tempUid,
      name: offlinePlayerName.trim(),
      vekn_id: offlinePlayerVeknId.trim() || undefined,
      email: offlinePlayerEmail.trim() || undefined,
    });
    await doAction('AddPlayer', { user_uid: tempUid });
    offlinePlayerName = '';
    offlinePlayerVeknId = '';
    offlinePlayerEmail = '';
    showOfflinePlayerForm = false;
  }
</script>

<div class="space-y-4">
  <!-- Header + Add Player -->
  <div class="space-y-2">
    <div class="flex items-center gap-3">
      <p class="text-ash-400 shrink-0">{m.players_count({ count: String(tournament.players?.length ?? 0) })}</p>
      {#if isOrganizer}
        <AddPlayerForm {tournament} onadd={addPlayerByUser} />
      {/if}
    </div>
    {#if isOrganizer && isOfflineMode}
      <div class="border-t border-ash-800 pt-2">
        <button
          onclick={() => showOfflinePlayerForm = !showOfflinePlayerForm}
          class="text-sm text-amber-400 hover:text-amber-300 transition-colors flex items-center gap-1"
        >
          <UserPlus class="w-4 h-4" />
          {m.offline_add_new_player()}
        </button>
        {#if showOfflinePlayerForm}
          <div class="mt-2 space-y-2 bg-ash-900/50 rounded-lg p-3">
            <input
              type="text"
              bind:value={offlinePlayerName}
              placeholder={m.offline_player_name()}
              class="w-full px-3 py-2 bg-ash-800 border border-ash-700 rounded text-sm text-bone-100 placeholder-ash-500"
            />
            <input
              type="text"
              bind:value={offlinePlayerVeknId}
              placeholder={m.offline_player_vekn_id()}
              class="w-full px-3 py-2 bg-ash-800 border border-ash-700 rounded text-sm text-bone-100 placeholder-ash-500"
            />
            <input
              type="email"
              bind:value={offlinePlayerEmail}
              placeholder={m.offline_player_email()}
              class="w-full px-3 py-2 bg-ash-800 border border-ash-700 rounded text-sm text-bone-100 placeholder-ash-500"
            />
            <button
              onclick={addOfflinePlayerAction}
              disabled={!offlinePlayerName.trim() || actionLoading}
              class="px-4 py-2 text-sm font-medium btn-amber disabled:bg-ash-700 rounded transition-colors"
            >{m.offline_player_add()}</button>
          </div>
        {/if}
      </div>
    {/if}
  </div>

  <!-- Toss controls -->
  {#if isOrganizer && hasFinalsCandidate && top5HasTiesFn(standings)}
    <div class="flex items-center gap-2">
      <button
        onclick={randomToss}
        disabled={actionLoading}
        class="px-3 py-1.5 text-sm text-ash-300 bg-ash-800 hover:bg-ash-700 rounded-lg transition-colors"
      >
        <Dice3 class="w-4 h-4 inline mr-1" />
        {m.players_random_toss()}
      </button>
      <span class="text-xs text-ash-500">{m.players_toss_hint()}</span>
    </div>
  {/if}

  {#if (tournament.players?.length ?? 0) > 0}
    <!-- Sort + filter controls -->
    <div class="flex flex-wrap items-center gap-x-4 gap-y-2">
      <div class="flex gap-1">
        {#if standings.length > 0}
          <button
            class="px-3 py-2 sm:px-2 sm:py-1 text-xs rounded transition-colors {playerSort === 'standings' ? 'bg-ash-700 text-bone-100' : 'bg-ash-800/50 text-ash-400 hover:text-ash-200'}"
            onclick={() => playerSort = 'standings'}
          >{m.players_sort_standings()}</button>
        {/if}
        <button
          class="px-3 py-2 sm:px-2 sm:py-1 text-xs rounded transition-colors {playerSort === 'name' ? 'bg-ash-700 text-bone-100' : 'bg-ash-800/50 text-ash-400 hover:text-ash-200'}"
          onclick={() => playerSort = 'name'}
        >{m.players_sort_name()}</button>
        <button
          class="px-3 py-2 sm:px-2 sm:py-1 text-xs rounded transition-colors {playerSort === 'vekn' ? 'bg-ash-700 text-bone-100' : 'bg-ash-800/50 text-ash-400 hover:text-ash-200'}"
          onclick={() => playerSort = 'vekn'}
        >{m.players_sort_vekn()}</button>
      </div>
      {#if isOrganizer}
        <div class="flex items-center gap-2">
          <div class="flex gap-1">
            <button
              class="px-3 py-2 sm:px-2 sm:py-1 text-xs rounded transition-colors {paymentFilter === 'all' ? 'bg-ash-700 text-bone-100' : 'bg-ash-800/50 text-ash-400 hover:text-ash-200'}"
              onclick={() => paymentFilter = 'all'}
            >{m.payment_filter_all()}</button>
            <button
              class="px-3 py-2 sm:px-2 sm:py-1 text-xs rounded transition-colors {paymentFilter === 'Pending' ? 'btn-amber' : 'bg-ash-800/50 text-ash-400 hover:text-ash-200'}"
              onclick={() => paymentFilter = 'Pending'}
            >{m.payment_pending()}</button>
            <button
              class="px-3 py-2 sm:px-2 sm:py-1 text-xs rounded transition-colors {paymentFilter === 'Paid' ? 'btn-emerald' : 'bg-ash-800/50 text-ash-400 hover:text-ash-200'}"
              onclick={() => paymentFilter = 'Paid'}
            >{m.payment_paid()}</button>
          </div>
          <span class="text-xs text-ash-500">{m.payment_summary({ paid: String(paidCount), total: String(totalPlayers) })}</span>
        </div>
      {/if}
    </div>

    <!-- Mobile card layout -->
    <div class="sm:hidden space-y-2">
      {#each filteredPlayers as player}
        {@const puid = player.user_uid ?? ""}
        {@const entry = standingsMap.get(puid)}
        {@const standingsIdx = entry ? standings.indexOf(entry) : -1}
        {@const isTop5 = standingsIdx >= 0 && standingsIdx < 5}
        {@const isTied = entry ? standings.some((s, j) => j !== standingsIdx && s.gw === entry.gw && s.vp === entry.vp && s.tp === entry.tp && (isTop5 || j < 5)) : false}
        <div class="bg-ash-900/50 rounded-lg p-3 {isTied && playerSort === 'standings' && (isTop5 || standingsIdx <= 5) ? 'ring-1 ring-crimson-800' : ''}">
          <!-- Top row: rank + name + sanctions + status -->
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0 flex-1">
              <div class="flex items-center gap-1.5">
                {#if playerSort === 'standings' && entry}
                  <span class="text-ash-500 text-xs font-medium shrink-0">#{entry.rank}</span>
                {/if}
                <span class="truncate {isTop5 && playerSort === 'standings' ? 'text-bone-100 font-medium' : 'text-ash-300'} text-sm">
                  {playerInfo[puid]?.name ?? (puid || m.players_no_account())}
                </span>
                {#if playerSanctionsMap[puid]?.length}
                  <SanctionIndicator sanctions={playerSanctionsMap[puid]} />
                {/if}
              </div>
              {#if playerInfo[puid]?.nickname || playerInfo[puid]?.vekn}
                <div class="text-xs text-ash-500 truncate">{[playerInfo[puid]?.nickname, playerInfo[puid]?.vekn ? `#${playerInfo[puid].vekn}` : null].filter(Boolean).join(" · ")}</div>
              {/if}
            </div>
            <div class="shrink-0">
              {#if player.state === "Disqualified"}
                <span class="text-xs px-2 py-0.5 rounded bg-crimson-900/60 text-crimson-300">{m.player_state_disqualified()}</span>
              {:else if player.state === "Finished"}
                {@const played = standingsMap.has(puid)}
                {@const finalsPhase = tournament.finals !== null || tournament.state === "Finished"}
                <span class="text-xs px-2 py-0.5 rounded bg-ash-800 text-ash-500">{played && finalsPhase ? m.tournament_status_finished() : m.tournament_status_dropped()}</span>
              {:else}
                <span class="text-xs px-2 py-0.5 rounded {player.state === 'Checked-in' ? 'badge-emerald' : 'bg-ash-800 text-ash-400'}">{translatePlayerState(player.state)}</span>
              {/if}
            </div>
          </div>
          <!-- Score row -->
          {#if entry}
            <div class="mt-1 flex items-center gap-3 text-xs text-ash-400">
              <span>{formatScore(entry.gw, entry.vp, entry.tp)}</span>
              {#if hasFinals && entry.finals}<span>{entry.finals}</span>{/if}
              {#if isFinished && playerSort === 'standings'}<span class="text-ash-500">{getRatingPts(entry)} RP</span>{/if}
              {#if isTied && hasFinalsCandidate && top5HasTiesFn(standings) && playerSort === 'standings'}
                <span class="text-ash-500">Toss: {entry.toss || "—"}</span>
                {#if isOrganizer}
                  <input type="number" min="1" class="w-10 min-h-[44px] bg-ash-800 text-bone-100 text-xs rounded px-1 py-1.5 border border-ash-700"
                    value={tossInputs[puid] ?? ""} oninput={(e) => tossInputs[puid] = (e.target as HTMLInputElement).value} />
                  <button onclick={() => setToss(puid)} disabled={actionLoading}
                    class="px-2 py-1.5 text-xs text-emerald-400 border border-emerald-800 rounded">{m.players_set_toss()}</button>
                {/if}
              {/if}
            </div>
          {/if}
          <!-- Organizer actions row -->
          {#if isOrganizer}
            <div class="mt-2 flex items-center gap-2 flex-wrap">
              <button onclick={() => doAction("SetPaymentStatus", { player_uid: puid, status: player.payment_status === 'Paid' ? 'Pending' : 'Paid' })}
                disabled={actionLoading}
                class="px-2 py-1 text-xs rounded transition-colors {player.payment_status === 'Paid' ? 'badge-emerald hover:opacity-80' : 'badge-amber hover:opacity-80'}">
                {player.payment_status === 'Paid' ? m.payment_paid() : m.payment_pending()}
              </button>
              {#if tournament.decklist_required || isOrganizer}
                {@const deckStatus = getDeckStatus(puid)}
                <button onclick={() => togglePlayer(puid)} class="p-1.5 hover:bg-ash-800 rounded transition-colors" title={m.players_view_deck()}>
                  {#if deckStatus === 'valid'}<CircleCheck class="w-4 h-4 text-emerald-400" />
                  {:else if deckStatus === 'warning'}<TriangleAlert class="w-4 h-4 text-amber-400" />
                  {:else if deckStatus === 'error'}<CircleX class="w-4 h-4 text-crimson-400" />
                  {:else}<FileX class="w-4 h-4 text-ash-500" />{/if}
                </button>
              {/if}
              {#if tournament.state === "Waiting" && (player.state === "Finished" || player.state === "Registered") && puid}
                <button onclick={() => doAction("CheckIn", { player_uid: puid })}
                  class="px-3 py-2 text-xs text-emerald-400 border border-emerald-800 rounded transition-colors">{m.players_check_in()}</button>
              {/if}
              {#if puid && hasRounds && tournament.state === "Waiting" && player.state !== "Finished"}
                <button onclick={() => dropPlayer(puid)}
                  class="px-3 py-2 text-xs text-crimson-400 border border-crimson-800 rounded transition-colors">{m.players_drop()}</button>
              {:else if puid && !hasRounds}
                <button onclick={() => removePlayer(puid)} class="p-1.5 text-crimson-400 hover:text-crimson-300 transition-colors" title={m.players_remove_title()}>
                  <X class="w-4 h-4" />
                </button>
              {/if}
              {#if puid && hasRounds && !isOfflineMode}
                <button onclick={() => sanctionTarget = { uid: puid, name: playerInfo[puid]?.name ?? puid }}
                  class="p-1.5 text-amber-400 hover:text-amber-300 transition-colors" title={m.sanction_tournament_issue_title()}>
                  <TriangleAlert class="w-4 h-4" />
                </button>
              {/if}
            </div>
          {/if}
          <!-- Expanded deck -->
          {#if expandedPlayer === puid}
            {@const playerDeck = getPlayerDeck(puid)}
            {@const errors = validationCache[puid] ?? []}
            <div class="mt-2 pt-2 border-t border-ash-800 space-y-3">
              {#if playerDeck}
                <DeckDisplay deck={playerDeck} onreplace={isOrganizer ? () => uploadingFor = puid : undefined} />
                {#if errors.length > 0}
                  <div class="space-y-1">
                    {#each errors as err}
                      <p class="text-sm {err.severity === 'error' ? 'text-crimson-400' : 'text-amber-400'}">
                        {#if err.severity === 'error'}<CircleX class="w-4 h-4 inline mr-1" />{:else}<TriangleAlert class="w-4 h-4 inline mr-1" />{/if}
                        {err.message}
                      </p>
                    {/each}
                  </div>
                {/if}
              {:else}
                <p class="text-sm text-ash-400">{m.players_no_deck()}</p>
              {/if}
              {#if isOrganizer && (uploadingFor === puid || !playerDeck)}
                <DeckUpload tournamentUid={tournament.uid} playerUid={puid} playerName={playerInfo[puid]?.name} playerVekn={playerInfo[puid]?.vekn ?? undefined} onuploaded={onUploaded} />
              {/if}
            </div>
          {/if}
        </div>
      {/each}
    </div>

    <!-- Desktop table -->
    <div class="hidden sm:block bg-ash-900/50 rounded-lg p-4 overflow-x-auto">
      <table class="w-full text-sm">
        <thead>
          <tr class="text-ash-400 text-xs border-b border-ash-700">
            {#if playerSort === 'standings' && standings.length > 0}
              <th class="text-left py-1.5 pr-2">{m.tournament_col_rank()}</th>
            {/if}
            <th class="text-left py-1.5 pr-2">{m.tournament_col_player()}</th>
            {#if standings.length > 0}
              <th class="text-right py-1.5 px-2">{m.tournament_col_score()}</th>
              {#if hasFinals}
                <th class="text-right py-1.5 px-2">{m.tournament_col_finals()}</th>
              {/if}
              {#if isFinished && playerSort === 'standings'}
                <th class="text-right py-1.5 px-2">{m.tournament_col_rating()}</th>
              {/if}
            {/if}
            {#if hasFinalsCandidate && top5HasTiesFn(standings) && playerSort === 'standings'}
              <th class="text-right py-1.5 px-2">{m.tournament_col_toss()}</th>
            {/if}
            <th class="text-left py-1.5 px-2">{m.tournament_col_status()}</th>
            {#if isOrganizer}
              <th class="text-center py-1.5 px-2">{m.payment_column()}</th>
            {/if}
            {#if tournament.decklist_required || isOrganizer}
              <th class="text-center py-1.5 px-2">{m.tournament_col_deck()}</th>
            {/if}
            {#if isOrganizer}<th></th>{/if}
          </tr>
        </thead>
        <tbody>
          {#each filteredPlayers as player}
            {@const puid = player.user_uid ?? ""}
            {@const entry = standingsMap.get(puid)}
            {@const standingsIdx = entry ? standings.indexOf(entry) : -1}
            {@const isTop5 = standingsIdx >= 0 && standingsIdx < 5}
            {@const isTied = entry ? standings.some((s, j) => j !== standingsIdx && s.gw === entry.gw && s.vp === entry.vp && s.tp === entry.tp && (isTop5 || j < 5)) : false}
            <tr class="{isTop5 && playerSort === 'standings' ? 'text-bone-100 font-medium' : 'text-ash-300'} {isTied && playerSort === 'standings' && (isTop5 || standingsIdx <= 5) ? 'bg-crimson-900/10' : ''} border-t border-ash-700">
              {#if playerSort === 'standings' && standings.length > 0}
                <td class="py-1.5 pr-2 text-ash-500">{entry?.rank ?? "—"}</td>
              {/if}
              <td class="py-1.5 pr-2">
                <span class="truncate flex items-center gap-1">
                  {playerInfo[puid]?.name ?? (puid || m.players_no_account())}
                  {#if playerSanctionsMap[puid]?.length}
                    <SanctionIndicator sanctions={playerSanctionsMap[puid]} />
                  {/if}
                </span>
                {#if playerInfo[puid]?.nickname || playerInfo[puid]?.vekn}
                  <span class="text-xs text-ash-500 truncate block">{[playerInfo[puid]?.nickname, playerInfo[puid]?.vekn ? `#${playerInfo[puid].vekn}` : null].filter(Boolean).join(" · ")}</span>
                {/if}
              </td>
              {#if standings.length > 0}
                <td class="text-right py-1.5 px-2">{entry ? formatScore(entry.gw, entry.vp, entry.tp) : "—"}</td>
                {#if hasFinals}
                  <td class="text-right py-1.5 px-2">{entry?.finals ?? ""}</td>
                {/if}
                {#if isFinished && playerSort === 'standings'}
                  <td class="text-right py-1.5 px-2 text-ash-400">{entry ? getRatingPts(entry) : "—"}</td>
                {/if}
              {/if}
              {#if hasFinalsCandidate && top5HasTiesFn(standings) && playerSort === 'standings'}
                <td class="text-right py-1.5 px-2">
                  {#if isOrganizer && isTied}
                    <div class="flex items-center gap-1 justify-end">
                      <span class="text-ash-500">{entry?.toss || "—"}</span>
                      <input type="number" min="1"
                        class="w-10 bg-ash-800 text-bone-100 text-xs rounded px-1 py-0.5 border border-ash-700"
                        value={tossInputs[puid] ?? ""}
                        oninput={(e) => tossInputs[puid] = (e.target as HTMLInputElement).value} />
                      <button onclick={() => setToss(puid)} disabled={actionLoading}
                        class="px-1.5 py-0.5 text-xs text-emerald-400 hover:text-emerald-300 border border-emerald-800 rounded"
                      >{m.players_set_toss()}</button>
                    </div>
                  {:else if isTied}
                    {entry?.toss || "—"}
                  {/if}
                </td>
              {/if}
              <td class="py-1.5 px-2">
                {#if player.state === "Disqualified"}
                  <span class="text-xs px-2 py-0.5 rounded bg-crimson-900/60 text-crimson-300">{m.player_state_disqualified()}</span>
                {:else if player.state === "Finished"}
                  {@const played = standingsMap.has(puid)}
                  {@const finalsPhase = tournament.finals !== null || tournament.state === "Finished"}
                  <span class="text-xs px-2 py-0.5 rounded bg-ash-800 text-ash-500">{played && finalsPhase ? m.tournament_status_finished() : m.tournament_status_dropped()}</span>
                {:else}
                  <span class="text-xs px-2 py-0.5 rounded {player.state === 'Checked-in' ? 'badge-emerald' : 'bg-ash-800 text-ash-400'}">
                    {translatePlayerState(player.state)}
                  </span>
                {/if}
              </td>
              {#if isOrganizer}
                <td class="text-center py-1.5 px-2">
                  <button
                    onclick={() => doAction("SetPaymentStatus", { player_uid: puid, status: player.payment_status === 'Paid' ? 'Pending' : 'Paid' })}
                    disabled={actionLoading}
                    class="px-2 py-0.5 text-xs rounded transition-colors {player.payment_status === 'Paid' ? 'badge-emerald hover:opacity-80' : 'badge-amber hover:opacity-80'}"
                    title={player.payment_status === 'Paid' ? m.payment_mark_unpaid() : m.payment_mark_paid()}>
                    {player.payment_status === 'Paid' ? m.payment_paid() : m.payment_pending()}
                  </button>
                </td>
              {/if}
              {#if tournament.decklist_required || isOrganizer}
                {@const deckStatus = getDeckStatus(puid)}
                <td class="text-center py-1.5 px-2">
                  <button onclick={() => togglePlayer(puid)} class="p-1 hover:bg-ash-800 rounded transition-colors" title={m.players_view_deck()}>
                    {#if deckStatus === 'valid'}<CircleCheck class="w-4 h-4 text-emerald-400" />
                    {:else if deckStatus === 'warning'}<TriangleAlert class="w-4 h-4 text-amber-400" />
                    {:else if deckStatus === 'error'}<CircleX class="w-4 h-4 text-crimson-400" />
                    {:else}<FileX class="w-4 h-4 text-ash-500" />{/if}
                  </button>
                </td>
              {/if}
              {#if isOrganizer}
                <td class="py-1.5 text-right whitespace-nowrap">
                  {#if tournament.state === "Waiting" && (player.state === "Finished" || player.state === "Registered") && puid}
                    <button onclick={() => doAction("CheckIn", { player_uid: puid })}
                      class="px-2 py-1 text-xs text-emerald-400 hover:text-emerald-300 border border-emerald-800 rounded transition-colors"
                    >{m.players_check_in()}</button>
                  {/if}
                  {#if puid && hasRounds && tournament.state === "Waiting" && player.state !== "Finished"}
                    <button onclick={() => dropPlayer(puid)}
                      class="px-2 py-1 text-xs text-crimson-400 hover:text-crimson-300 border border-crimson-800 rounded transition-colors"
                    >{m.players_drop()}</button>
                  {:else if puid && !hasRounds}
                    <button onclick={() => removePlayer(puid)} class="p-1 text-crimson-400 hover:text-crimson-300 transition-colors" title={m.players_remove_title()}>
                      <X class="w-4 h-4" />
                    </button>
                  {/if}
                  {#if puid && hasRounds && !isOfflineMode}
                    <button onclick={() => sanctionTarget = { uid: puid, name: playerInfo[puid]?.name ?? puid }}
                      class="p-1 text-amber-400 hover:text-amber-300 transition-colors" title={m.sanction_tournament_issue_title()}>
                      <TriangleAlert class="w-4 h-4" />
                    </button>
                  {/if}
                </td>
              {/if}
            </tr>
            <!-- Expanded deck row -->
            {#if expandedPlayer === puid}
              {@const playerDeck = getPlayerDeck(puid)}
              {@const errors = validationCache[puid] ?? []}
              <tr class="bg-ash-900/50">
                <td colspan="99" class="p-4">
                  <div class="space-y-3">
                    {#if playerDeck}
                      <DeckDisplay deck={playerDeck} onreplace={isOrganizer ? () => uploadingFor = puid : undefined} />
                      {#if errors.length > 0}
                        <div class="space-y-1">
                          {#each errors as err}
                            <p class="text-sm {err.severity === 'error' ? 'text-crimson-400' : 'text-amber-400'}">
                              {#if err.severity === 'error'}<CircleX class="w-4 h-4 inline mr-1" />{:else}<TriangleAlert class="w-4 h-4 inline mr-1" />{/if}
                              {err.message}
                            </p>
                          {/each}
                        </div>
                      {/if}
                    {:else}
                      <p class="text-sm text-ash-400">{m.players_no_deck()}</p>
                    {/if}
                    {#if isOrganizer && (uploadingFor === puid || !playerDeck)}
                      <DeckUpload tournamentUid={tournament.uid} playerUid={puid} playerName={playerInfo[puid]?.name} playerVekn={playerInfo[puid]?.vekn ?? undefined} onuploaded={onUploaded} />
                    {/if}
                  </div>
                </td>
              </tr>
            {/if}
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</div>

<!-- Tournament Sanction Modal -->
{#if sanctionTarget && isOrganizer}
  <TournamentSanctionModal
    {tournament}
    playerUid={sanctionTarget.uid}
    playerName={sanctionTarget.name}
    {currentRound}
    onClose={() => sanctionTarget = null}
  />
{/if}
