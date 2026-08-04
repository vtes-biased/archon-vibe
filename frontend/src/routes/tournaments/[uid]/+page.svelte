<script lang="ts">
  import { page } from "$app/stores";
  import { goto, replaceState } from "$app/navigation";
  import { untrack } from "svelte";
  import { deleteTournamentApi, syncTournamentVekn, qrCheckin } from "$lib/api";
  import { tournamentAction, setTableScore } from "$lib/tournament-actions";
  import { getCountries, getCountryFlag } from "$lib/geonames";
  import { getAuthState } from "$lib/stores/auth.svelte";
  import { canTakeTournamentOffline, canForceUnlockTournament } from "$lib/engine";
  import { syncManager } from "$lib/sync";
  import { getUser, getTournament, getTournamentContextSanctions, getDeviceId, getDecksByTournamentGrouped, getLeague, saveTournament } from "$lib/db";
  import type { Tournament, TournamentState, User, Sanction, DeckObject } from "$lib/types";
  import { initEngine, validateDeck, isOrganizer as engineIsOrganizer, type TournamentEventType, type ValidationError } from "$lib/engine";
  import { engineReady } from "$lib/stores/engine-ready.svelte";
  import { getStateBadgeClass, translateTournamentState, computeStandings, type PlayerInfoMap } from "$lib/tournament-utils";
  import { zonedDate } from "$lib/utils";
  import { isOffline, goOffline, goOnline, forceTakeover, forceUnlock, getLastSyncTime, OfflineLockLostError } from "$lib/stores/offline.svelte";
  import { isBrowserOnline } from "$lib/stores/connectivity.svelte";
  // The back link returns to the list the way it was left, like the nav menu.
  import { openLastView } from "$lib/last-view";
  import { ArrowLeft, Loader2, WifiOff, Wifi, Lock, Shield, User as UserIcon, UserPlus, TriangleAlert, Users, Swords, Trophy, Settings, ExternalLink, MapPin, CloudOff, CloudAlert, Trash2, Upload, CloudUpload, Share2, CalendarPlus } from "@lucide/svelte";
  import FoldableDescription from "$lib/components/FoldableDescription.svelte";
  import Button from "$lib/components/Button.svelte";
  import TournamentBanner from "$lib/components/TournamentBanner.svelte";
  import { showToast } from "$lib/stores/toast.svelte";
  import * as m from '$lib/paraglide/messages.js';

  // Deck validation state for player's own deck
  // null = validation unavailable (treated as no blocking errors — never gates)
  let myDeckErrors = $state<ValidationError[] | null>([]);

  import ActionBar from "./ActionBar.svelte";
  import ArchonImportModal from "./ArchonImportModal.svelte";
  import CsvRegisterModal from "./CsvRegisterModal.svelte";
  import PlayersTab from "./PlayersTab.svelte";
  import RoundsTab from "./RoundsTab.svelte";
  import FinalsTab from "./FinalsTab.svelte";
  import ConfigTab from "./ConfigTab.svelte";
import { toUserMessage } from '$lib/errors';
import TournamentModals from "./TournamentModals.svelte";
  import PlayerView from "./PlayerView.svelte";
  import JudgeCallBanner from "./JudgeCallBanner.svelte";
  import AnnouncementBanner from "./AnnouncementBanner.svelte";
  import PushOptIn from "./PushOptIn.svelte";
  import AnnouncementComposer from "./AnnouncementComposer.svelte";
  import SanctionIndicator from "$lib/components/SanctionIndicator.svelte";
  import RankedBadge from "./RankedBadge.svelte";
  import type { JudgeCallData } from "$lib/sync";

  const countries = getCountries();
  const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

  let tournament = $state<Tournament | null>(null);
  let tournamentSanctions = $state<Sanction[]>([]);
  let organizerNames = $state<Record<string, string>>({});
  let loading = $state(true);
  let error = $state<string | null>(null);
  let actionLoading = $state(false);

  const auth = $derived(getAuthState());
  const uid = $derived($page.params.uid as string);
  const isOrganizer = $derived(
    tournament ? engineIsOrganizer(auth.user, tournament) : false
  );
  const veknPush = import.meta.env.VITE_VEKN_PUSH === "true";
  // Strict null: undefined means the viewer's projection omits the field.
  // rounds>0 mirrors batch_push's guard — results without in-app play data
  // (VEKN imports, migrated history) are never pushed, so never "pending".
  const veknResultsPending = $derived(
    veknPush && tournament?.state === "Finished" && tournament?.vekn_pushed_at === null
      && (tournament?.rounds?.length ?? 0) > 0
  );
  // Deletable at any state until it reaches VEKN: once a calendar event
  // (external_ids.vekn) or pushed results (vekn_pushed_at) exist, deleting here
  // would orphan the vekn.net record — mirrors the server gate in tournaments.py.
  const canDelete = $derived(
    !tournament?.external_ids?.vekn && !tournament?.vekn_pushed_at
  );
  // Strengthen the delete confirmation once real play data exists.
  const deleteHasResults = $derived((tournament?.rounds?.length ?? 0) > 0);
  const currentPlayerEntry = $derived(
    tournament?.players?.find(p => p.user_uid === auth.user?.uid) ?? null
  );
  // Push opt-in eligibility: a live tournament (Waiting/Playing) where notifications
  // are useful — for a participant who hasn't dropped out ("which table am I at?",
  // #314), or for an organizer (judge calls, #323).
  const pushLive = $derived(
    tournament?.state === "Waiting" || tournament?.state === "Playing"
  );
  const pushEligible = $derived(
    pushLive &&
    (
      isOrganizer ||
      (!!currentPlayerEntry &&
        currentPlayerEntry.state !== "Finished" &&
        currentPlayerEntry.state !== "Disqualified")
    )
  );
  let viewAsPlayer = $state(false);
  let showDeleteConfirm = $state(false);
  let configExpandOrganizers = $state(false);
  let configExpandPromos = $state(false);
  // Offline mode state
  const tournamentIsOffline = $derived(isOffline(uid));
  const deviceId = getDeviceId();
  const isLockedByOtherDevice = $derived(
    tournament?.offline_mode === true && tournament?.offline_device_id !== deviceId
  );
  let judgeCallBanner = $state<ReturnType<typeof JudgeCallBanner> | null>(null);
  // Reactive device connectivity, for the unprepared-at-venue nudge below
  // (navigator.onLine itself isn't reactive).
  let deviceOnline = $state(navigator.onLine);
  $effect(() => {
    const on = () => (deviceOnline = true);
    const off = () => (deviceOnline = false);
    window.addEventListener('online', on);
    window.addEventListener('offline', off);
    return () => {
      window.removeEventListener('online', on);
      window.removeEventListener('offline', off);
    };
  });
  let showGoOfflineConfirm = $state(false);
  let showGoOnlineConfirm = $state(false);
  let showForceTakeoverConfirm = $state(false);
  let showForceUnlockConfirm = $state(false);
  const canForceUnlock = $derived(canForceUnlockTournament(auth.user).allowed);
  // Organizer AND member-creation power: the offline lock mints real members at
  // go-online, so it carries more than running the event.
  const canGoOffline = $derived(
    !!tournament && canTakeTournamentOffline(auth.user, tournament)
  );
  let offlineActionLoading = $state(false);
  const lastSync = $derived(getLastSyncTime(uid));
  const showOrganizerView = $derived(isOrganizer && !viewAsPlayer);
  // Minimal view: API returned TournamentMinimal (no players array) — non-auth or non-member
  const isMinimalView = $derived(!tournament?.players);

  // League name + parent meta-league for display
  let leagueName = $state<string | null>(null);
  let metaLeague = $state<{ uid: string; name: string } | null>(null);
  $effect(() => {
    const luid = tournament?.league_uid;
    if (!luid) { leagueName = null; metaLeague = null; return; }
    getLeague(luid).then(async l => {
      leagueName = l?.name ?? null;
      const p = l?.parent_uid ? await getLeague(l.parent_uid) : undefined;
      metaLeague = p && !p.deleted_at ? { uid: p.uid, name: p.name } : null;
    });
  });

  // Decks loaded from IDB (separate store)
  let decksByUser = $state<Record<string, DeckObject[]>>({});

  $effect(() => {
    const _uid = uid;
    if (!_uid) return;
    getDecksByTournamentGrouped(_uid).then(grouped => {
      decksByUser = grouped;
    });
  });

  // Player's deck and validation status
  const myDeck = $derived(
    (auth.user?.uid && decksByUser[auth.user.uid]?.[0]) ?? null
  );
  const playerHasValidDeck = $derived(
    !tournament?.decklist_required || (myDeck !== null && !(myDeckErrors ?? []).some(e => e.severity === 'error'))
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
  type TabId = 'players' | 'rounds' | 'finals' | 'config';
  let activeTab = $state<TabId>('players');
  // Archon import modal (organizer; opened from the action-bar More menu)
  let showArchonImport = $state(false);
  let showCsvImport = $state(false);

  const tabs = $derived.by(() => {
    const t: { id: TabId; label: string; icon: typeof Users }[] = [
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
  let playerInfo = $state<PlayerInfoMap>({});

  // Supersession guard: SSE bursts fire load()/loadPlayerNames concurrently and
  // the runs finish out of order — only the newest run may assign state (the
  // sync.ts epoch pattern), else the display rolls back mid-round.
  let playerNamesEpoch = 0;

  async function loadPlayerNames() {
    if (!tournament) return;
    const epoch = ++playerNamesEpoch;
    // Build display_name lookup from tournament players
    const displayNames: Record<string, string | null> = {};
    for (const p of tournament.players ?? []) {
      if (p.user_uid) displayNames[p.user_uid] = p.display_name ?? null;
    }
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
    const uidList = [...uids];
    const users = await Promise.all(uidList.map(u => getUser(u)));
    if (epoch !== playerNamesEpoch) return; // superseded by a newer run
    const info: PlayerInfoMap = {};
    uidList.forEach((u, i) => {
      const user = users[i];
      info[u] = {
        name: user?.name || u,
        nickname: user?.nickname ?? null,
        vekn: user?.vekn_id ?? null,
        display_name: displayNames[u] ?? null,
      };
    });
    playerInfo = info;
  }

  // Info-card organizer names (organizers may not be players, so playerInfo
  // can't serve them); resolved from IndexedDB like the league page does.
  async function fetchOrganizerNames(t: Tournament): Promise<Record<string, string>> {
    const uids = t.organizers_uids ?? [];
    const users = await Promise.all(uids.map(u => getUser(u)));
    return Object.fromEntries(uids.map((u, i) => [u, users[i]?.name || u.slice(0, 8)]));
  }

  // Standings — pure computation lives in tournament-utils; read engineReady() here
  // so placement recomputes once the WASM engine finishes loading.
  const standings = $derived.by(() => {
    engineReady(); // reactive dep: recompute placement once WASM finishes loading
    return computeStandings(tournament);
  });


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
  // Only show after at least one round is fully completed
  const cutoffScore = $derived.by(() => {
    if (tournament?.state === "Finished") return null;
    if ((tournament?.standings_mode ?? "Private") !== "Cutoff") return null;
    const rounds = tournament?.rounds?.length ?? 0;
    // During Playing, the last round is in progress, so completed = rounds - 1
    if (tournament?.state === "Playing" && rounds < 2) return null;
    // During Waiting before any round, no data yet
    if (tournament?.state === "Waiting" && rounds < 1) return null;
    const entry = standings[4];
    if (!entry) return null;
    return { gw: entry.gw, vp: entry.vp, tp: entry.tp };
  });


  const hasRounds = $derived((tournament?.rounds?.length ?? 0) > 0);

  // Archon import lives in the action-bar More menu across every organizer state.
  const archonImportItem = $derived({ label: m.archon_import_title(), icon: Upload, onclick: () => (showArchonImport = true) });
  const csvImportItem = $derived({ label: m.csv_import_title(), icon: Upload, onclick: () => (showCsvImport = true) });

  let syncingVekn = $state(false);
  // VEKN needs a round count to register an event: require it configured (a
  // running/finished event already has rounds; a Planned one needs max_rounds).
  const roundsConfigured = $derived(
    (tournament?.rounds?.length ?? 0) > 0 || (tournament?.max_rounds ?? 0) > 0
  );
  async function doSyncVekn() {
    if (!tournament || syncingVekn) return; // guard double-click: avoids a duplicate VEKN event
    if (!roundsConfigured) {
      // Stay visible + explain rather than silently disappear (mobile has no hover).
      showToast({ type: 'error', message: m.vekn_sync_rounds_required() });
      return;
    }
    syncingVekn = true;
    try {
      const updated = await syncTournamentVekn(tournament.uid);
      await saveTournament(updated);
      showToast({ type: 'success', message: m.vekn_sync_success() });
    } catch (e) {
      showToast({ type: 'error', message: toUserMessage(e, m.vekn_sync_error()) });
    } finally {
      syncingVekn = false;
    }
  }
  // "Publish to VEKN" — register the calendar event on demand, and for a finished
  // event also push results + the winner's TWDA deck. Shown whenever push is on and
  // the event isn't fully on VEKN yet (never silently absent — an unconfigured round
  // count is explained on click, not hidden). Not for non-VEKN open-rounds events.
  const syncVeknItem = $derived(
    veknPush && !tournament?.open_rounds && !tournament?.self_organized_rounds
      && (!tournament?.external_ids?.vekn
          || (tournament?.state === "Finished" && !tournament?.vekn_pushed_at))
      ? { label: m.vekn_sync_action(), icon: CloudUpload, onclick: () => doSyncVekn(), disabled: actionLoading || syncingVekn }
      : null
  );


  function playerUidsOf(t: Tournament | null | undefined): string[] {
    return (t?.players ?? []).map(p => p.user_uid).filter((u): u is string => !!u);
  }


  let scoreSaving = $state<number | null>(null);
  let scoreSavingSeat = $state<string | null>(null);

  async function setVp(roundIndex: number, tableIndex: number, playerUid: string, vp: number, seating: Array<{ player_uid: string; result: { vp: number } }>) {
    if (!tournament) return;
    const scores = seating.map(s => ({
      player_uid: s.player_uid,
      vp: s.player_uid === playerUid ? vp : s.result.vp,
    }));
    scoreSaving = tableIndex;
    scoreSavingSeat = playerUid;
    try {
      tournament = await setTableScore(uid, roundIndex, tableIndex, scores);
      await loadPlayerNames();
    } catch (e) {
      error = toUserMessage(e, m.tournament_error_save_scores());
    } finally {
      scoreSaving = null;
      scoreSavingSeat = null;
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
    scoreSavingSeat = playerUid;
    try {
      tournament = await setTableScore(uid, roundIndex, 0, scores);
      await loadPlayerNames();
    } catch (e) {
      error = toUserMessage(e, m.tournament_error_save_finals());
    } finally {
      scoreSaving = null;
      scoreSavingSeat = null;
    }
  }

  let loadEpoch = 0;

  async function load() {
    const epoch = ++loadEpoch;
    if (!tournament) loading = true;
    error = null;
    try {
      await initEngine(); // standings ranking is engine-computed; ensure it's ready
      const t = await getTournament(uid);
      if (epoch !== loadEpoch) return; // superseded by a newer run
      if (t) {
        tournament = t;
        const [, sanctions, orgNames] = await Promise.all([
          loadPlayerNames(), // self-guarded by playerNamesEpoch
          getTournamentContextSanctions(uid, playerUidsOf(t)),
          fetchOrganizerNames(t),
        ]);
        if (epoch !== loadEpoch) return;
        tournamentSanctions = sanctions;
        organizerNames = orgNames;
      } else if (!tournament) {
        // No data in IndexedDB yet — will arrive via SSE
        error = m.tournament_error_not_synced();
      }
    } catch (e) {
      if (epoch !== loadEpoch) return;
      error = toUserMessage(e, m.tournament_error_load());
    } finally {
      if (epoch === loadEpoch) loading = false;
    }
  }

  // Returns the user-facing error message on failure (null on success) so a
  // caller with its own inline surface (e.g. the self-organize dialog) can show
  // it in place; `silent` skips the top-of-page banner, which is likely
  // scrolled out of view from where the action was triggered.
  async function doAction(action: TournamentEventType, data?: Record<string, unknown>, opts?: { silent?: boolean }): Promise<string | null> {
    actionLoading = true;
    try {
      tournament = await tournamentAction(uid, action, data);
      await loadPlayerNames();
      if (action === 'StartRound') activeTab = 'rounds';
      else if (action === 'StartFinals') activeTab = 'finals';
      return null;
    } catch (e) {
      const msg = toUserMessage(e, m.tournament_error_action());
      if (!opts?.silent) error = msg;
      return msg;
    } finally {
      actionLoading = false;
    }
  }

  async function handleDelete() {
    try {
      await deleteTournamentApi(uid, { suppressErrorToast: true });
      showDeleteConfirm = false;
      goto("/tournaments");
    } catch (e) {
      error = toUserMessage(e, m.tournament_error_delete());
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
      showToast({ type: 'error', message: toUserMessage(e, m.offline_error_go_offline()) });
    } finally {
      offlineActionLoading = false;
    }
  }

  async function shareEvent() {
    const url = `${window.location.origin}/tournaments/${uid}`;
    if (navigator.share) {
      try {
        await navigator.share({ title: tournament?.name, url });
        return;
      } catch (e) {
        if (e instanceof Error && e.name === "AbortError") return; // user cancelled
      }
    }
    try {
      await navigator.clipboard.writeText(url);
      showToast({ type: "success", message: m.tournament_share_copied() });
    } catch {
      showToast({ type: "error", message: m.share_results_error() });
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
      // Lock-lost already surfaced a persistent toast at the source.
      if (e instanceof OfflineLockLostError) { showGoOnlineConfirm = false; }
      else showToast({ type: 'error', message: toUserMessage(e, m.offline_error_go_online()) });
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
      showToast({ type: 'error', message: toUserMessage(e, m.offline_error_takeover()) });
    } finally {
      offlineActionLoading = false;
    }
  }

  async function handleForceUnlock() {
    offlineActionLoading = true;
    try {
      await forceUnlock(uid);
      showForceUnlockConfirm = false;
      showToast({ type: 'success', message: m.offline_unlock_success() });
    } catch (e) {
      showToast({ type: 'error', message: toUserMessage(e, m.offline_error_unlock()) });
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
      return zonedDate(iso, tournament.timezone || "UTC").toLocaleString(undefined, opts);
    } catch { return iso; }
  }

  function formatDateLocal(iso: string | null): string | null {
    if (!iso || !tournament || tournament.online) return null;
    const tournamentTz = tournament.timezone || "UTC";
    if (tournamentTz === browserTz) return null;
    try {
      return zonedDate(iso, tournamentTz).toLocaleString(undefined, {
        hour: "2-digit", minute: "2-digit",
        timeZoneName: "short",
      });
    } catch { return null; }
  }

  async function dropPlayer(playerUid: string) {
    await doAction("DropOut", { player_uid: playerUid });
  }

  // QR self-check-in (?checkin=CODE from a native-camera scan of the printed QR).
  // Stash the code and IMMEDIATELY strip the param from the address bar and
  // history — after consumption the code must not be retrievable via copy-link,
  // share sheet, or back-history (it never renders in the UI; full-projection
  // only). Anonymous visitors keep the stash (NOT in the login redirect URL)
  // and it is consumed on login-return.
  const QR_STASH_KEY = "archon-qr-checkin";
  $effect(() => {
    const code = $page.url.searchParams.get("checkin");
    if (!code) return;
    try {
      sessionStorage.setItem(QR_STASH_KEY, JSON.stringify({ uid, code }));
    } catch { /* storage unavailable — the in-app scanner still works */ }
    replaceState(`/tournaments/${uid}`, {});
  });

  let qrCheckinFired = false; // one-shot per page life; stash removal is the durable guard
  $effect(() => {
    if (!auth.isAuthenticated || !tournament || qrCheckinFired) return;
    let stash: { uid: string; code: string } | null = null;
    try {
      stash = JSON.parse(sessionStorage.getItem(QR_STASH_KEY) ?? "null");
    } catch { /* corrupted stash */ }
    if (!stash || stash.uid !== uid) return;
    qrCheckinFired = true;
    sessionStorage.removeItem(QR_STASH_KEY);
    qrCheckin(uid, stash.code)
      .then(async (updated) => {
        await saveTournament(updated);
        tournament = updated;
        showToast({ type: "success", message: m.checkin_qr_success() });
      })
      .catch((e) => {
        showToast({ type: "error", message: toUserMessage(e, m.checkin_qr_error()) });
      });
  });

  $effect(() => {
    const _currentUid = uid; // explicit dependency on uid
    untrack(() => load());

    const handleSync = (event: { type: string; data?: any }) => {
      if (event.type === "tournament") untrack(() => load());
      if (event.type === "deck" && (!event.data?.tournament_uid || event.data.tournament_uid === uid)) {
        getDecksByTournamentGrouped(uid).then(grouped => { decksByUser = grouped; });
      }
      if (event.type === "sanction") {
        getTournamentContextSanctions(uid, playerUidsOf(tournament)).then(s => { tournamentSanctions = s; });
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
    <a href="/tournaments" onclick={(e) => openLastView(e, '/tournaments')} class="inline-flex items-center gap-2 text-ink-muted hover:text-ink-bright mb-4">
      <ArrowLeft class="w-4 h-4" />
      {m.nav_tournaments()}
    </a>

    {#if loading}
      <div class="text-center py-12">
        <Loader2 class="mx-auto h-12 w-12 text-ink-faint animate-spin" />
      </div>
    {:else if error && !tournament}
      <div class="bg-accent-soft/20 border border-accent-soft-border rounded-lg p-4">
        <p class="text-link-soft">{error}</p>
      </div>
    {:else if tournament}
      <!-- Tournament banner (optional, PUBLIC level — visible pre-login). Sits at
           the top as a masthead; warnings + header follow below. -->
      <TournamentBanner
        tournamentUid={tournament.uid}
        bannerPath={tournament.banner_path}
        canManage={showOrganizerView}
      />

      <!-- Offline mode banner (this device has lock) -->
      {#if tournamentIsOffline}
        <div class="banner-warn border rounded-lg p-4 mb-4 flex items-center justify-between gap-4">
          <div class="flex items-center gap-2 min-w-0">
            <WifiOff class="w-5 h-5 shrink-0" />
            <div class="min-w-0">
              <span class="text-warn font-medium text-sm">{m.offline_mode_banner()}</span>
              {#if lastSync}
                <span class="text-xs text-ink-muted ml-2">{m.offline_last_sync({ time: new Date(lastSync).toLocaleTimeString() })}</span>
              {:else}
                <span class="text-xs text-ink-faint ml-2">{m.offline_not_synced()}</span>
              {/if}
            </div>
          </div>
          <Button variant="primary" size="lg" class="shrink-0" disabled={offlineActionLoading} onclick={() => showGoOnlineConfirm = true}>
            <Wifi class="w-4 h-4" />
            {m.offline_go_online()}
          </Button>
        </div>
      {/if}

      <!-- Unprepared-at-venue wedge: device offline, event NOT locked — every
           action would optimistically apply then revert, and Go Offline itself
           needs the server. Explain instead of failing silently. -->
      {#if showOrganizerView && !deviceOnline && !tournament.offline_mode}
        <div class="banner-warn border rounded-lg p-3 mb-4 text-sm flex items-start gap-2">
          <WifiOff class="w-4 h-4 mt-0.5 shrink-0" aria-hidden="true" />
          <span>{m.offline_not_locked_nudge()}</span>
        </div>
      {/if}

      <!-- Locked by another device banner -->
      {#if isLockedByOtherDevice}
        <div class="bg-surface-muted/50 border border-line-strong rounded-lg p-4 mb-4">
          <div class="flex items-center justify-between gap-4">
            <div class="flex items-center gap-2 min-w-0">
              <Lock class="w-5 h-5 text-ink-muted shrink-0" />
              <span class="text-ink text-sm">{m.offline_locked_banner()}</span>
            </div>
            <div class="flex items-center gap-2 shrink-0">
              {#if canGoOffline}
                <Button variant="ghost" size="md" disabled={offlineActionLoading} onclick={() => showForceTakeoverConfirm = true}>
                  {m.offline_force_takeover()}
                </Button>
              {/if}
              {#if canForceUnlock}
                <Button variant="danger" size="md" disabled={offlineActionLoading} onclick={() => showForceUnlockConfirm = true}>
                  <TriangleAlert class="w-4 h-4" aria-hidden="true" />
                  {m.offline_force_unlock()}
                </Button>
              {/if}
            </div>
          </div>
        </div>
      {/if}

      <!-- Header -->
      <div class="flex items-start justify-between mb-6">
        <div>
          <h1 class="text-3xl font-semibold text-accent">{tournament.name}</h1>
          <div class="flex flex-wrap items-center gap-3 mt-2">
            <span class="px-2 py-1 rounded text-xs font-medium {getStateBadgeClass(tournament.state)}">
              {translateTournamentState(tournament.state)}
            </span>
            <span class="text-sm text-ink-muted">{tournament.format}</span>
            {#if tournament.rank}
              <span class="text-sm text-ink-muted">· {tournament.rank}</span>
            {/if}
            <RankedBadge {tournament} />
            {#if tournament.external_ids?.vekn}
              <a href="https://www.vekn.net/event-calendar/event/{tournament.external_ids.vekn}"
                 target="_blank" rel="noopener noreferrer"
                 class="px-2 py-0.5 rounded text-xs font-medium bg-surface-muted text-ink hover:text-ink-strong inline-flex items-center gap-1"
                 title={m.tournament_vekn_link_title()}>
                VEKN <ExternalLink class="w-3 h-3" />
              </a>
            {/if}
            {#if isOrganizer && veknResultsPending}
              <span class="px-2 py-0.5 rounded text-xs font-medium banner-warn border inline-flex items-center gap-1"
                    title={m.vekn_sync_pending_hint()}>
                <CloudOff class="w-3 h-3" aria-hidden="true" />
                {m.vekn_sync_pending_results()}
              </span>
            {/if}
            {#if isOrganizer && tournament.vekn_results_stale}
              <span class="px-2 py-0.5 rounded text-xs font-medium banner-warn border inline-flex items-center gap-1"
                    title={m.vekn_out_of_sync_hint()}>
                <CloudAlert class="w-3 h-3" aria-hidden="true" />
                {m.vekn_out_of_sync()}
              </span>
            {/if}
            {#if tournament.league_uid && leagueName}
              <a href="/leagues/{tournament.league_uid}"
                 class="px-2 py-0.5 rounded text-xs font-medium badge-blue inline-flex items-center gap-1 hover:opacity-80 transition-opacity max-w-48 truncate">
                {leagueName}
              </a>
            {/if}
            {#if metaLeague}
              <a href="/leagues/{metaLeague.uid}" title={m.league_kind_meta()}
                 class="px-2 py-0.5 rounded text-xs font-medium badge-amethyst inline-flex items-center gap-1 hover:opacity-80 transition-opacity max-w-48 truncate">
                {metaLeague.name}
              </a>
            {/if}
            <!-- Sole organizer, pre-event: surface the add-co-organizer moment
                 (OrganizerManager itself lives in a Config accordion). -->
            {#if showOrganizerView && (tournament.state === "Planned" || tournament.state === "Registration") && (tournament.organizers_uids?.length ?? 0) === 1}
              <button onclick={() => { configExpandOrganizers = true; activeTab = 'config'; }}
                class="px-2 py-0.5 rounded text-xs font-medium bg-surface-muted text-ink hover:text-ink-strong inline-flex items-center gap-1 min-h-[28px]">
                <UserPlus class="w-3 h-3" aria-hidden="true" />
                {m.organizers_add_chip()}
              </button>
            {/if}
          </div>
        </div>

        <div class="flex items-center gap-2">
          <Button variant="ghost" size="md" onclick={shareEvent} title={m.tournament_share()}>
            <Share2 class="w-4 h-4" aria-hidden="true" />
            {m.tournament_share()}
          </Button>
          {#if showOrganizerView && !tournament.offline_mode && canGoOffline}
            <Button variant="ghost" size="md" onclick={() => showGoOfflineConfirm = true}>
              <WifiOff class="w-4 h-4" />
              {m.offline_go_offline()}
            </Button>
          {/if}
          {#if showOrganizerView && canDelete}
            <Button variant="danger" size="md" onclick={() => (showDeleteConfirm = true)}><Trash2 class="w-4 h-4" aria-hidden="true" />{m.common_delete()}</Button>
          {/if}
        </div>
      </div>

      {#if error}
        <div class="bg-accent-soft/20 border border-accent-soft-border rounded-lg p-3 mb-4">
          <p class="text-link-soft text-sm">{error}</p>
        </div>
      {/if}

      <!-- Info Card -->
      <div class="bg-surface-card rounded-lg shadow p-6 border border-line mb-6">
        <div class="grid grid-cols-2 sm:grid-cols-3 gap-4 text-sm">
          <div>
            <div class="text-ink-faint">{m.tournament_info_date()}</div>
            <div class="text-ink-bright">{formatDate(tournament.start)}</div>
            {#if formatDateLocal(tournament.start)}
              <div class="text-xs text-ink-faint">{formatDateLocal(tournament.start)} {m.tournament_in_timezone()}</div>
            {/if}
            <!-- Server-generated download — hidden offline (dead link otherwise) -->
            {#if tournament.start && tournament.state !== "Finished" && isBrowserOnline()}
              <a href="{API_BASE}/api/calendar/tournaments/{uid}.ics" download
                 class="text-xs text-link hover:text-link-soft inline-flex items-center gap-1 mt-1">
                <CalendarPlus class="w-3 h-3" aria-hidden="true" />
                {m.tournament_add_to_calendar()}
              </a>
            {/if}
          </div>
          <div>
            <div class="text-ink-faint">{m.tournament_info_location()}</div>
            <div class="text-ink-bright">
              {#if tournament.online}
                {m.tournaments_online()}
                {#if tournament.venue}
                  <br />
                  {#if tournament.venue_url}
                    <a href={tournament.venue_url} target="_blank" rel="noopener" class="text-link hover:text-link-soft inline-flex items-center gap-1">{tournament.venue} <ExternalLink class="w-3 h-3" aria-hidden="true" /></a>
                  {:else}
                    <span class="text-ink-muted">{tournament.venue}</span>
                  {/if}
                {/if}
              {:else if tournament.country}
                {getCountryFlag(tournament.country)} {countries[tournament.country]?.name ?? tournament.country}
                {#if tournament.venue}
                  <br />
                  {#if tournament.venue_url}
                    <a href={tournament.venue_url} target="_blank" rel="noopener" class="text-link hover:text-link-soft inline-flex items-center gap-1">{tournament.venue} <ExternalLink class="w-3 h-3" aria-hidden="true" /></a>
                  {:else}
                    <span class="text-ink-muted">{tournament.venue}</span>
                  {/if}
                {/if}
                {#if tournament.address}
                  <br />
                  {#if tournament.map_url}
                    <a href={tournament.map_url} target="_blank" rel="noopener" class="text-ink-faint hover:text-link-soft text-xs inline-flex items-center gap-1"><MapPin class="w-3 h-3" aria-hidden="true" /> {tournament.address}</a>
                  {:else}
                    <span class="text-ink-faint text-xs"><MapPin class="w-3 h-3 inline" aria-hidden="true" /> {tournament.address}</span>
                  {/if}
                {/if}
              {:else}
                —
              {/if}
            </div>
          </div>
          {#if tournament.players}
          <div>
            <div class="text-ink-faint">{m.tournament_info_players()}</div>
            <div class="text-ink-bright">{m.tournament_registered_count({ count: String(tournament.players.length) })}</div>
          </div>
          {/if}
          {#if tournament.organizers_uids?.length}
          <div>
            <div class="text-ink-faint">{m.tournament_info_organizers()}</div>
            <div class="text-ink-bright">
              {#each tournament.organizers_uids as ouid, i}{#if i > 0}<span>, </span>{/if}<a href="/users/{ouid}" class="text-link hover:text-link-soft">{organizerNames[ouid] || "…"}</a>{/each}
            </div>
          </div>
          {/if}
        </div>
      </div>

      <!-- Collapsible description -->
      {#if tournament.description}
        <FoldableDescription description={tournament.description} title={tournament.name} />
      {/if}

      {#if isMinimalView}
        <div class="bg-surface-card rounded-lg shadow border border-line p-6 text-center">
          <p class="text-ink-muted">{m.tournament_sign_in_details()}</p>
          {#if !auth.isAuthenticated}
            <a href="/login?redirect={encodeURIComponent(`/tournaments/${uid}`)}"
               class="mt-4 inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-medium min-h-[44px] bg-accent-strong hover:bg-accent-strong-hover text-white transition-colors">
              {m.community_sign_in()}
            </a>
          {/if}
        </div>
      {:else}
      <!-- View toggle for organizers -->
      {#if isOrganizer}
        <div class="flex justify-end mb-4">
          <button
            onclick={() => viewAsPlayer = !viewAsPlayer}
            class="px-3 py-1.5 text-sm text-ink bg-surface-hover hover:bg-surface-active rounded-lg transition-colors"
          >
            {#if viewAsPlayer}<Shield class="w-4 h-4 inline mr-1" />{:else}<UserIcon class="w-4 h-4 inline mr-1" />{/if}
            {viewAsPlayer ? m.tournament_view_organizer() : m.tournament_view_player()}
          </button>
        </div>
      {/if}

      <!-- Judge Call Banner (organizer only, shown in any view) -->
      {#if tournament.state === "Playing"}
        <JudgeCallBanner bind:this={judgeCallBanner} tournamentUid={uid} />
      {/if}

      <!-- Live announcements: organizers compose & manage; everyone else sees the
           banner. Hidden while offline-locked (announcements are online-only and
           would just fail) — consistent with the timer/call-judge affordances. -->
      <PushOptIn tournamentUid={uid} eligible={pushEligible} {isOrganizer} />
      {#if showOrganizerView && !tournament.offline_mode}
        <AnnouncementComposer {tournament} />
      {:else if !showOrganizerView}
        <AnnouncementBanner announcements={tournament.announcements ?? []} tournamentUid={uid} tournamentState={tournament.state} />
      {/if}

      <!-- Organizer Console with Tabs -->
      {#if showOrganizerView}
        <div class="bg-surface-card rounded-lg shadow border border-line mb-6">
          <!-- Tab bar -->
          <div class="flex border-b border-line overflow-x-auto">
            {#each tabs as tab}
              {@const TabIcon = tab.icon}
              <button
                onclick={() => activeTab = tab.id}
                class="flex items-center gap-1.5 px-4 py-3 text-sm font-medium whitespace-nowrap transition-colors border-b-2 {activeTab === tab.id ? 'border-accent text-ink-strong' : 'border-transparent text-ink-muted hover:text-ink-bright hover:border-line-strong'}"
              >
                <TabIcon class="w-4 h-4" />
                {tab.label}
              </button>
            {/each}
          </div>

          <ActionBar
            {tournament}
            {standings}
            {playerInfo}
            {decksByUser}
            {actionLoading}
            {doAction}
            {syncVeknItem}
            {archonImportItem}
            {csvImportItem}
            onImportArchon={() => (showArchonImport = true)}
            onRecordPromos={() => { configExpandPromos = true; activeTab = 'config'; }}
          />

          <!-- Tab content -->
          <div class="p-3 sm:p-6">
            {#if activeTab === 'players'}
              <PlayersTab
                {tournament}
                {playerInfo}
                {standings}
                {playerStandings}
                {cutoffScore}
                isOrganizer={true}
                {actionLoading}
                {doAction}
                {tournamentSanctions}
                isOfflineMode={tournamentIsOffline}
                {decksByUser}
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
                {setVp}
                {scoreSaving}
                {scoreSavingSeat}
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
                {setFinalsVp}
                {scoreSaving}
                {scoreSavingSeat}
                {tournamentSanctions}
              />
            {:else if activeTab === 'config'}
              <ConfigTab
                bind:tournament={tournament}
                isOrganizer={true}
                expandOrganizers={configExpandOrganizers}
                expandPromos={configExpandPromos}
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
          {playerStandings}
          {cutoffScore}
          {playerHasValidDeck}
          {myDeckErrors}
          userUid={auth.user?.uid ?? ""}
          userVeknId={auth.user?.vekn_id ?? null}
          {actionLoading}
          {scoreSaving}
          {scoreSavingSeat}
          {doAction}
          {dropPlayer}
          {setVp}
          {setFinalsVp}
          {tournamentSanctions}
          {decksByUser}
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
  bind:showForceUnlockConfirm
  {offlineActionLoading}
  {deleteHasResults}
  onDelete={handleDelete}
  onGoOffline={handleGoOffline}
  onGoOnline={handleGoOnline}
  onForceTakeover={handleForceTakeover}
  onForceUnlock={handleForceUnlock}
/>

<ArchonImportModal bind:show={showArchonImport} tournamentUid={uid} {hasRounds} />
<CsvRegisterModal bind:show={showCsvImport} tournamentUid={uid} onImported={() => load()} />
