<script lang="ts">
  import type { Tournament, User, Player, DeckObject, Sanction } from "$lib/types";
  type DeckMap = Record<string, DeckObject[]>;
  import { formatScore } from "$lib/utils";
  import AddPlayerForm from "$lib/components/AddPlayerForm.svelte";
  import DeckDisplay from "$lib/components/DeckDisplay.svelte";
  import DeckUpload from "$lib/components/DeckUpload.svelte";
  import SanctionIndicator from "$lib/components/SanctionIndicator.svelte";
  import RankCell from "$lib/components/RankCell.svelte";
  import TournamentSanctionModal from "$lib/components/TournamentSanctionModal.svelte";
  import SanctionListModal from "$lib/components/SanctionListModal.svelte";
  import { UserPlus, Dice3, CircleCheck, TriangleAlert, CircleX, FileX, X, ChevronDown, ChevronRight, EyeOff, Trash2, Ellipsis, Dices } from "@lucide/svelte";
  import { slide } from "svelte/transition";
  import DeckAccordion from "$lib/components/DeckAccordion.svelte";
  import RaffleSection from "./RaffleSection.svelte";
  import Button from "$lib/components/Button.svelte";
  import { validateDeck, computeRatingPoints, type ValidationError } from "$lib/engine";
  import { sponsorVeknMember, createUser, isOnline } from "$lib/api";
  import { showToast } from "$lib/stores/toast.svelte";
  import { top5HasTies as top5HasTiesFn, top5HasScoreTies as top5HasScoreTiesFn, translatePlayerState, type StandingEntry, type PlayerInfoMap } from "$lib/tournament-utils";
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
    decksByUser,
  }: {
    tournament: Tournament;
    playerInfo: PlayerInfoMap;
    standings: StandingEntry[];
    isOrganizer: boolean;
    actionLoading: boolean;
    doAction: (action: string, body?: any) => Promise<void>;
    tournamentSanctions?: Sanction[];
    isOfflineMode?: boolean;
    decksByUser: DeckMap;
  } = $props();

  // Sanction modal state
  let sanctionTarget = $state<{ uid: string; name: string } | null>(null);
  // Sanction list modal state (view + cancel issued sanctions)
  let sanctionListTarget = $state<{ uid: string; name: string } | null>(null);

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

  let editingToss = $state(false);
  let tossEdits = $state<Record<string, string>>({});
  let raffleExpanded = $state(false);
  // svelte-ignore state_referenced_locally — intentionally captures initial value
  let playerSort = $state<'standings' | 'name' | 'vekn'>(standings.length > 0 ? 'standings' : 'name');
  let standingsInitialized = false;
  let paymentFilter = $state<'all' | 'Pending' | 'Paid'>('all');

  const paidCount = $derived(tournament.players?.filter(p => p.payment_status === 'Paid').length ?? 0);
  const totalPlayers = $derived(tournament.players?.length ?? 0);

  // Deck expansion state
  let expandedPlayer = $state<string | null>(null);
  let expandedDeckRound = $state<number | null>(null);
  let uploadingFor = $state<string | null>(null);
  let uploadingRound = $state<number | undefined>(undefined);
  let validationCache = $state<Record<string, ValidationError[]>>({});

  function togglePlayer(uid: string) {
    expandedPlayer = expandedPlayer === uid ? null : uid;
    expandedDeckRound = null;
    uploadingFor = null;
    uploadingRound = undefined;
  }

  function onUploaded() {
    const uid = uploadingFor;
    uploadingFor = null;
    uploadingRound = undefined;
    // Clear validation cache so it re-validates with the new deck
    if (uid) {
      const { [uid]: _, ...rest } = validationCache;
      validationCache = rest;
    }
  }

  const isMultideck = $derived(!!tournament.multideck);
  const roundCount = $derived(tournament.rounds?.length ?? 0);
  // Hide a deck's card contents from organizers until its round has started.
  // Single-deck (round=null): hidden until round 1 starts.
  // Multideck (round=N): hidden until round N+1 exists (i.e. round N has started).
  function isDeckHiddenFromOrganizer(round: number | null): boolean {
    if (!isOrganizer) return false;
    if (round === null) return roundCount === 0;
    return roundCount <= round;
  }

  type RoundSlot = { round: number; deck: DeckObject | null };
  function getMultideckSlots(uid: string): RoundSlot[] {
    const decks = getPlayerDecks(uid);
    if (roundCount === 0) return decks.map((d, i) => ({ round: d.round ?? i, deck: d }));
    const byRound = new Map(decks.map(d => [d.round, d]));
    return Array.from({ length: roundCount }, (_, r) => ({ round: r, deck: byRound.get(r) ?? null }));
  }

  // Get player's decks (hide future-round decks from organizers during play)
  function getPlayerDecks(uid: string): DeckObject[] {
    const decks = decksByUser[uid] ?? [];
    if (!isMultideck || tournament.state !== 'Playing') return decks;
    return decks.filter(d => d.round === null || d.round < roundCount);
  }
  function getPlayerDeck(uid: string): DeckObject | null {
    return getPlayerDecks(uid)[0] ?? null;
  }

  // Compute deck status for a player (aggregate across all decks)
  type DeckStatus = 'valid' | 'warning' | 'error' | 'none';
  function getDeckStatus(uid: string): DeckStatus {
    const decks = getPlayerDecks(uid);
    if (decks.length === 0) return 'none';
    const errors = validationCache[uid];
    if (!errors) return 'valid'; // Not validated yet, assume valid
    const hasError = errors.some(e => e.severity === 'error');
    const hasWarning = errors.some(e => e.severity === 'warning');
    if (hasError) return 'error';
    if (hasWarning) return 'warning';
    return 'valid';
  }

  // Validate decks when they change (all decks per player, aggregate errors)
  $effect(() => {
    const decks = decksByUser;
    const format = tournament.format;
    if (!Object.keys(decks).length) return;

    for (const [uid, playerDecks] of Object.entries(decks)) {
      if (playerDecks.length > 0 && !validationCache[uid]) {
        Promise.all(
          playerDecks.filter(Boolean).map(d => validateDeck(d, format))
        ).then(results => {
          validationCache = { ...validationCache, [uid]: results.flat() };
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
  // Per-player-cap MECHANICS (engine-driven by max_rounds), not the non-VEKN
  // `open_rounds` reporting flag — keep this keyed on max_rounds.
  const openRounds = $derived((tournament?.max_rounds ?? 0) > 0);
  // Per-player rounds-played, computed once per render (open rounds: each player has their own count).
  const roundsPlayedMap = $derived.by(() => {
    const counts = new Map<string, number>();
    for (const round of tournament?.rounds ?? []) {
      for (const table of round) {
        for (const seat of table.seating ?? []) {
          counts.set(seat.player_uid, (counts.get(seat.player_uid) ?? 0) + 1);
        }
      }
    }
    return counts;
  });

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

  // Sponsor modal state
  let sponsorTarget = $state<User | null>(null);
  let sponsorLoading = $state(false);

  // Create-and-register modal state
  let showCreateModal = $state(false);
  let createName = $state('');
  let createEmail = $state('');
  let createCountry = $state('');
  let createLoading = $state(false);

  async function addPlayerByUser(user: User) {
    if (!user.vekn_id) {
      // Show sponsor modal instead of directly registering
      sponsorTarget = user;
      return;
    }
    await doAction("AddPlayer", { user_uid: user.uid, vekn_id: user.vekn_id });
  }

  async function handleSponsorAndRegister() {
    if (!sponsorTarget) return;
    sponsorLoading = true;
    try {
      const result = await sponsorVeknMember(sponsorTarget.uid);
      showToast({ type: "success", message: result.message });
      await doAction("AddPlayer", { user_uid: sponsorTarget.uid, vekn_id: result.user.vekn_id });
      sponsorTarget = null;
    } catch {
      // Error toast shown by apiRequest (e.g. 403 if no sponsor rights)
    } finally {
      sponsorLoading = false;
    }
  }

  async function handleCreateAndRegister() {
    if (!createName.trim() || !createEmail.trim()) return;
    createLoading = true;
    try {
      if (isOnline()) {
        const newUser = await createUser(createName.trim(), createCountry || tournament.country || '', null, null, createEmail.trim());
        await doAction("AddPlayer", { user_uid: newUser.uid, vekn_id: newUser.vekn_id });
      } else {
        // Offline mode: create temp player
        const tempUid = crypto.randomUUID();
        const tempVeknId = `TEMP-${tempUid.slice(0, 8)}`;
        const { addOfflinePlayer } = await import('$lib/stores/offline.svelte');
        await addOfflinePlayer(tournament.uid, {
          temp_uid: tempUid,
          name: createName.trim(),
          vekn_id: tempVeknId,
          email: createEmail.trim(),
        });
        await doAction('AddPlayer', { user_uid: tempUid, vekn_id: tempVeknId });
      }
      showCreateModal = false;
      createName = '';
      createEmail = '';
      createCountry = tournament.country ?? '';
    } catch {
      // Error toast shown by apiRequest
    } finally {
      createLoading = false;
    }
  }

  async function removePlayer(userUid: string) {
    await doAction("RemovePlayer", { user_uid: userUid });
  }

  async function dropPlayer(playerUid: string) {
    await doAction("DropOut", { player_uid: playerUid });
  }

  function enterTossEdit() {
    editingToss = true;
    const edits: Record<string, string> = {};
    for (const entry of standings) {
      const idx = standings.indexOf(entry);
      const isTop5 = idx >= 0 && idx < 5;
      const isTied = !entry.disqualified && standings.some((s, j) => j !== idx && !s.disqualified && s.gw === entry.gw && s.vp === entry.vp && s.tp === entry.tp && (isTop5 || j < 5));
      if (isTied) {
        edits[entry.user_uid] = String(entry.toss ?? "");
      }
    }
    tossEdits = edits;
  }

  async function saveTossEdits() {
    for (const [uid, val] of Object.entries(tossEdits)) {
      const entry = standingsMap.get(uid);
      const numVal = parseInt(val, 10);
      if (isNaN(numVal) || numVal < 0) continue;
      if (entry && entry.toss !== numVal) {
        const player = tournament.players?.find(p => p.user_uid === uid);
        if (player) await doAction("SetToss", { player_uid: uid, toss: numVal });
      }
    }
    editingToss = false;
    tossEdits = {};
  }

  function cancelTossEdit() {
    editingToss = false;
    tossEdits = {};
  }

  async function randomToss() {
    await doAction("RandomToss");
  }

  const isFinished = $derived(tournament.state === "Finished");

  // Per-player "More" drawer (rare/destructive tail: drop/remove, sanction, proxy)
  let morePlayer = $state<string | null>(null);
  function toggleMore(uid: string) { morePlayer = morePlayer === uid ? null : uid; }
  // Proxy is settled once the event is decided — mirror the engine guard.
  const canSetProxy = $derived(!tournament.finals && tournament.state !== "Finished");

  function getRatingPts(entry: StandingEntry): number {
    if (!isFinished || entry.disqualified || entry.non_competing) return 0; // DQ'd/proxy earn no RTP, not even the base
    const isWinner = entry.user_uid === tournament.winner;
    const finalistPos = isWinner ? 1
      : (tournament.finals?.seating.some(s => s.player_uid === entry.user_uid) ? 2 : 0);
    const gw = isWinner ? entry.gw + 1 : entry.gw;
    return computeRatingPoints(entry.vp, gw, finalistPos, standings.length, tournament.rank);
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
    const veknId = offlinePlayerVeknId.trim() || `TEMP-${tempUid.slice(0, 8)}`;
    const { addOfflinePlayer } = await import('$lib/stores/offline.svelte');
    await addOfflinePlayer(tournament.uid, {
      temp_uid: tempUid,
      name: offlinePlayerName.trim(),
      vekn_id: veknId,
      email: offlinePlayerEmail.trim() || undefined,
    });
    await doAction('AddPlayer', { user_uid: tempUid, vekn_id: veknId });
    offlinePlayerName = '';
    offlinePlayerVeknId = '';
    offlinePlayerEmail = '';
    showOfflinePlayerForm = false;
  }
</script>

<div class="space-y-4">
  <!-- Per-player "More" drawer: rare/destructive tail (drop/remove + sanction lead,
       proxy demoted). Shared by the mobile card and the desktop expand row. -->
  {#snippet moreDrawer(player: Player, puid: string)}
    <div class="space-y-3">
      <div class="flex gap-2 flex-wrap">
        {#if puid && hasRounds && tournament.state === "Waiting" && player.state !== "Finished"}
          <Button variant="danger" size="sm" onclick={() => dropPlayer(puid)}><Trash2 class="w-4 h-4" aria-hidden="true" />{m.players_drop_player()}</Button>
        {:else if puid && !hasRounds}
          <Button variant="danger" size="sm" onclick={() => removePlayer(puid)}><X class="w-4 h-4" aria-hidden="true" />{m.players_remove_title()}</Button>
        {/if}
        {#if puid && hasRounds && !isOfflineMode}
          <Button variant="secondary" size="sm" onclick={() => sanctionTarget = { uid: puid, name: playerInfo[puid]?.name ?? puid }}>
            <TriangleAlert class="w-4 h-4 text-warn" aria-hidden="true" />{m.sanction_tournament_issue_title()}
          </Button>
        {/if}
      </div>
      <!-- Proxy: demoted toggle, with the §5.1.1 explanation. -->
      <div class="pt-2 border-t border-dashed border-line">
        <div class="flex items-center gap-2">
          <span class="text-xs text-ink-muted">{m.proxy_label()}</span>
          <span class="flex-1"></span>
          <button
            role="switch"
            aria-checked={!!player.non_competing}
            aria-label={m.proxy_label()}
            title={m.proxy_hint()}
            disabled={!canSetProxy || actionLoading}
            onclick={() => doAction("SetNonCompeting", { player_uid: puid, non_competing: !player.non_competing })}
            class="relative w-9 h-5 rounded-full transition-colors disabled:opacity-50 {player.non_competing ? 'bg-info' : 'bg-surface-active'}"
          >
            <span class="absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform {player.non_competing ? 'translate-x-4' : ''}"></span>
          </button>
        </div>
        <p class="text-xs text-ink-faint mt-1.5">{m.proxy_hint()}</p>
      </div>
    </div>
  {/snippet}

  <!-- Header + Add Player -->
  <div class="space-y-2">
    <div class="flex items-center gap-3">
      <p class="text-ink-muted shrink-0">{m.players_count({ count: String(tournament.players?.length ?? 0) })}</p>
      {#if isOrganizer}
        <AddPlayerForm {tournament} onadd={addPlayerByUser} oncreate={() => { createCountry = tournament.country ?? ''; showCreateModal = true; }} />
      {/if}
    </div>
    {#if isOrganizer && isOfflineMode}
      <div class="border-t border-line pt-2">
        <button
          onclick={() => showOfflinePlayerForm = !showOfflinePlayerForm}
          class="text-sm text-warn hover:opacity-80 transition-colors flex items-center gap-1"
        >
          <UserPlus class="w-4 h-4" />
          {m.offline_add_new_player()}
        </button>
        {#if showOfflinePlayerForm}
          <div class="mt-2 space-y-2 bg-surface-muted/50 rounded-lg p-3">
            <input
              type="text"
              bind:value={offlinePlayerName}
              placeholder={m.offline_player_name()}
              class="w-full px-3 py-2 bg-surface-hover border border-line-strong rounded text-sm text-ink-strong placeholder-ink-faint"
            />
            <input
              type="text"
              bind:value={offlinePlayerVeknId}
              placeholder={m.offline_player_vekn_id()}
              class="w-full px-3 py-2 bg-surface-hover border border-line-strong rounded text-sm text-ink-strong placeholder-ink-faint"
            />
            <input
              type="email"
              bind:value={offlinePlayerEmail}
              placeholder={m.offline_player_email()}
              class="w-full px-3 py-2 bg-surface-hover border border-line-strong rounded text-sm text-ink-strong placeholder-ink-faint"
            />
            <Button
              variant="primary"
              size="lg"
              onclick={addOfflinePlayerAction}
              disabled={!offlinePlayerName.trim() || actionLoading}
            >{m.offline_player_add()}</Button>
          </div>
        {/if}
      </div>
    {/if}
  </div>

  <!-- Toss controls (only between rounds, not during play) -->
  {#if isOrganizer && tournament.state === "Waiting" && hasFinalsCandidate && top5HasScoreTiesFn(standings)}
    <div class="flex items-center gap-2">
      {#if editingToss}
        <Button
          variant="secondary"
          onclick={saveTossEdits}
          disabled={actionLoading}
        >{m.common_save()}</Button>
        <Button
          variant="secondary"
          onclick={cancelTossEdit}
        >{m.common_cancel()}</Button>
      {:else}
        <Button
          variant="secondary"
          onclick={randomToss}
          disabled={actionLoading}
        >
          <Dice3 class="w-4 h-4 inline mr-1" />
          {m.players_random_toss()}
        </Button>
        <Button
          variant="secondary"
          onclick={enterTossEdit}
        >{m.players_edit_toss()}</Button>
        {#if top5HasTiesFn(standings)}
          <span class="text-xs text-ink-faint">{m.players_toss_hint()}</span>
        {/if}
      {/if}
    </div>
  {/if}

  <!-- Raffle (re-homed from the former Overview tab) -->
  {#if isOrganizer && (tournament.state === "Waiting" || tournament.state === "Playing" || tournament.state === "Finished")}
    <div class="bg-surface-muted/30 rounded-lg p-4">
      <button onclick={() => raffleExpanded = !raffleExpanded}
        aria-expanded={raffleExpanded}
        class="flex items-center gap-2 py-2 text-sm font-medium text-ink w-full text-left">
        {#if raffleExpanded}<ChevronDown class="w-4 h-4" />{:else}<ChevronRight class="w-4 h-4" />{/if}
        {m.raffle_title()}
      </button>
      {#if raffleExpanded}
        <div class="mt-3">
          <RaffleSection
            {tournament}
            {playerInfo}
            isOrganizer={true}
            {doAction}
            {actionLoading}
          />
        </div>
      {/if}
    </div>
  {/if}

  {#if (tournament.players?.length ?? 0) > 0}
    <!-- Sort + filter controls -->
    <div class="flex flex-wrap items-center gap-x-4 gap-y-2">
      <div class="flex gap-1">
        {#if standings.length > 0}
          <button
            class="px-3 py-2 sm:px-2 sm:py-1 text-xs rounded transition-colors {playerSort === 'standings' ? 'bg-surface-active text-ink-strong' : 'bg-surface-hover/50 text-ink-muted hover:text-ink-bright'}"
            onclick={() => playerSort = 'standings'}
          >{m.players_sort_standings()}</button>
        {/if}
        <button
          class="px-3 py-2 sm:px-2 sm:py-1 text-xs rounded transition-colors {playerSort === 'name' ? 'bg-surface-active text-ink-strong' : 'bg-surface-hover/50 text-ink-muted hover:text-ink-bright'}"
          onclick={() => playerSort = 'name'}
        >{m.players_sort_name()}</button>
        <button
          class="px-3 py-2 sm:px-2 sm:py-1 text-xs rounded transition-colors {playerSort === 'vekn' ? 'bg-surface-active text-ink-strong' : 'bg-surface-hover/50 text-ink-muted hover:text-ink-bright'}"
          onclick={() => playerSort = 'vekn'}
        >{m.players_sort_vekn()}</button>
      </div>
      {#if isOrganizer}
        <div class="flex items-center gap-2">
          <div class="flex gap-1">
            <button
              class="px-3 py-2 sm:px-2 sm:py-1 text-xs rounded transition-colors {paymentFilter === 'all' ? 'bg-surface-active text-ink-strong' : 'bg-surface-hover/50 text-ink-muted hover:text-ink-bright'}"
              onclick={() => paymentFilter = 'all'}
            >{m.payment_filter_all()}</button>
            <button
              class="px-3 py-2 sm:px-2 sm:py-1 text-xs rounded transition-colors {paymentFilter === 'Pending' ? 'btn-pending' : 'bg-surface-hover/50 text-ink-muted hover:text-ink-bright'}"
              onclick={() => paymentFilter = 'Pending'}
            >{m.payment_pending()}</button>
            <button
              class="px-3 py-2 sm:px-2 sm:py-1 text-xs rounded transition-colors {paymentFilter === 'Paid' ? 'btn-success' : 'bg-surface-hover/50 text-ink-muted hover:text-ink-bright'}"
              onclick={() => paymentFilter = 'Paid'}
            >{m.payment_paid()}</button>
          </div>
          <span class="text-xs text-ink-faint">{m.payment_summary({ paid: String(paidCount), total: String(totalPlayers) })}</span>
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
        {@const isTied = entry && !entry.disqualified ? standings.some((s, j) => j !== standingsIdx && !s.disqualified && s.gw === entry.gw && s.vp === entry.vp && s.tp === entry.tp && (isTop5 || j < 5)) : false}
        <div class="bg-surface-muted/50 rounded-lg p-3 {isTied && playerSort === 'standings' && (isTop5 || standingsIdx <= 5) ? 'ring-1 ring-accent-soft-border' : ''}">
          <!-- Top row: rank + name + sanctions + status -->
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0 flex-1">
              <div class="flex items-center gap-1.5">
                {#if playerSort === 'standings' && entry}
                  <span class="text-ink-faint text-xs font-medium shrink-0">{#if entry.disqualified || entry.non_competing}—{:else}<RankCell rank={entry.rank} finalist={entry.finalist} hash />{/if}</span>
                {/if}
                <span class="truncate {(entry?.disqualified || entry?.non_competing) ? 'text-ink-faint' : (isTop5 && playerSort === 'standings' ? 'text-ink-strong font-medium' : 'text-ink')} text-sm">
                  {playerInfo[puid]?.name ?? (puid || m.players_no_account())}
                </span>
                {#if player.non_competing}
                  <span class="text-xs px-2 py-0.5 rounded bg-surface-active text-ink-muted shrink-0" title={m.proxy_hint()}>{m.proxy_label()}</span>
                {/if}
                {#if playerSanctionsMap[puid]?.length}
                  <SanctionIndicator
                    sanctions={playerSanctionsMap[puid]}
                    onclick={() => sanctionListTarget = { uid: puid, name: playerInfo[puid]?.name ?? puid }}
                  />
                {/if}
              </div>
              {#if (tournament.online && playerInfo[puid]?.nickname) || playerInfo[puid]?.vekn}
                <div class="text-xs text-ink-faint truncate">{[tournament.online ? playerInfo[puid]?.nickname : null, playerInfo[puid]?.vekn ? `#${playerInfo[puid].vekn}` : null].filter(Boolean).join(" · ")}</div>
              {/if}
            </div>
            <div class="shrink-0">
              {#if player.state === "Disqualified"}
                <span class="text-xs px-2 py-0.5 rounded bg-accent-soft/60 text-link-soft">{m.player_state_disqualified()}</span>
              {:else if player.state === "Finished"}
                {@const played = standingsMap.has(puid)}
                {@const finalsPhase = tournament.finals !== null || tournament.state === "Finished"}
                <span class="text-xs px-2 py-0.5 rounded bg-surface-hover text-ink-faint">{played && finalsPhase ? m.tournament_status_finished() : m.tournament_status_dropped()}</span>
              {:else if player.state === "Completed"}
                <!-- Open rounds: reached per-player cap — done with prelims, awaiting finals. -->
                <span class="text-xs px-2 py-0.5 rounded bg-surface-active text-ink-muted" title={m.player_completed_hint()}>{m.player_state_completed()}</span>
              {:else}
                <span class="text-xs px-2 py-0.5 rounded {player.state === 'Checked-in' ? 'badge-success' : 'bg-surface-hover text-ink-muted'}">{translatePlayerState(player.state)}</span>
              {/if}
              <!-- Open rounds: show progress toward the per-player cap while in-flight; the badge carries the capped/done state. -->
              {#if openRounds}
                {@const rp = roundsPlayedMap.get(puid) ?? 0}
                {#if rp > 0 && rp < (tournament.max_rounds ?? 0)}
                  <span class="text-xs text-ink-faint ml-1">{rp}/{tournament.max_rounds} {m.player_rounds_unit()}</span>
                {/if}
              {/if}
            </div>
          </div>
          <!-- Score row -->
          {#if entry}
            <div class="mt-1 flex items-center gap-3 text-xs text-ink-muted">
              <span>{formatScore(entry.gw, entry.vp, entry.tp)}</span>
              {#if hasFinals && entry.finals}<span>{entry.finals}</span>{/if}
              {#if isFinished && playerSort === 'standings'}<span class="text-ink-faint">{getRatingPts(entry)} RP</span>{/if}
              {#if isTied && tournament.state === "Waiting" && hasFinalsCandidate && top5HasScoreTiesFn(standings) && playerSort === 'standings'}
                {#if editingToss && isOrganizer}
                  <span class="text-ink-faint">{m.tournament_toss_label()}</span>
                  <input type="number" min="1" class="w-12 min-h-[44px] bg-surface-hover text-ink-strong text-xs rounded px-1 py-1.5 border border-line-strong"
                    value={tossEdits[puid] ?? ""} oninput={(e) => tossEdits[puid] = (e.target as HTMLInputElement).value} />
                {:else}
                  <span class="text-ink-faint">{m.tournament_toss_label()} {entry.toss || "—"}</span>
                {/if}
              {/if}
            </div>
          {/if}
          <!-- Organizer actions row -->
          {#if isOrganizer}
            <div class="mt-2 flex items-center gap-2 flex-wrap">
              <button onclick={() => doAction("SetPaymentStatus", { player_uid: puid, status: player.payment_status === 'Paid' ? 'Pending' : 'Paid' })}
                disabled={actionLoading}
                class="px-2 py-1 text-xs rounded transition-colors {player.payment_status === 'Paid' ? 'badge-success hover:opacity-80' : 'badge-pending hover:opacity-80'}">
                {player.payment_status === 'Paid' ? m.payment_paid() : m.payment_pending()}
              </button>
              {#if tournament.decklist_required || isOrganizer}
                {@const deckStatus = getDeckStatus(puid)}
                <button onclick={() => togglePlayer(puid)} class="inline-flex items-center gap-1 px-2 py-1 text-xs rounded transition-colors hover:bg-surface-hover" title={player.non_competing ? m.proxy_hint() : m.players_view_deck()}>
                  {#if player.non_competing}<Dices class="w-3.5 h-3.5 text-ink-faint" /><span class="text-ink-muted">{m.proxy_random_deck()}</span>
                  {:else if deckStatus === 'valid'}<CircleCheck class="w-3.5 h-3.5 text-info" /><span class="text-info">{m.players_view_deck()}</span>
                  {:else if deckStatus === 'warning'}<TriangleAlert class="w-3.5 h-3.5 text-warn" /><span class="text-warn">{m.players_view_deck()}</span>
                  {:else if deckStatus === 'error'}<CircleX class="w-3.5 h-3.5 text-link" /><span class="text-link">{m.players_view_deck()}</span>
                  {:else}<FileX class="w-3.5 h-3.5 text-ink-faint" /><span class="text-ink-muted">{m.players_no_deck()}</span>{/if}
                </button>
              {/if}
              {#if tournament.state === "Waiting" && puid && openRounds && player.state !== "Disqualified" && player.state !== "Finished" && (roundsPlayedMap.get(puid) ?? 0) >= (tournament.max_rounds ?? 0)}
                <!-- Open rounds: at cap and not dropped — no check-in, show their played count. -->
                <Button variant="ghost" size="sm" disabled title={m.player_completed_hint()}>{roundsPlayedMap.get(puid)}/{tournament.max_rounds} {m.player_rounds_unit()}</Button>
              {:else if tournament.state === "Waiting" && (player.state === "Finished" || player.state === "Registered") && puid}
                <!-- Finished = dropped out: CheckIn reinstates (Checked-in under cap, Completed at cap). -->
                <Button variant="ghost" size="sm" onclick={() => doAction("CheckIn", { player_uid: puid })}>{m.players_check_in()}</Button>
              {:else if tournament.state === "Waiting" && player.state === "Checked-in" && puid}
                <Button variant="ghost" size="sm" onclick={() => doAction("CheckOut", { player_uid: puid })}>{m.players_check_out()}</Button>
              {/if}
              <!-- Rare/destructive tail (drop/remove · sanction · proxy) lives in "More". -->
              <Button variant="ghost" size="sm" onclick={() => toggleMore(puid)} class="ml-auto" aria-expanded={morePlayer === puid}><Ellipsis class="w-4 h-4" aria-hidden="true" />{m.players_more()}</Button>
            </div>
            {#if morePlayer === puid}
              <div class="mt-2 pt-2 border-t border-line">
                {@render moreDrawer(player, puid)}
              </div>
            {/if}
          {/if}
          <!-- Expanded deck -->
          {#if expandedPlayer === puid}
            {@const playerDecks = getPlayerDecks(puid)}
            {@const errors = validationCache[puid] ?? []}
            <div class="mt-2 pt-2 border-t border-line space-y-2">
              {#if isOrganizer && uploadingFor === puid}
                <DeckUpload tournamentUid={tournament.uid} playerUid={puid} playerName={playerInfo[puid]?.name} playerVekn={playerInfo[puid]?.vekn ?? undefined} round={uploadingRound} onuploaded={onUploaded} />
              {:else if playerDecks.length > 0}
                {#if isMultideck}
                  {#each getMultideckSlots(puid) as slot}
                    <DeckAccordion
                      expanded={expandedDeckRound === slot.round}
                      ontoggle={() => expandedDeckRound = expandedDeckRound === slot.round ? null : slot.round}
                      roundLabel={m.decks_round_label({ n: String(slot.round + 1) })}
                    >
                      {#snippet headerExtra()}
                        <span class="text-ink-faint truncate">{slot.deck ? (slot.deck.name || m.decks_unnamed()) : m.players_no_deck()}</span>
                      {/snippet}
                      {#if slot.deck && isDeckHiddenFromOrganizer(slot.round)}
                        <p class="text-sm text-ink-muted flex items-center gap-1.5">
                          <EyeOff class="w-4 h-4 shrink-0" />
                          {m.decks_hidden_until_round()}
                        </p>
                        <Button
                          variant="secondary"
                          size="lg"
                          onclick={() => { uploadingFor = puid; uploadingRound = slot.round; }}
                        >{m.decks_replace()}</Button>
                      {:else if slot.deck}
                        <DeckDisplay deck={slot.deck} onreplace={isOrganizer ? () => { uploadingFor = puid; uploadingRound = slot.round; } : undefined} />
                      {:else if isOrganizer}
                        <DeckUpload tournamentUid={tournament.uid} playerUid={puid} playerName={playerInfo[puid]?.name} playerVekn={playerInfo[puid]?.vekn ?? undefined} round={slot.round} onuploaded={onUploaded} />
                      {:else}
                        <p class="text-sm text-ink-muted">{m.players_no_deck()}</p>
                      {/if}
                    </DeckAccordion>
                  {/each}
                {:else if playerDecks[0]}
                  {#if isDeckHiddenFromOrganizer(null)}
                    <p class="text-sm text-ink-muted flex items-center gap-1.5">
                      <EyeOff class="w-4 h-4 shrink-0" />
                      {m.decks_hidden_until_round()}
                    </p>
                    {#if isOrganizer}
                      <Button
                        variant="secondary"
                        size="lg"
                        onclick={() => { uploadingFor = puid; uploadingRound = undefined; }}
                      >{m.decks_replace()}</Button>
                    {/if}
                  {:else}
                    <DeckDisplay deck={playerDecks[0]} onreplace={isOrganizer ? () => { uploadingFor = puid; uploadingRound = undefined; } : undefined} />
                  {/if}
                {/if}
                {#if errors.length > 0 && !isDeckHiddenFromOrganizer(isMultideck ? 0 : null)}
                  <div class="space-y-1">
                    {#each errors as err}
                      <p class="text-sm {err.severity === 'error' ? 'text-link' : 'text-warn'}">
                        {#if err.severity === 'error'}<CircleX class="w-4 h-4 inline mr-1" />{:else}<TriangleAlert class="w-4 h-4 inline mr-1" />{/if}
                        {err.message}
                      </p>
                    {/each}
                  </div>
                {/if}
              {:else}
                <p class="text-sm text-ink-muted">{m.players_no_deck()}</p>
              {/if}
              {#if isOrganizer && playerDecks.length === 0 && (!isMultideck || roundCount === 0) && uploadingFor !== puid}
                <DeckUpload tournamentUid={tournament.uid} playerUid={puid} playerName={playerInfo[puid]?.name} playerVekn={playerInfo[puid]?.vekn ?? undefined} round={isMultideck ? 0 : undefined} onuploaded={onUploaded} />
              {/if}
            </div>
          {/if}
        </div>
      {/each}
    </div>

    <!-- Desktop table -->
    <div class="hidden sm:block bg-surface-muted/50 rounded-lg p-4 overflow-x-auto">
      <table class="w-full text-sm">
        <thead>
          <tr class="text-ink-muted text-xs border-b border-line-strong">
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
            {#if tournament.state === "Waiting" && hasFinalsCandidate && top5HasScoreTiesFn(standings) && playerSort === 'standings'}
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
            {@const isTied = entry && !entry.disqualified ? standings.some((s, j) => j !== standingsIdx && !s.disqualified && s.gw === entry.gw && s.vp === entry.vp && s.tp === entry.tp && (isTop5 || j < 5)) : false}
            <tr class="{(entry?.disqualified || entry?.non_competing) ? 'text-ink-faint' : (isTop5 && playerSort === 'standings' ? 'text-ink-strong font-medium' : 'text-ink')} {isTied && playerSort === 'standings' && (isTop5 || standingsIdx <= 5) ? 'bg-accent-soft/10' : ''} border-t border-line-strong">
              {#if playerSort === 'standings' && standings.length > 0}
                <td class="py-1.5 pr-2 text-ink-faint">{(entry?.disqualified || entry?.non_competing) ? "—" : (entry?.rank ?? "—")}</td>
              {/if}
              <td class="py-1.5 pr-2">
                <span class="truncate flex items-center gap-1">
                  {playerInfo[puid]?.name ?? (puid || m.players_no_account())}
                  {#if player.non_competing}
                    <span class="text-xs px-2 py-0.5 rounded bg-surface-active text-ink-muted shrink-0" title={m.proxy_hint()}>{m.proxy_label()}</span>
                  {/if}
                  {#if playerSanctionsMap[puid]?.length}
                    <SanctionIndicator
                      sanctions={playerSanctionsMap[puid]}
                      onclick={() => sanctionListTarget = { uid: puid, name: playerInfo[puid]?.name ?? puid }}
                    />
                  {/if}
                </span>
                {#if (tournament.online && playerInfo[puid]?.nickname) || playerInfo[puid]?.vekn}
                  <span class="text-xs text-ink-faint truncate block">{[tournament.online ? playerInfo[puid]?.nickname : null, playerInfo[puid]?.vekn ? `#${playerInfo[puid].vekn}` : null].filter(Boolean).join(" · ")}</span>
                {/if}
              </td>
              {#if standings.length > 0}
                <td class="text-right py-1.5 px-2">{entry ? formatScore(entry.gw, entry.vp, entry.tp) : "—"}</td>
                {#if hasFinals}
                  <td class="text-right py-1.5 px-2">{entry?.finals ?? ""}</td>
                {/if}
                {#if isFinished && playerSort === 'standings'}
                  <td class="text-right py-1.5 px-2 text-ink-muted">{entry ? getRatingPts(entry) : "—"}</td>
                {/if}
              {/if}
              {#if tournament.state === "Waiting" && hasFinalsCandidate && top5HasScoreTiesFn(standings) && playerSort === 'standings'}
                <td class="text-right py-1.5 px-2">
                  {#if isTied}
                    {#if editingToss && isOrganizer}
                      <input type="number" min="1"
                        class="w-14 bg-surface-hover text-ink-strong text-xs rounded px-1 py-0.5 border border-line-strong"
                        value={tossEdits[puid] ?? ""}
                        oninput={(e) => tossEdits[puid] = (e.target as HTMLInputElement).value} />
                    {:else}
                      {entry?.toss || "—"}
                    {/if}
                  {/if}
                </td>
              {/if}
              <td class="py-1.5 px-2">
                {#if player.state === "Disqualified"}
                  <span class="text-xs px-2 py-0.5 rounded bg-accent-soft/60 text-link-soft">{m.player_state_disqualified()}</span>
                {:else if player.state === "Finished"}
                  {@const played = standingsMap.has(puid)}
                  {@const finalsPhase = tournament.finals !== null || tournament.state === "Finished"}
                  <span class="text-xs px-2 py-0.5 rounded bg-surface-hover text-ink-faint">{played && finalsPhase ? m.tournament_status_finished() : m.tournament_status_dropped()}</span>
                {:else if player.state === "Completed"}
                  <span class="text-xs px-2 py-0.5 rounded bg-surface-active text-ink-muted" title={m.player_completed_hint()}>{m.player_state_completed()}</span>
                {:else}
                  <span class="text-xs px-2 py-0.5 rounded {player.state === 'Checked-in' ? 'badge-success' : 'bg-surface-hover text-ink-muted'}">
                    {translatePlayerState(player.state)}
                  </span>
                {/if}
                {#if openRounds}
                  {@const rp = roundsPlayedMap.get(puid) ?? 0}
                  {#if rp > 0 && rp < (tournament.max_rounds ?? 0)}
                    <span class="text-xs text-ink-faint ml-1">{rp}/{tournament.max_rounds} {m.player_rounds_unit()}</span>
                  {/if}
                {/if}
              </td>
              {#if isOrganizer}
                <td class="text-center py-1.5 px-2">
                  <button
                    onclick={() => doAction("SetPaymentStatus", { player_uid: puid, status: player.payment_status === 'Paid' ? 'Pending' : 'Paid' })}
                    disabled={actionLoading}
                    class="px-2 py-0.5 text-xs rounded transition-colors {player.payment_status === 'Paid' ? 'badge-success hover:opacity-80' : 'badge-pending hover:opacity-80'}"
                    title={player.payment_status === 'Paid' ? m.payment_mark_unpaid() : m.payment_mark_paid()}>
                    {player.payment_status === 'Paid' ? m.payment_paid() : m.payment_pending()}
                  </button>
                </td>
              {/if}
              {#if tournament.decklist_required || isOrganizer}
                {@const deckStatus = getDeckStatus(puid)}
                <td class="text-center py-1.5 px-2">
                  <button onclick={() => togglePlayer(puid)} class="p-1 hover:bg-surface-hover rounded transition-colors" title={player.non_competing ? m.proxy_hint() : m.players_view_deck()}>
                    {#if player.non_competing}<Dices class="w-4 h-4 text-ink-faint" />
                    {:else if deckStatus === 'valid'}<CircleCheck class="w-4 h-4 text-info" />
                    {:else if deckStatus === 'warning'}<TriangleAlert class="w-4 h-4 text-warn" />
                    {:else if deckStatus === 'error'}<CircleX class="w-4 h-4 text-link" />
                    {:else}<FileX class="w-4 h-4 text-ink-faint" />{/if}
                  </button>
                </td>
              {/if}
              {#if isOrganizer}
                <td class="py-1.5 text-right whitespace-nowrap">
                  {#if tournament.state === "Waiting" && puid && openRounds && player.state !== "Disqualified" && player.state !== "Finished" && (roundsPlayedMap.get(puid) ?? 0) >= (tournament.max_rounds ?? 0)}
                    <Button variant="ghost" size="sm" disabled title={m.player_completed_hint()}>{roundsPlayedMap.get(puid)}/{tournament.max_rounds} {m.player_rounds_unit()}</Button>
                  {:else if tournament.state === "Waiting" && (player.state === "Finished" || player.state === "Registered") && puid}
                    <Button variant="ghost" size="sm" onclick={() => doAction("CheckIn", { player_uid: puid })}>{m.players_check_in()}</Button>
                  {:else if tournament.state === "Waiting" && player.state === "Checked-in" && puid}
                    <Button variant="ghost" size="sm" onclick={() => doAction("CheckOut", { player_uid: puid })}>{m.players_check_out()}</Button>
                  {/if}
                  <!-- Rare/destructive tail (drop/remove · sanction · proxy) lives in "More". -->
                  <Button variant="ghost" size="sm" onclick={() => toggleMore(puid)} aria-expanded={morePlayer === puid}><Ellipsis class="w-4 h-4" aria-hidden="true" />{m.players_more()}</Button>
                </td>
              {/if}
            </tr>
            <!-- Expanded "More" row (drop/remove · sanction · proxy) -->
            {#if isOrganizer && morePlayer === puid}
              <tr class="bg-surface-muted/50">
                <td colspan="99" class="px-4 pb-3 pt-1">
                  {@render moreDrawer(player, puid)}
                </td>
              </tr>
            {/if}
            <!-- Expanded deck row -->
            {#if expandedPlayer === puid}
              {@const playerDecks = getPlayerDecks(puid)}
              {@const errors = validationCache[puid] ?? []}
              <tr class="bg-surface-muted/50">
                <td colspan="99" class="p-4">
                  <div class="space-y-2">
                    {#if isOrganizer && uploadingFor === puid}
                      <DeckUpload tournamentUid={tournament.uid} playerUid={puid} playerName={playerInfo[puid]?.name} playerVekn={playerInfo[puid]?.vekn ?? undefined} round={uploadingRound} onuploaded={onUploaded} />
                    {:else if playerDecks.length > 0}
                      {#if isMultideck}
                        {#each getMultideckSlots(puid) as slot}
                          <DeckAccordion
                            expanded={expandedDeckRound === slot.round}
                            ontoggle={() => expandedDeckRound = expandedDeckRound === slot.round ? null : slot.round}
                            roundLabel={m.decks_round_label({ n: String(slot.round + 1) })}
                          >
                            {#snippet headerExtra()}
                              <span class="text-ink-faint truncate">{slot.deck ? (slot.deck.name || m.decks_unnamed()) : m.players_no_deck()}</span>
                            {/snippet}
                            {#if slot.deck && isDeckHiddenFromOrganizer(slot.round)}
                              <p class="text-sm text-ink-muted flex items-center gap-1.5">
                                <EyeOff class="w-4 h-4 shrink-0" />
                                {m.decks_hidden_until_round()}
                              </p>
                              <Button
                                variant="secondary"
                                size="lg"
                                onclick={() => { uploadingFor = puid; uploadingRound = slot.round; }}
                              >{m.decks_replace()}</Button>
                            {:else if slot.deck}
                              <DeckDisplay deck={slot.deck} onreplace={isOrganizer ? () => { uploadingFor = puid; uploadingRound = slot.round; } : undefined} />
                            {:else if isOrganizer}
                              <DeckUpload tournamentUid={tournament.uid} playerUid={puid} playerName={playerInfo[puid]?.name} playerVekn={playerInfo[puid]?.vekn ?? undefined} round={slot.round} onuploaded={onUploaded} />
                            {:else}
                              <p class="text-sm text-ink-muted">{m.players_no_deck()}</p>
                            {/if}
                          </DeckAccordion>
                        {/each}
                      {:else if playerDecks[0]}
                        {#if isDeckHiddenFromOrganizer(null)}
                          <p class="text-sm text-ink-muted flex items-center gap-1.5">
                            <EyeOff class="w-4 h-4 shrink-0" />
                            {m.decks_hidden_until_round()}
                          </p>
                          {#if isOrganizer}
                            <Button
                              variant="secondary"
                              size="lg"
                              onclick={() => { uploadingFor = puid; uploadingRound = undefined; }}
                            >{m.decks_replace()}</Button>
                          {/if}
                        {:else}
                          <DeckDisplay deck={playerDecks[0]} onreplace={isOrganizer ? () => { uploadingFor = puid; uploadingRound = undefined; } : undefined} />
                        {/if}
                      {/if}
                      {#if errors.length > 0 && !isDeckHiddenFromOrganizer(isMultideck ? 0 : null)}
                        <div class="space-y-1">
                          {#each errors as err}
                            <p class="text-sm {err.severity === 'error' ? 'text-link' : 'text-warn'}">
                              {#if err.severity === 'error'}<CircleX class="w-4 h-4 inline mr-1" />{:else}<TriangleAlert class="w-4 h-4 inline mr-1" />{/if}
                              {err.message}
                            </p>
                          {/each}
                        </div>
                      {/if}
                    {:else}
                      <p class="text-sm text-ink-muted">{m.players_no_deck()}</p>
                    {/if}
                    {#if isOrganizer && playerDecks.length === 0 && (!isMultideck || roundCount === 0) && uploadingFor !== puid}
                      <DeckUpload tournamentUid={tournament.uid} playerUid={puid} playerName={playerInfo[puid]?.name} playerVekn={playerInfo[puid]?.vekn ?? undefined} round={isMultideck ? 0 : undefined} onuploaded={onUploaded} />
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

<!-- Sanction List Modal -->
{#if sanctionListTarget}
  <SanctionListModal
    playerName={sanctionListTarget.name}
    sanctions={playerSanctionsMap[sanctionListTarget.uid] ?? []}
    tournamentUid={tournament.uid}
    canManage={isOrganizer && tournament.state !== "Finished"}
    onClose={() => sanctionListTarget = null}
  />
{/if}

<!-- Sponsor & Register Modal -->
{#if sponsorTarget}
  <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
    <div class="bg-surface-card border border-line-strong rounded-lg p-6 max-w-sm w-full mx-4 space-y-4">
      <h3 class="text-lg font-medium text-ink-strong">{m.vekn_sponsor_to_register_title()}</h3>
      <p class="text-sm text-ink">{m.vekn_sponsor_to_register_message({ name: sponsorTarget.name })}</p>
      <div class="flex gap-2 justify-end">
        <Button
          variant="ghost"
          size="lg"
          onclick={() => sponsorTarget = null}
        >{m.common_cancel()}</Button>
        <Button
          variant="primary"
          size="lg"
          loading={sponsorLoading}
          onclick={handleSponsorAndRegister}
        >{m.vekn_sponsor_and_register()}</Button>
      </div>
    </div>
  </div>
{/if}

<!-- Create & Register Modal -->
{#if showCreateModal}
  <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
    <div class="bg-surface-card border border-line-strong rounded-lg p-6 max-w-sm w-full mx-4 space-y-4">
      <h3 class="text-lg font-medium text-ink-strong">{m.create_and_register_title()}</h3>
      <p class="text-sm text-ink">{m.create_and_register_message()}</p>
      <div class="space-y-2">
        <input
          type="text"
          bind:value={createName}
          placeholder={m.offline_player_name()}
          class="w-full px-3 py-2 bg-surface-hover border border-line-strong rounded text-sm text-ink-strong placeholder-ink-faint"
        />
        <input
          type="email"
          bind:value={createEmail}
          placeholder={m.common_email()}
          class="w-full px-3 py-2 bg-surface-hover border border-line-strong rounded text-sm text-ink-strong placeholder-ink-faint"
        />
      </div>
      <div class="flex gap-2 justify-end">
        <Button
          variant="ghost"
          size="lg"
          onclick={() => showCreateModal = false}
        >{m.common_cancel()}</Button>
        <Button
          variant="primary"
          size="lg"
          loading={createLoading}
          disabled={!createName.trim() || !createEmail.trim()}
          onclick={handleCreateAndRegister}
        >{m.create_and_register_btn()}</Button>
      </div>
    </div>
  </div>
{/if}
