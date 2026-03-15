<script lang="ts">
  import type { Tournament } from "$lib/types";
  import { formatScore } from "$lib/utils";
  import { tournamentAction, setTableScore } from "$lib/api";
  import SeatingSortable from "$lib/components/SeatingSortable.svelte";
  import { GripVertical, ShieldCheck, Lock } from "lucide-svelte";
  import { seatDisplay as seatDisplayUtil, vpOptions, computeGwFinals, computeTpLocal, translateTableState, type StandingEntry } from "$lib/tournament-utils";
  import * as m from '$lib/paraglide/messages.js';

  let {
    tournament = $bindable(),
    playerInfo,
    standings,
    isOrganizer,
    actionLoading,
    doAction,
    loadPlayerNames,
  }: {
    tournament: Tournament;
    playerInfo: Record<string, { name: string; nickname: string | null; vekn: string | null }>;
    standings: StandingEntry[];
    isOrganizer: boolean;
    actionLoading: boolean;
    doAction: (action: string, body?: any) => Promise<void>;
    loadPlayerNames: () => Promise<void>;
  } = $props();

  let error = $state<string | null>(null);
  let scoreSaving = $state<number | null>(null);

  // Alter seating mode
  let alterMode = $state(false);
  let alterSeating = $state<string[]>([]);

  const canEditSeating = $derived(
    isOrganizer && (tournament.state === "Playing" || tournament.state === "Finished" || tournament.state === "Waiting")
  );

  function enterAlterMode() {
    alterSeating = tournament.finals!.seating.map(s => s.player_uid);
    alterTables = [alterSeating];
    alterMode = true;
  }

  function cancelAlterMode() {
    alterMode = false;
    alterSeating = [];
    alterTables = [];
  }

  async function saveAlterSeating() {
    await doAction("AlterSeating", { round: tournament.rounds!.length, seating: [alterTables[0]] });
    cancelAlterMode();
  }

  // Wrapper to expose single table as tables array for SeatingSortable
  let alterTables = $state<string[][]>([]);
  let overrideTable_ = $state<number | null>(null);
  let overrideComment = $state("");
  let overrideSaving = $state(false);

  function seatDisplay(uid: string): string {
    return seatDisplayUtil(uid, playerInfo);
  }

  async function setFinalsVp(playerUid: string, vp: number, seating: Array<{ player_uid: string; result: { vp: number } }>) {
    const roundIndex = tournament.rounds!.length; // sentinel for finals
    const scores = seating.map(s => ({
      player_uid: s.player_uid,
      vp: s.player_uid === playerUid ? vp : s.result.vp,
    }));
    scoreSaving = -1;
    try {
      tournament = await setTableScore(tournament.uid, roundIndex, 0, scores);
      await loadPlayerNames();
    } catch (e) {
      error = e instanceof Error ? e.message : m.finals_error_save();
    } finally {
      scoreSaving = null;
    }
  }

  const hasFinalsCandidate = $derived(standings.length >= 5 && (tournament?.rounds?.length ?? 0) >= 2);
</script>

<div class="space-y-4">
  {#if error}
    <div class="bg-crimson-900/20 border border-crimson-800 rounded-lg p-3">
      <p class="text-crimson-300 text-sm">{error}</p>
    </div>
  {/if}

  {#if !hasFinalsCandidate}
    <p class="text-ash-400">{m.finals_require_rounds()}</p>
  {:else if !tournament.finals}
    <p class="text-ash-400">{m.finals_not_started()}</p>
  {:else}
    <h3 class="text-lg font-medium text-bone-100">{m.finals_title()}</h3>

    <!-- Finals table -->
    <div class="bg-ash-900/50 rounded-lg p-4">
      <div class="flex items-center justify-between mb-2">
        <div class="flex items-center gap-2">
          <h3 class="text-sm font-medium text-bone-100">{m.finals_table()}</h3>
          {#if canEditSeating && !alterMode}
            <button
              onclick={enterAlterMode}
              class="px-2 py-1 text-xs text-ash-300 bg-ash-800 hover:bg-ash-700 rounded transition-colors"
            >
              <GripVertical class="w-3.5 h-3.5 inline mr-0.5" />{m.rounds_alter_seating()}
            </button>
          {/if}
        </div>
        <span class="text-xs px-2 py-0.5 rounded {tournament.finals.state === 'Finished' ? 'badge-emerald' : tournament.finals.state === 'Invalid' ? 'bg-crimson-900/60 text-crimson-300' : 'badge-amber'}">
          {translateTableState(tournament.finals.state)}
        </span>
      </div>
      {#if alterMode}
        <!-- In-place alter seating mode -->
        <p class="text-sm text-ash-300 mb-2">{m.rounds_alter_hint()}</p>
        <SeatingSortable
          bind:tables={alterTables}
          {playerInfo}
          playerIssues={new Map()}
          isFinals={true}
          onchange={() => { alterSeating = alterTables[0] ?? []; }}
        />
        <div class="flex gap-2 mt-3">
          <button
            onclick={saveAlterSeating}
            disabled={actionLoading}
            class="px-4 py-2 text-sm font-medium btn-emerald rounded-lg transition-colors"
          >{m.rounds_save_seating()}</button>
          <button
            onclick={cancelAlterMode}
            class="px-4 py-2 text-sm text-ash-300 bg-ash-800 hover:bg-ash-700 rounded-lg transition-colors"
          >{m.common_cancel()}</button>
        </div>
      {:else}
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
              <div class="text-xs text-ash-500">{m.finals_seed({ n: String(seedIdx) })}{#if seedStanding} · {formatScore(seedStanding.gw, seedStanding.vp, seedStanding.tp)}{/if}</div>
            </div>
            <div class="flex items-center gap-2">
              <span class="text-ash-400 text-xs">VP:</span>
              {#if !isOrganizer && tournament.finals.seating.some(s => s.judge_uid)}
                <span class="inline-flex items-center gap-1 text-xs text-ash-400">
                  {seat.result.vp}
                  <Lock class="w-3.5 h-3.5" />
                </span>
              {:else}
                <select
                  class="bg-ash-800 text-bone-100 text-xs rounded px-1.5 py-1.5 sm:py-0.5 border border-ash-700"
                  disabled={scoreSaving === -1}
                  value={seat.result.vp}
                  onchange={(e) => setFinalsVp(seat.player_uid, parseFloat((e.target as HTMLSelectElement).value), tournament.finals!.seating)}
                >
                  {#each vpOptions(tournament.finals.seating.length, isOrganizer) as v}
                    <option value={v}>{v}</option>
                  {/each}
                </select>
              {/if}
              <span class="text-ash-500 text-xs">{tGws[j]}GW {tTps[j]}TP</span>
            </div>
          </div>
        {/each}
      </div>
      {/if}

      <!-- Override controls -->
      {#if isOrganizer && (tournament.finals.state === 'Invalid' || tournament.finals.state === 'In Progress')}
        {#if overrideTable_ === -1}
          <div class="mt-2 pt-2 border-t border-ash-800">
            <label class="text-xs text-ash-400 block mb-1">{m.override_judge_comment()}
              <textarea
                bind:value={overrideComment}
                class="w-full bg-ash-800 text-bone-100 text-xs rounded px-2 py-1 border border-ash-700 resize-none"
                rows="2"
                placeholder={m.override_placeholder()}
              ></textarea>
            </label>
            <div class="flex gap-2 mt-1 justify-end">
              <button onclick={() => { overrideTable_ = null; overrideComment = ""; }} class="px-2 py-1 text-xs text-ash-400 hover:text-ash-200">{m.common_cancel()}</button>
              <button
                onclick={async () => {
                  if (!overrideComment.trim()) return;
                  overrideSaving = true;
                  try {
                    tournament = await tournamentAction(tournament.uid, "Override", { round: tournament.rounds!.length, table: 0, comment: overrideComment.trim() });
                    await loadPlayerNames();
                    overrideTable_ = null;
                    overrideComment = "";
                  } catch (e) { error = e instanceof Error ? e.message : m.override_error(); } finally { overrideSaving = false; }
                }}
                disabled={overrideSaving || !overrideComment.trim()}
                class="px-3 py-1 text-xs font-medium btn-amber rounded transition-colors"
              >{overrideSaving ? m.common_saving() : m.override_save()}</button>
            </div>
          </div>
        {:else}
          <div class="mt-2 flex justify-end">
            <button
              onclick={() => { overrideTable_ = -1; overrideComment = ""; }}
              class="px-2 py-1 text-xs text-amber-400 hover:text-amber-300 transition-colors"
            >
              <ShieldCheck class="w-3.5 h-3.5 inline mr-1" />{m.override_btn()}
            </button>
          </div>
        {/if}
      {/if}
      {#if isOrganizer && tournament.finals.override}
        <div class="mt-2 pt-2 border-t border-ash-800 flex items-center justify-between">
          <span class="text-xs text-amber-400">
            <ShieldCheck class="w-3.5 h-3.5 inline mr-1" />
            {m.override_overridden({ comment: tournament.finals.override.comment })}
          </span>
          <button
            onclick={async () => {
              overrideSaving = true;
              try {
                tournament = await tournamentAction(tournament.uid, "Unoverride", { round: tournament.rounds!.length, table: 0 });
                await loadPlayerNames();
              } catch (e) { error = e instanceof Error ? e.message : m.override_remove_error(); } finally { overrideSaving = false; }
            }}
            disabled={overrideSaving}
            class="px-2 py-1 text-xs text-ash-500 hover:text-crimson-400 transition-colors"
          >{m.override_remove()}</button>
        </div>
      {/if}
    </div>
  {/if}
</div>
