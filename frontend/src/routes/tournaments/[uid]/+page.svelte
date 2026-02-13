<script lang="ts">
  import { page } from "$app/stores";
  import { goto } from "$app/navigation";
  import { untrack } from "svelte";
  import { deleteTournamentApi, tournamentAction, setTableScore } from "$lib/api";
  import { getCountries, getCountryFlag } from "$lib/geonames";
  import { getAuthState, hasAnyRole } from "$lib/stores/auth.svelte";
  import { syncManager } from "$lib/sync";
  import { getUser, getUserByVeknId, getTournament } from "$lib/db";
  import type { Tournament, TournamentState, User } from "$lib/types";
  import { scoreSeatingSync, computeRatingPoints, validateDeck, type ValidationError } from "$lib/engine";
  import { formatScore } from "$lib/utils";
  import Icon from "@iconify/svelte";
  import { renderMarkdown } from "$lib/markdown";

  // Deck validation state for player's own deck
  let myDeckErrors = $state<ValidationError[]>([]);

  import OverviewTab from "./OverviewTab.svelte";
  import PlayersTab from "./PlayersTab.svelte";
  import RoundsTab from "./RoundsTab.svelte";
  import FinalsTab from "./FinalsTab.svelte";
  import ConfigTab from "./ConfigTab.svelte";
  import DecksTab from "./DecksTab.svelte"; // Used in player view only

  const countries = getCountries();

  let tournament = $state<Tournament | null>(null);
  let loading = $state(true);
  let error = $state<string | null>(null);
  let actionLoading = $state(false);

  const auth = $derived(getAuthState());
  const uid = $derived($page.params.uid as string);
  const isOrganizer = $derived(
    tournament?.organizers_uids?.includes(auth.user?.uid ?? "") ?? false
  );
  const currentPlayerEntry = $derived(
    tournament?.players?.find(p => p.user_uid === auth.user?.uid) ?? null
  );
  let viewAsPlayer = $state(false);
  let showRegisteredPlayers = $state(false);
  const showOrganizerView = $derived(isOrganizer && !viewAsPlayer);
  // Minimal view: API returned TournamentMinimal (no players array) — non-auth or non-member
  const isMinimalView = $derived(!tournament?.players);

  // Player's deck and validation status
  const myDeck = $derived(
    (auth.user?.uid && tournament?.decks?.[auth.user.uid]?.[0]) ?? null
  );
  const playerHasValidDeck = $derived(
    !tournament?.decklist_required || (myDeck !== null && !myDeckErrors.some(e => e.severity === 'error'))
  );

  // Validate player's deck when it changes
  $effect(() => {
    const deck = myDeck;
    const format = tournament?.format;
    if (!deck || !format) {
      myDeckErrors = [];
      return;
    }
    validateDeck(deck, format).then(errors => {
      myDeckErrors = errors;
    });
  });

  // Tab state
  type TabId = 'overview' | 'players' | 'rounds' | 'finals' | 'config';
  let activeTab = $state<TabId>('overview');

  const tabs = $derived.by(() => {
    const t: { id: TabId; label: string; icon: string }[] = [
      { id: 'overview', label: 'Overview', icon: 'lucide:layout-dashboard' },
      { id: 'players', label: 'Players', icon: 'lucide:users' },
      { id: 'rounds', label: 'Rounds', icon: 'lucide:swords' },
    ];
    // Show Finals tab when ≥2 rounds played
    const hasFinalsCandidate = (tournament?.rounds?.length ?? 0) >= 2;
    if (hasFinalsCandidate || tournament?.finals) {
      t.push({ id: 'finals', label: 'Finals', icon: 'lucide:trophy' });
    }
    if (showOrganizerView) {
      t.push({ id: 'config', label: 'Config', icon: 'lucide:settings' });
    }
    return t;
  });

  // Player display info keyed by uid
  let playerInfo = $state<Record<string, { name: string; nickname: string | null; vekn: string | null }>>({});

  async function loadPlayerNames() {
    if (!tournament) return;
    const info: Record<string, { name: string; nickname: string | null; vekn: string | null }> = {};
    const uids = new Set<string>();
    for (const p of tournament.players ?? []) {
      if (p.user_uid) uids.add(p.user_uid);
    }
    for (const round of tournament.rounds ?? []) {
      for (const table of round) {
        for (const seat of table.seating) {
          if (seat.player_uid) uids.add(seat.player_uid);
        }
      }
    }
    for (const uid of uids) {
      const user = await getUser(uid);
      info[uid] = {
        name: user?.name || uid,
        nickname: user?.nickname ?? null,
        vekn: user?.vekn_id ?? null,
      };
    }
    playerInfo = info;
  }

  // Standings
  interface StandingEntry {
    user_uid: string;
    gw: number;
    vp: number;
    tp: number;
    toss: number;
    rank: number;
    finals?: string;
  }

  function computeStandings(): StandingEntry[] {
    if (!tournament || !tournament.players) return [];

    // VEKN-synced tournaments: no rounds, use player.result directly
    if (!tournament.rounds || tournament.rounds.length < 1) {
      const finalistUids = new Set(
        tournament.players.filter(p => p.finalist && p.user_uid).map(p => p.user_uid!)
      );
      const entries: StandingEntry[] = tournament.players
        .filter(p => p.user_uid && (p.result.gw || p.result.vp || p.result.tp))
        .map(p => ({
          user_uid: p.user_uid!,
          gw: p.result.gw,
          vp: p.result.vp,
          tp: p.result.tp,
          toss: p.toss ?? 0,
          rank: 0,
        }));
      // Sort: winner first, then other finalists, then by score
      entries.sort((a, b) => {
        const aW = a.user_uid === tournament!.winner ? 2 : finalistUids.has(a.user_uid) ? 1 : 0;
        const bW = b.user_uid === tournament!.winner ? 2 : finalistUids.has(b.user_uid) ? 1 : 0;
        if (aW !== bW) return bW - aW;
        return b.gw - a.gw || b.vp - a.vp || b.tp - a.tp || b.toss - a.toss;
      });
      // Rank: winner=1, other finalists=2, rest by position
      const finalistCount = finalistUids.size;
      for (let i = 0; i < entries.length; i++) {
        const e = entries[i]!;
        if (e.user_uid === tournament.winner) { e.rank = 1; }
        else if (finalistUids.has(e.user_uid)) { e.rank = 2; }
        else if (i === 0) { e.rank = finalistCount + 1; }
        else {
          const prev = entries[i - 1]!;
          if (!finalistUids.has(prev.user_uid) && e.gw === prev.gw && e.vp === prev.vp && e.tp === prev.tp && e.toss === prev.toss) {
            e.rank = prev.rank;
          } else {
            e.rank = i + 1;
          }
        }
      }
      return entries;
    }

    const map = new Map<string, { gw: number; vp: number; tp: number }>();
    for (const round of tournament.rounds) {
      for (const table of round) {
        for (const seat of table.seating) {
          if (!seat.player_uid) continue;
          const e = map.get(seat.player_uid) ?? { gw: 0, vp: 0, tp: 0 };
          e.gw += seat.result.gw ?? 0;
          e.vp += seat.result.vp ?? 0;
          e.tp += seat.result.tp ?? 0;
          map.set(seat.player_uid, e);
        }
      }
    }
    const tossMap = new Map<string, number>();
    for (const p of tournament.players) {
      if (p.user_uid) tossMap.set(p.user_uid, p.toss ?? 0);
    }
    const entries: StandingEntry[] = [...map.entries()].map(([uid, s]) => ({
      user_uid: uid, ...s, toss: tossMap.get(uid) ?? 0, rank: 0,
    }));

    // For finished tournaments with finals, incorporate finals results into ranking
    if (tournament.state === "Finished" && tournament.finals) {
      const finalistUids = new Set(tournament.finals.seating.map(s => s.player_uid));
      const finalsResults = new Map(tournament.finals.seating.map(s => [s.player_uid, s.result]));
      // Determine winner: finalist with highest GW then VP
      let winnerUid = tournament.winner;
      if (!winnerUid) {
        const sorted = [...tournament.finals.seating].sort((a, b) => (b.result.gw - a.result.gw) || (b.result.vp - a.result.vp));
        winnerUid = sorted[0]?.player_uid ?? "";
      }
      // Set finals display string
      for (const e of entries) {
        const fr = finalsResults.get(e.user_uid);
        if (fr) e.finals = formatScore(fr.gw, fr.vp, fr.tp);
      }
      // Sort: winner first, other finalists next, then non-finalists by prelim stats
      entries.sort((a, b) => {
        const aWinner = a.user_uid === winnerUid ? 1 : 0;
        const bWinner = b.user_uid === winnerUid ? 1 : 0;
        if (aWinner !== bWinner) return bWinner - aWinner;
        const aFinalist = finalistUids.has(a.user_uid) ? 1 : 0;
        const bFinalist = finalistUids.has(b.user_uid) ? 1 : 0;
        if (aFinalist !== bFinalist) return bFinalist - aFinalist;
        return b.gw - a.gw || b.vp - a.vp || b.tp - a.tp || b.toss - a.toss;
      });
      // Assign ranks: winner=1, other finalists=2, non-finalists=6+
      for (let i = 0; i < entries.length; i++) {
        const e = entries[i]!;
        if (e.user_uid === winnerUid) { e.rank = 1; }
        else if (finalistUids.has(e.user_uid)) { e.rank = 2; }
        else {
          const finalistCount = tournament.finals.seating.length;
          if (i === 0) { e.rank = finalistCount + 1; }
          else {
            const prev = entries[i - 1]!;
            if (!finalistUids.has(prev.user_uid) && e.gw === prev.gw && e.vp === prev.vp && e.tp === prev.tp && e.toss === prev.toss) {
              e.rank = prev.rank;
            } else {
              e.rank = i + 1;
            }
          }
        }
      }
      return entries;
    }

    entries.sort((a, b) => b.gw - a.gw || b.vp - a.vp || b.tp - a.tp || b.toss - a.toss);
    for (let i = 0; i < entries.length; i++) {
      if (i === 0) { entries[i]!.rank = 1; continue; }
      const prev = entries[i - 1]!;
      const cur = entries[i]!;
      cur.rank = (cur.gw === prev.gw && cur.vp === prev.vp && cur.tp === prev.tp && cur.toss === prev.toss)
        ? prev.rank
        : i + 1;
    }
    return entries;
  }

  const standings = $derived(computeStandings());

  // Rating points per player (only for finished tournaments)
  function getRatingPts(entry: StandingEntry): number {
    if (!tournament || tournament.state !== "Finished") return 0;
    const finalistPos = entry.user_uid === tournament.winner ? 1
      : (tournament.finals?.seating.some(s => s.player_uid === entry.user_uid) ? 2 : 0);
    const playerCount = standings.length;
    return computeRatingPoints(entry.vp, entry.gw, finalistPos, playerCount, tournament.rank);
  }

  const isFinished = $derived(tournament?.state === "Finished");

  // Player standings visibility
  const playerStandings = $derived.by(() => {
    if (!standings.length) return [];
    const mode = tournament?.standings_mode ?? "Private";
    if (tournament?.state === "Finished") return standings;
    if (mode === "Private") return [];
    if (mode === "Cutoff") return standings.slice(0, 5);
    if (mode === "Top 10") return standings.slice(0, 10);
    return standings;
  });

  const isFinals = $derived(tournament?.finals != null && (tournament?.state === "Playing" || tournament?.state === "Finished"));

  function seatDisplay(uid: string): string {
    const info = playerInfo[uid];
    if (!info) return uid;
    const display = info.nickname || info.name;
    return info.vekn ? `${display} (${info.vekn})` : display;
  }

  function vpOptions(tableSize: number, allowImpossible: boolean): number[] {
    const opts: number[] = [];
    for (let v = 0; v <= tableSize; v += 0.5) {
      if (!allowImpossible && v === tableSize - 0.5) continue;
      opts.push(v);
    }
    return opts;
  }

  function computeGwLocal(vps: number[]): number[] {
    if (vps.length === 0) return [];
    const max = Math.max(...vps);
    const maxCount = vps.filter(v => v === max).length;
    return vps.map(v => (v >= 2 && v === max && maxCount === 1 ? 1 : 0));
  }

  function computeTpLocal(tableSize: number, vps: number[]): number[] {
    const base: Record<number, number[]> = {
      5: [60, 48, 36, 24, 12],
      4: [60, 48, 24, 12],
      3: [60, 36, 12],
    };
    const b = base[tableSize];
    if (!b) return vps.map(() => 0);
    const indices = vps.map((_, i) => i).sort((a, c) => (vps[c] ?? 0) - (vps[a] ?? 0));
    const result = new Array(vps.length).fill(0);
    let i = 0;
    while (i < indices.length) {
      let j = i + 1;
      while (j < indices.length && vps[indices[j]!] === vps[indices[i]!]) j++;
      let sum = 0;
      for (let k = i; k < j; k++) sum += b[k] ?? 0;
      const avg = sum / (j - i);
      for (let k = i; k < j; k++) result[indices[k]!] = avg;
      i = j;
    }
    return result;
  }

  let scoreSaving = $state<number | null>(null);

  async function setVp(tableIndex: number, playerUid: string, vp: number, seating: Array<{ player_uid: string; result: { vp: number } }>) {
    if (!tournament) return;
    const roundIndex = tournament.rounds.length - 1;
    const scores = seating.map(s => ({
      player_uid: s.player_uid,
      vp: s.player_uid === playerUid ? vp : s.result.vp,
    }));
    scoreSaving = tableIndex;
    try {
      tournament = await setTableScore(uid, roundIndex, tableIndex, scores);
      await loadPlayerNames();
    } catch (e) {
      error = e instanceof Error ? e.message : "Failed to save scores";
    } finally {
      scoreSaving = null;
    }
  }

  async function setFinalsVp(playerUid: string, vp: number, seating: Array<{ player_uid: string; result: { vp: number } }>) {
    if (!tournament) return;
    const roundIndex = tournament.rounds.length;
    const scores = seating.map(s => ({
      player_uid: s.player_uid,
      vp: s.player_uid === playerUid ? vp : s.result.vp,
    }));
    scoreSaving = -1;
    try {
      tournament = await setTableScore(uid, roundIndex, 0, scores);
      await loadPlayerNames();
    } catch (e) {
      error = e instanceof Error ? e.message : "Failed to save finals scores";
    } finally {
      scoreSaving = null;
    }
  }

  async function load() {
    if (!tournament) loading = true;
    error = null;
    try {
      const t = await getTournament(uid);
      if (t) {
        tournament = t;
        await loadPlayerNames();
      } else if (!tournament) {
        // No data in IndexedDB yet — will arrive via SSE
        error = "Tournament not yet synced. Waiting for data...";
      }
    } catch (e) {
      error = e instanceof Error ? e.message : "Failed to load tournament";
    } finally {
      loading = false;
    }
  }

  async function doAction(action: string, data?: Record<string, unknown>) {
    actionLoading = true;
    try {
      tournament = await tournamentAction(uid, action, data);
      await loadPlayerNames();
    } catch (e) {
      error = e instanceof Error ? e.message : "Action failed";
    } finally {
      actionLoading = false;
    }
  }

  async function handleDelete() {
    if (!confirm("Delete this tournament? This cannot be undone.")) return;
    try {
      await deleteTournamentApi(uid);
      goto("/tournaments");
    } catch (e) {
      error = e instanceof Error ? e.message : "Delete failed";
    }
  }

  const browserTz = Intl.DateTimeFormat().resolvedOptions().timeZone;

  function formatDate(iso: string | null): string {
    if (!iso) return "—";
    if (!tournament) return iso;
    try {
      const tz = tournament.online ? undefined : tournament.timezone || "UTC";
      const opts: Intl.DateTimeFormatOptions = {
        year: "numeric", month: "short", day: "numeric",
        hour: "2-digit", minute: "2-digit",
        timeZoneName: "short",
        ...(tz ? { timeZone: tz } : {}),
      };
      return new Date(iso).toLocaleString(undefined, opts);
    } catch { return iso; }
  }

  function formatDateLocal(iso: string | null): string | null {
    if (!iso || !tournament || tournament.online) return null;
    const tournamentTz = tournament.timezone || "UTC";
    if (tournamentTz === browserTz) return null;
    try {
      return new Date(iso).toLocaleString(undefined, {
        hour: "2-digit", minute: "2-digit",
        timeZoneName: "short",
      });
    } catch { return null; }
  }

  function getStateBadgeClass(state: TournamentState): string {
    switch (state) {
      case "Planned": return "bg-ash-800 text-ash-300";
      case "Registration": return "bg-emerald-900/60 text-emerald-300";
      case "Waiting": return "bg-amber-900/60 text-amber-300";
      case "Playing": return "bg-crimson-900/60 text-crimson-300";
      case "Finished": return "bg-ash-700 text-ash-400";
      default: return "bg-ash-800 text-ash-300";
    }
  }

  async function dropPlayer(playerUid: string) {
    await doAction("DropOut", { player_uid: playerUid });
  }

  $effect(() => {
    const _currentUid = uid; // explicit dependency on uid
    untrack(() => load());

    const handleSync = (event: { type: string }) => {
      if (event.type === "tournament") untrack(() => load());
    };
    syncManager.addEventListener(handleSync);
    return () => syncManager.removeEventListener(handleSync);
  });
</script>

<svelte:head>
  <title>{tournament?.name ?? "Tournament"} - Archon</title>
</svelte:head>

<div class="p-4 sm:p-8">
  <div class="max-w-4xl mx-auto">
    <!-- Back link -->
    <a href="/tournaments" class="inline-flex items-center gap-2 text-ash-400 hover:text-ash-200 mb-4">
      <Icon icon="lucide:arrow-left" class="w-4 h-4" />
      Tournaments
    </a>

    {#if loading}
      <div class="text-center py-12">
        <Icon icon="lucide:loader-2" class="mx-auto h-12 w-12 text-ash-500 animate-spin" />
      </div>
    {:else if error && !tournament}
      <div class="bg-crimson-900/20 border border-crimson-800 rounded-lg p-4">
        <p class="text-crimson-300">{error}</p>
      </div>
    {:else if tournament}
      <!-- Header -->
      <div class="flex items-start justify-between mb-6">
        <div>
          <h1 class="text-3xl font-light text-bone-100">{tournament.name}</h1>
          <div class="flex items-center gap-3 mt-2">
            <span class="px-2 py-1 rounded text-xs font-medium {getStateBadgeClass(tournament.state)}">
              {tournament.state}
            </span>
            <span class="text-sm text-ash-400">{tournament.format}</span>
            {#if tournament.rank}
              <span class="text-sm text-ash-400">· {tournament.rank}</span>
            {/if}
          </div>
        </div>

        {#if showOrganizerView && tournament.state === "Planned"}
          <button
            onclick={handleDelete}
            class="px-3 py-1.5 text-sm text-crimson-400 hover:text-crimson-300 border border-crimson-800 hover:border-crimson-700 rounded-lg transition-colors"
          >Delete</button>
        {/if}
      </div>

      {#if error}
        <div class="bg-crimson-900/20 border border-crimson-800 rounded-lg p-3 mb-4">
          <p class="text-crimson-300 text-sm">{error}</p>
        </div>
      {/if}

      <!-- Info Card -->
      <div class="bg-dusk-950 rounded-lg shadow p-6 border border-ash-800 mb-6">
        <div class="grid grid-cols-2 sm:grid-cols-3 gap-4 text-sm">
          <div>
            <div class="text-ash-500">Date</div>
            <div class="text-ash-200">{formatDate(tournament.start)}</div>
            {#if formatDateLocal(tournament.start)}
              <div class="text-xs text-ash-500">{formatDateLocal(tournament.start)} in your timezone</div>
            {/if}
          </div>
          <div>
            <div class="text-ash-500">Location</div>
            <div class="text-ash-200">
              {#if tournament.online}
                Online
              {:else if tournament.country}
                {getCountryFlag(tournament.country)} {countries[tournament.country]?.name ?? tournament.country}
                {#if tournament.venue}
                  <br /><span class="text-ash-400">{tournament.venue}</span>
                {/if}
              {:else}
                —
              {/if}
            </div>
          </div>
          {#if tournament.players}
          <div>
            <div class="text-ash-500">Players</div>
            <div class="text-ash-200">{tournament.players.length} registered</div>
          </div>
          {/if}
          {#if tournament.description}
            <div class="col-span-full">
              <div class="text-ash-500">Description</div>
              <div class="text-ash-300 mt-1 prose prose-invert prose-sm max-w-none">{@html renderMarkdown(tournament.description)}</div>
            </div>
          {/if}
        </div>
      </div>

      {#if isMinimalView}
        <div class="bg-dusk-950 rounded-lg shadow border border-ash-800 p-6 text-center">
          <p class="text-ash-400">Sign in to view full tournament details.</p>
        </div>
      {:else}
      <!-- View toggle for organizers -->
      {#if isOrganizer}
        <div class="flex justify-end mb-4">
          <button
            onclick={() => viewAsPlayer = !viewAsPlayer}
            class="px-3 py-1.5 text-sm text-ash-300 bg-ash-800 hover:bg-ash-700 rounded-lg transition-colors"
          >
            <Icon icon={viewAsPlayer ? "lucide:shield" : "lucide:user"} class="w-4 h-4 inline mr-1" />
            {viewAsPlayer ? "Organizer view" : "Player view"}
          </button>
        </div>
      {/if}

      <!-- Organizer Console with Tabs -->
      {#if showOrganizerView}
        <div class="bg-dusk-950 rounded-lg shadow border border-ash-800 mb-6">
          <!-- Tab bar -->
          <div class="flex border-b border-ash-800 overflow-x-auto">
            {#each tabs as tab}
              <button
                onclick={() => activeTab = tab.id}
                class="flex items-center gap-1.5 px-4 py-3 text-sm font-medium whitespace-nowrap transition-colors border-b-2 {activeTab === tab.id ? 'border-crimson-500 text-bone-100' : 'border-transparent text-ash-400 hover:text-ash-200 hover:border-ash-600'}"
              >
                <Icon icon={tab.icon} class="w-4 h-4" />
                {tab.label}
              </button>
            {/each}
          </div>

          <!-- Tab content -->
          <div class="p-6">
            {#if activeTab === 'overview'}
              <OverviewTab
                {tournament}
                {playerInfo}
                {standings}
                isOrganizer={true}
                {actionLoading}
                {doAction}
              />
            {:else if activeTab === 'players'}
              <PlayersTab
                {tournament}
                {playerInfo}
                {standings}
                isOrganizer={true}
                {actionLoading}
                {doAction}
              />
            {:else if activeTab === 'rounds'}
              <RoundsTab
                bind:tournament={tournament}
                {playerInfo}
                isOrganizer={true}
                {actionLoading}
                {doAction}
                {loadPlayerNames}
              />
            {:else if activeTab === 'finals'}
              <FinalsTab
                bind:tournament={tournament}
                {playerInfo}
                {standings}
                isOrganizer={true}
                {actionLoading}
                {doAction}
                {loadPlayerNames}
              />
            {:else if activeTab === 'config'}
              <ConfigTab
                bind:tournament={tournament}
                isOrganizer={true}
              />
            {/if}
          </div>
        </div>
      {/if}

      <!-- Player View (non-organizer) -->
      {#if !showOrganizerView && auth.isAuthenticated}
        <div class="bg-dusk-950 rounded-lg shadow border border-ash-800 mb-6 p-6">
          {#if tournament.state === "Registration" && !currentPlayerEntry}
            <button
              onclick={() => doAction("Register", { user_uid: auth.user?.uid })}
              disabled={actionLoading}
              class="px-4 py-2 text-sm font-medium text-bone-100 bg-emerald-700 hover:bg-emerald-600 disabled:bg-ash-700 rounded-lg transition-colors"
            >Register</button>
          {:else if tournament.state === "Registration" && currentPlayerEntry}
            <div class="text-sm mb-3 flex items-center justify-between">
              <div>
                <span class="text-ash-500">Your status:</span>
                <span class="ml-2 text-ash-200">{currentPlayerEntry.state}</span>
              </div>
              <button
                onclick={() => doAction("Unregister", { user_uid: auth.user?.uid })}
                disabled={actionLoading}
                class="px-3 py-1.5 text-sm text-crimson-400 hover:text-crimson-300 border border-crimson-800 hover:border-crimson-700 rounded-lg transition-colors"
              >Unregister</button>
            </div>
          {:else if currentPlayerEntry}
            <div class="text-sm mb-3 flex items-center justify-between">
              <div>
                <span class="text-ash-500">Your status:</span>
                <span class="ml-2 text-ash-200">{currentPlayerEntry.state === "Finished"
                  ? ((tournament.finals !== null || tournament.state === "Finished") && standings.some(s => s.user_uid === currentPlayerEntry.user_uid) ? "Finished" : "Dropped")
                  : currentPlayerEntry.state}</span>
              </div>
              {#if currentPlayerEntry.state === "Registered" && tournament.state === "Waiting" && !playerHasValidDeck}
                <div class="flex items-center gap-2 text-amber-400 text-sm">
                  <Icon icon="lucide:alert-triangle" class="w-4 h-4" />
                  Upload a valid deck to check in
                </div>
              {:else if currentPlayerEntry.state === "Finished" && tournament.state === "Waiting"}
                {#if !playerHasValidDeck}
                  <div class="flex items-center gap-2 text-amber-400 text-sm">
                    <Icon icon="lucide:alert-triangle" class="w-4 h-4" />
                    Upload a valid deck to check in
                  </div>
                {:else}
                  <button
                    onclick={() => doAction("CheckIn", { player_uid: auth.user?.uid ?? "" })}
                    disabled={actionLoading}
                    class="px-3 py-1.5 text-sm text-emerald-400 hover:text-emerald-300 border border-emerald-800 hover:border-emerald-700 rounded-lg transition-colors"
                  >Check In</button>
                {/if}
              {:else if currentPlayerEntry.state !== "Finished" && (tournament.state === "Waiting" || tournament.state === "Playing")}
                <button
                  onclick={() => dropPlayer(auth.user?.uid ?? "")}
                  disabled={actionLoading}
                  class="px-3 py-1.5 text-sm text-crimson-400 hover:text-crimson-300 border border-crimson-800 hover:border-crimson-700 rounded-lg transition-colors"
                >Drop Out</button>
              {/if}
            </div>
            <!-- Standings for players -->
            {#if tournament.state !== "Finished" && playerStandings.length > 0}
              <div class="bg-ash-900/50 rounded-lg p-4">
                <h3 class="text-sm font-medium text-bone-100 mb-2">
                  Standings
                  {#if tournament.standings_mode !== "Public"}
                    <span class="text-xs text-ash-500 font-normal ml-1">({tournament.standings_mode === "Cutoff" ? "Top 5" : tournament.standings_mode})</span>
                  {/if}
                </h3>
                <table class="w-full text-sm">
                  <thead>
                    <tr class="text-ash-500 text-xs">
                      <th class="text-left py-1 pr-2">#</th>
                      <th class="text-left py-1 pr-2">Player</th>
                      <th class="text-right py-1 px-2">Score</th>
                    </tr>
                  </thead>
                  <tbody>
                    {#each playerStandings as entry, idx}
                      <tr class="{idx < 5 ? 'text-bone-100' : 'text-ash-400'} border-t border-ash-800">
                        <td class="py-1 pr-2 text-ash-500">{entry.rank}</td>
                        <td class="py-1 pr-2">{seatDisplay(entry.user_uid)}</td>
                        <td class="text-right py-1 px-2">{formatScore(entry.gw, entry.vp, entry.tp)}</td>
                      </tr>
                    {/each}
                  </tbody>
                </table>
              </div>
            {/if}
            <!-- Finals table for player view -->
            {#if isFinals && tournament.finals}
              <div class="bg-ash-900/50 rounded-lg p-4">
                <h3 class="text-sm font-medium text-bone-100 mb-2">Finals</h3>
                <div class="divide-y divide-ash-800">
                  {#each tournament.finals.seating as seat, j}
                    {@const tVps = tournament.finals.seating.map(s => s.result.vp)}
                    {@const tGws = computeGwLocal(tVps)}
                    {@const tTps = computeTpLocal(tournament.finals.seating.length, tVps)}
                    {@const seedIdx = tournament.finals.seed_order.indexOf(seat.player_uid) + 1}
                    {@const seedStanding = standings.find(s => s.user_uid === seat.player_uid)}
                    <div class="py-1.5 flex items-center justify-between text-sm">
                      <div>
                        <span class="text-ash-300">{seatDisplay(seat.player_uid)}</span>
                        <div class="text-xs text-ash-500">Seed #{seedIdx}{#if seedStanding} · {formatScore(seedStanding.gw, seedStanding.vp, seedStanding.tp)}{/if}</div>
                      </div>
                      <div class="flex items-center gap-2">
                        <span class="text-ash-400 text-xs">VP:</span>
                        <select
                          class="bg-ash-800 text-bone-100 text-xs rounded px-1.5 py-0.5 border border-ash-700"
                          disabled={scoreSaving === -1}
                          value={seat.result.vp}
                          onchange={(e) => setFinalsVp(seat.player_uid, parseFloat((e.target as HTMLSelectElement).value), tournament!.finals!.seating)}
                        >
                          {#each vpOptions(tournament.finals.seating.length, false) as v}
                            <option value={v}>{v}</option>
                          {/each}
                        </select>
                        <span class="text-ash-500 text-xs">{tGws[j]}GW {tTps[j]}TP</span>
                      </div>
                    </div>
                  {/each}
                </div>
              </div>
            {:else if tournament.state === "Playing" && tournament.rounds.length > 0 && tournament.rounds[tournament.rounds.length - 1]}
              {@const currentRound = tournament.rounds[tournament.rounds.length - 1]!}
              {@const myTableIdx = currentRound.findIndex(t => t.seating.some(s => s.player_uid === auth.user?.uid))}
              {#if myTableIdx >= 0 && currentRound[myTableIdx]}
                {@const myTable = currentRound[myTableIdx]!}
                <div class="bg-ash-900/50 rounded-lg p-4">
                  <div class="flex items-center justify-between mb-2">
                    <h3 class="text-sm font-medium text-bone-100">Your Table (Table {myTableIdx + 1})</h3>
                    <span class="text-xs px-2 py-0.5 rounded {myTable.state === 'Finished' ? 'bg-emerald-900/60 text-emerald-300' : myTable.state === 'Invalid' ? 'bg-crimson-900/60 text-crimson-300' : 'bg-amber-900/60 text-amber-300'}">
                      {myTable.state}
                    </span>
                  </div>
                  <div class="divide-y divide-ash-800">
                    {#each myTable.seating as seat, j}
                      {@const tVps = myTable.seating.map(s => s.result.vp)}
                      {@const tGws = computeGwLocal(tVps)}
                      {@const tTps = computeTpLocal(myTable.seating.length, tVps)}
                      <div class="py-1.5 flex items-center justify-between text-sm">
                        <span class="text-ash-300">{seatDisplay(seat.player_uid)}</span>
                        <div class="flex items-center gap-2">
                          <span class="text-ash-400 text-xs">VP:</span>
                          <select
                            class="bg-ash-800 text-bone-100 text-xs rounded px-1.5 py-0.5 border border-ash-700"
                            disabled={scoreSaving === myTableIdx}
                            value={seat.result.vp}
                            onchange={(e) => setVp(myTableIdx, seat.player_uid, parseFloat((e.target as HTMLSelectElement).value), myTable.seating)}
                          >
                            {#each vpOptions(myTable.seating.length, false) as v}
                              <option value={v}>{v}</option>
                            {/each}
                          </select>
                          <span class="text-ash-500 text-xs">{tGws[j]}GW {tTps[j]}TP</span>
                        </div>
                      </div>
                    {/each}
                  </div>
                </div>
              {/if}
            {/if}
          {:else}
            <p class="text-ash-400 text-sm">Registration is not open.</p>
          {/if}

          <!-- Registered players list (player view, Planned/Registration) -->
          {#if (tournament.state === "Planned" || tournament.state === "Registration") && tournament.players.length > 0}
            {@const registered = tournament.players.filter(p => p.state === "Registered")}
            {#if registered.length > 0}
              <div class="mt-4">
                <button
                  onclick={() => showRegisteredPlayers = !showRegisteredPlayers}
                  class="text-sm text-ash-400 hover:text-ash-200 transition-colors flex items-center gap-1"
                >
                  <Icon icon={showRegisteredPlayers ? "lucide:chevron-down" : "lucide:chevron-right"} class="w-4 h-4" />
                  Registered players ({registered.length})
                </button>
                {#if showRegisteredPlayers}
                  <div class="mt-2 flex flex-wrap gap-2">
                    {#each registered as player}
                      {@const puid = player.user_uid ?? ""}
                      <span class="px-2 py-1 text-sm bg-ash-800 rounded text-ash-200">
                        {seatDisplay(puid)}
                      </span>
                    {/each}
                  </div>
                {/if}
              </div>
            {/if}
          {/if}

          <!-- Player deck section -->
          {#if currentPlayerEntry || (tournament.state === 'Finished' && tournament.decklists_mode)}
            <div class="mt-4">
              <DecksTab
                {tournament}
                {playerInfo}
                isOrganizer={false}
              />
            </div>
          {/if}
        </div>
      {/if}

      <!-- Finished tournament results (VEKN members only) -->
      {#if !showOrganizerView && tournament.state === "Finished" && auth.user?.vekn_id}
        {@const hasFinals = standings.some(e => e.finals)}
        <div class="bg-dusk-950 rounded-lg shadow border border-ash-800 mb-6 p-6 space-y-4">
          {#if tournament.winner}
            <div class="bg-emerald-900/20 border border-emerald-800 rounded-lg p-4">
              <div class="text-ash-500 text-sm">Winner</div>
              <div class="text-xl font-medium text-bone-100">{seatDisplay(tournament.winner)}</div>
            </div>
          {/if}
          {#if standings.length > 0}
            <div class="bg-ash-900/50 rounded-lg p-4">
              <h3 class="text-sm font-medium text-bone-100 mb-2">Standings</h3>
              <div class="overflow-x-auto">
                <table class="w-full text-sm">
                  <thead>
                    <tr class="text-ash-500 text-xs">
                      <th class="text-left py-1 pr-2">#</th>
                      <th class="text-left py-1 pr-2">Player</th>
                      <th class="text-right py-1 px-2">Score</th>
                      {#if hasFinals}
                        <th class="text-right py-1 px-2">Finals</th>
                      {/if}
                      {#if isFinished}
                        <th class="text-right py-1 px-2">Rating</th>
                      {/if}
                    </tr>
                  </thead>
                  <tbody>
                    {#each standings as entry, idx}
                      <tr class="{idx < 5 ? 'text-bone-100' : 'text-ash-400'} border-t border-ash-800">
                        <td class="py-1 pr-2 text-ash-500">{entry.rank}</td>
                        <td class="py-1 pr-2">{seatDisplay(entry.user_uid)}</td>
                        <td class="text-right py-1 px-2">{formatScore(entry.gw, entry.vp, entry.tp)}</td>
                        {#if hasFinals}
                          <td class="text-right py-1 px-2">{entry.finals ?? ""}</td>
                        {/if}
                        {#if isFinished}
                          <td class="text-right py-1 px-2 text-ash-400">{getRatingPts(entry)}</td>
                        {/if}
                      </tr>
                    {/each}
                  </tbody>
                </table>
              </div>
            </div>
          {/if}
          {#if tournament.finals}
            <div class="bg-ash-900/50 rounded-lg p-4">
              <h3 class="text-sm font-medium text-bone-100 mb-2">Finals Table</h3>
              <div class="divide-y divide-ash-800">
                {#each tournament.finals.seating as seat, j}
                  {@const tVps = tournament.finals.seating.map(s => s.result.vp)}
                  {@const tGws = computeGwLocal(tVps)}
                  {@const tTps = computeTpLocal(tournament.finals.seating.length, tVps)}
                  {@const seedIdx = tournament.finals.seed_order.indexOf(seat.player_uid) + 1}
                  {@const seedStanding = standings.find(s => s.user_uid === seat.player_uid)}
                  <div class="py-1.5 flex items-center justify-between text-sm">
                    <div>
                      <span class="text-ash-300">{seatDisplay(seat.player_uid)}</span>
                      <div class="text-xs text-ash-500">Seed #{seedIdx}{#if seedStanding} · {formatScore(seedStanding.gw, seedStanding.vp, seedStanding.tp)}{/if}</div>
                    </div>
                    <span class="text-ash-500 text-xs">{seat.result.vp}VP {tGws[j]}GW {tTps[j]}TP</span>
                  </div>
                {/each}
              </div>
            </div>
          {/if}
        </div>
      {/if}
      {/if}<!-- end isMinimalView else -->
    {/if}
  </div>
</div>
