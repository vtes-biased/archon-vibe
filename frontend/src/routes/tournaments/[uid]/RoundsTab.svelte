<script lang="ts">
  import type { Tournament, Table } from "$lib/types";
  import { tournamentAction, setTableScore } from "$lib/api";
  import { scoreSeatingSync } from "$lib/engine";
  import Icon from "@iconify/svelte";
  import * as m from '$lib/paraglide/messages.js';

  let {
    tournament = $bindable(),
    playerInfo,
    isOrganizer,
    actionLoading,
    doAction,
    loadPlayerNames,
  }: {
    tournament: Tournament;
    playerInfo: Record<string, { name: string; nickname: string | null; vekn: string | null }>;
    isOrganizer: boolean;
    actionLoading: boolean;
    doAction: (action: string, body?: any) => Promise<void>;
    loadPlayerNames: () => Promise<void>;
  } = $props();

  let error = $state<string | null>(null);
  let swapSource: { round: number; table: number; seat: number; playerUid: string } | null = $state(null);
  let showCancelConfirm = $state(false);
  let showScoreDetails = $state(false);
  let scoreSaving = $state<number | null>(null);
  let overrideTable_ = $state<number | null>(null);
  let overrideComment = $state("");
  let overrideSaving = $state(false);
  let seatTargetTable = $state<number | null>(null);
  let expandedRounds = $state<Set<number>>(new Set());

  // Auto-expand current round
  $effect(() => {
    if (tournament.rounds.length > 0) {
      const lastIdx = tournament.rounds.length - 1;
      if (tournament.state === "Playing") {
        expandedRounds = new Set([lastIdx]);
      } else if (expandedRounds.size === 0) {
        expandedRounds = new Set([lastIdx]);
      }
    }
  });

  function toggleRound(idx: number) {
    const next = new Set(expandedRounds);
    if (next.has(idx)) next.delete(idx); else next.add(idx);
    expandedRounds = next;
  }

  const currentRoundIdx = $derived(
    tournament.state === "Playing" ? tournament.rounds.length - 1 : -1
  );
  const allTablesFinished = $derived(
    tournament.rounds.length > 0 && currentRoundIdx >= 0
    && tournament.rounds[currentRoundIdx]!.every(t => t.state === "Finished")
  );

  // Seating score
  let seatingScore = $state<{ rules: number[]; minimums: number[]; mean_vps: number; mean_transfers: number } | null>(null);

  function computeSeatingScore() {
    if (!tournament.rounds.length) { seatingScore = null; return; }
    const rounds = tournament.rounds.map(round =>
      round.map(table => table.seating.map(s => s.player_uid).filter(Boolean))
    );
    seatingScore = scoreSeatingSync(rounds);
  }

  $effect(() => { computeSeatingScore(); });

  const hasR1Violation = $derived(seatingScore ? (seatingScore.rules[0] ?? 0) > 0 : false);

  const RULE_LABELS = $derived([
    m.rounds_r1(), m.rounds_r2(), m.rounds_r3(), m.rounds_r4(), m.rounds_r5(),
    m.rounds_r6(), m.rounds_r7(), m.rounds_r8(), m.rounds_r9(),
  ]);

  function scoreIssueCount(): number {
    if (!seatingScore) return 0;
    return seatingScore.rules.filter((v, i) => {
      if (i === 0) return false;
      const min = seatingScore!.minimums[i] ?? 0;
      if (i === 2 || i === 7) return v - min > 0.1;
      return v > min;
    }).length;
  }

  function scoreExpectedCount(): number {
    if (!seatingScore) return 0;
    return seatingScore.rules.filter((v, i) => {
      if (i === 0) return false;
      const min = seatingScore!.minimums[i] ?? 0;
      if (min <= 0) return false;
      if (i === 2 || i === 7) return v - min <= 0.1 && v > 0.1;
      return v > 0 && v <= min;
    }).length;
  }

  // Organizer can swap/seat on last round in Playing or Finished
  const canEditSeating = $derived(
    isOrganizer && tournament.rounds.length > 0
    && (tournament.state === "Playing" || tournament.state === "Finished")
  );

  const unseatedPlayers = $derived(
    canEditSeating
      ? tournament.players.filter(p => p.state === "Registered")
      : []
  );

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

  function startSwap(round: number, table: number, seat: number, playerUid: string) {
    if (swapSource && swapSource.round === round && swapSource.table === table && swapSource.seat === seat) {
      swapSource = null;
    } else if (swapSource && swapSource.round === round) {
      doAction("SwapSeats", {
        round,
        table1: swapSource.table,
        seat1: swapSource.seat,
        table2: table,
        seat2: seat,
      });
      swapSource = null;
    } else {
      swapSource = { round, table, seat, playerUid };
    }
  }

  async function setVp(roundIndex: number, tableIndex: number, playerUid: string, vp: number, seating: Array<{ player_uid: string; result: { vp: number } }>) {
    const scores = seating.map(s => ({
      player_uid: s.player_uid,
      vp: s.player_uid === playerUid ? vp : s.result.vp,
    }));
    scoreSaving = tableIndex;
    try {
      tournament = await setTableScore(tournament.uid, roundIndex, tableIndex, scores);
      await loadPlayerNames();
      computeSeatingScore();
    } catch (e) {
      error = e instanceof Error ? e.message : m.rounds_error_save();
    } finally {
      scoreSaving = null;
    }
  }

  async function submitOverride(roundIndex: number, tableIndex: number) {
    if (!overrideComment.trim()) return;
    overrideSaving = true;
    try {
      tournament = await tournamentAction(tournament.uid, "Override", {
        round: roundIndex,
        table: tableIndex,
        comment: overrideComment.trim(),
      });
      await loadPlayerNames();
      computeSeatingScore();
      overrideTable_ = null;
      overrideComment = "";
    } catch (e) {
      error = e instanceof Error ? e.message : m.override_error();
    } finally {
      overrideSaving = false;
    }
  }

  async function removeOverride(roundIndex: number, tableIndex: number) {
    overrideSaving = true;
    try {
      tournament = await tournamentAction(tournament.uid, "Unoverride", {
        round: roundIndex,
        table: tableIndex,
      });
      await loadPlayerNames();
      computeSeatingScore();
    } catch (e) {
      error = e instanceof Error ? e.message : m.override_remove_error();
    } finally {
      overrideSaving = false;
    }
  }

  function cancelRound() {
    showCancelConfirm = false;
    doAction("CancelRound");
  }

  function isCurrentRound(idx: number): boolean {
    return idx === currentRoundIdx;
  }
</script>

<div class="space-y-4">
  {#if error}
    <div class="bg-crimson-900/20 border border-crimson-800 rounded-lg p-3">
      <p class="text-crimson-300 text-sm">{error}</p>
    </div>
  {/if}

  {#if tournament.rounds.length === 0}
    <p class="text-ash-400">{m.rounds_no_rounds()}</p>
  {:else}
    <!-- Current round controls -->
    {#if isOrganizer && currentRoundIdx >= 0}
      <div class="flex items-center justify-between flex-wrap gap-2">
        <div class="flex items-center gap-3">
          <p class="text-ash-400">{m.rounds_round_in_progress({ n: String(currentRoundIdx + 1) })}</p>
          {#if seatingScore}
            {#if hasR1Violation}
              <button
                onclick={() => showScoreDetails = !showScoreDetails}
                class="px-2 py-0.5 text-xs rounded-full bg-crimson-900/60 text-crimson-300 font-medium"
              >{m.rounds_seating_invalid()}</button>
            {:else}
              {@const issues = scoreIssueCount()}
              {@const expected = scoreExpectedCount()}
              <button
                onclick={() => showScoreDetails = !showScoreDetails}
                class="px-2 py-0.5 text-xs rounded-full {issues === 0 ? 'bg-emerald-900/60 text-emerald-300' : 'bg-amber-900/60 text-amber-300'}"
              >
                {#if issues === 0 && expected === 0}{m.rounds_seating_perfect()}
                {:else if issues === 0}{m.rounds_seating_ok({ count: String(expected) })}
                {:else}{m.rounds_seating_issues({ count: String(issues) })}{/if}
              </button>
            {/if}
          {/if}
        </div>
        <div class="flex gap-2">
          <button
            onclick={() => doAction("AddTable")}
            disabled={actionLoading}
            class="px-3 py-1.5 text-sm text-ash-300 bg-ash-800 hover:bg-ash-700 rounded-lg transition-colors"
          >
            <Icon icon="lucide:plus-square" class="w-4 h-4 inline mr-1" />{m.rounds_add_table()}
          </button>
          <button
            onclick={() => showCancelConfirm = true}
            disabled={actionLoading}
            class="px-3 py-1.5 text-sm text-crimson-400 hover:text-crimson-300 border border-crimson-800 hover:border-crimson-700 rounded-lg transition-colors"
          >{m.rounds_cancel_round()}</button>
          <button
            onclick={() => doAction("FinishRound")}
            disabled={actionLoading || !allTablesFinished}
            title={allTablesFinished ? m.rounds_end_round_ready() : m.rounds_end_round_hint()}
            class="px-4 py-2 text-sm font-medium text-bone-100 bg-amber-700 hover:bg-amber-600 disabled:bg-ash-700 disabled:text-ash-500 rounded-lg transition-colors"
          >{m.rounds_end_round()}</button>
        </div>
      </div>

      <!-- Score details panel -->
      {#if showScoreDetails && seatingScore}
        <div class="bg-ash-900/50 rounded-lg p-4 text-sm space-y-1">
          {#each RULE_LABELS as label, i}
            {@const val = seatingScore.rules[i] ?? 0}
            {@const min = seatingScore.minimums[i] ?? 0}
            {@const isStddev = i === 2 || i === 7}
            {@const isR1 = i === 0}
            {@const atMinimum = isStddev ? val - min <= 0.1 : val <= min}
            {@const isZero = isStddev ? val < 0.1 : val === 0}
            {@const displayVal = isStddev ? val.toFixed(2) : String(val)}
            <div class="flex items-center gap-2">
              {#if isR1 && val > 0}
                <span class="text-crimson-400">!!</span>
                <span class="text-crimson-300 font-medium">{label}:</span>
                <span class="text-crimson-400">{displayVal}</span>
              {:else if isZero}
                <span class="text-emerald-400">✓</span>
                <span class="text-ash-300">{label}:</span>
                <span class="text-ash-400">{displayVal}</span>
              {:else if atMinimum && min > 0}
                <span class="text-ash-500">—</span>
                <span class="text-ash-400">{label}:</span>
                <span class="text-ash-500">{displayVal}</span>
                <span class="text-ash-600 text-xs">{m.rounds_unavoidable()}</span>
              {:else}
                <span class="text-amber-400">✗</span>
                <span class="text-ash-300">{label}:</span>
                <span class="text-amber-400">{displayVal}</span>
                {#if min > 0}
                  <span class="text-ash-600 text-xs">(min: {isStddev ? min.toFixed(2) : String(min)})</span>
                {/if}
              {/if}
            </div>
          {/each}
        </div>
      {/if}

      <!-- Cancel round confirmation -->
      {#if showCancelConfirm}
        <div class="bg-crimson-900/20 border border-crimson-800 rounded-lg p-4 space-y-3">
          <p class="text-crimson-300 text-sm font-medium">{m.rounds_cancel_title()}</p>
          <p class="text-ash-400 text-sm">{m.rounds_cancel_msg()}</p>
          <div class="flex gap-2">
            <button
              onclick={cancelRound}
              disabled={actionLoading}
              class="px-4 py-2 text-sm font-medium text-bone-100 bg-crimson-700 hover:bg-crimson-600 disabled:bg-ash-700 rounded-lg transition-colors"
            >{m.rounds_cancel_yes()}</button>
            <button
              onclick={() => showCancelConfirm = false}
              class="px-4 py-2 text-sm text-ash-300 bg-ash-800 hover:bg-ash-700 rounded-lg transition-colors"
            >{m.rounds_cancel_keep()}</button>
          </div>
        </div>
      {/if}

    {/if}

    <!-- Swap hint -->
    {#if swapSource}
      <div class="bg-amber-900/20 border border-amber-800 rounded-lg p-3 flex items-center justify-between">
        <p class="text-amber-300 text-sm">
          {m.rounds_swap_hint({ name: seatDisplay(swapSource.playerUid) })}
        </p>
        <button onclick={() => swapSource = null} class="text-ash-400 hover:text-ash-200 text-sm">{m.common_cancel()}</button>
      </div>
    {/if}

    <!-- Not seated players (outside header, visible in Playing and Finished) -->
    {#if unseatedPlayers.length > 0}
      <div class="bg-amber-900/10 border border-amber-800/50 rounded-lg p-3">
        <p class="text-xs text-amber-400 mb-2">{m.rounds_not_seated()}</p>
        <div class="flex flex-wrap gap-2">
          {#each unseatedPlayers as player}
            {@const puid = player.user_uid ?? ""}
            <span class="inline-flex items-center gap-1 px-2 py-1 text-sm bg-ash-800 rounded text-ash-200">
              {seatDisplay(puid)}
            </span>
          {/each}
        </div>
      </div>
    {/if}

    {#each tournament.rounds as round, r}
      {@const isCurrent = isCurrentRound(r)}
      {@const isEditable = canEditSeating}
      {@const isExpanded = expandedRounds.has(r)}
      <div class="bg-ash-900/30 rounded-lg border border-ash-800">
        <button
          onclick={() => toggleRound(r)}
          class="w-full px-4 py-3 flex items-center justify-between text-left"
        >
          <div class="flex items-center gap-2">
            <Icon icon={isExpanded ? "lucide:chevron-down" : "lucide:chevron-right"} class="w-4 h-4 text-ash-500" />
            <span class="text-sm font-medium {isCurrent ? 'text-bone-100' : 'text-ash-300'}">
              {m.rounds_round_n({ n: String(r + 1) })}
            </span>
            {#if tournament.state === "Playing" && isCurrent}
              <span class="text-xs px-2 py-0.5 rounded bg-amber-900/60 text-amber-300">{m.rounds_in_progress()}</span>
            {/if}
          </div>
          <span class="text-xs text-ash-500">{m.rounds_table_count({ count: String(round.length) })}</span>
        </button>

        {#if isExpanded}
          <div class="px-4 pb-4 space-y-3">
            {#each round as table, i}
              <div class="bg-ash-900/50 rounded-lg p-4">
                <div class="flex items-center justify-between mb-2">
                  <div class="flex items-center gap-2">
                    <h3 class="text-sm font-medium text-bone-100">{m.rounds_table_n({ n: String(i + 1) })}</h3>
                    {#if table.seating.length < 4 || table.seating.length > 5}
                      <span class="text-xs text-amber-400">{m.rounds_n_players({ count: String(table.seating.length) })}</span>
                    {/if}
                  </div>
                  <div class="flex items-center gap-2">
                    <span class="text-xs px-2 py-0.5 rounded {table.state === 'Finished' ? 'bg-emerald-900/60 text-emerald-300' : table.state === 'Invalid' ? 'bg-crimson-900/60 text-crimson-300' : 'bg-amber-900/60 text-amber-300'}">
                      {table.state}
                    </span>
                    {#if isEditable && r === tournament.rounds.length - 1 && table.seating.length === 0}
                      <button
                        onclick={() => doAction("RemoveTable", { table: i })}
                        class="p-1 text-crimson-400 hover:text-crimson-300 transition-colors"
                        title={m.rounds_remove_empty_table()}
                      >
                        <Icon icon="lucide:x" class="w-4 h-4" />
                      </button>
                    {/if}
                  </div>
                </div>
                <div class="divide-y divide-ash-800">
                  {#each table.seating as seat, j}
                    {@const isSwapSource = isEditable && swapSource?.round === r && swapSource?.table === i && swapSource?.seat === j}
                    {@const tVps = table.seating.map(s => s.result.vp)}
                    {@const tGws = computeGwLocal(tVps)}
                    {@const tTps = computeTpLocal(table.seating.length, tVps)}
                    <div class="py-1.5 flex items-center justify-between text-sm">
                      {#if isEditable}
                        <button
                          onclick={() => startSwap(r, i, j, seat.player_uid)}
                          class="text-left transition-colors {isSwapSource ? 'text-amber-300 font-medium' : 'text-ash-300 hover:text-ash-100'}"
                          title={isSwapSource ? "Click to deselect" : "Click to swap this player"}
                        >
                          <Icon icon={isSwapSource ? "lucide:arrow-left-right" : "lucide:grip-vertical"} class="w-3.5 h-3.5 inline mr-1.5 text-ash-500" />
                          {seatDisplay(seat.player_uid)}
                        </button>
                      {:else}
                        <span class="text-ash-300">{seatDisplay(seat.player_uid)}</span>
                      {/if}
                      <div class="flex items-center gap-2">
                        <span class="text-ash-400 text-xs">VP:</span>
                        {#if isOrganizer}
                          <select
                            class="bg-ash-800 text-bone-100 text-xs rounded px-1.5 py-0.5 border border-ash-700"
                            disabled={scoreSaving === i}
                            value={seat.result.vp}
                            onchange={(e) => setVp(r, i, seat.player_uid, parseFloat((e.target as HTMLSelectElement).value), table.seating)}
                          >
                            {#each vpOptions(table.seating.length, isOrganizer) as v}
                              <option value={v}>{v}</option>
                            {/each}
                          </select>
                        {:else}
                          <span class="text-bone-100 text-xs">{seat.result.vp}</span>
                        {/if}
                        <span class="text-ash-500 text-xs">{tGws[j]}GW {tTps[j]}TP</span>
                        {#if isEditable}
                          <button
                            onclick={() => doAction("UnseatPlayer", { player_uid: seat.player_uid })}
                            class="p-0.5 text-ash-500 hover:text-crimson-400 transition-colors"
                            title={m.rounds_unseat_title()}
                          >
                            <Icon icon="lucide:user-minus" class="w-3.5 h-3.5" />
                          </button>
                        {/if}
                      </div>
                    </div>
                  {/each}
                </div>
                <!-- Override controls -->
                {#if isOrganizer && (table.state === 'Invalid' || table.state === 'In Progress')}
                  {#if overrideTable_ === i}
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
                          onclick={() => submitOverride(r, i)}
                          disabled={overrideSaving || !overrideComment.trim()}
                          class="px-3 py-1 text-xs font-medium text-bone-100 bg-amber-700 hover:bg-amber-600 disabled:bg-ash-700 rounded transition-colors"
                        >{overrideSaving ? m.common_saving() : m.override_save()}</button>
                      </div>
                    </div>
                  {:else}
                    <div class="mt-2 flex justify-end">
                      <button
                        onclick={() => { overrideTable_ = i; overrideComment = ""; }}
                        class="px-2 py-1 text-xs text-amber-400 hover:text-amber-300 transition-colors"
                        title="Override table result as judge"
                      >
                        <Icon icon="lucide:shield-check" class="w-3.5 h-3.5 inline mr-1" />{m.override_btn()}
                      </button>
                    </div>
                  {/if}
                {/if}
                {#if isOrganizer && table.override}
                  <div class="mt-2 pt-2 border-t border-ash-800 flex items-center justify-between">
                    <span class="text-xs text-amber-400">
                      <Icon icon="lucide:shield-check" class="w-3.5 h-3.5 inline mr-1" />
                      {m.override_overridden({ comment: table.override.comment })}
                    </span>
                    <button
                      onclick={() => removeOverride(r, i)}
                      disabled={overrideSaving}
                      class="px-2 py-1 text-xs text-ash-500 hover:text-crimson-400 transition-colors"
                    >{m.override_remove()}</button>
                  </div>
                {/if}
                <!-- Seat a player -->
                {#if isEditable && unseatedPlayers.length > 0}
                  <div class="mt-2 pt-2 border-t border-ash-800">
                    {#if seatTargetTable === i}
                      <div class="flex flex-wrap gap-1">
                        {#each unseatedPlayers as player}
                          {@const puid = player.user_uid ?? ""}
                          <button
                            onclick={() => { doAction("SeatPlayer", { player_uid: puid, table: i, seat: table.seating.length }); seatTargetTable = null; }}
                            class="px-2 py-1 text-xs bg-ash-800 hover:bg-emerald-900/60 text-ash-300 hover:text-emerald-300 rounded transition-colors"
                          >{seatDisplay(puid)}</button>
                        {/each}
                        <button onclick={() => seatTargetTable = null} class="px-2 py-1 text-xs text-ash-500 hover:text-ash-300">{m.common_cancel()}</button>
                      </div>
                    {:else}
                      <button
                        onclick={() => seatTargetTable = i}
                        class="text-xs text-ash-500 hover:text-emerald-400 transition-colors"
                      >
                        <Icon icon="lucide:plus" class="w-3.5 h-3.5 inline mr-1" />{m.rounds_seat_player()}
                      </button>
                    {/if}
                  </div>
                {/if}
              </div>
            {/each}
            {#if isEditable && r === tournament.rounds.length - 1}
              <button
                onclick={() => doAction("AddTable")}
                disabled={actionLoading}
                class="px-3 py-1.5 text-sm text-ash-300 bg-ash-800 hover:bg-ash-700 rounded-lg transition-colors"
              >
                <Icon icon="lucide:plus-square" class="w-4 h-4 inline mr-1" />{m.rounds_add_table()}
              </button>
            {/if}
          </div>
        {/if}
      </div>
    {/each}
  {/if}
</div>
