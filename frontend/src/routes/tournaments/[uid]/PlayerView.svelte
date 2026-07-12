<script lang="ts">
  import type { Tournament, Player, Sanction, DeckObject } from "$lib/types";
  import type { StandingEntry, PlayerInfoMap } from "$lib/tournament-utils";
  import { seatDisplay as seatDisplayUtil, vpOptions, computeGwLocal, computeGwFinals, computeTpLocal, translatePlayerState, translateTableState, translateStandingsMode, resolveTableLabel, roundsPlayed } from "$lib/tournament-utils";
  import { formatScore } from "$lib/utils";
  import { computeRatingPoints, type ValidationError, type TournamentEventType } from "$lib/engine";
  import { TriangleAlert, ChevronDown, ChevronRight, QrCode, Gavel, Ban, Trash2, ExternalLink, Users } from "@lucide/svelte";
  import SanctionIndicator from "$lib/components/SanctionIndicator.svelte";
  import SelfOrganizeDialog from "./SelfOrganizeDialog.svelte";
  import RankCell from "$lib/components/RankCell.svelte";
  import ScoreLegend from "$lib/components/ScoreLegend.svelte";
  import QrCheckinScanner from "$lib/components/QrCheckinScanner.svelte";
  import Button from '$lib/components/Button.svelte';
  import TimerDisplay from "./TimerDisplay.svelte";
  import VpInput from "./VpInput.svelte";
  import PlayerDecksSection from "./PlayerDecksSection.svelte";
  import RaffleSection from "./RaffleSection.svelte";
  import { callJudge } from "$lib/api";
  import { isOnline } from "$lib/api";
  import { isUserCurrentlySanctioned } from "$lib/db";
  import * as m from '$lib/paraglide/messages.js';

  let {
    tournament,
    playerInfo,
    standings,
    currentPlayerEntry,
    playerStandings,
    cutoffScore,
    isFinals,
    isFinished,
    playerHasValidDeck,
    myDeckErrors,
    userUid,
    userVeknId,
    actionLoading,
    scoreSaving,
    scoreSavingSeat,
    doAction,
    dropPlayer,
    setVp,
    setFinalsVp,
    tournamentSanctions,
    decksByUser,
  }: {
    tournament: Tournament;
    playerInfo: PlayerInfoMap;
    standings: StandingEntry[];
    currentPlayerEntry: Player | null;
    playerStandings: StandingEntry[];
    cutoffScore: { gw: number; vp: number; tp: number } | null;
    isFinals: boolean;
    isFinished: boolean;
    playerHasValidDeck: boolean;
    myDeckErrors?: ValidationError[] | null;
    userUid: string;
    userVeknId: string | null;
    actionLoading: boolean;
    scoreSaving: number | null;
    scoreSavingSeat: string | null;
    doAction: (action: TournamentEventType, body?: any) => Promise<void>;
    dropPlayer: (uid: string) => Promise<void>;
    setVp: (roundIndex: number, tableIndex: number, playerUid: string, vp: number, seating: Array<{ player_uid: string; result: { vp: number } }>) => Promise<void>;
    setFinalsVp: (playerUid: string, vp: number, seating: Array<{ player_uid: string; result: { vp: number } }>) => Promise<void>;
    tournamentSanctions: Sanction[];
    decksByUser?: Record<string, DeckObject[]>;
  } = $props();

  let showRegisteredPlayers = $state(false);
  let showPreviousRounds = $state(false);
  let showQrScanner = $state(false);
  let judgeCallCooldown = $state(false);
  let userSuspended = $state(false);

  // Check if current user is suspended
  $effect(() => {
    if (userUid) {
      isUserCurrentlySanctioned(userUid).then(v => { userSuspended = v; });
    }
  });

  const myStanding = $derived(standings.find(s => s.user_uid === userUid));
  // Open rounds: this player has reached their per-player round cap. Gate self-check-in on the
  // rounds-played count (not the player state), so a capped player can't self-check-in regardless
  // of whether they rest in Completed, Finished, or Registered.
  const atCap = $derived(
    (tournament.max_rounds ?? 0) > 0 && roundsPlayed(tournament, userUid) >= (tournament.max_rounds ?? 0),
  );

  // Self-organized rounds (open-rounds): a registered participant can seat their own
  // 4-5 pod without an organizer — no online or per-player-cap requirement. Mirrors the
  // engine's eligibility gate (error.rs); the engine re-validates server-side, the UI
  // just avoids showing an impossible action.
  let showSelfOrganize = $state(false);
  function isSelfOrganizeEligible(p: Player): boolean {
    const uid = p.user_uid;
    if (!uid) return false;
    if (p.state !== "Registered" && p.state !== "Checked-in") return false;
    // No cap (max_rounds 0) means no per-player limit; only gate when a cap is set.
    return !((tournament.max_rounds ?? 0) > 0 && roundsPlayed(tournament, uid) >= (tournament.max_rounds ?? 0));
  }
  const canSelfOrganize = $derived(
    (tournament.self_organized_rounds ?? false) &&
    !tournament.finals &&
    (tournament.state === "Waiting" || tournament.state === "Playing") &&
    !!currentPlayerEntry &&
    isSelfOrganizeEligible(currentPlayerEntry),
  );
  // The other eligible players the initiator may seat (current user excluded).
  const selfOrganizeCandidates = $derived(
    (tournament.players ?? [])
      .filter(p => p.user_uid && p.user_uid !== userUid && isSelfOrganizeEligible(p))
      .map(p => ({ uid: p.user_uid as string, name: seatDisplayUtil(p.user_uid as string, playerInfo, tournament.online) }))
      .sort((a, b) => a.name.localeCompare(b.name)),
  );

  async function submitSelfOrganize(picked: string[]) {
    await doAction("SelfOrganizeRound", { player_uids: [userUid, ...picked] });
    showSelfOrganize = false;
  }

  // Deck check-in CTA: distinguish "no deck" from "deck present but invalid",
  // and surface the blocking validation errors inline so the player can act
  // at the door instead of hunting for the deck section.
  const hasDeck = $derived(!!decksByUser?.[userUid]?.[0]);
  const deckErrorMessages = $derived((myDeckErrors ?? []).filter(e => e.severity === 'error').map(e => e.message));
  // A registered (or reinstatable Finished) player who still needs to check in during
  // the check-in window. Drives the prominent check-in call and the deck warning.
  const notCheckedIn = $derived(
    !!currentPlayerEntry &&
    (currentPlayerEntry.state === "Registered" || currentPlayerEntry.state === "Finished") &&
    tournament.state === "Waiting" &&
    !atCap
  );
  // Missing/invalid decklist is a warning beside the check-in CTA, NOT a gate: the
  // engine allows deck-less check-in (mod.rs CheckIn just stamps missing_decklist).
  // Only surfaced when a decklist is required (playerHasValidDeck is always true otherwise).
  const showDeckWarn = $derived(notCheckedIn && tournament.decklist_required && !playerHasValidDeck);
  const previousRounds = $derived.by(() => {
    if (!tournament.rounds || tournament.rounds.length < 1) return [];
    const result: { round: number; tableLabel: string; table: typeof tournament.rounds[0][0] }[] = [];
    for (let r = 0; r < tournament.rounds.length; r++) {
      const round = tournament.rounds[r]!;
      // Skip in-progress rounds (shown as "Your Table(s)")
      if (tournament.state === "Playing" && !isFinals && round.some(t => t.state !== "Finished")) continue;
      const tIdx = round.findIndex(t => t.seating.some(s => s.player_uid === userUid));
      if (tIdx >= 0) {
        result.push({
          round: r + 1,
          tableLabel: resolveTableLabel(tournament.table_rooms, tIdx) ?? m.rounds_table_n({ n: String(tIdx + 1) }),
          table: round[tIdx]!,
        });
      }
    }
    return result;
  });

  // Active rounds where the player is seated (for parallel round support)
  const myActiveRounds = $derived.by(() => {
    if (!tournament.rounds || tournament.state !== "Playing" || isFinals) return [];
    const lastRoundIdx = tournament.rounds.length - 1;
    return tournament.rounds
      .map((round, r) => ({ round, r }))
      // Players may keep revising their table until the round is actually closed —
      // i.e. until the organizer advances (a later round exists) or finals/finish.
      // The current (last) round stays editable even once every table reads
      // Finished; earlier rounds stay editable only while a table is unfinished
      // (parallel-round safety). The engine permits this: a player-scored table
      // carries no judge_uid, so SetScore is allowed while the tournament Plays.
      .filter(({ round, r }) => r === lastRoundIdx || round.some(t => t.state !== "Finished"))
      .map(({ round, r }) => {
        const tIdx = round.findIndex(t => t.seating.some(s => s.player_uid === userUid));
        return tIdx >= 0 ? { roundIdx: r, tableIdx: tIdx, table: round[tIdx]! } : null;
      })
      .filter((x): x is { roundIdx: number; tableIdx: number; table: typeof tournament.rounds[0][0] } => x !== null);
  });

  const hasParallelRounds = $derived(myActiveRounds.length > 1 || (
    tournament.rounds?.filter(r => r.some(t => t.state !== "Finished")).length ?? 0
  ) > 1);

  async function handleCallJudge(tableIdx: number) {
    if (judgeCallCooldown) return;
    try {
      await callJudge(tournament.uid, tableIdx);
      judgeCallCooldown = true;
      setTimeout(() => { judgeCallCooldown = false; }, 30_000);
    } catch {}
  }

  function seatDisplay(uid: string): string {
    return seatDisplayUtil(uid, playerInfo, tournament.online);
  }

  function isPlayerDQ(userUid: string): boolean {
    return tournament.players?.some(p => p.user_uid === userUid && p.state === "Disqualified") ?? false;
  }

  function sanctionsForPlayer(uid: string): Sanction[] {
    return tournamentSanctions.filter(s => s.user_uid === uid);
  }

  function getRatingPts(entry: StandingEntry): number {
    if (!isFinished) return 0;
    const isWinner = entry.user_uid === tournament.winner;
    const finalistPos = isWinner ? 1
      : (tournament.finals?.seating.some(s => s.player_uid === entry.user_uid) ? 2 : 0);
    const gw = isWinner ? entry.gw + 1 : entry.gw;
    return computeRatingPoints(entry.vp, gw, finalistPos, standings.length, tournament.rank);
  }
</script>

<!-- Missing/invalid decklist no longer hides the check-in button (engine treats it
     as non-blocking). Surface it as a warning BESIDE the check-in CTA — penalty
     framing + specific errors. No jump-to-deck button: the deck upload section is
     right below, and the button read as a spurious 'upload' action (it only scrolled). -->
{#snippet deckWarn()}
  <div class="banner-warn border rounded-lg p-3">
    <div class="flex items-start gap-2 text-sm">
      <TriangleAlert class="w-4 h-4 mt-0.5 shrink-0" aria-hidden="true" />
      <div class="min-w-0">
        <p class="font-medium">{hasDeck ? m.tournament_checkin_invalid_deck_warn() : m.tournament_checkin_no_deck_warn()}</p>
        {#if deckErrorMessages.length > 0}
          <ul class="mt-1 list-disc list-inside text-xs space-y-0.5">
            {#each deckErrorMessages as msg}<li>{msg}</li>{/each}
          </ul>
        {/if}
      </div>
    </div>
  </div>
{/snippet}

<!-- Online events have no on-site QR to scan: check-in happens in the server
     (self-serve via the Discord bot, or organizer-driven). Point the player at
     the join link instead of a dead camera scanner. Button has no href, so this
     mirrors its primary/lg/block styling on an <a>. -->
{#snippet onlineJoin()}
  {#if tournament.venue_url}
    <a href={tournament.venue_url} target="_blank" rel="noopener"
       class="inline-flex w-full items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-medium min-h-[44px] bg-accent-strong hover:bg-accent-strong-hover text-white transition-colors">
      <ExternalLink class="w-4 h-4" aria-hidden="true" />
      {m.tournament_join_online_btn({ venue: tournament.venue ?? "" })}
    </a>
  {/if}
{/snippet}

<!-- Player interaction section -->
<div class="bg-surface-card rounded-lg shadow border border-line mb-6 p-6 space-y-4">
  {#if tournament.state === "Registration" && !currentPlayerEntry}
    {#if userSuspended}
      <div class="text-sm text-link">{m.error_suspended_cannot_register()}</div>
    {:else if !userVeknId}
      <div class="banner-warn border rounded-lg p-3 flex items-center gap-2 text-sm">
        <TriangleAlert class="w-4 h-4 shrink-0" aria-hidden="true" />
        <span>{m.tournament_vekn_id_required_to_register()}</span>
      </div>
    {:else}
      <Button
        variant="primary"
        size="lg"
        onclick={() => doAction("Register", { user_uid: userUid, vekn_id: userVeknId })}
        disabled={actionLoading}
      >{m.tournament_register_btn()}</Button>
    {/if}
  {:else if tournament.state === "Registration" && currentPlayerEntry}
    <div class="text-sm mb-3 flex items-center justify-between">
      <div>
        <span class="text-ink-faint">{m.tournament_your_status()}</span>
        <span class="ml-2 text-ink-bright">{translatePlayerState(currentPlayerEntry.state)}</span>
      </div>
      <Button
        variant="danger"
        onclick={() => doAction("Unregister", { user_uid: userUid })}
        disabled={actionLoading}
      ><Ban class="w-4 h-4" aria-hidden="true" />{m.tournament_unregister_btn()}</Button>
    </div>
  {:else if tournament.state === "Waiting" && !currentPlayerEntry}
    {#if tournament.online}
      {@render onlineJoin()}
      <p class="text-sm text-ink-muted">{m.tournament_online_checkin_unregistered()}</p>
    {:else}
      <Button
        variant="primary"
        size="lg"
        onclick={() => showQrScanner = true}
        disabled={actionLoading}
      >
        <QrCode class="w-4 h-4" />
        {m.tournament_register_checkin_btn()}
      </Button>
    {/if}
  {:else if currentPlayerEntry}
    <!-- Prominent check-in call: during the check-in window this is the loudest
         message a not-yet-checked-in player sees — above status and deck notes. -->
    {#if notCheckedIn}
      <div class="banner-info border rounded-lg p-3 mb-3 text-sm">
        <p class="font-medium">{m.tournament_checkin_call_player()}</p>
        <p class="text-ink-muted">{tournament.online ? m.tournament_checkin_call_player_online() : m.tournament_checkin_call_player_qr()}</p>
      </div>
    {/if}
    <div class="text-sm mb-3 flex items-center justify-between">
      <div>
        <span class="text-ink-faint">{m.tournament_your_status()}</span>
        <span class="ml-2 text-ink-bright">{currentPlayerEntry.state === "Finished"
          ? ((tournament.finals !== null || tournament.state === "Finished") && standings.some(s => s.user_uid === currentPlayerEntry.user_uid) ? m.tournament_status_finished() : m.tournament_status_dropped())
          : translatePlayerState(currentPlayerEntry.state)}</span>
      </div>
      {#if !tournament.online && !atCap && currentPlayerEntry.state === "Registered" && tournament.state === "Waiting"}
        <Button
          variant="ghost"
          onclick={() => showQrScanner = !showQrScanner}
          disabled={actionLoading}
        >
          <QrCode class="w-4 h-4" />
          {m.checkin_qr_scan_btn()}
        </Button>
      {:else if !tournament.online && !atCap && currentPlayerEntry.state === "Finished" && tournament.state === "Waiting"}
        <Button
          variant="ghost"
          onclick={() => showQrScanner = true}
          disabled={actionLoading}
        >
          <QrCode class="w-4 h-4" />
          {m.tournament_check_in_btn()}
        </Button>
      {:else if currentPlayerEntry.state !== "Finished" && (tournament.state === "Waiting" || tournament.state === "Playing")}
        <Button
          variant="danger"
          onclick={() => dropPlayer(userUid)}
          disabled={actionLoading}
        ><Trash2 class="w-4 h-4" aria-hidden="true" />{m.tournament_drop_out_btn()}</Button>
      {/if}
    </div>
    <!-- Online check-in is server-side (bot self-serve or organizer). The check-in
         call banner above carries the instruction; here we just surface the Join link. -->
    {#if tournament.online && notCheckedIn}
      <div class="mb-3">
        {@render onlineJoin()}
      </div>
    {/if}
    <!-- Open rounds: capped player gets no check-in CTA — tell them they're done and finals-eligible. -->
    {#if atCap && tournament.state === "Waiting"}
      <p class="text-sm text-ink-muted mb-3">{m.player_completed_awaiting_finals()}</p>
    {/if}
    {#if showDeckWarn}
      <div class="mb-3">{@render deckWarn()}</div>
    {/if}
    <!-- Player's current score -->
    {#if myStanding && (tournament.state === "Playing" || tournament.state === "Waiting") && (tournament.rounds?.length ?? 0) > 0}
      <div class="text-sm">
        <span class="text-ink-faint">{m.tournament_your_score()}</span>
        <span class="ml-2 text-ink-strong font-medium">{formatScore(myStanding.gw, myStanding.vp, myStanding.tp)}</span>
      </div>
    {/if}
    <!-- Self-organize a round (open-rounds, online): seat your own 4-5 pod without an organizer -->
    {#if canSelfOrganize}
      <div class="bg-surface-muted/50 rounded-lg p-4 space-y-2">
        <div class="flex items-start gap-2">
          <Users class="w-4 h-4 mt-0.5 text-link shrink-0" aria-hidden="true" />
          <div class="min-w-0">
            <h3 class="text-sm font-medium text-ink-strong">{m.self_organize_title()}</h3>
            <p class="text-xs text-ink-muted mt-0.5">{m.self_organize_tip()}</p>
          </div>
        </div>
        <Button
          variant="primary"
          size="lg"
          block
          class="min-h-[44px]"
          disabled={actionLoading}
          onclick={() => showSelfOrganize = true}
        >
          {m.self_organize_start_btn()}
        </Button>
      </div>
    {/if}
    <!-- Your table + seat — the primary card during play; standings/cutoff/history follow below -->
    {#if isFinals && !isFinished && tournament.finals}
      {@const finalsSeatIdx = tournament.finals.seating.findIndex(s => s.player_uid === userUid)}
      {@const finalsSize = tournament.finals.seating.length}
      <div class="bg-surface-muted/50 rounded-lg p-4">
        <div class="flex items-center justify-between mb-2">
          <h3 class="text-sm font-medium text-ink-strong">{m.tournament_finals_heading()}</h3>
          <span class="text-xs px-2 py-0.5 rounded {tournament.finals.state === 'Finished' ? 'badge-success' : tournament.finals.state === 'Invalid' ? 'bg-accent-soft/60 text-link-soft' : 'badge-pending'}">
            {translateTableState(tournament.finals.state)}
          </span>
        </div>
        <div class="space-y-1.5">
          {#each tournament.finals.seating as seat, j}
            {@const tVps = tournament.finals.seating.map(s => s.result.vp)}
            {@const tGws = computeGwFinals(tVps, tournament.finals.seed_order, tournament.finals.seating.map(s => s.player_uid))}
            {@const tTps = computeTpLocal(tournament.finals.seating.length, tVps)}
            {@const seedIdx = tournament.finals.seed_order.indexOf(seat.player_uid) + 1}
            {@const seedStanding = standings.find(s => s.user_uid === seat.player_uid)}
            {@const isMe = seat.player_uid === userUid}
            {@const isPrey = finalsSeatIdx >= 0 && j === (finalsSeatIdx + 1) % finalsSize}
            {@const isPredator = finalsSeatIdx >= 0 && j === (finalsSeatIdx - 1 + finalsSize) % finalsSize}
            <div class="px-2.5 -mx-2.5 py-2 rounded-md {isMe ? 'ring-1 ring-inset ring-accent/40 bg-accent-soft/10' : ''}">
              <div class="flex items-center justify-between gap-2 mb-1.5 text-sm">
                <div class="min-w-0">
                  <span class="min-w-0 inline-flex items-center gap-1.5">
                    <span class="text-ink-faint text-xs tabular-nums shrink-0">{m.tournament_seat_n({ n: String(j + 1) })}</span>
                    <span class="text-ink truncate min-w-0">{seatDisplay(seat.player_uid)}</span>
                    {#if isMe}<span class="shrink-0 px-1.5 py-0.5 rounded text-xs badge-slate">{m.tournament_seat_you()}</span>
                    {:else if isPrey}<span class="shrink-0 px-1.5 py-0.5 rounded text-xs badge-slate">{m.tournament_seat_prey()}</span>
                    {:else if isPredator}<span class="shrink-0 px-1.5 py-0.5 rounded text-xs badge-slate">{m.tournament_seat_predator()}</span>{/if}
                  </span>
                  <div class="text-xs text-ink-faint">{m.tournament_seed({ n: String(seedIdx) })}{#if seedStanding} · {formatScore(seedStanding.gw, seedStanding.vp, seedStanding.tp)}{/if} · {tGws[j]}GW {tTps[j]}TP</div>
                </div>
              </div>
              <VpInput
                value={seat.result.vp}
                options={vpOptions(tournament.finals.seating.length, false)}
                label={seatDisplay(seat.player_uid)}
                disabled={scoreSaving === -1}
                saving={scoreSavingSeat === seat.player_uid && scoreSaving === -1}
                onchange={(v) => setFinalsVp(seat.player_uid, v, tournament.finals!.seating)}
              />
            </div>
          {/each}
        </div>
      </div>
    {:else if tournament.state === "Playing" && (tournament.rounds?.length ?? 0) > 0}
      {#if currentPlayerEntry?.state === "Completed"}
        <div class="banner-info border rounded-lg p-4">
          <p class="text-sm">{m.player_completed_awaiting_finals()}</p>
        </div>
      {:else if myActiveRounds.length === 0 && currentPlayerEntry?.state === "Checked-in"}
        <div class="banner-info border rounded-lg p-4">
          <p class="text-sm">{m.player_sitting_out()}</p>
        </div>
      {:else}
        {#each myActiveRounds as active}
          {@const myTable = active.table}
          {@const myTableIdx = active.tableIdx}
          {@const roundIdx = active.roundIdx}
          {@const mySeatIdx = myTable.seating.findIndex(s => s.player_uid === userUid)}
          {@const tableSize = myTable.seating.length}
          <div class="bg-surface-muted/50 rounded-lg p-4">
            <div class="flex items-center justify-between mb-2">
              <h3 class="text-sm font-medium text-ink-strong">
                {#if hasParallelRounds}{m.rounds_round_n({ n: String(roundIdx + 1) })} · {/if}{m.tournament_your_table({ label: resolveTableLabel(tournament.table_rooms, myTableIdx) ?? m.rounds_table_n({ n: String(myTableIdx + 1) }) })}
              </h3>
              <span class="text-xs px-2 py-0.5 rounded {myTable.state === 'Finished' ? 'badge-success' : myTable.state === 'Invalid' ? 'bg-accent-soft/60 text-link-soft' : 'badge-pending'}">
                {translateTableState(myTable.state)}
              </span>
            </div>
            <!-- Timer for player's table (hidden in offline tournaments and parallel rounds) -->
            {#if !hasParallelRounds && !tournament.offline_mode && (tournament.round_time ?? 0) > 0}
              <div class="mb-2">
                <TimerDisplay {tournament} tableIndex={myTableIdx} />
              </div>
            {/if}
            <div class="space-y-1.5">
              {#each myTable.seating as seat, j}
                {@const tVps = myTable.seating.map(s => s.result.vp)}
                {@const tGws = computeGwLocal(tVps)}
                {@const tTps = computeTpLocal(myTable.seating.length, tVps)}
                {@const isMe = seat.player_uid === userUid}
                {@const isPrey = mySeatIdx >= 0 && j === (mySeatIdx + 1) % tableSize}
                {@const isPredator = mySeatIdx >= 0 && j === (mySeatIdx - 1 + tableSize) % tableSize}
                <div class="px-2.5 -mx-2.5 py-2 rounded-md {isMe ? 'ring-1 ring-inset ring-accent/40 bg-accent-soft/10' : ''}">
                  <div class="flex items-center justify-between gap-2 mb-1.5 text-sm">
                    <span class="min-w-0 inline-flex items-center gap-1.5">
                      <span class="text-ink-faint text-xs tabular-nums shrink-0">{m.tournament_seat_n({ n: String(j + 1) })}</span>
                      <span class="text-ink truncate min-w-0">{seatDisplay(seat.player_uid)}</span>
                      {#if isMe}<span class="shrink-0 px-1.5 py-0.5 rounded text-xs badge-slate">{m.tournament_seat_you()}</span>
                      {:else if isPrey}<span class="shrink-0 px-1.5 py-0.5 rounded text-xs badge-slate">{m.tournament_seat_prey()}</span>
                      {:else if isPredator}<span class="shrink-0 px-1.5 py-0.5 rounded text-xs badge-slate">{m.tournament_seat_predator()}</span>{/if}
                    </span>
                    <span class="text-ink-faint text-xs shrink-0">{tGws[j]}GW {tTps[j]}TP</span>
                  </div>
                  <VpInput
                    value={seat.result.vp}
                    options={vpOptions(myTable.seating.length, false)}
                    label={seatDisplay(seat.player_uid)}
                    disabled={scoreSaving === myTableIdx}
                    saving={scoreSavingSeat === seat.player_uid && scoreSaving === myTableIdx}
                    onchange={(v) => setVp(roundIdx, myTableIdx, seat.player_uid, v, myTable.seating)}
                  />
                </div>
              {/each}
            </div>
            <!-- Call Judge: prominent emergency action for the player at this table -->
            {#if !tournament.offline_mode && isOnline()}
              <Button
                variant="primary"
                size="lg"
                block
                disabled={judgeCallCooldown}
                onclick={() => handleCallJudge(myTableIdx)}
                class="mt-3 min-h-[44px]"
              >
                <Gavel class="w-5 h-5" />
                {judgeCallCooldown ? m.judge_call_cooldown() : m.judge_call_btn()}
              </Button>
            {/if}
          </div>
        {/each}
      {/if}
    {/if}
    <!-- Cutoff score threshold for players -->
    {#if cutoffScore}
      <div class="bg-surface-muted/50 rounded-lg p-4">
        <h3 class="text-sm font-medium text-ink-strong mb-2">
          {m.tournament_standings()}
          <span class="text-xs text-ink-faint font-normal ml-1">({m.tournament_standings_cutoff()})</span>
        </h3>
        <ScoreLegend />
        <p class="text-sm text-ink">
          {m.tournament_cutoff_threshold()} <span class="text-ink-strong font-medium">{formatScore(cutoffScore.gw, cutoffScore.vp, cutoffScore.tp)}</span>
        </p>
      </div>
    {/if}
    <!-- Standings for players -->
    {#if tournament.state !== "Finished" && playerStandings.length > 0}
      <div class="bg-surface-muted/50 rounded-lg p-4">
        <h3 class="text-sm font-medium text-ink-strong mb-2">
          {m.tournament_standings()}
          {#if tournament.standings_mode !== "Public"}
            <span class="text-xs text-ink-faint font-normal ml-1">({translateStandingsMode(tournament.standings_mode)})</span>
          {/if}
        </h3>
        <ScoreLegend />
        <table class="w-full text-sm">
          <thead>
            <tr class="text-ink-faint text-xs">
              <th class="text-left py-1 pr-2">{m.tournament_col_rank()}</th>
              <th class="text-left py-1 pr-2">{m.tournament_col_player()}</th>
              <th class="text-right py-1 px-2">{m.tournament_col_score()}</th>
            </tr>
          </thead>
          <tbody>
            {#each playerStandings as entry, idx}
              <tr class="{idx < 5 ? 'text-ink-strong' : 'text-ink-muted'} border-t border-line">
                <td class="py-1 pr-2 text-ink-faint"><RankCell rank={entry.rank} finalist={entry.finalist} /></td>
                <td class="py-1 pr-2">
                  <span class="inline-flex items-center gap-1">
                    {seatDisplay(entry.user_uid)}
                    <SanctionIndicator sanctions={sanctionsForPlayer(entry.user_uid)} />
                    {#if isPlayerDQ(entry.user_uid)}<span class="text-xs text-link">{m.tournament_disqualified()}</span>{/if}
                  </span>
                </td>
                <td class="text-right py-1 px-2">{formatScore(entry.gw, entry.vp, entry.tp)}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
    <!-- Previous rounds history -->
    {#if previousRounds.length > 0}
      <div>
        <button
          onclick={() => showPreviousRounds = !showPreviousRounds}
          class="text-sm text-ink-muted hover:text-ink-bright transition-colors flex items-center gap-1"
        >
          {#if showPreviousRounds}<ChevronDown class="w-4 h-4" />{:else}<ChevronRight class="w-4 h-4" />{/if}
          {m.tournament_previous_rounds()}
        </button>
        {#if showPreviousRounds}
          <div class="mt-2 space-y-3">
            {#each previousRounds as prev}
              <div class="bg-surface-muted/50 rounded-lg p-3">
                <h4 class="text-xs font-medium text-ink-muted mb-1.5">{m.tournament_round_table({ round: String(prev.round), table: prev.tableLabel })}</h4>
                <div class="divide-y divide-line">
                  {#each prev.table.seating as seat, j}
                    {@const tVps = prev.table.seating.map(s => s.result.vp)}
                    {@const tGws = computeGwLocal(tVps)}
                    {@const tTps = computeTpLocal(prev.table.seating.length, tVps)}
                    <div class="py-1 flex items-center justify-between text-sm {seat.player_uid === userUid ? 'text-ink-strong' : 'text-ink-muted'}">
                      <span>{seatDisplay(seat.player_uid)}</span>
                      <span class="text-xs">{seat.result.vp}VP {tGws[j]}GW {tTps[j]}TP</span>
                    </div>
                  {/each}
                </div>
              </div>
            {/each}
          </div>
        {/if}
      </div>
    {/if}
  {:else}
    <p class="text-ink-muted text-sm">{m.tournament_registration_not_open()}</p>
  {/if}

  <!-- QR Check-in scanner -->
  {#if showQrScanner}
    <QrCheckinScanner tournamentUid={tournament.uid} onclose={() => showQrScanner = false} />
  {/if}

  <!-- Self-organize round picker -->
  {#if showSelfOrganize}
    <SelfOrganizeDialog
      selfName={seatDisplay(userUid)}
      candidates={selfOrganizeCandidates}
      submitting={actionLoading}
      onSubmit={submitSelfOrganize}
      onClose={() => showSelfOrganize = false}
    />
  {/if}

  <!-- Registered players list (player view, Planned/Registration) -->
  {#if (tournament.state === "Planned" || tournament.state === "Registration") && (tournament.players?.length ?? 0) > 0}
    {@const registered = tournament.players!.filter(p => p.state === "Registered")}
    {#if registered.length > 0}
      <div class="mt-4">
        <button
          onclick={() => showRegisteredPlayers = !showRegisteredPlayers}
          class="text-sm text-ink-muted hover:text-ink-bright transition-colors flex items-center gap-1"
        >
          {#if showRegisteredPlayers}<ChevronDown class="w-4 h-4" />{:else}<ChevronRight class="w-4 h-4" />{/if}
          {m.tournament_registered_players({ count: String(registered.length) })}
        </button>
        {#if showRegisteredPlayers}
          <div class="mt-2 flex flex-wrap gap-2">
            {#each registered as player}
              {@const puid = player.user_uid ?? ""}
              <span class="px-2 py-1 text-sm bg-surface-hover rounded text-ink-bright">
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
    <div id="player-deck-section" class="mt-4 scroll-mt-4">
      <PlayerDecksSection
        {tournament}
        {playerInfo}
        {decksByUser}
      />
    </div>
  {/if}
</div>

<!-- Raffle results (visible to all players) -->
{#if (tournament.state === "Waiting" || tournament.state === "Playing" || tournament.state === "Finished") && (tournament.raffles?.length ?? 0) > 0}
  <div class="bg-surface-card rounded-lg shadow border border-line mb-6 p-6">
    <h3 class="text-sm font-medium text-ink mb-3">{m.raffle_title()}</h3>
    <RaffleSection
      {tournament}
      {playerInfo}
      isOrganizer={false}
    />
  </div>
{/if}

<!-- Finished tournament results (VEKN members only) -->
{#if tournament.state === "Finished" && userVeknId}
  {@const hasFinals = standings.some(e => e.finals)}
  <div class="bg-surface-card rounded-lg shadow border border-line mb-6 p-6 space-y-4">
    {#if tournament.winner}
      <div class="banner-highlight border rounded-lg p-4">
        <div class="text-ink-faint text-sm">{m.tournament_winner()}</div>
        <div class="text-xl font-medium text-ink-strong">{seatDisplay(tournament.winner)}</div>
      </div>
    {/if}
    {#if standings.length > 0}
      <div class="bg-surface-muted/50 rounded-lg p-4">
        <h3 class="text-sm font-medium text-ink-strong mb-2">{m.tournament_standings()}</h3>
        <ScoreLegend />
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="text-ink-faint text-xs">
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
                <tr class="{idx < 5 ? 'text-ink-strong' : 'text-ink-muted'} border-t border-line">
                  <td class="py-1 pr-2 text-ink-faint"><RankCell rank={entry.rank} finalist={entry.finalist} /></td>
                  <td class="py-1 pr-2">
                    <span class="inline-flex items-center gap-1">
                      {seatDisplay(entry.user_uid)}
                      <SanctionIndicator sanctions={sanctionsForPlayer(entry.user_uid)} />
                      {#if isPlayerDQ(entry.user_uid)}<span class="text-xs text-link">{m.tournament_disqualified()}</span>{/if}
                    </span>
                  </td>
                  <td class="text-right py-1 px-2">{formatScore(entry.gw, entry.vp, entry.tp)}</td>
                  {#if hasFinals}
                    <td class="text-right py-1 px-2">{entry.finals ?? ""}</td>
                  {/if}
                  {#if isFinished}
                    <td class="text-right py-1 px-2 text-ink-muted">{getRatingPts(entry)}</td>
                  {/if}
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      </div>
    {/if}
    {#if tournament.finals}
      <div class="bg-surface-muted/50 rounded-lg p-4">
        <h3 class="text-sm font-medium text-ink-strong mb-2">{m.tournament_finals_table()}</h3>
        <div class="divide-y divide-line">
          {#each tournament.finals.seating as seat, j}
            {@const tVps = tournament.finals.seating.map(s => s.result.vp)}
            {@const tGws = computeGwFinals(tVps, tournament.finals.seed_order, tournament.finals.seating.map(s => s.player_uid))}
            {@const tTps = computeTpLocal(tournament.finals.seating.length, tVps)}
            {@const seedIdx = tournament.finals.seed_order.indexOf(seat.player_uid) + 1}
            {@const seedStanding = standings.find(s => s.user_uid === seat.player_uid)}
            <div class="py-1.5 flex items-center justify-between text-sm">
              <div>
                <span class="text-ink">{seatDisplay(seat.player_uid)}</span>
                <div class="text-xs text-ink-faint">{m.tournament_seed({ n: String(seedIdx) })}{#if seedStanding} · {formatScore(seedStanding.gw, seedStanding.vp, seedStanding.tp)}{/if}</div>
              </div>
              <span class="text-ink-faint text-xs">{seat.result.vp}VP {tGws[j]}GW {tTps[j]}TP</span>
            </div>
          {/each}
        </div>
      </div>
    {/if}
  </div>
{/if}
