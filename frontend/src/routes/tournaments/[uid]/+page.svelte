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
  import { getStateBadgeClass, seatDisplay as seatDisplayUtil, vpOptions, computeGwLocal, computeTpLocal, stripLeadingTitle, translateTournamentState, top5HasTies as top5HasTiesFn, type StandingEntry } from "$lib/tournament-utils";
  import { isOffline, goOffline, goOnline, forceTakeover, getLastSyncTime } from "$lib/stores/offline.svelte";
  import { ArrowLeft, Loader2, WifiOff, Wifi, Lock, Shield, User as UserIcon, TriangleAlert, LayoutDashboard, Users, Swords, Trophy, Settings, ChevronDown, ChevronRight, ExternalLink, MapPin, QrCode } from "lucide-svelte";
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
  import TournamentModals from "./TournamentModals.svelte";
  import PlayerView from "./PlayerView.svelte";
  import JudgeCallBanner from "./JudgeCallBanner.svelte";
  import SanctionIndicator from "$lib/components/SanctionIndicator.svelte";
  import QrCheckinDisplay from "$lib/components/QrCheckinDisplay.svelte";
  import type { JudgeCallData } from "$lib/sync";

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
  let descriptionExpanded = $state(false);
  let showDeleteConfirm = $state(false);
  // Offline mode state
  const tournamentIsOffline = $derived(isOffline(uid));
  const deviceId = getDeviceId();
  const isLockedByOtherDevice = $derived(
    tournament?.offline_mode === true && tournament?.offline_device_id !== deviceId
  );
  let judgeCallBanner = $state<ReturnType<typeof JudgeCallBanner> | null>(null);
  let showQrCode = $state(false);
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
    const t: { id: TabId; label: string; icon: typeof LayoutDashboard }[] = [
      { id: 'overview', label: m.tournament_tab_overview(), icon: LayoutDashboard },
      { id: 'players', label: m.tournament_tab_players(), icon: Users },
      { id: 'rounds', label: m.tournament_tab_rounds(), icon: Swords },
    ];
    // Show Finals tab when ≥2 rounds played
    const hasFinalsCandidate = (tournament?.rounds?.length ?? 0) >= 2;
    if (hasFinalsCandidate || tournament?.finals) {
      t.push({ id: 'finals', label: m.tournament_tab_finals(), icon: Trophy });
    }
    if (showOrganizerView) {
      t.push({ id: 'config', label: m.tournament_tab_config(), icon: Settings });
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
  function computeStandings(): StandingEntry[] {
    if (!tournament || !tournament.players) return [];

    // VEKN-synced tournaments: no rounds, use tournament.standings directly
    if (!tournament.rounds || tournament.rounds.length < 1) {
      const finalistUids = new Set(
        tournament.players.filter(p => p.finalist && p.user_uid).map(p => p.user_uid!)
      );
      // Prefer tournament.standings (populated by VEKN import), fall back to player.result
      const entries: StandingEntry[] = (tournament.standings?.length
        ? tournament.standings.map(s => ({
            user_uid: s.user_uid,
            gw: s.gw ?? 0,
            vp: s.vp ?? 0,
            tp: s.tp ?? 0,
            toss: s.toss ?? 0,
            rank: 0,
          }))
        : tournament.players
          .filter(p => p.user_uid && p.result && (p.result.gw || p.result.vp || p.result.tp))
          .map(p => ({
            user_uid: p.user_uid!,
            gw: p.result.gw ?? 0,
            vp: p.result.vp ?? 0,
            tp: p.result.tp ?? 0,
            toss: p.toss ?? 0,
            rank: 0,
          }))
      );
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
    if (mode === "Cutoff") return [];
    if (mode === "Top 10") return standings.slice(0, 10);
    return standings;
  });

  // Cutoff score: 5th player's score threshold for finals selection
  const cutoffScore = $derived.by(() => {
    if (tournament?.state === "Finished") return null;
    if ((tournament?.standings_mode ?? "Private") !== "Cutoff") return null;
    const entry = standings[4];
    if (!entry) return null;
    return { gw: entry.gw, vp: entry.vp, tp: entry.tp };
  });

  const isFinals = $derived(tournament?.finals != null && (tournament?.state === "Playing" || tournament?.state === "Finished"));

  // Action bar derived values
  const registeredCount = $derived(tournament?.players?.length ?? 0);
  const checkedInCount = $derived(tournament?.players?.filter(p => p.state === "Checked-in").length ?? 0);
  const finishedPlayerCount = $derived(tournament?.players?.filter(p => p.state === "Finished").length ?? 0);
  const hasRounds = $derived((tournament?.rounds?.length ?? 0) > 0);
  const hasFinalsCandidate = $derived(standings.length >= 5 && (tournament?.rounds?.length ?? 0) >= 2);
  const finalsReady = $derived(hasFinalsCandidate && !top5HasTiesFn(standings));
  const allTablesFinished = $derived.by(() => {
    if (!tournament?.rounds?.length) return false;
    const lastRound = tournament.rounds[tournament.rounds.length - 1]!;
    return lastRound.length > 0 && lastRound.every(t => t.state === "Finished");
  });
  const finalsTableFinished = $derived(tournament?.finals?.state === "Finished");
  const tablesFinishedCount = $derived.by(() => {
    if (!tournament?.rounds?.length) return { done: 0, total: 0 };
    const lastRound = tournament.rounds[tournament.rounds.length - 1]!;
    return { done: lastRound.filter(t => t.state === "Finished").length, total: lastRound.length };
  });

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

    const handleSync = (event: { type: string; data?: any }) => {
      if (event.type === "tournament") untrack(() => load());
      if (event.type === "sanction") {
        getSanctionsForTournament(uid).then(s => { tournamentSanctions = s; });
      }
      if (event.type === "judge_call" && event.data) {
        judgeCallBanner?.addCall(event.data as JudgeCallData);
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
      <ArrowLeft class="w-4 h-4" />
      {m.nav_tournaments()}
    </a>

    {#if loading}
      <div class="text-center py-12">
        <Loader2 class="mx-auto h-12 w-12 text-ash-500 animate-spin" />
      </div>
    {:else if error && !tournament}
      <div class="bg-crimson-900/20 border border-crimson-800 rounded-lg p-4">
        <p class="text-crimson-300">{error}</p>
      </div>
    {:else if tournament}
      <!-- Offline mode banner (this device has lock) -->
      {#if tournamentIsOffline}
        <div class="banner-amber border rounded-lg p-4 mb-4 flex items-center justify-between gap-4">
          <div class="flex items-center gap-2 min-w-0">
            <WifiOff class="w-5 h-5 shrink-0" />
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
            class="px-4 py-2 text-sm font-medium btn-emerald disabled:bg-ash-700 rounded-lg transition-colors shrink-0"
          >
            <Wifi class="w-4 h-4 inline mr-1" />
            {m.offline_go_online()}
          </button>
        </div>
      {/if}

      <!-- Locked by another device banner -->
      {#if isLockedByOtherDevice}
        <div class="bg-ash-900/50 border border-ash-700 rounded-lg p-4 mb-4">
          <div class="flex items-center justify-between gap-4">
            <div class="flex items-center gap-2 min-w-0">
              <Lock class="w-5 h-5 text-ash-400 shrink-0" />
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
              {translateTournamentState(tournament.state)}
            </span>
            <span class="text-sm text-ash-400">{tournament.format}</span>
            {#if tournament.rank}
              <span class="text-sm text-ash-400">· {tournament.rank}</span>
            {/if}
            {#if tournament.external_ids?.vekn}
              <a href="https://www.vekn.net/event-calendar/event/{tournament.external_ids.vekn}"
                 target="_blank" rel="noopener noreferrer"
                 class="px-2 py-0.5 rounded text-xs font-medium bg-dusk-800 text-ash-300 hover:text-ash-100 inline-flex items-center gap-1"
                 title="View on vekn.net">
                VEKN <ExternalLink class="w-3 h-3" />
              </a>
            {/if}
          </div>
        </div>

        <div class="flex items-center gap-2">
          {#if showOrganizerView && !tournament.offline_mode}
            <button
              onclick={() => showGoOfflineConfirm = true}
              class="px-3 py-1.5 text-sm text-amber-400 hover:text-amber-300 border border-amber-800 hover:border-amber-700 rounded-lg transition-colors"
            >
              <WifiOff class="w-4 h-4 inline mr-1" />
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
                  <br />
                  {#if tournament.venue_url}
                    <a href={tournament.venue_url} target="_blank" rel="noopener" class="text-ash-400 hover:text-ember-400 inline-flex items-center gap-1">{tournament.venue} <ExternalLink class="w-3 h-3" /></a>
                  {:else}
                    <span class="text-ash-400">{tournament.venue}</span>
                  {/if}
                {/if}
                {#if tournament.address}
                  <br />
                  {#if tournament.map_url}
                    <a href={tournament.map_url} target="_blank" rel="noopener" class="text-ash-500 hover:text-ember-400 text-xs inline-flex items-center gap-1"><MapPin class="w-3 h-3" /> {tournament.address}</a>
                  {:else}
                    <span class="text-ash-500 text-xs"><MapPin class="w-3 h-3 inline" /> {tournament.address}</span>
                  {/if}
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
        </div>
      </div>

      <!-- Collapsible description -->
      {#if tournament.description}
        {@const cleaned = stripLeadingTitle(tournament.description, tournament.name)}
        <div class="bg-dusk-950 rounded-lg shadow border border-ash-800 mb-6">
          <button
            onclick={() => descriptionExpanded = !descriptionExpanded}
            class="w-full flex items-center gap-2 px-4 py-3 text-left text-sm font-medium text-ash-300 hover:text-bone-100 transition-colors"
          >
            {#if descriptionExpanded}<ChevronDown class="w-4 h-4 shrink-0" />{:else}<ChevronRight class="w-4 h-4 shrink-0" />{/if}
            {m.common_description()}
          </button>
          {#if descriptionExpanded}
            <div class="px-4 pb-4 prose dark:prose-invert prose-sm max-w-none">{@html renderMarkdown(cleaned)}</div>
          {:else}
            <div class="px-4 pb-3 text-sm text-ash-400 line-clamp-3">{@html renderMarkdown(cleaned)}</div>
          {/if}
        </div>
      {/if}

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
            {#if viewAsPlayer}<Shield class="w-4 h-4 inline mr-1" />{:else}<UserIcon class="w-4 h-4 inline mr-1" />{/if}
            {viewAsPlayer ? m.tournament_view_organizer() : m.tournament_view_player()}
          </button>
        </div>
      {/if}

      <!-- Judge Call Banner (organizer only) -->
      {#if showOrganizerView && tournament.state === "Playing"}
        <JudgeCallBanner bind:this={judgeCallBanner} tournamentUid={uid} />
      {/if}

      <!-- Organizer Console with Tabs -->
      {#if showOrganizerView}
        <div class="bg-dusk-950 rounded-lg shadow border border-ash-800 mb-6">
          <!-- Tab bar -->
          <div class="flex border-b border-ash-800 overflow-x-auto">
            {#each tabs as tab}
              {@const TabIcon = tab.icon}
              <button
                onclick={() => activeTab = tab.id}
                class="flex items-center gap-1.5 px-4 py-3 text-sm font-medium whitespace-nowrap transition-colors border-b-2 {activeTab === tab.id ? 'border-crimson-500 text-bone-100' : 'border-transparent text-ash-400 hover:text-ash-200 hover:border-ash-600'}"
              >
                <TabIcon class="w-4 h-4" />
                {tab.label}
              </button>
            {/each}
          </div>

          <!-- Action Bar -->
          <div class="border-b border-ash-800 px-3 sm:px-6 py-3 space-y-3">
            <!-- Step indicator -->
            <div class="flex items-center gap-1 sm:gap-2 text-xs overflow-x-auto">
              {#each ["Planned", "Registration", "Waiting", "Playing", "Finished"] as step, i}
                {@const states = ["Planned", "Registration", "Waiting", "Playing", "Finished"]}
                {@const currentIdx = states.indexOf(tournament.state)}
                {@const isDone = i < currentIdx}
                {@const isCurrent = i === currentIdx}
                {#if i > 0}<span class="text-ash-700">—</span>{/if}
                <span class="whitespace-nowrap {isDone ? 'text-emerald-400' : isCurrent ? 'text-crimson-400 font-medium' : 'text-ash-600'}">
                  <span class="inline-block w-2 h-2 rounded-full mr-1 align-middle {isDone ? 'bg-emerald-400' : isCurrent ? 'bg-crimson-400' : 'bg-ash-700'}"></span>
                  <span class="hidden sm:inline">{translateTournamentState(step as TournamentState)}</span>
                </span>
              {/each}
            </div>

            <!-- Guidance message -->
            <p class="text-sm text-ash-400">
              {#if tournament.state === "Planned"}
                {m.action_bar_planned()}
              {:else if tournament.state === "Registration"}
                {m.action_bar_registration({ count: String(registeredCount) })}
              {:else if tournament.state === "Waiting"}
                {#if hasFinalsCandidate}
                  {m.action_bar_waiting_finals_ready({ n: String(tournament.rounds!.length) })}
                {:else if hasRounds}
                  {m.action_bar_waiting_after_round({ n: String(tournament.rounds!.length) })}
                {:else}
                  {m.action_bar_waiting_initial({ checked: String(checkedInCount), total: String(registeredCount - finishedPlayerCount) })}
                {/if}
              {:else if tournament.state === "Playing"}
                {#if isFinals}
                  {m.action_bar_playing_finals()}
                {:else}
                  {m.action_bar_playing_round({ n: String(tournament.rounds!.length), done: String(tablesFinishedCount.done), total: String(tablesFinishedCount.total) })}
                {/if}
              {:else if tournament.state === "Finished"}
                {m.action_bar_finished()}
              {/if}
            </p>

            <!-- Primary actions -->
            <div class="flex flex-wrap gap-2">
              {#if tournament.state === "Planned"}
                <button onclick={() => doAction("OpenRegistration")} disabled={actionLoading}
                  class="px-4 py-2 text-sm font-medium btn-emerald disabled:bg-ash-700 rounded-lg transition-colors"
                >{m.overview_open_registration()}</button>

              {:else if tournament.state === "Registration"}
                <button onclick={() => doAction("CloseRegistration")} disabled={actionLoading}
                  class="px-4 py-2 text-sm font-medium btn-amber disabled:bg-ash-700 rounded-lg transition-colors"
                >{m.overview_close_registration()}</button>
                <button onclick={() => doAction("CancelRegistration")} disabled={actionLoading}
                  class="px-3 py-1.5 text-sm text-ash-300 border border-ash-700 hover:border-ash-600 hover:text-ash-200 rounded-lg transition-colors"
                >{m.overview_back_to_planning()}</button>
                {#if tournament.checkin_code}
                  <button onclick={() => showQrCode = !showQrCode}
                    class="px-3 py-1.5 text-sm text-ash-300 bg-ash-800 hover:bg-ash-700 rounded-lg transition-colors flex items-center gap-1.5"
                  >
                    <QrCode class="w-4 h-4" />
                    {showQrCode ? m.checkin_qr_hide_code() : m.checkin_qr_show_code()}
                  </button>
                {/if}

              {:else if tournament.state === "Waiting"}
                <button onclick={() => doAction("StartRound")} disabled={actionLoading || checkedInCount < 4}
                  class="px-4 py-2 text-sm font-medium btn-emerald disabled:bg-ash-700 rounded-lg transition-colors"
                >{m.overview_start_round({ n: String((tournament.rounds?.length ?? 0) + 1) })}</button>
                {#if finalsReady}
                  <button onclick={() => doAction("StartFinals")} disabled={actionLoading}
                    class="px-4 py-2 text-sm font-medium btn-emerald disabled:bg-ash-700 rounded-lg transition-colors"
                  >{m.overview_start_finals()}</button>
                {/if}
                <!-- Secondary actions -->
                <button onclick={() => doAction("CheckInAll")} disabled={actionLoading}
                  class="px-3 py-1.5 text-sm text-ash-300 bg-ash-800 hover:bg-ash-700 rounded-lg transition-colors"
                >{m.overview_check_all_in()}</button>
                <button onclick={() => doAction("MarkAllPaid")} disabled={actionLoading}
                  class="px-3 py-1.5 text-sm text-ash-300 bg-ash-800 hover:bg-ash-700 rounded-lg transition-colors"
                >{m.payment_mark_all_paid()}</button>
                {#if hasRounds}
                  <button onclick={() => doAction("ResetCheckIn")} disabled={actionLoading}
                    class="px-3 py-1.5 text-sm text-ash-300 bg-ash-800 hover:bg-ash-700 rounded-lg transition-colors"
                  >{m.overview_reset_checkin()}</button>
                {/if}
                {#if tournament.checkin_code}
                  <button onclick={() => showQrCode = !showQrCode}
                    class="px-3 py-1.5 text-sm text-ash-300 bg-ash-800 hover:bg-ash-700 rounded-lg transition-colors flex items-center gap-1.5"
                  >
                    <QrCode class="w-4 h-4" />
                    {showQrCode ? m.checkin_qr_hide_code() : m.checkin_qr_show_code()}
                  </button>
                {/if}
                <!-- Seating warning -->
                {#if [6, 7, 11].includes(checkedInCount)}
                  <span class="text-sm text-amber-300">{m.overview_seating_warning({ count: String(checkedInCount) })}</span>
                {/if}

              {:else if tournament.state === "Playing"}
                {#if isFinals}
                  <button onclick={() => doAction("FinishFinals")} disabled={actionLoading || !finalsTableFinished}
                    class="px-4 py-2 text-sm font-medium btn-amber disabled:bg-ash-700 disabled:text-ash-500 rounded-lg transition-colors"
                  >{m.finals_finish()}</button>
                {:else}
                  <button onclick={() => doAction("FinishRound")} disabled={actionLoading || !allTablesFinished}
                    class="px-4 py-2 text-sm font-medium btn-amber disabled:bg-ash-700 disabled:text-ash-500 rounded-lg transition-colors"
                  >{m.rounds_end_round()}</button>
                {/if}

              {:else if tournament.state === "Finished"}
                <button onclick={() => doAction("ReopenTournament")} disabled={actionLoading}
                  class="px-3 py-1.5 text-sm text-ash-300 border border-ash-700 hover:border-ash-600 hover:text-ash-200 rounded-lg transition-colors"
                >{m.overview_reopen_tournament()}</button>
              {/if}
            </div>

            <!-- Danger actions (Waiting state) -->
            {#if tournament.state === "Waiting"}
              <div class="pt-2 border-t border-ash-800 flex flex-wrap gap-2">
                <button onclick={() => doAction("FinishTournament")} disabled={actionLoading}
                  class="px-3 py-1.5 text-sm text-ash-500 hover:text-crimson-400 transition-colors"
                >{m.overview_finish_tournament()}</button>
                <button onclick={() => doAction("ReopenRegistration")} disabled={actionLoading}
                  class="px-3 py-1.5 text-sm text-ash-500 hover:text-ash-300 transition-colors"
                >{m.overview_reopen_registration()}</button>
              </div>
            {/if}

            <!-- QR Check-in display -->
            {#if showQrCode && (tournament.state === "Registration" || tournament.state === "Waiting") && tournament.checkin_code}
              <div class="pt-3 border-t border-ash-800">
                <QrCheckinDisplay code={tournament.checkin_code} tournamentUid={tournament.uid} tournamentName={tournament.name} />
              </div>
            {/if}
          </div>

          <!-- Tab content -->
          <div class="p-3 sm:p-6">
            {#if activeTab === 'overview'}
              <OverviewTab
                bind:tournament={tournament}
                {playerInfo}
                {standings}
                isOrganizer={true}
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
        <PlayerView
          {tournament}
          {playerInfo}
          {standings}
          {currentPlayerEntry}
          {playerStandings}
          {cutoffScore}
          {isFinals}
          {isFinished}
          {playerHasValidDeck}
          userUid={auth.user?.uid ?? ""}
          userVeknId={auth.user?.vekn_id ?? null}
          {actionLoading}
          {scoreSaving}
          {doAction}
          {dropPlayer}
          {setVp}
          {setFinalsVp}
          {tournamentSanctions}
        />
      {/if}
      {/if}<!-- end isMinimalView else -->
    {/if}
  </div>
</div>

<TournamentModals
  bind:showDeleteConfirm
  bind:showGoOfflineConfirm
  bind:showGoOnlineConfirm
  bind:showForceTakeoverConfirm
  {offlineActionLoading}
  onDelete={handleDelete}
  onGoOffline={handleGoOffline}
  onGoOnline={handleGoOnline}
  onForceTakeover={handleForceTakeover}
/>
