<script lang="ts">
  import type { Tournament, Player, Sanction } from "$lib/types";
  import type { StandingEntry } from "$lib/tournament-utils";
  import { seatDisplay as seatDisplayUtil, vpOptions, computeGwLocal, computeTpLocal, translatePlayerState, translateTableState, resolveTableLabel } from "$lib/tournament-utils";
  import { formatScore } from "$lib/utils";
  import { computeRatingPoints } from "$lib/engine";
  import { TriangleAlert, ChevronDown, ChevronRight, QrCode, Gavel } from "lucide-svelte";
  import SanctionIndicator from "$lib/components/SanctionIndicator.svelte";
  import QrCheckinScanner from "$lib/components/QrCheckinScanner.svelte";
  import TimerDisplay from "./TimerDisplay.svelte";
  import DecksTab from "./DecksTab.svelte";
  import RaffleSection from "./RaffleSection.svelte";
  import { callJudge } from "$lib/api";
  import { isOnline } from "$lib/api";
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
    doAction,
    dropPlayer,
    setVp,
    setFinalsVp,
    tournamentSanctions,
  }: {
    tournament: Tournament;
    playerInfo: Record<string, { name: string; nickname: string | null; vekn: string | null }>;
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
    doAction: (action: string, body?: any) => Promise<void>;
    dropPlayer: (uid: string) => Promise<void>;
    setVp: (tableIndex: number, playerUid: string, vp: number, seating: Array<{ player_uid: string; result: { vp: number } }>) => Promise<void>;
    setFinalsVp: (playerUid: string, vp: number, seating: Array<{ player_uid: string; result: { vp: number } }>) => Promise<void>;
    tournamentSanctions: Sanction[];
  } = $props();

  let showRegisteredPlayers = $state(false);
  let showQrScanner = $state(false);
  let judgeCallCooldown = $state(false);

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
    const finalistPos = entry.user_uid === tournament.winner ? 1
      : (tournament.finals?.seating.some(s => s.player_uid === entry.user_uid) ? 2 : 0);
    return computeRatingPoints(entry.vp, entry.gw, finalistPos, standings.length, tournament.rank);
  }
</script>

<!-- Player interaction section -->
<div class="bg-dusk-950 rounded-lg shadow border border-ash-800 mb-6 p-6 space-y-4">
  {#if tournament.state === "Registration" && !currentPlayerEntry}
    <button
      onclick={() => doAction("Register", { user_uid: userUid })}
      disabled={actionLoading}
      class="px-4 py-2 text-sm font-medium btn-emerald disabled:bg-ash-700 rounded-lg transition-colors"
    >{m.tournament_register_btn()}</button>
  {:else if tournament.state === "Registration" && currentPlayerEntry}
    <div class="text-sm mb-3 flex items-center justify-between">
      <div>
        <span class="text-ash-500">{m.tournament_your_status()}</span>
        <span class="ml-2 text-ash-200">{translatePlayerState(currentPlayerEntry.state)}</span>
      </div>
      <button
        onclick={() => doAction("Unregister", { user_uid: userUid })}
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
          <TriangleAlert class="w-4 h-4" />
          {m.tournament_upload_valid_deck()}
        </div>
      {:else if currentPlayerEntry.state === "Registered" && tournament.state === "Waiting" && playerHasValidDeck}
        <button
          onclick={() => showQrScanner = !showQrScanner}
          disabled={actionLoading}
          class="px-3 py-1.5 text-sm text-emerald-400 hover:text-emerald-300 border border-emerald-800 hover:border-emerald-700 rounded-lg transition-colors flex items-center gap-1.5"
        >
          <QrCode class="w-4 h-4" />
          {m.checkin_qr_scan_btn()}
        </button>
      {:else if currentPlayerEntry.state === "Finished" && tournament.state === "Waiting"}
        {#if !playerHasValidDeck}
          <div class="flex items-center gap-2 text-amber-400 text-sm">
            <TriangleAlert class="w-4 h-4" />
            {m.tournament_upload_valid_deck()}
          </div>
        {:else}
          <button
            onclick={() => doAction("CheckIn", { player_uid: userUid })}
            disabled={actionLoading}
            class="px-3 py-1.5 text-sm text-emerald-400 hover:text-emerald-300 border border-emerald-800 hover:border-emerald-700 rounded-lg transition-colors"
          >{m.tournament_check_in_btn()}</button>
        {/if}
      {:else if currentPlayerEntry.state !== "Finished" && (tournament.state === "Waiting" || tournament.state === "Playing")}
        <button
          onclick={() => dropPlayer(userUid)}
          disabled={actionLoading}
          class="px-3 py-1.5 text-sm text-crimson-400 hover:text-crimson-300 border border-crimson-800 hover:border-crimson-700 rounded-lg transition-colors"
        >{m.tournament_drop_out_btn()}</button>
      {/if}
    </div>
    <!-- QR Check-in scanner -->
    {#if showQrScanner}
      <QrCheckinScanner tournamentUid={tournament.uid} onclose={() => showQrScanner = false} />
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
            <span class="text-xs text-ash-500 font-normal ml-1">({tournament.standings_mode})</span>
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
    {#if isFinals && !isFinished && tournament.finals}
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
                  onchange={(e) => setFinalsVp(seat.player_uid, parseFloat((e.target as HTMLSelectElement).value), tournament.finals!.seating)}
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
      {@const myTableIdx = currentRound.findIndex(t => t.seating.some(s => s.player_uid === userUid))}
      {#if myTableIdx >= 0 && currentRound[myTableIdx]}
        {@const myTable = currentRound[myTableIdx]!}
        <div class="bg-ash-900/50 rounded-lg p-4">
          <div class="flex items-center justify-between mb-2">
            <h3 class="text-sm font-medium text-bone-100">{m.tournament_your_table({ label: resolveTableLabel(tournament.table_rooms, myTableIdx) ?? m.rounds_table_n({ n: String(myTableIdx + 1) }) })}</h3>
            <div class="flex items-center gap-2">
              <span class="text-xs px-2 py-0.5 rounded {myTable.state === 'Finished' ? 'badge-emerald' : myTable.state === 'Invalid' ? 'bg-crimson-900/60 text-crimson-300' : 'badge-amber'}">
                {translateTableState(myTable.state)}
              </span>
              {#if !tournament.offline_mode && isOnline()}
                <button
                  onclick={() => handleCallJudge(myTableIdx)}
                  disabled={judgeCallCooldown}
                  class="px-2 py-1 text-xs {judgeCallCooldown ? 'text-ash-500 border-ash-700' : 'text-amber-400 hover:text-amber-300 border-amber-800 hover:border-amber-700'} border rounded-lg transition-colors flex items-center gap-1"
                  title={judgeCallCooldown ? m.judge_call_cooldown() : m.judge_call_btn()}
                >
                  <Gavel class="w-3 h-3" />
                  {judgeCallCooldown ? m.judge_call_cooldown() : m.judge_call_btn()}
                </button>
              {/if}
            </div>
          </div>
          <!-- Timer for player's table -->
          {#if (tournament.round_time ?? 0) > 0}
            <div class="mb-2">
              <TimerDisplay {tournament} tableIndex={myTableIdx} />
            </div>
          {/if}
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
      <DecksTab
        {tournament}
        {playerInfo}
        isOrganizer={false}
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
      standings={tournament.standings ?? []}
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
