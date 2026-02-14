<script lang="ts">
  import type { Tournament } from "$lib/types";
  import { formatScore } from "$lib/utils";
  import { tournamentAction, setTableScore } from "$lib/api";
  import Icon from "@iconify/svelte";
  import * as m from '$lib/paraglide/messages.js';

  interface StandingEntry {
    user_uid: string;
    gw: number;
    vp: number;
    tp: number;
    toss: number;
    rank: number;
  }

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
  let swapSource: { seat: number; playerUid: string } | null = $state(null);

  const canEditSeating = $derived(
    isOrganizer && (tournament.state === "Playing" || tournament.state === "Finished")
  );

  function startSwap(seat: number, playerUid: string) {
    if (swapSource && swapSource.seat === seat) {
      swapSource = null;
    } else if (swapSource) {
      doAction("SwapSeats", {
        round: tournament.rounds.length,
        table1: 0,
        seat1: swapSource.seat,
        table2: 0,
        seat2: seat,
      });
      swapSource = null;
    } else {
      swapSource = { seat, playerUid };
    }
  }
  let overrideTable_ = $state<number | null>(null);
  let overrideComment = $state("");
  let overrideSaving = $state(false);

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

  async function setFinalsVp(playerUid: string, vp: number, seating: Array<{ player_uid: string; result: { vp: number } }>) {
    const roundIndex = tournament.rounds.length; // sentinel for finals
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

  async function finishFinals() {
    await doAction("FinishFinals");
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
    <!-- Finish Finals button -->
    {#if isOrganizer && tournament.state === "Playing"}
      <div class="flex items-center justify-between">
        <h3 class="text-lg font-medium text-bone-100">{m.finals_title()}</h3>
        <button
          onclick={finishFinals}
          disabled={actionLoading || tournament.finals.state !== "Finished"}
          title={tournament.finals.state !== "Finished" ? m.finals_finish_hint_not_ready() : m.finals_finish_hint_ready()}
          class="px-4 py-2 text-sm font-medium text-bone-100 bg-amber-700 hover:bg-amber-600 disabled:bg-ash-700 disabled:text-ash-500 rounded-lg transition-colors"
        >{m.finals_finish()}</button>
      </div>
    {/if}

    {#if swapSource}
      <div class="bg-amber-900/20 border border-amber-800 rounded-lg p-3 flex items-center justify-between">
        <p class="text-amber-300 text-sm">
          {m.rounds_swap_hint({ name: seatDisplay(swapSource.playerUid) })}
        </p>
        <button onclick={() => swapSource = null} class="text-ash-400 hover:text-ash-200 text-sm">{m.common_cancel()}</button>
      </div>
    {/if}

    <!-- Finals table -->
    <div class="bg-ash-900/50 rounded-lg p-4">
      <div class="flex items-center justify-between mb-2">
        <h3 class="text-sm font-medium text-bone-100">{m.finals_table()}</h3>
        <span class="text-xs px-2 py-0.5 rounded {tournament.finals.state === 'Finished' ? 'bg-emerald-900/60 text-emerald-300' : tournament.finals.state === 'Invalid' ? 'bg-crimson-900/60 text-crimson-300' : 'bg-amber-900/60 text-amber-300'}">
          {tournament.finals.state}
        </span>
      </div>
      <div class="divide-y divide-ash-800">
        {#each tournament.finals.seating as seat, j}
          {@const tVps = tournament.finals.seating.map(s => s.result.vp)}
          {@const tGws = computeGwLocal(tVps)}
          {@const tTps = computeTpLocal(tournament.finals.seating.length, tVps)}
          {@const seedIdx = tournament.finals.seed_order.indexOf(seat.player_uid) + 1}
          {@const seedStanding = standings.find(s => s.user_uid === seat.player_uid)}
          {@const isSwapSource = canEditSeating && swapSource?.seat === j}
          <div class="py-1.5 flex items-center justify-between text-sm">
            <div>
              {#if canEditSeating}
                <button
                  onclick={() => startSwap(j, seat.player_uid)}
                  class="text-left transition-colors {isSwapSource ? 'text-amber-300 font-medium' : 'text-ash-300 hover:text-ash-100'}"
                  title={isSwapSource ? "Click to deselect" : "Click to swap this player"}
                >
                  <Icon icon={isSwapSource ? "lucide:arrow-left-right" : "lucide:grip-vertical"} class="w-3.5 h-3.5 inline mr-1.5 text-ash-500" />
                  {seatDisplay(seat.player_uid)}
                </button>
              {:else}
                <span class="text-ash-300">{seatDisplay(seat.player_uid)}</span>
              {/if}
              <div class="text-xs text-ash-500">{m.finals_seed({ n: String(seedIdx) })}{#if seedStanding} · {formatScore(seedStanding.gw, seedStanding.vp, seedStanding.tp)}{/if}</div>
            </div>
            <div class="flex items-center gap-2">
              <span class="text-ash-400 text-xs">VP:</span>
              <select
                class="bg-ash-800 text-bone-100 text-xs rounded px-1.5 py-0.5 border border-ash-700"
                disabled={scoreSaving === -1}
                value={seat.result.vp}
                onchange={(e) => setFinalsVp(seat.player_uid, parseFloat((e.target as HTMLSelectElement).value), tournament.finals!.seating)}
              >
                {#each vpOptions(tournament.finals.seating.length, isOrganizer) as v}
                  <option value={v}>{v}</option>
                {/each}
              </select>
              <span class="text-ash-500 text-xs">{tGws[j]}GW {tTps[j]}TP</span>
            </div>
          </div>
        {/each}
      </div>

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
                    tournament = await tournamentAction(tournament.uid, "Override", { round: tournament.rounds.length, table: 0, comment: overrideComment.trim() });
                    await loadPlayerNames();
                    overrideTable_ = null;
                    overrideComment = "";
                  } catch (e) { error = e instanceof Error ? e.message : m.override_error(); } finally { overrideSaving = false; }
                }}
                disabled={overrideSaving || !overrideComment.trim()}
                class="px-3 py-1 text-xs font-medium text-bone-100 bg-amber-700 hover:bg-amber-600 disabled:bg-ash-700 rounded transition-colors"
              >{overrideSaving ? m.common_saving() : m.override_save()}</button>
            </div>
          </div>
        {:else}
          <div class="mt-2 flex justify-end">
            <button
              onclick={() => { overrideTable_ = -1; overrideComment = ""; }}
              class="px-2 py-1 text-xs text-amber-400 hover:text-amber-300 transition-colors"
            >
              <Icon icon="lucide:shield-check" class="w-3.5 h-3.5 inline mr-1" />{m.override_btn()}
            </button>
          </div>
        {/if}
      {/if}
      {#if isOrganizer && tournament.finals.override}
        <div class="mt-2 pt-2 border-t border-ash-800 flex items-center justify-between">
          <span class="text-xs text-amber-400">
            <Icon icon="lucide:shield-check" class="w-3.5 h-3.5 inline mr-1" />
            {m.override_overridden({ comment: tournament.finals.override.comment })}
          </span>
          <button
            onclick={async () => {
              overrideSaving = true;
              try {
                tournament = await tournamentAction(tournament.uid, "Unoverride", { round: tournament.rounds.length, table: 0 });
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
