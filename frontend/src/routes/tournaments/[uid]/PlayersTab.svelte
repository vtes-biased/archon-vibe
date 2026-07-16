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
  import { UserPlus, Dice3, CircleCheck, CircleHelp, TriangleAlert, CircleX, FileX, X, ChevronDown, ChevronRight, EyeOff, Trash2, Ellipsis, Dices, Printer } from "@lucide/svelte";
  import DeckAccordion from "$lib/components/DeckAccordion.svelte";
  import RaffleSection from "./RaffleSection.svelte";
  import CreateAndRegisterModal from "./CreateAndRegisterModal.svelte";
  import Button from "$lib/components/Button.svelte";
  import { validateDeck, type ValidationError, type TournamentEventType } from "$lib/engine";
  import { top5HasTies as top5HasTiesFn, top5HasScoreTies as top5HasScoreTiesFn, translatePlayerState, seatDisplay, translateStandingsMode, getRatingPts, seatedPlayerCount, type StandingEntry, type PlayerInfoMap } from "$lib/tournament-utils";
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
    playerStandings,
    cutoffScore,
  }: {
    tournament: Tournament;
    playerInfo: PlayerInfoMap;
    standings: StandingEntry[];
    isOrganizer: boolean;
    actionLoading: boolean;
    doAction: (action: TournamentEventType, body?: any) => Promise<string | null>;
    tournamentSanctions?: Sanction[];
    isOfflineMode?: boolean;
    decksByUser: DeckMap;
    // Mode + finished-aware standings (the player-visible subset) for the print sheet.
    playerStandings: StandingEntry[];
    cutoffScore: { gw: number; vp: number; tp: number } | null;
  } = $props();

  // Printable standings sheet — mirrors the print-seating pattern (RoundsTab) and the
  // player-visible standings (honors standings_mode + finished state via playerStandings).
  function esc(s: string): string {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function printStandings() {
    const title = esc(tournament.name || m.tournament_fallback_title());
    const finished = tournament.state === "Finished";
    const modeLabel = !finished && tournament.standings_mode !== "Public"
      ? ` <span style="font-size:13pt;color:#888;font-weight:normal">(${esc(translateStandingsMode(tournament.standings_mode))})</span>`
      : '';

    let body: string;
    if (playerStandings.length === 0 && cutoffScore) {
      // Cutoff mode pre-finish: only the top-5 threshold is public, not the list.
      body = `<div style="font-size:14pt;padding:8px 0">${esc(m.tournament_cutoff_threshold())} <strong>${esc(formatScore(cutoffScore.gw, cutoffScore.vp, cutoffScore.tp))}</strong></div>`;
    } else {
      let rows = '';
      playerStandings.forEach((e, i) => {
        const tags: string[] = [];
        if (finished && e.user_uid === tournament.winner) tags.push(m.tournament_winner());
        else if (e.finalist) tags.push(m.tournament_finalist());
        if (e.non_competing) tags.push(m.proxy_label());
        if (e.disqualified) tags.push(m.tournament_disqualified());
        const tag = tags.length ? ` <span style="color:#888;font-size:10pt">[${tags.map(esc).join(', ')}]</span>` : '';
        // DQ'd / proxy carry no competitive rank — mirror the on-screen "—".
        const rankCell = e.disqualified || e.non_competing ? '—' : `${e.rank}.`;
        const bg = i % 2 === 0 ? '#f5f5f5' : 'transparent';
        rows += `<tr style="background:${bg}"><td style="padding:4px 10px;text-align:right;font-weight:bold;width:36px">${rankCell}</td><td style="padding:4px 10px">${esc(seatDisplay(e.user_uid, playerInfo, tournament.online))}${tag}</td><td style="padding:4px 10px;text-align:right;white-space:nowrap">${esc(formatScore(e.gw, e.vp, e.tp))}</td></tr>`;
      });
      body = `<table style="width:100%;border-collapse:collapse;font-size:12pt"><thead><tr style="color:#444;font-size:10pt;border-bottom:1px solid #000"><th style="padding:4px 10px;text-align:right">#</th><th style="padding:4px 10px;text-align:left">${esc(m.tournament_col_player())}</th><th style="padding:4px 10px;text-align:right">${esc(m.tournament_col_score())}</th></tr></thead><tbody>${rows}</tbody></table>`;
    }

    const css = [
      `body{font-family:"Segoe UI","Helvetica Neue",Arial,sans-serif;font-size:12pt;color:#000;margin:0;padding:0;line-height:1.4}`,
      `@page{margin:15mm}`,
      `.footer{position:fixed;bottom:0;width:100%;text-align:right;font-size:9pt;color:#999}`,
    ].join('');
    const heading = esc(m.tournament_standings());
    const html = `<!DOCTYPE html><html><head><meta charset="utf-8"><title>${title} — ${heading}</title><style>${css}</style></head><body>`
      + `<div style="font-size:20pt;font-weight:bold">${title}</div>`
      + `<div style="font-size:16pt;color:#444;margin-top:4px">${heading}${modeLabel}</div>`
      + `<hr style="border:none;border-top:2px solid #000;margin:8px 0 16px">`
      + body
      + `<div class="footer">${title}</div>`
      + `<script>window.onload=()=>window.print()<\/script></body></html>`;
    const w = window.open('', '_blank');
    if (w) { w.document.write(html); w.document.close(); }
  }

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
    return numRounds - 1;
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
  // null = validation unavailable for at least one of the player's decks (not a pass)
  let validationCache = $state<Record<string, ValidationError[] | null>>({});

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
  type DeckStatus = 'valid' | 'warning' | 'error' | 'none' | 'unknown';
  function getDeckStatus(uid: string): DeckStatus {
    const decks = getPlayerDecks(uid);
    if (decks.length === 0) return 'none';
    const errors = validationCache[uid];
    if (errors === undefined) return 'valid'; // Not validated yet, assume valid
    if (errors === null) return 'unknown'; // Validation unavailable — not a pass
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
      // Presence check (not truthiness): a cached null must not re-trigger this
      // effect, which reads validationCache and would loop on re-assignment.
      if (playerDecks.length > 0 && validationCache[uid] === undefined) {
        Promise.all(
          playerDecks.filter(Boolean).map(d => validateDeck(d, format))
        ).then(results => {
          validationCache = {
            ...validationCache,
            [uid]: results.some(r => r === null) ? null : results.flat().filter(e => e !== null),
          };
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
  // Exact-score ties involving a top-5 seat (either side of the pair) — the uids
  // needing a toss to break the finals cutoff. Computed once instead of the
  // former per-row O(n²) predicate; standings are sorted, so only i < 5 can pair.
  const tiedUids = $derived.by(() => {
    const out = new Set<string>();
    for (let i = 0; i < standings.length && i < 5; i++) {
      const a = standings[i]!;
      if (a.disqualified) continue;
      for (let j = i + 1; j < standings.length; j++) {
        const b = standings[j]!;
        if (b.disqualified) continue;
        if (a.gw === b.gw && a.vp === b.vp && a.tp === b.tp) {
          out.add(a.user_uid);
          out.add(b.user_uid);
        }
      }
    }
    return out;
  });
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

  // Deck chase (decklist-required events): mirror of the payment filter —
  // who still owes a deck, or has one with validation issues.
  let deckFilter = $state<'all' | 'missing' | 'problems'>('all');
  const decksSubmittedCount = $derived(
    tournament.players?.filter(p => getPlayerDecks(p.user_uid ?? '').length > 0).length ?? 0
  );

  const filteredPlayers = $derived.by(() => {
    if (!isOrganizer) return sortedPlayers;
    let players = sortedPlayers;
    if (paymentFilter !== 'all') players = players.filter(p => p.payment_status === paymentFilter);
    if (deckFilter === 'missing') {
      players = players.filter(p => getDeckStatus(p.user_uid ?? '') === 'none');
    } else if (deckFilter === 'problems') {
      players = players.filter(p => ['none', 'error', 'warning'].includes(getDeckStatus(p.user_uid ?? '')));
    }
    return players;
  });

  // Modal entry points (modal internals live in CreateAndRegisterModal)
  let sponsorTarget = $state<User | null>(null);
  let showCreateModal = $state(false);

  async function addPlayerByUser(user: User) {
    if (!user.vekn_id && "vekn_id" in user) {
      // Empty at an access level that shows it → genuinely unsponsored; the
      // modal explains eligibility. A missing KEY instead means the field is
      // hidden from this viewer (public-level co-organizer): fall through —
      // the server injects the authoritative vekn_id on AddPlayer, and
      // sponsoring a member who already has one would 400.
      sponsorTarget = user;
      return;
    }
    await doAction("AddPlayer", { user_uid: user.uid, vekn_id: user.vekn_id });
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
      if (tiedUids.has(entry.user_uid)) {
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

  const seatedCount = $derived(seatedPlayerCount(tournament));

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
        <!-- Available offline too: sanctions are offline-manageable on the
             lock-holding device (saved to IDB, reconciled at go-online). -->
        {#if puid && hasRounds}
          <Button variant="secondary" size="sm" onclick={() => sanctionTarget = { uid: puid, name: playerInfo[puid]?.name ?? puid }}>
            <TriangleAlert class="w-4 h-4 text-warn" aria-hidden="true" />{m.players_sanction_btn()}
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

  <!-- Per-player expanded deck panel (upload / accordion / validation errors).
       Shared by the mobile card and the desktop expand row. -->
  {#snippet deckPanel(puid: string)}
    {@const playerDecks = getPlayerDecks(puid)}
    {@const errors = validationCache[puid] ?? []}
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
  {/snippet}

  <!-- Header + Add Player -->
  <div class="space-y-2">
    <div class="flex items-center gap-3">
      <p class="text-ink-muted shrink-0">
        {#if (tournament.max_players ?? 0) > 0}
          {m.players_count_capped({ count: String(tournament.players?.length ?? 0), cap: String(tournament.max_players) })}
        {:else}
          {m.players_count({ count: String(tournament.players?.length ?? 0) })}
        {/if}
      </p>
      {#if isOrganizer}
        <AddPlayerForm {tournament} onadd={addPlayerByUser} oncreate={() => showCreateModal = true} />
      {/if}
    </div>
    <!-- Soft cap reached: warn-only — adding players is never blocked -->
    {#if isOrganizer && (tournament.max_players ?? 0) > 0 && (tournament.players?.length ?? 0) >= (tournament.max_players ?? 0)}
      <div class="banner-warn border rounded-lg p-2 text-xs flex items-start gap-2">
        <TriangleAlert class="w-4 h-4 shrink-0" aria-hidden="true" />
        <span>{m.players_cap_warning_organizer({ count: String(tournament.players?.length ?? 0), cap: String(tournament.max_players) })}</span>
      </div>
    {/if}
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
      {#if isOrganizer && (playerStandings.length > 0 || cutoffScore)}
        <button
          onclick={printStandings}
          class="inline-flex items-center gap-1 px-3 py-2 sm:px-2 sm:py-1 text-xs rounded bg-surface-hover/50 text-ink-muted hover:text-ink-bright transition-colors"
          title={m.players_print_standings_hint()}
        >
          <Printer class="w-3.5 h-3.5" />
          {m.players_print_standings()}
        </button>
      {/if}
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
        {#if tournament.decklist_required}
          <div class="flex items-center gap-2">
            <div class="flex gap-1">
              <button
                class="px-3 py-2 sm:px-2 sm:py-1 text-xs rounded transition-colors {deckFilter === 'all' ? 'bg-surface-active text-ink-strong' : 'bg-surface-hover/50 text-ink-muted hover:text-ink-bright'}"
                onclick={() => deckFilter = 'all'}
              >{m.deck_filter_all()}</button>
              <button
                class="px-3 py-2 sm:px-2 sm:py-1 text-xs rounded transition-colors {deckFilter === 'missing' ? 'btn-pending' : 'bg-surface-hover/50 text-ink-muted hover:text-ink-bright'}"
                onclick={() => deckFilter = 'missing'}
              >{m.decks_missing()}</button>
              <button
                class="px-3 py-2 sm:px-2 sm:py-1 text-xs rounded transition-colors {deckFilter === 'problems' ? 'btn-pending' : 'bg-surface-hover/50 text-ink-muted hover:text-ink-bright'}"
                onclick={() => deckFilter = 'problems'}
              >{m.deck_filter_problems()}</button>
            </div>
            <span class="text-xs text-ink-faint">{m.decks_submitted_count({ submitted: String(decksSubmittedCount), total: String(totalPlayers) })}</span>
          </div>
        {/if}
      {/if}
    </div>

    <!-- Mobile card layout -->
    <div class="sm:hidden space-y-2">
      {#each filteredPlayers as player}
        {@const puid = player.user_uid ?? ""}
        {@const entry = standingsMap.get(puid)}
        {@const standingsIdx = entry ? standings.indexOf(entry) : -1}
        {@const isTop5 = standingsIdx >= 0 && standingsIdx < 5}
        {@const isTied = entry ? tiedUids.has(entry.user_uid) : false}
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
              {#if isFinished && playerSort === 'standings'}<span class="text-ink-faint">{getRatingPts(entry, tournament, seatedCount)} RP</span>{/if}
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
              <!-- Door controls: mobile card is the on-the-floor surface — 44px touch floor. -->
              <button onclick={() => doAction("SetPaymentStatus", { player_uid: puid, status: player.payment_status === 'Paid' ? 'Pending' : 'Paid' })}
                disabled={actionLoading}
                class="px-3 py-1 min-h-[44px] text-xs rounded transition-colors {player.payment_status === 'Paid' ? 'badge-success hover:opacity-80' : 'badge-pending hover:opacity-80'}">
                {player.payment_status === 'Paid' ? m.payment_paid() : m.payment_pending()}
              </button>
              {#if tournament.decklist_required || isOrganizer}
                {@const deckStatus = getDeckStatus(puid)}
                <button onclick={() => togglePlayer(puid)} class="inline-flex items-center gap-1 px-3 py-1 min-h-[44px] text-xs rounded transition-colors hover:bg-surface-hover" title={player.non_competing ? m.proxy_hint() : m.players_view_deck()}>
                  {#if player.non_competing}<Dices class="w-3.5 h-3.5 text-ink-faint" /><span class="text-ink-muted">{m.proxy_random_deck()}</span>
                  {:else if deckStatus === 'valid'}<CircleCheck class="w-3.5 h-3.5 text-info" /><span class="text-info">{m.players_view_deck()}</span>
                  {:else if deckStatus === 'warning'}<TriangleAlert class="w-3.5 h-3.5 text-warn" /><span class="text-warn">{m.players_view_deck()}</span>
                  {:else if deckStatus === 'error'}<CircleX class="w-3.5 h-3.5 text-link" /><span class="text-link">{m.players_view_deck()}</span>
                  {:else if deckStatus === 'unknown'}<CircleHelp class="w-3.5 h-3.5 text-ink-faint" /><span class="text-ink-muted">{m.players_view_deck()}</span>
                  {:else}<FileX class="w-3.5 h-3.5 text-ink-faint" /><span class="text-ink-muted">{m.players_no_deck()}</span>{/if}
                </button>
              {/if}
              {#if tournament.state === "Waiting" && puid && openRounds && player.state !== "Disqualified" && player.state !== "Finished" && (roundsPlayedMap.get(puid) ?? 0) >= (tournament.max_rounds ?? 0)}
                <!-- Open rounds: at cap and not dropped — no check-in, show their played count. -->
                <Button variant="ghost" size="sm" class="min-h-[44px]" disabled title={m.player_completed_hint()}>{roundsPlayedMap.get(puid)}/{tournament.max_rounds} {m.player_rounds_unit()}</Button>
              {:else if tournament.state === "Waiting" && (player.state === "Finished" || player.state === "Registered") && puid}
                <!-- Finished = dropped out: CheckIn reinstates (Checked-in under cap, Completed at cap).
                     Primary for waiting registrants: check-in is THE door action of the moment. -->
                <Button variant={player.state === "Registered" ? "primary" : "ghost"} size="sm" class="min-h-[44px]" onclick={() => doAction("CheckIn", { player_uid: puid })}>{m.players_check_in()}</Button>
              {:else if tournament.state === "Waiting" && player.state === "Checked-in" && puid}
                <Button variant="ghost" size="sm" class="min-h-[44px]" onclick={() => doAction("CheckOut", { player_uid: puid })}>{m.players_check_out()}</Button>
              {/if}
              <!-- Rare/destructive tail (drop/remove · sanction · proxy) lives in "More". -->
              <Button variant="ghost" size="sm" onclick={() => toggleMore(puid)} class="ml-auto min-h-[44px]" aria-expanded={morePlayer === puid}><Ellipsis class="w-4 h-4" aria-hidden="true" />{m.players_more()}</Button>
            </div>
            {#if morePlayer === puid}
              <div class="mt-2 pt-2 border-t border-line">
                {@render moreDrawer(player, puid)}
              </div>
            {/if}
          {/if}
          <!-- Expanded deck -->
          {#if expandedPlayer === puid}
            <div class="mt-2 pt-2 border-t border-line space-y-2">
              {@render deckPanel(puid)}
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
            {@const isTied = entry ? tiedUids.has(entry.user_uid) : false}
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
                  <td class="text-right py-1.5 px-2 text-ink-muted">{entry ? getRatingPts(entry, tournament, seatedCount) : "—"}</td>
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
                    {:else if deckStatus === 'unknown'}<CircleHelp class="w-4 h-4 text-ink-faint" />
                    {:else}<FileX class="w-4 h-4 text-ink-faint" />{/if}
                  </button>
                </td>
              {/if}
              {#if isOrganizer}
                <td class="py-1.5">
                  <!-- Flex row: two adjacent inline-flex Buttons on a text line
                       baseline-shift when one leads with an icon (More).
                       nowrap: labels must not wrap under column squeeze. -->
                  <div class="flex items-center justify-end gap-1 whitespace-nowrap">
                    {#if tournament.state === "Waiting" && puid && openRounds && player.state !== "Disqualified" && player.state !== "Finished" && (roundsPlayedMap.get(puid) ?? 0) >= (tournament.max_rounds ?? 0)}
                      <Button variant="ghost" size="sm" disabled title={m.player_completed_hint()}>{roundsPlayedMap.get(puid)}/{tournament.max_rounds} {m.player_rounds_unit()}</Button>
                    {:else if tournament.state === "Waiting" && (player.state === "Finished" || player.state === "Registered") && puid}
                      <Button variant={player.state === "Registered" ? "primary" : "ghost"} size="sm" onclick={() => doAction("CheckIn", { player_uid: puid })}>{m.players_check_in()}</Button>
                    {:else if tournament.state === "Waiting" && player.state === "Checked-in" && puid}
                      <Button variant="ghost" size="sm" onclick={() => doAction("CheckOut", { player_uid: puid })}>{m.players_check_out()}</Button>
                    {/if}
                    <!-- Rare/destructive tail (drop/remove · sanction · proxy) lives in "More". -->
                    <Button variant="ghost" size="sm" onclick={() => toggleMore(puid)} aria-expanded={morePlayer === puid}><Ellipsis class="w-4 h-4" aria-hidden="true" />{m.players_more()}</Button>
                  </div>
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
              <tr class="bg-surface-muted/50">
                <td colspan="99" class="p-4">
                  <div class="space-y-2">
                    {@render deckPanel(puid)}
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

<!-- Sponsor & Register / Create & Register / Deceased-confirm modals -->
<CreateAndRegisterModal {tournament} {doAction} {addPlayerByUser} bind:showCreateModal bind:sponsorTarget />
