<script lang="ts">
  import { page } from "$app/stores";
  import { goto } from "$app/navigation";
  import { untrack } from "svelte";
  import { deleteTournamentApi, tournamentAction, setTableScore } from "$lib/api";
  import { getCountries, getCountryFlag } from "$lib/geonames";
  import { getAuthState, hasAnyRole } from "$lib/stores/auth.svelte";
  import { syncManager } from "$lib/sync";
  import { getUser, getUserByVeknId, getTournament, getSanctionsForTournament, getDeviceId } from "$lib/db";
  import type { Tournament, TournamentState, User, Sanction } from "$lib/types";
  import { scoreSeatingSync, computeRatingPoints, validateDeck, type ValidationError } from "$lib/engine";
  import { formatScore } from "$lib/utils";
  import { getStateBadgeClass, seatDisplay as seatDisplayUtil } from "$lib/tournament-utils";
  import { isOffline, goOffline, goOnline, forceTakeover, getLastSyncTime } from "$lib/stores/offline.svelte";
  import Icon from "@iconify/svelte";
  import { renderMarkdown } from "$lib/markdown";
  import { showToast } from "$lib/stores/toast.svelte";
  import * as m from '$lib/paraglide/messages.js';

  // Deck validation state for player's own deck
  let myDeckErrors = $state<ValidationError[]>([]);

  import OverviewTab from "./OverviewTab.svelte";
  import PlayersTab from "./PlayersTab.svelte";
  import RoundsTab from "./RoundsTab.svelte";
  import FinalsTab from "./FinalsTab.svelte";
  import ConfigTab from "./ConfigTab.svelte";
  import DecksTab from "./DecksTab.svelte"; // Used in player view only
  import SanctionIndicator from "$lib/components/SanctionIndicator.svelte";

  const countries = getCountries();

  let tournament = $state<Tournament | null>(null);
  let tournamentSanctions = $state<Sanction[]>([]);
  let loading = $state(true);
  let error = $state<string | null>(null);
  let actionLoading = $state(false);

  const auth = $derived(getAuthState());
  const uid = $derived($page.params.uid as string);
  const isOrganizer = $derived(
    (tournament?.organizers_uids?.includes(auth.user?.uid ?? "") ||
      auth.user?.roles?.includes("IC")) ?? false
  );
  const currentPlayerEntry = $derived(
    tournament?.players?.find(p => p.user_uid === auth.user?.uid) ?? null
  );
  let viewAsPlayer = $state(false);
  let showRegisteredPlayers = $state(false);
  let showDeleteConfirm = $state(false);
  // Offline mode state
  const tournamentIsOffline = $derived(isOffline(uid));
  const deviceId = getDeviceId();
  const isLockedByOtherDevice = $derived(
    tournament?.offline_mode === true && tournament?.offline_device_id !== deviceId
  );
  let showGoOfflineConfirm = $state(false);
  let showGoOnlineConfirm = $state(false);
  let showForceTakeoverConfirm = $state(false);
  let offlineActionLoading = $state(false);
  const lastSync = $derived(getLastSyncTime(uid));
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
      { id: 'overview', label: m.tournament_tab_overview(), icon: 'lucide:layout-dashboard' },
      { id: 'players', label: m.tournament_tab_players(), icon: 'lucide:users' },
      { id: 'rounds', label: m.tournament_tab_rounds(), icon: 'lucide:swords' },
    ];
    // Show Finals tab when ≥2 rounds played
    const hasFinalsCandidate = (tournament?.rounds?.length ?? 0) >= 2;
    if (hasFinalsCandidate || tournament?.finals) {
      t.push({ id: 'finals', label: m.tournament_tab_finals(), icon: 'lucide:trophy' });
    }
    if (showOrganizerView) {
      t.push({ id: 'config', label: m.tournament_tab_config(), icon: 'lucide:settings' });
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
        .filter(p => p.user_uid && p.result && (p.result.gw || p.result.vp || p.result.tp))
        .map(p => ({
          user_uid: p.user_uid!,
          gw: p.result.gw ?? 0,
          vp: p.result.vp ?? 0,
          tp: p.result.tp ?? 0,
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

  // Player DQ state and sanctions helpers for standings display
  function isPlayerDQ(userUid: string): boolean {
    return tournament?.players?.some(p => p.user_uid === userUid && p.state === "Disqualified") ?? false;
  }
  function sanctionsForPlayer(userUid: string): Sanction[] {
    return tournamentSanctions.filter(s => s.user_uid === userUid);
  }

  function seatDisplay(uid: string): string {
    return seatDisplayUtil(uid, playerInfo);
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
    const roundIndex = tournament.rounds!.length - 1;
    const scores = seating.map(s => ({
      player_uid: s.player_uid,
      vp: s.player_uid === playerUid ? vp : s.result.vp,
    }));
    scoreSaving = tableIndex;
    try {
      tournament = await setTableScore(uid, roundIndex, tableIndex, scores);
      await loadPlayerNames();
    } catch (e) {
      error = e instanceof Error ? e.message : m.tournament_error_save_scores();
    } finally {
      scoreSaving = null;
    }
  }

  async function setFinalsVp(playerUid: string, vp: number, seating: Array<{ player_uid: string; result: { vp: number } }>) {
    if (!tournament) return;
    const roundIndex = tournament.rounds!.length;
    const scores = seating.map(s => ({
      player_uid: s.player_uid,
      vp: s.player_uid === playerUid ? vp : s.result.vp,
    }));
    scoreSaving = -1;
    try {
      tournament = await setTableScore(uid, roundIndex, 0, scores);
      await loadPlayerNames();
    } catch (e) {
      error = e instanceof Error ? e.message : m.tournament_error_save_finals();
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
        tournamentSanctions = await getSanctionsForTournament(uid);
      } else if (!tournament) {
        // No data in IndexedDB yet — will arrive via SSE
        error = m.tournament_error_not_synced();
      }
    } catch (e) {
      error = e instanceof Error ? e.message : m.tournament_error_load();
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
      error = e instanceof Error ? e.message : m.tournament_error_action();
    } finally {
      actionLoading = false;
    }
  }

  async function handleDelete() {
    try {
      await deleteTournamentApi(uid);
      showDeleteConfirm = false;
      goto("/tournaments");
    } catch (e) {
      error = e instanceof Error ? e.message : m.tournament_error_delete();
      showDeleteConfirm = false;
    }
  }

  async function handleGoOffline() {
    offlineActionLoading = true;
    try {
      await goOffline(uid);
      showGoOfflineConfirm = false;
      showToast({ type: 'success', message: m.offline_now_offline() });
    } catch (e) {
      showToast({ type: 'error', message: e instanceof Error ? e.message : m.offline_error_go_offline() });
    } finally {
      offlineActionLoading = false;
    }
  }

  async function handleGoOnline() {
    offlineActionLoading = true;
    try {
      tournament = await goOnline(uid);
      await loadPlayerNames();
      showGoOnlineConfirm = false;
      showToast({ type: 'success', message: m.offline_back_online() });
    } catch (e) {
      showToast({ type: 'error', message: e instanceof Error ? e.message : m.offline_error_go_online() });
    } finally {
      offlineActionLoading = false;
    }
  }

  async function handleForceTakeover() {
    offlineActionLoading = true;
    try {
      await forceTakeover(uid);
      showForceTakeoverConfirm = false;
      showToast({ type: 'success', message: m.offline_takeover_success() });
    } catch (e) {
      showToast({ type: 'error', message: e instanceof Error ? e.message : m.offline_error_takeover() });
    } finally {
      offlineActionLoading = false;
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

  async function dropPlayer(playerUid: string) {
    await doAction("DropOut", { player_uid: playerUid });
  }

  $effect(() => {
    const _currentUid = uid; // explicit dependency on uid
    untrack(() => load());

    const handleSync = (event: { type: string }) => {
      if (event.type === "tournament") untrack(() => load());
      if (event.type === "sanction") {
        getSanctionsForTournament(uid).then(s => { tournamentSanctions = s; });
      }
    };
    syncManager.addEventListener(handleSync);
    return () => syncManager.removeEventListener(handleSync);
  });
</script>

<svelte:head>
  <title>{tournament?.name ?? m.tournament_fallback_title()} - Archon</title>
</svelte:head>

<div class="p-4 sm:p-8">
  <div class="max-w-4xl mx-auto">
    <!-- Back link -->
    <a href="/tournaments" class="inline-flex items-center gap-2 text-ash-400 hover:text-ash-200 mb-4">
      <Icon icon="lucide:arrow-left" class="w-4 h-4" />
      {m.nav_tournaments()}
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
      <!-- Offline mode banner (this device has lock) -->
      {#if tournamentIsOffline}
        <div class="bg-amber-900/30 border border-amber-700 rounded-lg p-4 mb-4 flex items-center justify-between gap-4">
          <div class="flex items-center gap-2 min-w-0">
            <Icon icon="lucide:wifi-off" class="w-5 h-5 text-amber-400 shrink-0" />
            <div class="min-w-0">
              <span class="text-amber-200 font-medium text-sm">{m.offline_mode_banner()}</span>
              {#if lastSync}
                <span class="text-xs text-ash-400 ml-2">{m.offline_last_sync({ time: new Date(lastSync).toLocaleTimeString() })}</span>
              {:else}
                <span class="text-xs text-ash-500 ml-2">{m.offline_not_synced()}</span>
              {/if}
            </div>
          </div>
          <button
            onclick={() => showGoOnlineConfirm = true}
            disabled={offlineActionLoading}
            class="px-4 py-2 text-sm font-medium text-white bg-emerald-700 hover:bg-emerald-600 disabled:bg-ash-700 rounded-lg transition-colors shrink-0"
          >
            <Icon icon="lucide:wifi" class="w-4 h-4 inline mr-1" />
            {m.offline_go_online()}
          </button>
        </div>
      {/if}

      <!-- Locked by another device banner -->
      {#if isLockedByOtherDevice}
        <div class="bg-ash-900/50 border border-ash-700 rounded-lg p-4 mb-4">
          <div class="flex items-center justify-between gap-4">
            <div class="flex items-center gap-2 min-w-0">
              <Icon icon="lucide:lock" class="w-5 h-5 text-ash-400 shrink-0" />
              <span class="text-ash-300 text-sm">{m.offline_locked_banner()}</span>
            </div>
            {#if isOrganizer}
              <button
                onclick={() => showForceTakeoverConfirm = true}
                disabled={offlineActionLoading}
                class="px-3 py-1.5 text-sm text-amber-400 hover:text-amber-300 border border-amber-800 hover:border-amber-700 rounded-lg transition-colors shrink-0"
              >
                {m.offline_force_takeover()}
              </button>
            {/if}
          </div>
        </div>
      {/if}

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

        <div class="flex items-center gap-2">
          {#if showOrganizerView && !tournament.offline_mode}
            <button
              onclick={() => showGoOfflineConfirm = true}
              class="px-3 py-1.5 text-sm text-amber-400 hover:text-amber-300 border border-amber-800 hover:border-amber-700 rounded-lg transition-colors"
            >
              <Icon icon="lucide:wifi-off" class="w-4 h-4 inline mr-1" />
              {m.offline_go_offline()}
            </button>
          {/if}
          {#if showOrganizerView && tournament.state === "Planned"}
            <button
              onclick={() => (showDeleteConfirm = true)}
              class="px-3 py-1.5 text-sm text-crimson-400 hover:text-crimson-300 border border-crimson-800 hover:border-crimson-700 rounded-lg transition-colors"
            >{m.common_delete()}</button>
          {/if}
        </div>
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
            <div class="text-ash-500">{m.tournament_info_date()}</div>
            <div class="text-ash-200">{formatDate(tournament.start)}</div>
            {#if formatDateLocal(tournament.start)}
              <div class="text-xs text-ash-500">{formatDateLocal(tournament.start)} {m.tournament_in_timezone()}</div>
            {/if}
          </div>
          <div>
            <div class="text-ash-500">{m.tournament_info_location()}</div>
            <div class="text-ash-200">
              {#if tournament.online}
                {m.tournaments_online()}
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
            <div class="text-ash-500">{m.tournament_info_players()}</div>
            <div class="text-ash-200">{m.tournament_registered_count({ count: String(tournament.players.length) })}</div>
          </div>
          {/if}
          {#if tournament.description}
            <div class="col-span-full">
              <div class="text-ash-500">{m.common_description()}</div>
              <div class="mt-1 prose dark:prose-invert prose-sm max-w-none">{@html renderMarkdown(tournament.description)}</div>
            </div>
          {/if}
        </div>
      </div>

      {#if isMinimalView}
        <div class="bg-dusk-950 rounded-lg shadow border border-ash-800 p-6 text-center">
          <p class="text-ash-400">{m.tournament_sign_in_details()}</p>
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
            {viewAsPlayer ? m.tournament_view_organizer() : m.tournament_view_player()}
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
                {tournamentSanctions}
                isOfflineMode={tournamentIsOffline}
              />
            {:else if activeTab === 'rounds'}
              <RoundsTab
                bind:tournament={tournament}
                {playerInfo}
                isOrganizer={true}
                {actionLoading}
                {doAction}
                {loadPlayerNames}
                {tournamentSanctions}
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
              class="px-4 py-2 text-sm font-medium text-white bg-emerald-700 hover:bg-emerald-600 disabled:bg-ash-700 rounded-lg transition-colors"
            >{m.tournament_register_btn()}</button>
          {:else if tournament.state === "Registration" && currentPlayerEntry}
            <div class="text-sm mb-3 flex items-center justify-between">
              <div>
                <span class="text-ash-500">{m.tournament_your_status()}</span>
                <span class="ml-2 text-ash-200">{currentPlayerEntry.state}</span>
              </div>
              <button
                onclick={() => doAction("Unregister", { user_uid: auth.user?.uid })}
                disabled={actionLoading}
                class="px-3 py-1.5 text-sm text-crimson-400 hover:text-crimson-300 border border-crimson-800 hover:border-crimson-700 rounded-lg transition-colors"
              >{m.tournament_unregister_btn()}</button>
            </div>
          {:else if currentPlayerEntry}
            <div class="text-sm mb-3 flex items-center justify-between">
              <div>
                <span class="text-ash-500">{m.tournament_your_status()}</span>
                <span class="ml-2 text-ash-200">{currentPlayerEntry.state === "Finished"
                  ? ((tournament.finals !== null || tournament.state === "Finished") && standings.some(s => s.user_uid === currentPlayerEntry.user_uid) ? m.tournament_status_finished() : m.tournament_status_dropped())
                  : currentPlayerEntry.state}</span>
              </div>
              {#if currentPlayerEntry.state === "Registered" && tournament.state === "Waiting" && !playerHasValidDeck}
                <div class="flex items-center gap-2 text-amber-400 text-sm">
                  <Icon icon="lucide:alert-triangle" class="w-4 h-4" />
                  {m.tournament_upload_valid_deck()}
                </div>
              {:else if currentPlayerEntry.state === "Finished" && tournament.state === "Waiting"}
                {#if !playerHasValidDeck}
                  <div class="flex items-center gap-2 text-amber-400 text-sm">
                    <Icon icon="lucide:alert-triangle" class="w-4 h-4" />
                    {m.tournament_upload_valid_deck()}
                  </div>
                {:else}
                  <button
                    onclick={() => doAction("CheckIn", { player_uid: auth.user?.uid ?? "" })}
                    disabled={actionLoading}
                    class="px-3 py-1.5 text-sm text-emerald-400 hover:text-emerald-300 border border-emerald-800 hover:border-emerald-700 rounded-lg transition-colors"
                  >{m.tournament_check_in_btn()}</button>
                {/if}
              {:else if currentPlayerEntry.state !== "Finished" && (tournament.state === "Waiting" || tournament.state === "Playing")}
                <button
                  onclick={() => dropPlayer(auth.user?.uid ?? "")}
                  disabled={actionLoading}
                  class="px-3 py-1.5 text-sm text-crimson-400 hover:text-crimson-300 border border-crimson-800 hover:border-crimson-700 rounded-lg transition-colors"
                >{m.tournament_drop_out_btn()}</button>
              {/if}
            </div>
            <!-- Standings for players -->
            {#if tournament.state !== "Finished" && playerStandings.length > 0}
              <div class="bg-ash-900/50 rounded-lg p-4">
                <h3 class="text-sm font-medium text-bone-100 mb-2">
                  {m.tournament_standings()}
                  {#if tournament.standings_mode !== "Public"}
                    <span class="text-xs text-ash-500 font-normal ml-1">({tournament.standings_mode === "Cutoff" ? m.tournament_standings_top5() : tournament.standings_mode})</span>
                  {/if}
                </h3>
                <table class="w-full text-sm">
                  <thead>
                    <tr class="text-ash-500 text-xs">
                      <th class="text-left py-1 pr-2">{m.tournament_col_rank()}</th>
                      <th class="text-left py-1 pr-2">{m.tournament_col_player()}</th>
                      <th class="text-right py-1 px-2">{m.tournament_col_score()}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {#each playerStandings as entry, idx}
                      <tr class="{idx < 5 ? 'text-bone-100' : 'text-ash-400'} border-t border-ash-800">
                        <td class="py-1 pr-2 text-ash-500">{entry.rank}</td>
                        <td class="py-1 pr-2">
                          <span class="inline-flex items-center gap-1">
                            {seatDisplay(entry.user_uid)}
                            <SanctionIndicator sanctions={sanctionsForPlayer(entry.user_uid)} />
                            {#if isPlayerDQ(entry.user_uid)}<span class="text-xs text-crimson-400">{m.tournament_disqualified()}</span>{/if}
                          </span>
                        </td>
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
                <h3 class="text-sm font-medium text-bone-100 mb-2">{m.tournament_finals_heading()}</h3>
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
                        <div class="text-xs text-ash-500">{m.tournament_seed({ n: String(seedIdx) })}{#if seedStanding} · {formatScore(seedStanding.gw, seedStanding.vp, seedStanding.tp)}{/if}</div>
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
            {:else if tournament.state === "Playing" && (tournament.rounds?.length ?? 0) > 0 && tournament.rounds![tournament.rounds!.length - 1]}
              {@const currentRound = tournament.rounds![tournament.rounds!.length - 1]!}
              {@const myTableIdx = currentRound.findIndex(t => t.seating.some(s => s.player_uid === auth.user?.uid))}
              {#if myTableIdx >= 0 && currentRound[myTableIdx]}
                {@const myTable = currentRound[myTableIdx]!}
                <div class="bg-ash-900/50 rounded-lg p-4">
                  <div class="flex items-center justify-between mb-2">
                    <h3 class="text-sm font-medium text-bone-100">{m.tournament_your_table({ n: String(myTableIdx + 1) })}</h3>
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
            <p class="text-ash-400 text-sm">{m.tournament_registration_not_open()}</p>
          {/if}

          <!-- Registered players list (player view, Planned/Registration) -->
          {#if (tournament.state === "Planned" || tournament.state === "Registration") && (tournament.players?.length ?? 0) > 0}
            {@const registered = tournament.players!.filter(p => p.state === "Registered")}
            {#if registered.length > 0}
              <div class="mt-4">
                <button
                  onclick={() => showRegisteredPlayers = !showRegisteredPlayers}
                  class="text-sm text-ash-400 hover:text-ash-200 transition-colors flex items-center gap-1"
                >
                  <Icon icon={showRegisteredPlayers ? "lucide:chevron-down" : "lucide:chevron-right"} class="w-4 h-4" />
                  {m.tournament_registered_players({ count: String(registered.length) })}
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
              <div class="text-ash-500 text-sm">{m.tournament_winner()}</div>
              <div class="text-xl font-medium text-bone-100">{seatDisplay(tournament.winner)}</div>
            </div>
          {/if}
          {#if standings.length > 0}
            <div class="bg-ash-900/50 rounded-lg p-4">
              <h3 class="text-sm font-medium text-bone-100 mb-2">{m.tournament_standings()}</h3>
              <div class="overflow-x-auto">
                <table class="w-full text-sm">
                  <thead>
                    <tr class="text-ash-500 text-xs">
                      <th class="text-left py-1 pr-2">{m.tournament_col_rank()}</th>
                      <th class="text-left py-1 pr-2">{m.tournament_col_player()}</th>
                      <th class="text-right py-1 px-2">{m.tournament_col_score()}</th>
                      {#if hasFinals}
                        <th class="text-right py-1 px-2">{m.tournament_col_finals()}</th>
                      {/if}
                      {#if isFinished}
                        <th class="text-right py-1 px-2">{m.tournament_col_rating()}</th>
                      {/if}
                    </tr>
                  </thead>
                  <tbody>
                    {#each standings as entry, idx}
                      <tr class="{idx < 5 ? 'text-bone-100' : 'text-ash-400'} border-t border-ash-800">
                        <td class="py-1 pr-2 text-ash-500">{entry.rank}</td>
                        <td class="py-1 pr-2">
                          <span class="inline-flex items-center gap-1">
                            {seatDisplay(entry.user_uid)}
                            <SanctionIndicator sanctions={sanctionsForPlayer(entry.user_uid)} />
                            {#if isPlayerDQ(entry.user_uid)}<span class="text-xs text-crimson-400">{m.tournament_disqualified()}</span>{/if}
                          </span>
                        </td>
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
              <h3 class="text-sm font-medium text-bone-100 mb-2">{m.tournament_finals_table()}</h3>
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
                      <div class="text-xs text-ash-500">{m.tournament_seed({ n: String(seedIdx) })}{#if seedStanding} · {formatScore(seedStanding.gw, seedStanding.vp, seedStanding.tp)}{/if}</div>
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

<!-- Delete Tournament Confirmation Modal -->
{#if showDeleteConfirm}
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
  <div
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
    role="presentation"
    onclick={() => (showDeleteConfirm = false)}
    onkeydown={(e) => { if (e.key === 'Escape') showDeleteConfirm = false; }}
  >
    <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
    <div
      class="bg-dusk-950 rounded-lg shadow-xl border border-ash-800 w-full max-w-md mx-4"
      onclick={(e) => e.stopPropagation()}
      onkeydown={(e) => e.stopPropagation()}
      role="dialog"
      aria-modal="true"
      tabindex="-1"
    >
      <div class="p-6 border-b border-ash-800">
        <h2 class="text-xl font-medium text-crimson-400">{m.tournament_delete_title()}</h2>
      </div>
      <div class="p-6">
        <p class="text-ash-300 mb-6">
          {m.tournament_delete_msg()}
        </p>
        <div class="flex gap-2">
          <button
            onclick={handleDelete}
            class="flex-1 px-4 py-2 bg-crimson-700 hover:bg-crimson-600 text-white rounded font-medium transition-colors"
          >{m.common_delete()}</button>
          <button
            onclick={() => (showDeleteConfirm = false)}
            class="px-4 py-2 bg-ash-700 hover:bg-ash-600 text-ash-200 rounded font-medium transition-colors"
          >{m.common_cancel()}</button>
        </div>
      </div>
    </div>
  </div>
{/if}

<!-- Go Offline Confirmation Modal -->
{#if showGoOfflineConfirm}
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
  <div
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
    role="presentation"
    onclick={() => (showGoOfflineConfirm = false)}
    onkeydown={(e) => { if (e.key === 'Escape') showGoOfflineConfirm = false; }}
  >
    <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
    <div
      class="bg-dusk-950 rounded-lg shadow-xl border border-ash-800 w-full max-w-md mx-4"
      onclick={(e) => e.stopPropagation()}
      onkeydown={(e) => e.stopPropagation()}
      role="dialog"
      aria-modal="true"
      tabindex="-1"
    >
      <div class="p-6 border-b border-ash-800">
        <h2 class="text-xl font-medium text-amber-400">{m.offline_go_offline_title()}</h2>
      </div>
      <div class="p-6">
        <p class="text-ash-300 mb-6">{m.offline_go_offline_msg()}</p>
        <div class="flex gap-2">
          <button
            onclick={handleGoOffline}
            disabled={offlineActionLoading}
            class="flex-1 px-4 py-2 bg-amber-700 hover:bg-amber-600 disabled:bg-ash-700 text-white rounded font-medium transition-colors"
          >{offlineActionLoading ? m.common_loading() : m.offline_go_offline_confirm()}</button>
          <button
            onclick={() => (showGoOfflineConfirm = false)}
            class="px-4 py-2 bg-ash-700 hover:bg-ash-600 text-ash-200 rounded font-medium transition-colors"
          >{m.common_cancel()}</button>
        </div>
      </div>
    </div>
  </div>
{/if}

<!-- Go Online Confirmation Modal -->
{#if showGoOnlineConfirm}
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
  <div
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
    role="presentation"
    onclick={() => (showGoOnlineConfirm = false)}
    onkeydown={(e) => { if (e.key === 'Escape') showGoOnlineConfirm = false; }}
  >
    <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
    <div
      class="bg-dusk-950 rounded-lg shadow-xl border border-ash-800 w-full max-w-md mx-4"
      onclick={(e) => e.stopPropagation()}
      onkeydown={(e) => e.stopPropagation()}
      role="dialog"
      aria-modal="true"
      tabindex="-1"
    >
      <div class="p-6 border-b border-ash-800">
        <h2 class="text-xl font-medium text-emerald-400">{m.offline_go_online_title()}</h2>
      </div>
      <div class="p-6">
        <p class="text-ash-300 mb-6">{m.offline_go_online_msg()}</p>
        <div class="flex gap-2">
          <button
            onclick={handleGoOnline}
            disabled={offlineActionLoading}
            class="flex-1 px-4 py-2 bg-emerald-700 hover:bg-emerald-600 disabled:bg-ash-700 text-white rounded font-medium transition-colors"
          >{offlineActionLoading ? m.common_loading() : m.offline_go_online_confirm()}</button>
          <button
            onclick={() => (showGoOnlineConfirm = false)}
            class="px-4 py-2 bg-ash-700 hover:bg-ash-600 text-ash-200 rounded font-medium transition-colors"
          >{m.common_cancel()}</button>
        </div>
      </div>
    </div>
  </div>
{/if}

<!-- Force Takeover Confirmation Modal -->
{#if showForceTakeoverConfirm}
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
  <div
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
    role="presentation"
    onclick={() => (showForceTakeoverConfirm = false)}
    onkeydown={(e) => { if (e.key === 'Escape') showForceTakeoverConfirm = false; }}
  >
    <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
    <div
      class="bg-dusk-950 rounded-lg shadow-xl border border-ash-800 w-full max-w-md mx-4"
      onclick={(e) => e.stopPropagation()}
      onkeydown={(e) => e.stopPropagation()}
      role="dialog"
      aria-modal="true"
      tabindex="-1"
    >
      <div class="p-6 border-b border-ash-800">
        <h2 class="text-xl font-medium text-amber-400">{m.offline_force_takeover_title()}</h2>
      </div>
      <div class="p-6">
        <p class="text-ash-300 mb-6">{m.offline_force_takeover_msg()}</p>
        <div class="flex gap-2">
          <button
            onclick={handleForceTakeover}
            disabled={offlineActionLoading}
            class="flex-1 px-4 py-2 bg-amber-700 hover:bg-amber-600 disabled:bg-ash-700 text-white rounded font-medium transition-colors"
          >{offlineActionLoading ? m.common_loading() : m.offline_force_takeover_confirm()}</button>
          <button
            onclick={() => (showForceTakeoverConfirm = false)}
            class="px-4 py-2 bg-ash-700 hover:bg-ash-600 text-ash-200 rounded font-medium transition-colors"
          >{m.common_cancel()}</button>
        </div>
      </div>
    </div>
  </div>
{/if}
