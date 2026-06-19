<script lang="ts">
  import type { Tournament, Player, Sanction, DeckObject } from "$lib/types";
  import type { StandingEntry, PlayerInfoMap } from "$lib/tournament-utils";
  import { seatDisplay as seatDisplayUtil, vpOptions, computeGwLocal, computeGwFinals, computeTpLocal, translatePlayerState, translateTableState, translateStandingsMode, resolveTableLabel } from "$lib/tournament-utils";
  import { formatScore } from "$lib/utils";
  import { computeRatingPoints } from "$lib/engine";
  import { TriangleAlert, ChevronDown, ChevronRight, QrCode, Gavel } from "@lucide/svelte";
  import SanctionIndicator from "$lib/components/SanctionIndicator.svelte";
  import RankCell from "$lib/components/RankCell.svelte";
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
    userUid: string;
    userVeknId: string | null;
    actionLoading: boolean;
    scoreSaving: number | null;
    scoreSavingSeat: string | null;
    doAction: (action: string, body?: any) => Promise<void>;
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
    return seatDisplayUtil(uid, playerInfo);
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

<!-- Player interaction section -->
<div class="bg-dusk-950 rounded-lg shadow border border-ash-800 mb-6 p-6 space-y-4">
  {#if tournament.state === "Registration" && !currentPlayerEntry}
    {#if userSuspended}
      <div class="text-sm text-crimson-400">{m.error_suspended_cannot_register()}</div>
    {:else if !userVeknId}
      <div class="text-sm text-amber-400">{m.tournament_vekn_id_required_to_register()}</div>
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
        <span class="text-ash-500">{m.tournament_your_status()}</span>
        <span class="ml-2 text-ash-200">{translatePlayerState(currentPlayerEntry.state)}</span>
      </div>
      <Button
        variant="danger"
        onclick={() => doAction("Unregister", { user_uid: userUid })}
        disabled={actionLoading}
      >{m.tournament_unregister_btn()}</Button>
    </div>
  {:else if tournament.state === "Waiting" && !currentPlayerEntry}
    <Button
      variant="primary"
      size="lg"
      onclick={() => showQrScanner = true}
      disabled={actionLoading}
    >
      <QrCode class="w-4 h-4" />
      {m.tournament_register_checkin_btn()}
    </Button>
  {:else if currentPlayerEntry}
    <div class="text-sm mb-3 flex items-center justify-between">
      <div>
        <span class="text-ash-500">{m.tournament_your_status()}</span>
        <span class="ml-2 text-ash-200">{currentPlayerEntry.state === "Finished"
          ? ((tournament.finals !== null || tournament.state === "Finished") && standings.some(s => s.user_uid === currentPlayerEntry.user_uid) ? m.tournament_status_finished() : m.tournament_status_dropped())
          : translatePlayerState(currentPlayerEntry.state)}</span>
      </div>
      {#if currentPlayerEntry.state === "Registered" && tournament.state === "Waiting" && !playerHasValidDeck}
        <div class="flex items-center gap-2 text-amber-400 text-sm">
          <TriangleAlert class="w-4 h-4" />
          {m.tournament_upload_valid_deck()}
        </div>
      {:else if currentPlayerEntry.state === "Registered" && tournament.state === "Waiting" && playerHasValidDeck}
        <Button
          variant="ghost"
          onclick={() => showQrScanner = !showQrScanner}
          disabled={actionLoading}
        >
          <QrCode class="w-4 h-4" />
          {m.checkin_qr_scan_btn()}
        </Button>
      {:else if currentPlayerEntry.state === "Finished" && tournament.state === "Waiting"}
        {#if !playerHasValidDeck}
          <div class="flex items-center gap-2 text-amber-400 text-sm">
            <TriangleAlert class="w-4 h-4" />
            {m.tournament_upload_valid_deck()}
          </div>
        {:else}
          <Button
            variant="ghost"
            onclick={() => showQrScanner = true}
            disabled={actionLoading}
          >
            <QrCode class="w-4 h-4" />
            {m.tournament_check_in_btn()}
          </Button>
        {/if}
      {:else if currentPlayerEntry.state !== "Finished" && (tournament.state === "Waiting" || tournament.state === "Playing")}
        <Button
          variant="danger"
          onclick={() => dropPlayer(userUid)}
          disabled={actionLoading}
        >{m.tournament_drop_out_btn()}</Button>
      {/if}
    </div>
    <!-- Player's current score -->
    {#if myStanding && (tournament.state === "Playing" || tournament.state === "Waiting") && (tournament.rounds?.length ?? 0) > 0}
      <div class="text-sm">
        <span class="text-ash-500">{m.tournament_your_score()}</span>
        <span class="ml-2 text-bone-100 font-medium">{formatScore(myStanding.gw, myStanding.vp, myStanding.tp)}</span>
      </div>
    {/if}
    <!-- Your table + seat — the primary card during play; standings/cutoff/history follow below -->
    {#if isFinals && !isFinished && tournament.finals}
      <div class="bg-ash-900/50 rounded-lg p-4">
        <h3 class="text-sm font-medium text-bone-100 mb-2">{m.tournament_finals_heading()}</h3>
        <div class="divide-y divide-ash-800">
          {#each tournament.finals.seating as seat, j}
            {@const tVps = tournament.finals.seating.map(s => s.result.vp)}
            {@const tGws = computeGwFinals(tVps, tournament.finals.seed_order, tournament.finals.seating.map(s => s.player_uid))}
            {@const tTps = computeTpLocal(tournament.finals.seating.length, tVps)}
            {@const seedIdx = tournament.finals.seed_order.indexOf(seat.player_uid) + 1}
            {@const seedStanding = standings.find(s => s.user_uid === seat.player_uid)}
            <div class="py-2.5">
              <div class="flex items-center justify-between gap-2 mb-1.5 text-sm">
                <div class="min-w-0">
                  <span class="text-ash-300 truncate">{seatDisplay(seat.player_uid)}</span>
                  <div class="text-xs text-ash-500">{m.tournament_seed({ n: String(seedIdx) })}{#if seedStanding} · {formatScore(seedStanding.gw, seedStanding.vp, seedStanding.tp)}{/if} · {tGws[j]}GW {tTps[j]}TP</div>
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
      {#if myActiveRounds.length === 0 && currentPlayerEntry?.state === "Checked-in"}
        <div class="bg-sky-900/20 border border-sky-800/40 rounded-lg p-4">
          <p class="text-sm text-sky-300">{m.player_sitting_out()}</p>
        </div>
      {:else}
        {#each myActiveRounds as active}
          {@const myTable = active.table}
          {@const myTableIdx = active.tableIdx}
          {@const roundIdx = active.roundIdx}
          <div class="bg-ash-900/50 rounded-lg p-4">
            <div class="flex items-center justify-between mb-2">
              <h3 class="text-sm font-medium text-bone-100">
                {#if hasParallelRounds}{m.rounds_round_n({ n: String(roundIdx + 1) })} · {/if}{m.tournament_your_table({ label: resolveTableLabel(tournament.table_rooms, myTableIdx) ?? m.rounds_table_n({ n: String(myTableIdx + 1) }) })}
              </h3>
              <span class="text-xs px-2 py-0.5 rounded {myTable.state === 'Finished' ? 'badge-emerald' : myTable.state === 'Invalid' ? 'bg-crimson-900/60 text-crimson-300' : 'badge-amber'}">
                {translateTableState(myTable.state)}
              </span>
            </div>
            <!-- Timer for player's table (hidden in offline tournaments and parallel rounds) -->
            {#if !hasParallelRounds && !tournament.offline_mode && (tournament.round_time ?? 0) > 0}
              <div class="mb-2">
                <TimerDisplay {tournament} tableIndex={myTableIdx} />
              </div>
            {/if}
            <div class="divide-y divide-ash-800">
              {#each myTable.seating as seat, j}
                {@const tVps = myTable.seating.map(s => s.result.vp)}
                {@const tGws = computeGwLocal(tVps)}
                {@const tTps = computeTpLocal(myTable.seating.length, tVps)}
                <div class="py-2.5">
                  <div class="flex items-center justify-between gap-2 mb-1.5 text-sm">
                    <span class="text-ash-300 truncate">{seatDisplay(seat.player_uid)}</span>
                    <span class="text-ash-500 text-xs shrink-0">{tGws[j]}GW {tTps[j]}TP</span>
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
                variant="warning"
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
      <div class="bg-ash-900/50 rounded-lg p-4">
        <h3 class="text-sm font-medium text-bone-100 mb-2">
          {m.tournament_standings()}
          <span class="text-xs text-ash-500 font-normal ml-1">({m.tournament_standings_cutoff()})</span>
        </h3>
        <p class="text-sm text-ash-300">
          {m.tournament_cutoff_threshold()} <span class="text-bone-100 font-medium">{formatScore(cutoffScore.gw, cutoffScore.vp, cutoffScore.tp)}</span>
        </p>
      </div>
    {/if}
    <!-- Standings for players -->
    {#if tournament.state !== "Finished" && playerStandings.length > 0}
      <div class="bg-ash-900/50 rounded-lg p-4">
        <h3 class="text-sm font-medium text-bone-100 mb-2">
          {m.tournament_standings()}
          {#if tournament.standings_mode !== "Public"}
            <span class="text-xs text-ash-500 font-normal ml-1">({translateStandingsMode(tournament.standings_mode)})</span>
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
                <td class="py-1 pr-2 text-ash-500"><RankCell rank={entry.rank} finalist={entry.finalist} /></td>
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
    <!-- Previous rounds history -->
    {#if previousRounds.length > 0}
      <div>
        <button
          onclick={() => showPreviousRounds = !showPreviousRounds}
          class="text-sm text-ash-400 hover:text-ash-200 transition-colors flex items-center gap-1"
        >
          {#if showPreviousRounds}<ChevronDown class="w-4 h-4" />{:else}<ChevronRight class="w-4 h-4" />{/if}
          {m.tournament_previous_rounds()}
        </button>
        {#if showPreviousRounds}
          <div class="mt-2 space-y-3">
            {#each previousRounds as prev}
              <div class="bg-ash-900/50 rounded-lg p-3">
                <h4 class="text-xs font-medium text-ash-400 mb-1.5">{m.tournament_round_table({ round: String(prev.round), table: prev.tableLabel })}</h4>
                <div class="divide-y divide-ash-800">
                  {#each prev.table.seating as seat, j}
                    {@const tVps = prev.table.seating.map(s => s.result.vp)}
                    {@const tGws = computeGwLocal(tVps)}
                    {@const tTps = computeTpLocal(prev.table.seating.length, tVps)}
                    <div class="py-1 flex items-center justify-between text-sm {seat.player_uid === userUid ? 'text-bone-100' : 'text-ash-400'}">
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
    <p class="text-ash-400 text-sm">{m.tournament_registration_not_open()}</p>
  {/if}

  <!-- QR Check-in scanner -->
  {#if showQrScanner}
    <QrCheckinScanner tournamentUid={tournament.uid} onclose={() => showQrScanner = false} />
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
          {#if showRegisteredPlayers}<ChevronDown class="w-4 h-4" />{:else}<ChevronRight class="w-4 h-4" />{/if}
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
  <div class="bg-dusk-950 rounded-lg shadow border border-ash-800 mb-6 p-6">
    <h3 class="text-sm font-medium text-ash-300 mb-3">{m.raffle_title()}</h3>
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
  <div class="bg-dusk-950 rounded-lg shadow border border-ash-800 mb-6 p-6 space-y-4">
    {#if tournament.winner}
      <div class="banner-emerald border rounded-lg p-4">
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
                  <td class="py-1 pr-2 text-ash-500"><RankCell rank={entry.rank} finalist={entry.finalist} /></td>
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
            {@const tGws = computeGwFinals(tVps, tournament.finals.seed_order, tournament.finals.seating.map(s => s.player_uid))}
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
