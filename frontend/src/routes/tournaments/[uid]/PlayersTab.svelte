<script lang="ts">
  import type { Tournament, User, Player, Deck } from "$lib/types";
  import { formatScore } from "$lib/utils";
  import AddPlayerForm from "$lib/components/AddPlayerForm.svelte";
  import DeckDisplay from "$lib/components/DeckDisplay.svelte";
  import DeckUpload from "$lib/components/DeckUpload.svelte";
  import Icon from "@iconify/svelte";
  import { validateDeck, type ValidationError } from "$lib/engine";

  interface StandingEntry {
    user_uid: string;
    gw: number;
    vp: number;
    tp: number;
    toss: number;
    rank: number;
    finals?: string;
  }

  let {
    tournament,
    playerInfo,
    standings,
    isOrganizer,
    actionLoading,
    doAction,
  }: {
    tournament: Tournament;
    playerInfo: Record<string, { name: string; nickname: string | null; vekn: string | null }>;
    standings: StandingEntry[];
    isOrganizer: boolean;
    actionLoading: boolean;
    doAction: (action: string, body?: any) => Promise<void>;
  } = $props();

  let showAddPlayer = $state(false);
  let tossInputs = $state<Record<string, string>>({});
  let playerSort = $state<'standings' | 'name' | 'vekn'>(standings.length > 0 ? 'standings' : 'name');
  let standingsInitialized = false;

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

  function top5HasTies(): boolean {
    if (standings.length < 5) return false;
    for (let i = 0; i < 5; i++) {
      for (let j = i + 1; j < 5; j++) {
        const a = standings[i]!, b = standings[j]!;
        if (a.gw === b.gw && a.vp === b.vp && a.tp === b.tp && a.toss === b.toss) return true;
      }
    }
    const fifth = standings[4]!;
    for (let k = 5; k < standings.length; k++) {
      const s = standings[k]!;
      if (s.gw === fifth.gw && s.vp === fifth.vp && s.tp === fifth.tp && s.toss === fifth.toss) return true;
    }
    return false;
  }

  const sortedPlayers = $derived.by(() => {
    const players = [...tournament.players];
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

  async function addPlayerByUser(user: User) {
    await doAction("AddPlayer", { user_uid: user.uid });
    showAddPlayer = false;
  }

  async function addPlayerByVeknId(veknId: string) {
    const { getUserByVeknId } = await import("$lib/db");
    const user = await getUserByVeknId(veknId);
    if (!user) return;
    await doAction("AddPlayer", { user_uid: user.uid });
    showAddPlayer = false;
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

  const hasFinalsCandidate = $derived(standings.length >= 5 && (tournament?.rounds?.length ?? 0) >= 2);
  const hasFinals = $derived(standings.some(e => e.finals));
  const finishedPlayerCount = $derived(tournament?.players?.filter(p => p.state === "Finished").length ?? 0);
</script>

<div class="space-y-4">
  <!-- Header -->
  <div class="flex items-center justify-between">
    <p class="text-ash-400">{tournament.players.length} player{tournament.players.length !== 1 ? "s" : ""}</p>
    {#if isOrganizer}
      <button
        onclick={() => showAddPlayer = !showAddPlayer}
        class="px-3 py-2 text-sm text-ash-300 bg-ash-800 hover:bg-ash-700 rounded-lg transition-colors"
      >
        <Icon icon="lucide:user-plus" class="w-4 h-4 inline mr-1" />
        Add Player
      </button>
    {/if}
  </div>

  <!-- Add Player UI -->
  {#if showAddPlayer && isOrganizer}
    <AddPlayerForm {tournament} onadd={addPlayerByUser} onaddvekn={addPlayerByVeknId} />
  {/if}

  <!-- Toss controls -->
  {#if isOrganizer && hasFinalsCandidate && top5HasTies()}
    <div class="flex items-center gap-2">
      <button
        onclick={randomToss}
        disabled={actionLoading}
        class="px-3 py-1.5 text-sm text-ash-300 bg-ash-800 hover:bg-ash-700 rounded-lg transition-colors"
      >
        <Icon icon="lucide:dice-3" class="w-4 h-4 inline mr-1" />
        Random Toss
      </button>
      <span class="text-xs text-ash-500">Break ties by random toss or enter values manually</span>
    </div>
  {/if}

  {#if tournament.players.length > 0}
    <!-- Sort toggles -->
    <div class="flex gap-1 mb-2">
      {#if standings.length > 0}
        <button
          class="px-2 py-1 text-xs rounded transition-colors {playerSort === 'standings' ? 'bg-ash-700 text-bone-100' : 'bg-ash-800/50 text-ash-400 hover:text-ash-200'}"
          onclick={() => playerSort = 'standings'}
        >Standings</button>
      {/if}
      <button
        class="px-2 py-1 text-xs rounded transition-colors {playerSort === 'name' ? 'bg-ash-700 text-bone-100' : 'bg-ash-800/50 text-ash-400 hover:text-ash-200'}"
        onclick={() => playerSort = 'name'}
      >Name</button>
      <button
        class="px-2 py-1 text-xs rounded transition-colors {playerSort === 'vekn' ? 'bg-ash-700 text-bone-100' : 'bg-ash-800/50 text-ash-400 hover:text-ash-200'}"
        onclick={() => playerSort = 'vekn'}
      >VEKN</button>
    </div>

    <!-- Player table -->
    <div class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead>
          <tr class="text-ash-500 text-xs">
            {#if playerSort === 'standings' && standings.length > 0}
              <th class="text-left py-1 pr-2">#</th>
            {/if}
            <th class="text-left py-1 pr-2">Player</th>
            {#if standings.length > 0}
              <th class="text-right py-1 px-2">Score</th>
              {#if hasFinals}
                <th class="text-right py-1 px-2">Finals</th>
              {/if}
            {/if}
            {#if top5HasTies() && playerSort === 'standings'}
              <th class="text-right py-1 px-2">Toss</th>
            {/if}
            <th class="text-left py-1 px-2">Status</th>
            {#if tournament.decklist_required}
              <th class="text-center py-1 px-2">Deck</th>
            {/if}
            {#if isOrganizer}<th></th>{/if}
          </tr>
        </thead>
        <tbody>
          {#each sortedPlayers as player}
            {@const puid = player.user_uid ?? ""}
            {@const entry = standingsMap.get(puid)}
            {@const standingsIdx = entry ? standings.indexOf(entry) : -1}
            {@const isTop5 = standingsIdx >= 0 && standingsIdx < 5}
            {@const isTied = entry ? standings.some((s, j) => j !== standingsIdx && s.gw === entry.gw && s.vp === entry.vp && s.tp === entry.tp && (isTop5 || j < 5)) : false}
            <tr class="{isTop5 && playerSort === 'standings' ? 'text-bone-100' : 'text-ash-300'} {isTied && playerSort === 'standings' && (isTop5 || standingsIdx <= 5) ? 'bg-amber-900/20' : ''} border-t border-ash-800">
              {#if playerSort === 'standings' && standings.length > 0}
                <td class="py-1 pr-2 text-ash-500">{entry?.rank ?? "—"}</td>
              {/if}
              <td class="py-1 pr-2">
                <span class="truncate block">{playerInfo[puid]?.name ?? (puid || "(no account)")}</span>
                {#if playerInfo[puid]?.nickname || playerInfo[puid]?.vekn}
                  <span class="text-xs text-ash-500 truncate block">{[playerInfo[puid]?.nickname, playerInfo[puid]?.vekn ? `#${playerInfo[puid].vekn}` : null].filter(Boolean).join(" · ")}</span>
                {/if}
              </td>
              {#if standings.length > 0}
                <td class="text-right py-1 px-2">{entry ? formatScore(entry.gw, entry.vp, entry.tp) : "—"}</td>
                {#if hasFinals}
                  <td class="text-right py-1 px-2">{entry?.finals ?? ""}</td>
                {/if}
              {/if}
              {#if top5HasTies() && playerSort === 'standings'}
                <td class="text-right py-1 px-2">
                  {#if isOrganizer && isTied}
                    <div class="flex items-center gap-1 justify-end">
                      <span class="text-ash-500">{entry?.toss || "—"}</span>
                      <input
                        type="number"
                        min="1"
                        class="w-12 bg-ash-800 text-bone-100 text-xs rounded px-1 py-0.5 border border-ash-700"
                        value={tossInputs[puid] ?? ""}
                        oninput={(e) => tossInputs[puid] = (e.target as HTMLInputElement).value}
                      />
                      <button
                        onclick={() => setToss(puid)}
                        disabled={actionLoading}
                        class="px-1.5 py-0.5 text-xs text-emerald-400 hover:text-emerald-300 border border-emerald-800 rounded"
                      >Set</button>
                    </div>
                  {:else if isTied}
                    {entry?.toss || "—"}
                  {:else}
                    <span class="text-ash-600">—</span>
                  {/if}
                </td>
              {/if}
              <td class="py-1 px-2">
                {#if player.state === "Finished"}
                  {@const played = standingsMap.has(puid)}
                  {@const finalsPhase = tournament.finals !== null || tournament.state === "Finished"}
                  <span class="text-xs px-2 py-0.5 rounded bg-ash-800 text-ash-500">{played && finalsPhase ? "Finished" : "Dropped"}</span>
                {:else}
                  <span class="text-xs px-2 py-0.5 rounded {player.state === 'Checked-in' ? 'bg-emerald-900/60 text-emerald-300' : 'bg-ash-800 text-ash-400'}">
                    {player.state}
                  </span>
                {/if}
              </td>
              {#if tournament.decklist_required}
                {@const deckStatus = getDeckStatus(puid)}
                <td class="text-center py-1 px-2">
                  <button onclick={() => togglePlayer(puid)} class="p-1 hover:bg-ash-800 rounded transition-colors" title="View deck">
                    {#if deckStatus === 'valid'}
                      <Icon icon="lucide:check-circle" class="w-4 h-4 text-emerald-400" />
                    {:else if deckStatus === 'warning'}
                      <Icon icon="lucide:alert-triangle" class="w-4 h-4 text-amber-400" />
                    {:else if deckStatus === 'error'}
                      <Icon icon="lucide:x-circle" class="w-4 h-4 text-crimson-400" />
                    {:else}
                      <Icon icon="lucide:file-x" class="w-4 h-4 text-ash-500" />
                    {/if}
                  </button>
                </td>
              {/if}
              {#if isOrganizer}
                <td class="py-1 text-right whitespace-nowrap">
                  {#if tournament.state === "Waiting" && player.state === "Finished" && puid}
                    <button
                      onclick={() => doAction("CheckIn", { player_uid: puid })}
                      class="px-2 py-1 text-xs text-emerald-400 hover:text-emerald-300 border border-emerald-800 rounded transition-colors"
                    >Check in</button>
                  {:else if tournament.state === "Waiting" && player.state === "Registered" && puid}
                    <button
                      onclick={() => doAction("CheckIn", { player_uid: puid })}
                      class="px-2 py-1 text-xs text-emerald-400 hover:text-emerald-300 border border-emerald-800 rounded transition-colors"
                    >Check in</button>
                  {/if}
                  {#if puid && hasRounds && tournament.state === "Waiting" && player.state !== "Finished"}
                    <button
                      onclick={() => dropPlayer(puid)}
                      class="px-2 py-1 text-xs text-crimson-400 hover:text-crimson-300 border border-crimson-800 rounded transition-colors"
                    >Drop</button>
                  {:else if puid && !hasRounds}
                    <button
                      onclick={() => removePlayer(puid)}
                      class="p-1 text-crimson-400 hover:text-crimson-300 transition-colors"
                      title="Remove player"
                    >
                      <Icon icon="lucide:x" class="w-4 h-4" />
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
                      <DeckDisplay deck={playerDeck} />
                      {#if errors.length > 0}
                        <div class="space-y-1">
                          {#each errors as err}
                            <p class="text-sm {err.severity === 'error' ? 'text-crimson-400' : 'text-amber-400'}">
                              <Icon icon={err.severity === 'error' ? 'lucide:x-circle' : 'lucide:alert-triangle'} class="w-4 h-4 inline mr-1" />
                              {err.message}
                            </p>
                          {/each}
                        </div>
                      {/if}
                      {#if isOrganizer}
                        <button
                          onclick={() => uploadingFor = puid}
                          class="text-sm text-crimson-400 hover:text-crimson-300"
                        >Replace deck</button>
                      {/if}
                    {:else}
                      <p class="text-sm text-ash-400">No deck uploaded</p>
                    {/if}
                    {#if isOrganizer && (uploadingFor === puid || !playerDeck)}
                      <DeckUpload tournamentUid={tournament.uid} playerUid={puid} onuploaded={onUploaded} />
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
