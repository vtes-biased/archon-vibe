<script lang="ts">
  import type { Tournament, Table, Sanction } from "$lib/types";
  import { tournamentAction, setTableScore } from "$lib/api";
  import { scoreSeatingSync, computePlayerIssuesSync } from "$lib/engine";
  import SanctionIndicator from "$lib/components/SanctionIndicator.svelte";
  import SeatingSortable from "$lib/components/SeatingSortable.svelte";
  import TournamentSanctionModal from "$lib/components/TournamentSanctionModal.svelte";
  import { ChevronDown, ChevronRight, SquarePlus, GripVertical, X, UserMinus, TriangleAlert, ShieldCheck, Plus, Printer } from "lucide-svelte";
  import TimerDisplay from "./TimerDisplay.svelte";
  import { seatDisplay as seatDisplayUtil, vpOptions, computeGwLocal, computeTpLocal, translateTableState, resolveTableLabel } from "$lib/tournament-utils";
  import * as m from '$lib/paraglide/messages.js';

  let {
    tournament = $bindable(),
    playerInfo,
    isOrganizer,
    actionLoading,
    doAction,
    loadPlayerNames,
    tournamentSanctions,
  }: {
    tournament: Tournament;
    playerInfo: Record<string, { name: string; nickname: string | null; vekn: string | null }>;
    isOrganizer: boolean;
    actionLoading: boolean;
    doAction: (action: string, body?: any) => Promise<void>;
    loadPlayerNames: () => Promise<void>;
    tournamentSanctions?: Sanction[];
  } = $props();

  // Sanction modal state
  let sanctionTarget = $state<{ uid: string; name: string; round: number } | null>(null);

  // Build a map of player uid → their sanctions
  const playerSanctionsMap = $derived.by(() => {
    const map: Record<string, Sanction[]> = {};
    for (const s of tournamentSanctions ?? []) {
      (map[s.user_uid] ??= []).push(s);
    }
    return map;
  });

  let error = $state<string | null>(null);
  let showCancelConfirm = $state(false);

  // Alter seating mode
  let alterMode = $state(false);
  let alterTables = $state<string[][]>([]);
  let alterRoundIdx = $state(-1);
  let playerIssues = $state<Map<string, { level: number; message: string }>>(new Map());
  let showScoreDetails = $state(false);
  let scoreSaving = $state<number | null>(null);
  let overrideTable_ = $state<number | null>(null);
  let overrideComment = $state("");
  let overrideSaving = $state(false);
  let seatTargetTable = $state<number | null>(null);
  let expandedRounds = $state<Set<number>>(new Set());

  // Auto-expand current round
  $effect(() => {
    if (tournament.rounds!.length > 0) {
      const lastIdx = tournament.rounds!.length - 1;
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
    tournament.state === "Playing" && !tournament.finals ? tournament.rounds!.length - 1 : -1
  );
  // Seating score
  let seatingScore = $state<{ rules: number[]; minimums: number[]; mean_vps: number; mean_transfers: number } | null>(null);

  function computeSeatingScore() {
    if (!tournament.rounds!.length) { seatingScore = null; return; }
    const rounds = tournament.rounds!.map(round =>
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
  const hasR1Issue = $derived(
    Array.from(playerIssues.values()).some(i => i.level === 0)
  );

  const canEditSeating = $derived(
    isOrganizer && tournament.rounds!.length > 0
    && (tournament.state === "Playing" || tournament.state === "Finished" || tournament.state === "Waiting")
  );

  const unseatedPlayers = $derived(
    canEditSeating
      ? (tournament.players ?? []).filter(p => p.state === "Registered")
      : []
  );

  // Players sitting out this round (Checked-in while tournament is Playing = stagger sit-out)
  const sittingOutPlayers = $derived(
    tournament.state === "Playing"
      ? (tournament.players ?? []).filter(p => p.state === "Checked-in")
      : []
  );

  function seatDisplay(uid: string): string {
    return seatDisplayUtil(uid, playerInfo);
  }

  function enterAlterMode(roundIdx: number) {
    const round = tournament.rounds![roundIdx]!;
    alterTables = round.map(t => t.seating.map(s => s.player_uid));
    alterRoundIdx = roundIdx;
    alterMode = true;
    recomputeIssues();
  }

  function cancelAlterMode() {
    alterMode = false;
    alterTables = [];
    alterRoundIdx = -1;
    playerIssues = new Map();
    computeSeatingScore();
  }

  async function saveAlterSeating() {
    await doAction("AlterSeating", { round: alterRoundIdx, seating: alterTables });
    cancelAlterMode();
  }

  function recomputeIssues() {
    const allRounds = tournament.rounds!.map((round, r) =>
      r === alterRoundIdx ? alterTables : round.map(t => t.seating.map(s => s.player_uid))
    );
    seatingScore = scoreSeatingSync(allRounds);
    const issues = computePlayerIssuesSync(allRounds);
    if (!issues) { playerIssues = new Map(); return; }
    // Build per-player map keeping highest-priority issue (lowest rule number)
    const map = new Map<string, { level: number; message: string }>();
    const ruleLabels = [
      m.rounds_r1(), m.rounds_r2(), m.rounds_r3(), m.rounds_r4(), m.rounds_r5(),
      m.rounds_r6(), m.rounds_r7(), m.rounds_r8(), m.rounds_r9(),
    ];
    for (const issue of issues) {
      for (const uid of issue.players) {
        const existing = map.get(uid);
        if (!existing || issue.rule < existing.level) {
          map.set(uid, { level: issue.rule, message: ruleLabels[issue.rule] ?? `R${issue.rule + 1}` });
        }
      }
    }
    playerIssues = map;
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

  function esc(s: string): string {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function printSeatHtml(uid: string): string {
    const info = playerInfo[uid];
    if (!info) return esc(uid);
    const name = esc(info.nickname || info.name);
    return info.vekn
      ? `${name} <span style="color:#888;font-size:10pt">(${esc(info.vekn)})</span>`
      : name;
  }

  function printRound(r: number) {
    const round = tournament.rounds![r]!;
    const title = esc(tournament.name || m.tournament_fallback_title());
    const roundLabel = esc(m.rounds_round_n({ n: String(r + 1) }));
    let tablesHtml = '';
    for (let i = 0; i < round.length; i++) {
      const table = round[i]!;
      let rows = '';
      for (let j = 0; j < table.seating.length; j++) {
        const s = table.seating[j]!;
        const bg = j % 2 === 0 ? '#f5f5f5' : 'transparent';
        rows += `<div style="padding:3px 8px 3px 12px;background:${bg};border-bottom:1px solid #ddd"><span style="display:inline-block;width:20px;text-align:right;font-weight:bold;margin-right:6px">${j + 1}.</span>${printSeatHtml(s.player_uid)}</div>`;
      }
      tablesHtml += `<div style="break-inside:avoid;display:inline-block;width:100%;margin-bottom:16px"><div style="font-size:14pt;font-weight:bold;background:#e8e8e8;padding:4px 8px">${esc(resolveTableLabel(tournament.table_rooms, i) ?? m.rounds_table_n({ n: String(i + 1) }))}</div>${rows}</div>`;
    }
    const css = [
      `body{font-family:"Segoe UI","Helvetica Neue",Arial,sans-serif;font-size:12pt;color:#000;margin:0;padding:0;line-height:1.4}`,
      `@page{margin:15mm}`,
      `.cols{column-count:2;column-gap:24px}`,
      `.footer{position:fixed;bottom:0;width:100%;text-align:right;font-size:9pt;color:#999}`,
    ].join('');
    const html = `<!DOCTYPE html><html><head><meta charset="utf-8"><title>${title} — ${roundLabel}</title><style>${css}</style></head><body>`
      + `<div style="font-size:20pt;font-weight:bold">${title}</div>`
      + `<div style="font-size:16pt;color:#444;margin-top:4px">${roundLabel}</div>`
      + `<hr style="border:none;border-top:2px solid #000;margin:8px 0 16px">`
      + `<div class="cols">${tablesHtml}</div>`
      + `<div class="footer">${title}</div>`
      + `<script>window.onload=()=>window.print()<\/script></body></html>`;
    const w = window.open('', '_blank');
    if (w) { w.document.write(html); w.document.close(); }
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

  <!-- Global Timer -->
  {#if (tournament.round_time ?? 0) > 0 && tournament.state === "Playing"}
    <div class="bg-ash-900/50 rounded-lg p-4 flex justify-center">
      <TimerDisplay {tournament} {isOrganizer} />
    </div>
  {/if}

  {#if tournament.rounds!.length === 0}
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
                class="px-2 py-0.5 text-xs rounded-full {issues === 0 ? 'badge-emerald' : 'badge-amber'}"
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
            <SquarePlus class="w-4 h-4 inline mr-1" />{m.rounds_add_table()}
          </button>
          <button
            onclick={() => showCancelConfirm = true}
            disabled={actionLoading}
            class="px-3 py-1.5 text-sm text-crimson-400 hover:text-crimson-300 border border-crimson-800 hover:border-crimson-700 rounded-lg transition-colors"
          >{m.rounds_cancel_round()}</button>
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
              class="px-4 py-2 text-sm font-medium text-white bg-crimson-700 hover:bg-crimson-600 disabled:bg-ash-800 disabled:text-ash-500 rounded-lg transition-colors"
            >{m.rounds_cancel_yes()}</button>
            <button
              onclick={() => showCancelConfirm = false}
              class="px-4 py-2 text-sm text-ash-300 bg-ash-800 hover:bg-ash-700 rounded-lg transition-colors"
            >{m.rounds_cancel_keep()}</button>
          </div>
        </div>
      {/if}

    {/if}

    <!-- Not seated players (alter mode, visible in Playing and Finished) -->
    {#if unseatedPlayers.length > 0}
      <div class="banner-amber border rounded-lg p-3">
        <p class="text-xs mb-2">{m.rounds_not_seated()}</p>
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
    <!-- Sitting out players (stagger rounds) -->
    {#if sittingOutPlayers.length > 0}
      <div class="bg-sky-900/20 border border-sky-800/40 rounded-lg p-3">
        <p class="text-xs text-sky-300 mb-2">{m.rounds_sitting_out()}</p>
        <div class="flex flex-wrap gap-2">
          {#each sittingOutPlayers as player}
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
        <div class="flex items-center">
          <button
            onclick={() => toggleRound(r)}
            class="flex-1 px-4 py-3 flex items-center justify-between text-left"
          >
            <div class="flex items-center gap-2">
              {#if isExpanded}<ChevronDown class="w-4 h-4 text-ash-500" />{:else}<ChevronRight class="w-4 h-4 text-ash-500" />{/if}
              <span class="text-sm font-medium {isCurrent ? 'text-bone-100' : 'text-ash-300'}">
                {m.rounds_round_n({ n: String(r + 1) })}
              </span>
              {#if tournament.state === "Playing" && isCurrent}
                <span class="text-xs px-2 py-0.5 rounded badge-amber">{m.rounds_in_progress()}</span>
              {/if}
            </div>
            <span class="text-xs text-ash-500">{m.rounds_table_count({ count: String(round.length) })}</span>
          </button>
          {#if isOrganizer && round.length > 0}
            <button
              onclick={() => printRound(r)}
              class="px-3 py-3 text-ash-500 hover:text-bone-100 transition-colors"
              title={m.rounds_print_seating()}
            >
              <Printer class="w-4 h-4" />
            </button>
          {/if}
        </div>

        {#if isExpanded}
          <div class="px-4 pb-4 space-y-3">
            {#if alterMode && r === alterRoundIdx}
              <!-- In-place alter seating mode -->
              <p class="text-sm text-ash-300">{m.rounds_alter_hint()}</p>
              {#if round.some(t => t.seating.some(s => s.result.vp > 0))}
                <p class="text-sm text-amber-400">{m.rounds_alter_scores_warning()}</p>
              {/if}
              <SeatingSortable
                bind:tables={alterTables}
                {playerInfo}
                {playerIssues}
                isFinals={false}
                tableRooms={tournament.table_rooms}
                onchange={recomputeIssues}
              />
              {#if hasR1Issue}
                <p class="text-sm text-crimson-400">{m.rounds_alter_r1_error()}</p>
              {/if}
              <div class="flex gap-2">
                <button
                  onclick={saveAlterSeating}
                  disabled={actionLoading || hasR1Issue}
                  class="px-4 py-2 text-sm font-medium btn-emerald rounded-lg transition-colors"
                >{m.rounds_save_seating()}</button>
                <button
                  onclick={cancelAlterMode}
                  class="px-4 py-2 text-sm text-ash-300 bg-ash-800 hover:bg-ash-700 rounded-lg transition-colors"
                >{m.common_cancel()}</button>
              </div>
            {:else}
            {#each round as table, i}
              <div class="bg-ash-900/50 rounded-lg p-4">
                <div class="flex items-center justify-between mb-2">
                  <div class="flex items-center gap-2">
                    <h3 class="text-sm font-medium text-bone-100">{resolveTableLabel(tournament.table_rooms, i) ?? m.rounds_table_n({ n: String(i + 1) })}</h3>
                    {#if table.seating.length < 4 || table.seating.length > 5}
                      <span class="text-xs text-amber-400">{m.rounds_n_players({ count: String(table.seating.length) })}</span>
                    {/if}
                  </div>
                  <div class="flex items-center gap-2">
                    <span class="text-xs px-2 py-0.5 rounded {table.state === 'Finished' ? 'badge-emerald' : table.state === 'Invalid' ? 'bg-crimson-900/60 text-crimson-300' : 'badge-amber'}">
                      {translateTableState(table.state)}
                    </span>
                    {#if isEditable && r === tournament.rounds!.length - 1 && table.seating.length === 0}
                      <button
                        onclick={() => doAction("RemoveTable", { table: i })}
                        class="p-1 text-crimson-400 hover:text-crimson-300 transition-colors"
                        title={m.rounds_remove_empty_table()}
                      >
                        <X class="w-4 h-4" />
                      </button>
                    {/if}
                  </div>
                </div>
                <!-- Per-table timer (organizer controls) -->
                {#if (tournament.round_time ?? 0) > 0 && tournament.state === "Playing" && r === tournament.rounds!.length - 1}
                  <div class="mb-2">
                    <TimerDisplay {tournament} {isOrganizer} tableIndex={i} />
                  </div>
                {/if}
                <div class="divide-y divide-ash-800">
                  {#each table.seating as seat, j}
                    {@const tVps = table.seating.map(s => s.result.vp)}
                    {@const tGws = computeGwLocal(tVps)}
                    {@const tTps = computeTpLocal(table.seating.length, tVps)}
                    <div class="py-1.5 flex items-center justify-between text-sm">
                      <span class="text-ash-300 inline-flex items-center gap-1">
                        {seatDisplay(seat.player_uid)}
                        {#if playerSanctionsMap[seat.player_uid]?.length}
                          <SanctionIndicator sanctions={playerSanctionsMap[seat.player_uid]!} />
                        {/if}
                      </span>
                      <div class="flex items-center gap-2">
                        <span class="text-ash-400 text-xs">VP:</span>
                        {#if isOrganizer}
                          <select
                            class="bg-ash-800 text-bone-100 text-xs rounded px-1.5 py-1.5 sm:py-0.5 border border-ash-700"
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
                            class="p-2 sm:p-0.5 text-ash-500 hover:text-crimson-400 transition-colors"
                            title={m.rounds_unseat_title()}
                          >
                            <UserMinus class="w-5 h-5 sm:w-3.5 sm:h-3.5" />
                          </button>
                        {/if}
                        {#if isOrganizer}
                          <button
                            onclick={() => sanctionTarget = { uid: seat.player_uid, name: seatDisplay(seat.player_uid), round: r }}
                            class="p-2 sm:p-0.5 text-ash-500 hover:text-amber-400 transition-colors"
                            title={m.sanction_tournament_issue_title()}
                          >
                            <TriangleAlert class="w-5 h-5 sm:w-3.5 sm:h-3.5" />
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
                          class="px-3 py-1 text-xs font-medium btn-amber rounded transition-colors"
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
                        <ShieldCheck class="w-3.5 h-3.5 inline mr-1" />{m.override_btn()}
                      </button>
                    </div>
                  {/if}
                {/if}
                {#if isOrganizer && table.override}
                  <div class="mt-2 pt-2 border-t border-ash-800 flex items-center justify-between">
                    <span class="text-xs text-amber-400">
                      <ShieldCheck class="w-3.5 h-3.5 inline mr-1" />
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
                {#if isEditable && unseatedPlayers.length > 0 && table.seating.length < 5}
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
                        <Plus class="w-3.5 h-3.5 inline mr-1" />{m.rounds_seat_player()}
                      </button>
                    {/if}
                  </div>
                {/if}
              </div>
            {/each}
            <div class="flex gap-2 flex-wrap">
              {#if isEditable && r === tournament.rounds!.length - 1}
                <button
                  onclick={() => doAction("AddTable")}
                  disabled={actionLoading}
                  class="px-3 py-1.5 text-sm text-ash-300 bg-ash-800 hover:bg-ash-700 rounded-lg transition-colors"
                >
                  <SquarePlus class="w-4 h-4 inline mr-1" />{m.rounds_add_table()}
                </button>
              {/if}
              {#if isEditable && !alterMode}
                <button
                  onclick={() => enterAlterMode(r)}
                  disabled={actionLoading}
                  class="px-3 py-1.5 text-sm text-ash-300 bg-ash-800 hover:bg-ash-700 rounded-lg transition-colors"
                >
                  <GripVertical class="w-4 h-4 inline mr-1" />{m.rounds_alter_seating()}
                </button>
              {/if}
            </div>
            {/if}
          </div>
        {/if}
      </div>
    {/each}
  {/if}
</div>

<!-- Tournament Sanction Modal -->
{#if sanctionTarget && isOrganizer}
  <TournamentSanctionModal
    {tournament}
    playerUid={sanctionTarget.uid}
    playerName={sanctionTarget.name}
    currentRound={sanctionTarget.round}
    onClose={() => sanctionTarget = null}
  />
{/if}
