<script lang="ts">
  import { toUserMessage } from '$lib/errors';
  import type { Tournament, Table, Sanction } from "$lib/types";
  import { tournamentAction } from "$lib/tournament-actions";
  import { timerAddTime } from "$lib/api";
  import { scoreSeatingSync, computePlayerIssuesSync, previewScoresSync, checkTableVpsSync, type TournamentEventType } from "$lib/engine";
  import { vpIssueText } from "$lib/vpIssue";
  import SanctionIndicator from "$lib/components/SanctionIndicator.svelte";
  import SeatingSortable from "$lib/components/SeatingSortable.svelte";
  import TournamentSanctionModal from "$lib/components/TournamentSanctionModal.svelte";
  import SanctionListModal from "$lib/components/SanctionListModal.svelte";
  import Button from '$lib/components/Button.svelte';
  import { ChevronDown, ChevronRight, SquarePlus, ArrowRightLeft, X, UserMinus, TriangleAlert, ShieldCheck, Plus, Printer, Lock, Ban, RotateCcw, Users, Settings2 } from "@lucide/svelte";
  import TimerDisplay from "./TimerDisplay.svelte";
  import VpInput from "./VpInput.svelte";
  import { seatDisplay as seatDisplayUtil, vpOptions, translateTableState, resolveTableLabel, type PlayerInfoMap } from "$lib/tournament-utils";
  import * as m from '$lib/paraglide/messages.js';
  import { showToast } from "$lib/stores/toast.svelte";

  let {
    tournament = $bindable(),
    playerInfo,
    isOrganizer,
    actionLoading,
    doAction,
    loadPlayerNames,
    tournamentSanctions,
    setVp,
    scoreSaving,
    scoreSavingSeat,
  }: {
    tournament: Tournament;
    playerInfo: PlayerInfoMap;
    isOrganizer: boolean;
    actionLoading: boolean;
    doAction: (action: TournamentEventType, body?: any) => Promise<string | null>;
    loadPlayerNames: () => Promise<void>;
    tournamentSanctions?: Sanction[];
    setVp: (roundIndex: number, tableIndex: number, playerUid: string, vp: number, seating: Array<{ player_uid: string; result: { vp: number } }>) => Promise<void>;
    scoreSaving: number | null;
    scoreSavingSeat: string | null;
  } = $props();

  // Sanction modal state
  let sanctionTarget = $state<{ uid: string; name: string; round: number } | null>(null);
  // Sanction list modal state (view + cancel issued sanctions)
  let sanctionListTarget = $state<{ uid: string; name: string } | null>(null);

  // Build a map of player uid → their sanctions
  const playerSanctionsMap = $derived.by(() => {
    const map: Record<string, Sanction[]> = {};
    for (const s of tournamentSanctions ?? []) {
      (map[s.user_uid] ??= []).push(s);
    }
    return map;
  });

  // Proxy (non-competing) seats: read-only badge here; the toggle lives in PlayersTab.
  const nonCompetingUids = $derived(
    new Set((tournament.players ?? []).filter(p => p.non_competing && p.user_uid).map(p => p.user_uid!))
  );

  let error = $state<string | null>(null);
  // Which round index is pending cancel confirmation (null = none). The engine now
  // soft-cancels any non-last round and hard-removes the last, so any round can be cancelled.
  let cancelConfirmRound = $state<number | null>(null);
  // Which fully-cancelled round is pending restore confirmation (null = none).
  let restoreConfirmRound = $state<number | null>(null);

  // Alter seating mode
  let alterMode = $state(false);
  let alterTables = $state<string[][]>([]);
  let alterRoundIdx = $state(-1);
  let playerIssues = $state<Map<string, { level: number; message: string }>>(new Map());
  let showScoreDetails = $state(false);
  let overrideTable_ = $state<number | null>(null);
  let overrideComment = $state("");
  let overrideSaving = $state(false);
  // "round:table" key — the pool can now open on any live round, so a bare
  // table index would collide across expanded rounds.
  let seatTargetTable = $state<string | null>(null);
  let expandedRounds = $state<Set<number>>(new Set());

  // Auto-expand in-progress rounds. Cancelled rounds stay discreet (collapsed) —
  // they're not "in progress"; the organizer expands one deliberately to restore it.
  $effect(() => {
    if (tournament.rounds!.length > 0) {
      if (tournament.state === "Playing") {
        const inProgress = new Set<number>();
        for (let i = 0; i < tournament.rounds!.length; i++) {
          if (tournament.rounds![i]!.some(t => t.state !== "Finished" && t.state !== "Cancelled")) {
            inProgress.add(i);
          }
        }
        expandedRounds = inProgress.size > 0 ? inProgress : new Set([tournament.rounds!.length - 1]);
      } else if (expandedRounds.size === 0) {
        expandedRounds = new Set([tournament.rounds!.length - 1]);
      }
    }
  });

  const inProgressRoundCount = $derived(
    tournament.rounds?.filter(r => r.some(t => t.state !== "Finished")).length ?? 0
  );
  const hasParallelRounds = $derived(inProgressRoundCount > 1);

  function toggleRound(idx: number) {
    const next = new Set(expandedRounds);
    if (next.has(idx)) next.delete(idx); else next.add(idx);
    expandedRounds = next;
  }

  // One-table-at-a-time scoring: only the expanded table shows its VP chip grid;
  // others stay compact (read-only scores). You never score two tables at once,
  // so this is an accordion — opening one collapses the rest. Keyed "round:table".
  let scoringTable = $state<string | null>(null);
  function toggleScoring(r: number, i: number) {
    const key = `${r}:${i}`;
    scoringTable = scoringTable === key ? null : key;
  }

  const currentRoundIdx = $derived(
    tournament.state === "Playing" && !tournament.finals ? tournament.rounds!.length - 1 : -1
  );

  function isRoundInProgress(idx: number): boolean {
    const round = tournament.rounds![idx];
    return round ? round.some(t => t.state !== "Finished") : false;
  }

  function roundProgress(idx: number): { done: number; total: number } {
    const round = tournament.rounds![idx];
    if (!round) return { done: 0, total: 0 };
    return { done: round.filter(t => t.state === "Finished").length, total: round.length };
  }

  function isRoundAllFinished(idx: number): boolean {
    const round = tournament.rounds![idx];
    return round ? round.length > 0 && round.every(t => t.state === "Finished") : false;
  }
  // A round still needs ending while it holds a seated player who is Playing and hasn't
  // moved on to a later round — i.e. FinishRound would actually release someone. Players
  // re-seated into a later parallel round are excluded so an already-superseded round stops
  // offering an End button; ended rounds (players no longer Playing) drop out too.
  function isRoundEndable(idx: number): boolean {
    if (tournament.state !== "Playing" || tournament.finals) return false;
    const round = tournament.rounds![idx];
    if (!round || round.length === 0) return false;
    const playing = new Set((tournament.players ?? []).filter(p => p.state === "Playing").map(p => p.user_uid));
    const laterSeated = new Set<string>();
    for (let i = idx + 1; i < tournament.rounds!.length; i++)
      for (const t of tournament.rounds![i]!) for (const s of t.seating) laterSeated.add(s.player_uid);
    return round.some(t => t.seating.some(s => playing.has(s.player_uid) && !laterSeated.has(s.player_uid)));
  }
  // Seating score
  let seatingScore = $state<{ rules: number[]; minimums: number[]; mean_vps: number; mean_transfers: number } | null>(null);

  function computeSeatingScore() {
    if (!tournament.rounds!.length) { seatingScore = null; return; }
    // Skip Cancelled tables — a voided round must not skew the seating score.
    const rounds = tournament.rounds!.map(round =>
      round.filter(t => t.state !== 'Cancelled').map(table => table.seating.map(s => s.player_uid).filter(Boolean))
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

  // Tables with 1-3 players are illegal (VEKN: tables seat 4 or 5); empty tables are a draft workspace
  const hasUndersizedTable = $derived(
    alterTables.some(t => t.length > 0 && t.length < 4)
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
    return seatDisplayUtil(uid, playerInfo, tournament.online);
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

  // Draft-only: empty tables left at save time are dropped by the engine
  function addTableInAlter() {
    alterTables = [...alterTables, []];
  }

  function recomputeIssues() {
    const allRounds = tournament.rounds!.map((round, r) =>
      r === alterRoundIdx ? alterTables : round.filter(t => t.state !== 'Cancelled').map(t => t.seating.map(s => s.player_uid))
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


  // Folded-row +time chips: extra time is granted mid-play from the table
  // list without unfolding the Manage panel. Cap mirrors TimerDisplay/server.
  let addTimeLoading = $state(false);
  async function addTableTime(tableIdx: number, secs: number) {
    addTimeLoading = true;
    try {
      await timerAddTime(tournament.uid, String(tableIdx), secs);
    } catch { /* error toast shown by apiRequest */ } finally {
      addTimeLoading = false;
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
      error = toUserMessage(e, m.override_error());
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
      error = toUserMessage(e, m.override_remove_error());
    } finally {
      overrideSaving = false;
    }
  }

  function cancelRound(roundIdx: number) {
    cancelConfirmRound = null;
    doAction("CancelRound", { round: roundIdx });
  }

  // A round is cancellable while the tournament is Playing (no finals) and the round
  // isn't already fully cancelled. Any round qualifies — the engine soft-cancels
  // non-last rounds and hard-removes the last.
  function isRoundCancellable(roundIdx: number): boolean {
    if (tournament.state !== "Playing" || tournament.finals) return false;
    const round = tournament.rounds?.[roundIdx];
    return !!round && round.some(t => t.state !== "Cancelled");
  }

  // Players seated in the round who can't be reinstated, by display name. Mirrors
  // the engine's all-or-nothing rule (dropped/Finished, disqualified, or — open
  // rounds — already at cap via OTHER rounds; the still-Cancelled target round is
  // naturally excluded from the count). The engine re-checks authoritatively; this
  // only names them up front so the toast can guide the organizer.
  function restoreBlockers(roundIdx: number): string[] {
    const round = tournament.rounds?.[roundIdx];
    if (!round) return [];
    const maxRounds = tournament.max_rounds ?? 0;
    const countPlayed = (uid: string) =>
      (tournament.rounds ?? []).filter(rd => rd.some(t => t.state !== 'Cancelled' && t.seating.some(s => s.player_uid === uid))).length;
    const seated = [...new Set(round.flatMap(t => t.seating.map(s => s.player_uid)))];
    return seated
      .filter(uid => {
        const p = (tournament.players ?? []).find(pl => pl.user_uid === uid);
        if (!p) return false;
        if (p.state === 'Disqualified' || p.state === 'Finished') return true;
        return maxRounds > 0 && countPlayed(uid) >= maxRounds;
      })
      .map(uid => seatDisplay(uid));
  }

  function restoreRound(roundIdx: number) {
    restoreConfirmRound = null;
    const blockers = restoreBlockers(roundIdx);
    if (blockers.length > 0) {
      showToast({ type: 'error', message: m.rounds_restore_blocked({ players: blockers.join(', ') }) });
      return;
    }
    doAction("RestoreRound", { round: roundIdx });
  }

  // A fully-cancelled (soft-voided) round shows a Cancelled badge and a Restore
  // affordance. The last round is hard-removed on cancel, so a fully-Cancelled
  // round is always a restorable non-last soft-cancel.
  function isRoundFullyCancelled(roundIdx: number): boolean {
    const round = tournament.rounds?.[roundIdx];
    return !!round && round.length > 0 && round.every(t => t.state === "Cancelled");
  }

  // Restore mirrors the engine guard: prelim-phase only (Playing/Waiting, no finals).
  function isRoundRestorable(roundIdx: number): boolean {
    if (tournament.finals) return false;
    if (tournament.state !== "Playing" && tournament.state !== "Waiting") return false;
    return isRoundFullyCancelled(roundIdx);
  }

  function esc(s: string): string {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function printSeatHtml(uid: string): string {
    const info = playerInfo[uid];
    if (!info) return esc(uid);
    const name = esc(info.nickname || info.name);
    const base = info.vekn
      ? `${name} <span style="color:#888;font-size:10pt">(${esc(info.vekn)})</span>`
      : name;
    return nonCompetingUids.has(uid)
      ? `${base} <span style="color:#888;font-size:9pt">(${esc(m.proxy_label())})</span>`
      : base;
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
    return tournament.state === "Playing" && !tournament.finals && isRoundInProgress(idx);
  }
</script>

<div class="space-y-4">
  {#snippet cancelConfirmBox(roundIdx: number)}
    <!-- Cancelling the LAST round hard-removes it (results lost); any earlier round
         is soft-voided and restorable, so the warning differs. -->
    {@const isLastRound = roundIdx === tournament.rounds!.length - 1}
    <div class="bg-accent-soft/20 border border-accent-soft-border rounded-lg p-4 space-y-3">
      <p class="text-link-soft text-sm font-medium">{m.rounds_cancel_title()}</p>
      <p class="text-ink-muted text-sm">{isLastRound ? m.rounds_cancel_msg_last() : m.rounds_cancel_msg()}</p>
      <div class="flex gap-2">
        <Button variant="danger" size="lg" onclick={() => cancelRound(roundIdx)} disabled={actionLoading}><Ban class="w-4 h-4" aria-hidden="true" />{m.rounds_cancel_yes()}</Button>
        <Button variant="secondary" size="lg" onclick={() => cancelConfirmRound = null}>{m.rounds_cancel_keep()}</Button>
      </div>
    </div>
  {/snippet}

  {#snippet restoreConfirmBox(roundIdx: number)}
    <div class="bg-accent-soft/20 border border-accent-soft-border rounded-lg p-4 space-y-3">
      <p class="text-link-soft text-sm font-medium">{m.rounds_restore_title()}</p>
      <p class="text-ink-muted text-sm">{m.rounds_restore_msg()}</p>
      <div class="flex gap-2">
        <Button variant="primary" size="lg" onclick={() => restoreRound(roundIdx)} disabled={actionLoading}><RotateCcw class="w-4 h-4" aria-hidden="true" />{m.rounds_restore_yes()}</Button>
        <Button variant="secondary" size="lg" onclick={() => restoreConfirmRound = null}>{m.rounds_restore_keep()}</Button>
      </div>
    </div>
  {/snippet}

  {#if error}
    <div class="bg-accent-soft/20 border border-accent-soft-border rounded-lg p-3">
      <p class="text-link-soft text-sm">{error}</p>
    </div>
  {/if}

  <!-- Global Timer (hidden with parallel rounds) -->
  {#if !hasParallelRounds && (tournament.round_time ?? 0) > 0 && tournament.state === "Playing"}
    <div class="bg-surface-muted/50 rounded-lg p-4 flex justify-center">
      <TimerDisplay {tournament} {isOrganizer} />
    </div>
  {/if}

  {#if tournament.rounds!.length === 0}
    <!-- VEKN-synced tournaments carry standings but no round details (engine
         preserves them: standings.rs update_standings guard). Distinguish those
         from a not-yet-played event, which has neither. -->
    <p class="text-ink-muted">
      {(tournament.standings?.length ?? 0) > 0 ? m.rounds_no_rounds_recorded() : m.rounds_no_rounds()}
    </p>
  {:else}
    <!-- Current round controls -->
    {#if isOrganizer && currentRoundIdx >= 0 && !hasParallelRounds}
      <div class="flex items-center justify-between flex-wrap gap-2">
        <div class="flex items-center gap-3">
          <p class="text-ink-muted">{m.rounds_round_in_progress({ n: String(currentRoundIdx + 1) })}</p>
          {#if seatingScore}
            {#if hasR1Violation}
              <button
                onclick={() => showScoreDetails = !showScoreDetails}
                class="px-2 py-0.5 text-xs rounded-full bg-accent-soft/60 text-link-soft font-medium"
              >{m.rounds_seating_invalid()}</button>
            {:else}
              {@const issues = scoreIssueCount()}
              {@const expected = scoreExpectedCount()}
              <button
                onclick={() => showScoreDetails = !showScoreDetails}
                class="px-2 py-0.5 text-xs rounded-full {issues === 0 ? 'badge-success' : 'badge-pending'}"
              >
                {#if issues === 0 && expected === 0}{m.rounds_seating_perfect()}
                {:else if issues === 0}{m.rounds_seating_ok({ count: String(expected) })}
                {:else}{m.rounds_seating_issues({ count: String(issues) })}{/if}
              </button>
            {/if}
          {/if}
        </div>
        <div class="flex gap-2">
          <Button variant="danger" size="md" onclick={() => cancelConfirmRound = currentRoundIdx} disabled={actionLoading}><Ban class="w-4 h-4" aria-hidden="true" />{m.rounds_cancel_round()}</Button>
        </div>
      </div>

      <!-- Score details panel -->
      {#if showScoreDetails && seatingScore}
        <div class="bg-surface-muted/50 rounded-lg p-4 text-sm space-y-1">
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
                <span class="text-link">!!</span>
                <span class="text-link-soft font-medium">{label}:</span>
                <span class="text-link">{displayVal}</span>
              {:else if isZero}
                <span class="text-info">✓</span>
                <span class="text-ink">{label}:</span>
                <span class="text-ink-muted">{displayVal}</span>
              {:else if atMinimum && min > 0}
                <span class="text-ink-faint">—</span>
                <span class="text-ink-muted">{label}:</span>
                <span class="text-ink-faint">{displayVal}</span>
                <span class="text-ink-faint text-xs">{m.rounds_unavoidable()}</span>
              {:else}
                <span class="text-warn">✗</span>
                <span class="text-ink">{label}:</span>
                <span class="text-warn">{displayVal}</span>
                {#if min > 0}
                  <span class="text-ink-faint text-xs">(min: {isStddev ? min.toFixed(2) : String(min)})</span>
                {/if}
              {/if}
            </div>
          {/each}
        </div>
      {/if}

      <!-- Cancel round confirmation -->
      {#if cancelConfirmRound === currentRoundIdx}
        {@render cancelConfirmBox(currentRoundIdx)}
      {/if}

    {/if}

    <!-- Not seated players (alter mode, visible in Playing and Finished) -->
    {#if unseatedPlayers.length > 0}
      <div class="banner-warn border rounded-lg p-3">
        <p class="text-xs mb-2">{m.rounds_not_seated()}</p>
        <div class="flex flex-wrap gap-2">
          {#each unseatedPlayers as player}
            {@const puid = player.user_uid ?? ""}
            <span class="inline-flex items-center gap-1 px-2 py-1 text-sm bg-surface-hover rounded text-ink-bright">
              {seatDisplay(puid)}
            </span>
          {/each}
        </div>
      </div>
    {/if}
    <!-- Sitting out players (stagger rounds, hidden with parallel rounds) -->
    {#if !hasParallelRounds && sittingOutPlayers.length > 0}
      <div class="banner-info border rounded-lg p-3">
        <p class="text-xs mb-2">{m.rounds_sitting_out()}</p>
        <div class="flex flex-wrap gap-2">
          {#each sittingOutPlayers as player}
            {@const puid = player.user_uid ?? ""}
            <span class="inline-flex items-center gap-1 px-2 py-1 text-sm bg-surface-hover rounded text-ink-bright">
              {seatDisplay(puid)}
            </span>
          {/each}
        </div>
      </div>
    {/if}

    {#each tournament.rounds as round, r}
      {@const isCurrent = isCurrentRound(r)}
      {@const isEditable = canEditSeating}
      {@const isLast = r === tournament.rounds!.length - 1}
      {@const isRoundLive = round.some(t => t.state !== "Finished" && t.state !== "Cancelled")}
      {@const isExpanded = expandedRounds.has(r)}
      {@const canEndRound = isOrganizer && isRoundEndable(r)}
      {@const allTablesScored = isRoundAllFinished(r)}
      <div class="bg-surface-muted/30 rounded-lg border border-line">
        <div class="flex items-center">
          <button
            onclick={() => toggleRound(r)}
            class="flex-1 px-4 py-3 flex items-center justify-between text-left"
          >
            <div class="flex items-center gap-2">
              {#if isExpanded}<ChevronDown class="w-4 h-4 text-ink-faint" />{:else}<ChevronRight class="w-4 h-4 text-ink-faint" />{/if}
              <span class="text-sm font-medium {isCurrent ? 'text-ink-strong' : 'text-ink'}">
                {m.rounds_round_n({ n: String(r + 1) })}
              </span>
              {#if isRoundFullyCancelled(r)}
                <span class="text-xs px-2 py-0.5 rounded badge-slate">{m.rounds_cancelled_badge()}</span>
              {:else if tournament.state === "Playing" && isRoundInProgress(r)}
                {@const prog = roundProgress(r)}
                <span class="text-xs px-2 py-0.5 rounded badge-pending">{m.rounds_in_progress()}</span>
                <span class="text-xs text-ink-faint">{prog.done}/{prog.total}</span>
              {/if}
            </div>
            <span class="text-xs text-ink-faint">{m.rounds_table_count({ count: String(round.length) })}</span>
          </button>
          {#if isOrganizer && round.length > 0}
            <button
              onclick={() => printRound(r)}
              class="px-3 py-3 text-ink-faint hover:text-ink-strong transition-colors"
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
              <p class="text-sm text-ink">{m.rounds_alter_hint()}</p>
              {#if unseatedPlayers.length > 0}
                <!-- Cross-link: adding a pool player is a separate engine event
                     (AlterSeating keeps the player set fixed), so point at it. -->
                <p class="text-sm text-ink-muted">{m.rounds_alter_pool_hint({ count: String(unseatedPlayers.length) })}</p>
              {/if}
              {#if round.some(t => t.seating.some(s => s.result.vp > 0))}
                <p class="text-sm text-warn">{m.rounds_alter_scores_warning()}</p>
              {/if}
              {#if hasR1Issue}
                <p class="text-sm text-link">{m.rounds_alter_r1_error()}</p>
              {/if}
              {#if hasUndersizedTable}
                <p class="text-sm text-link">{m.rounds_alter_size_error()}</p>
              {/if}
              <div class="flex gap-2 flex-wrap">
                <Button variant="primary" size="lg" onclick={saveAlterSeating} disabled={actionLoading || hasR1Issue || hasUndersizedTable}>{m.rounds_save_seating()}</Button>
                <Button variant="secondary" size="lg" onclick={cancelAlterMode}>{m.common_cancel()}</Button>
              </div>
              <SeatingSortable
                bind:tables={alterTables}
                {playerInfo}
                {playerIssues}
                isFinals={false}
                tableRooms={tournament.table_rooms}
                online={tournament.online}
                onchange={recomputeIssues}
              />
              <Button variant="secondary" size="md" onclick={addTableInAlter} disabled={actionLoading}>
                <SquarePlus class="w-4 h-4" />{m.rounds_add_table()}
              </Button>
            {:else}
            {#if isOrganizer}
              <div class="flex gap-2 flex-wrap">
                {#if isEditable && !alterMode && !isRoundFullyCancelled(r)}
                  <Button variant="secondary" size="md" onclick={() => enterAlterMode(r)} disabled={actionLoading}>
                    <ArrowRightLeft class="w-4 h-4" />{m.rounds_alter_seating()}
                  </Button>
                {/if}
                {#if canEndRound}
                  <Button variant="secondary" size="md" onclick={() => doAction("FinishRound", { round: r })} disabled={actionLoading || !allTablesScored} aria-describedby={!allTablesScored ? `end-round-hint-${r}` : undefined}>{m.rounds_finish_round_n({ n: String(r + 1) })}</Button>
                {/if}
                {#if isRoundCancellable(r) && !(!hasParallelRounds && r === currentRoundIdx)}
                  <Button variant="danger" size="md" onclick={() => cancelConfirmRound = r} disabled={actionLoading}><Ban class="w-4 h-4" aria-hidden="true" />{m.rounds_cancel_round()}</Button>
                {/if}
                {#if isRoundRestorable(r)}
                  <Button variant="secondary" size="md" onclick={() => restoreConfirmRound = r} disabled={actionLoading}><RotateCcw class="w-4 h-4" aria-hidden="true" />{m.rounds_restore_round()}</Button>
                {/if}
              </div>
              {#if canEndRound && !allTablesScored}
                <p id="end-round-hint-{r}" class="text-sm text-ink-faint">{m.rounds_end_round_hint()}</p>
              {/if}
              {#if cancelConfirmRound === r && !(!hasParallelRounds && r === currentRoundIdx)}
                {@render cancelConfirmBox(r)}
              {/if}
              {#if restoreConfirmRound === r}
                {@render restoreConfirmBox(r)}
              {/if}
            {/if}
            {#each round as table, i}
              {@const isScoring = scoringTable === `${r}:${i}`}
              {@const isCancelled = table.state === 'Cancelled'}
              <div class="bg-surface-muted/50 rounded-lg p-4 {isCancelled ? 'opacity-60' : ''}">
                <div class="flex items-center justify-between mb-2 gap-2">
                  <button
                    onclick={() => toggleScoring(r, i)}
                    class="group flex items-center gap-2 text-left min-w-0 flex-1 min-h-[44px]"
                    aria-expanded={isScoring}
                  >
                    {#if table.seating.length > 0 && !isCancelled}
                      {#if isScoring}<ChevronDown class="w-4 h-4 text-ink-muted group-hover:text-ink-strong shrink-0" />{:else}<ChevronRight class="w-4 h-4 text-ink-muted group-hover:text-ink-strong shrink-0" />{/if}
                    {/if}
                    <h3 class="text-sm font-medium truncate {isCancelled ? 'text-ink-muted line-through' : 'text-ink-strong'}">{resolveTableLabel(tournament.table_rooms, i) ?? m.rounds_table_n({ n: String(i + 1) })}</h3>
                    {#if !isCancelled && (table.seating.length < 4 || table.seating.length > 5)}
                      <span class="text-xs text-warn shrink-0">{m.rounds_n_players({ count: String(table.seating.length) })}</span>
                    {/if}
                  </button>
                  <div class="flex items-center gap-2 shrink-0">
                    {#if table.organized_by}
                      <span class="text-xs px-2 py-0.5 rounded badge-blue shrink-0" title={m.self_organize_organized_by({ name: seatDisplay(table.organized_by) })}>
                        <Users class="w-3 h-3 inline -mt-0.5" aria-hidden="true" /> {seatDisplay(table.organized_by)}
                      </span>
                    {/if}
                    {#if isOrganizer && !isScoring && !isCancelled && table.state !== "Finished" && !hasParallelRounds && (tournament.round_time ?? 0) > 0 && tournament.state === "Playing" && r === tournament.rounds!.length - 1 && tournament.timer && !tournament.timer.paused}
                      <!-- +time without unfolding: the on-the-floor judge move -->
                      {@const tExtra = tournament.table_extra_time?.[String(i)] ?? 0}
                      <span class="flex items-center gap-1 shrink-0">
                        {#if tExtra > 0}
                          <span class="text-xs text-ink-muted">+{Math.round(tExtra / 60)}min</span>
                        {/if}
                        {#each [60, 300] as secs}
                          <button
                            onclick={() => addTableTime(i, secs)}
                            disabled={addTimeLoading || tExtra + secs > 1800}
                            class="text-xs px-2 min-h-[44px] sm:min-h-0 sm:py-1 rounded border border-line-strong text-ink-muted hover:text-ink-strong hover:bg-surface-hover/50 disabled:opacity-40 transition-colors"
                            title={m.timer_add_table_time()}
                          >+{secs / 60}min</button>
                        {/each}
                      </span>
                    {/if}
                    {#if isOrganizer && !isScoring && !isCancelled && table.seating.length > 0}
                      <button
                        onclick={() => toggleScoring(r, i)}
                        class="inline-flex items-center gap-1 text-xs font-medium text-select border border-select/40 rounded-md px-2.5 min-h-[44px] sm:min-h-0 sm:py-1.5 hover:bg-select/10 transition-colors shrink-0"
                      ><Settings2 class="w-3.5 h-3.5" aria-hidden="true" />{m.rounds_manage()}</button>
                    {/if}
                    <span class="text-xs px-2 py-0.5 rounded {table.state === 'Finished' ? 'badge-success' : table.state === 'Invalid' ? 'bg-accent-soft/60 text-link-soft' : isCancelled ? 'badge-slate' : 'badge-pending'}">
                      {translateTableState(table.state)}
                    </span>
                    {#if isEditable && isLast && table.seating.length === 0}
                      <button
                        onclick={() => doAction("RemoveTable", { table: i })}
                        class="p-1 text-link hover:text-link-soft transition-colors"
                        title={m.rounds_remove_empty_table()}
                      >
                        <X class="w-4 h-4" />
                      </button>
                    {/if}
                  </div>
                </div>
                <!-- Per-table timer + extension controls (unfold-only: the unfold is this table's org-action surface; the folded list stays compact, and the global round timer above keeps time visible at all times) -->
                {#if isScoring && !hasParallelRounds && (tournament.round_time ?? 0) > 0 && tournament.state === "Playing" && r === tournament.rounds!.length - 1}
                  <div class="mb-2">
                    <TimerDisplay {tournament} {isOrganizer} tableIndex={i} showAdvisory={false} />
                  </div>
                {/if}
                <div class="divide-y divide-line">
                  {#each table.seating as seat, j}
                    {@const tVps = table.seating.map(s => s.result.vp)}
                    {@const preview = previewScoresSync(tournament, tournamentSanctions, r, i, tVps)}
                    {@const tGws = preview ? preview.gw : table.seating.map(s => s.result.gw)}
                    {@const tTps = preview ? preview.tp : table.seating.map(s => s.result.tp)}
                    <div class="py-2.5">
                      <div class="flex items-center justify-between gap-2 text-sm">
                        <span class="text-ink inline-flex items-center gap-1 min-w-0">
                          {seatDisplay(seat.player_uid)}
                          {#if nonCompetingUids.has(seat.player_uid)}
                            <span class="text-[10px] px-1.5 py-0.5 rounded bg-surface-active text-ink-muted shrink-0" title={m.proxy_hint()}>{m.proxy_label()}</span>
                          {/if}
                          {#if playerSanctionsMap[seat.player_uid]?.length}
                            <SanctionIndicator
                              sanctions={playerSanctionsMap[seat.player_uid]!}
                              onclick={() => sanctionListTarget = { uid: seat.player_uid, name: seatDisplay(seat.player_uid) }}
                            />
                          {/if}
                        </span>
                        <div class="flex items-center gap-2 shrink-0">
                          <span class="text-ink-faint text-xs">{#if !isScoring}<span class="text-ink-strong font-medium tabular-nums">{seat.result.vp}VP</span> {/if}{tGws[j]}GW {tTps[j]}TP</span>
                          {#if isEditable && (isLast || isRoundLive)}
                            <!-- p-3 + 20px icon = 44px touch floor on the on-the-floor issuance path -->
                            <button
                              onclick={() => doAction("UnseatPlayer", { player_uid: seat.player_uid, round: r })}
                              class="p-3 sm:p-0.5 -m-1 sm:m-0 text-ink-faint hover:text-link transition-colors"
                              title={m.rounds_unseat_title()}
                            >
                              <UserMinus class="w-5 h-5 sm:w-3.5 sm:h-3.5" />
                            </button>
                          {/if}
                          {#if isOrganizer && !isCancelled}
                            <button
                              onclick={() => sanctionTarget = { uid: seat.player_uid, name: seatDisplay(seat.player_uid), round: r }}
                              class="p-3 sm:p-0.5 -m-1 sm:m-0 text-ink-faint hover:text-warn transition-colors"
                              title={m.players_sanction_btn()}
                            >
                              <TriangleAlert class="w-5 h-5 sm:w-3.5 sm:h-3.5" />
                            </button>
                          {/if}
                        </div>
                      </div>
                      {#if isScoring}
                        <div class="mt-1.5">
                          {#if !isOrganizer && table.seating.some(s => s.judge_uid)}
                            <span class="inline-flex items-center gap-1 text-xs text-ink-muted">
                              {seat.result.vp}
                              <Lock class="w-3.5 h-3.5" />
                            </span>
                          {:else}
                            <VpInput
                              value={seat.result.vp}
                              options={vpOptions(table.seating.length, isOrganizer)}
                              label={seatDisplay(seat.player_uid)}
                              disabled={scoreSaving === i}
                              saving={scoreSavingSeat === seat.player_uid && scoreSaving === i}
                              onchange={(v) => setVp(r, i, seat.player_uid, v, table.seating)}
                            />
                          {/if}
                        </div>
                      {/if}
                    </div>
                  {/each}
                </div>
                <!-- Why the table won't close, then the way past it. Without the
                     reason an impossible table and a half-typed one look identical:
                     no error, just a round that never finishes. -->
                {#if isScoring && (table.state === 'Invalid' || table.state === 'In Progress')}
                  {@const vpIssue = checkTableVpsSync(table.seating.map(s => s.result.vp))}
                  {@const blocked = !!vpIssue && vpIssue.code !== 'incomplete'}
                  {#if blocked}
                    <div class="mt-2 banner-warn border rounded-lg p-3">
                      <p class="text-xs flex items-start gap-1.5">
                        <TriangleAlert class="w-4 h-4 shrink-0" />
                        <span>{vpIssueText(vpIssue!, table.seating.length)}</span>
                      </p>
                      {#if isOrganizer && overrideTable_ !== i}
                        <p class="text-xs mt-1.5">{m.vp_blocked_override_hint()}</p>
                      {/if}
                    </div>
                  {/if}
                  {#if isOrganizer}
                    {#if overrideTable_ === i}
                      <div class="mt-2 pt-2 border-t border-line">
                        <p class="text-xs text-ink-faint mb-1.5">{m.override_usage_hint()}</p>
                        <label class="text-xs text-ink-muted block mb-1">{m.override_judge_comment()}
                          <textarea
                            bind:value={overrideComment}
                            class="w-full bg-surface-hover text-ink-strong text-xs rounded px-2 py-1 border border-line-strong resize-none"
                            rows="2"
                            placeholder={m.override_placeholder()}
                          ></textarea>
                        </label>
                        <div class="flex gap-2 mt-1 justify-end">
                          <button onclick={() => { overrideTable_ = null; overrideComment = ""; }} class="px-2 py-1 text-xs text-ink-muted hover:text-ink-bright">{m.common_cancel()}</button>
                          <Button
                            variant="primary"
                            size="sm"
                            loading={overrideSaving}
                            disabled={overrideSaving || !overrideComment.trim()}
                            onclick={() => submitOverride(r, i)}
                          >{overrideSaving ? m.common_saving() : m.override_save()}</Button>
                        </div>
                      </div>
                    {:else if blocked}
                      <!-- Primary: the numbers are impossible and only a judge can move
                           this table on, so the way out stops being a ghost button. -->
                      <div class="mt-2">
                        <Button variant="primary" size="lg" block class="min-h-[44px]" onclick={() => { overrideTable_ = i; overrideComment = ""; }}>
                          <ShieldCheck class="w-4 h-4" />{m.vp_blocked_override_btn()}
                        </Button>
                      </div>
                    {:else}
                      <div class="mt-2 flex justify-end">
                        <button
                          onclick={() => { overrideTable_ = i; overrideComment = ""; }}
                          class="px-2 py-1 text-xs text-warn hover:opacity-80 transition-opacity"
                          title={m.override_title()}
                        >
                          <ShieldCheck class="w-3.5 h-3.5 inline mr-1" />{m.override_btn()}
                        </button>
                      </div>
                    {/if}
                  {/if}
                {/if}
                {#if isOrganizer && table.override}
                  <div class="mt-2 pt-2 border-t border-line flex items-center justify-between">
                    <span class="text-xs text-warn">
                      <ShieldCheck class="w-3.5 h-3.5 inline mr-1" />
                      {m.override_overridden({ comment: table.override.comment })}
                    </span>
                    <button
                      onclick={() => removeOverride(r, i)}
                      disabled={overrideSaving}
                      class="px-2 py-1 text-xs text-ink-faint hover:text-link transition-colors"
                    >{m.override_remove()}</button>
                  </div>
                {/if}
                <!-- Seat a player (last round, or an earlier still-live round — parallel/open pods take substitutes too) -->
                {#if isEditable && (isLast || isRoundLive) && unseatedPlayers.length > 0 && table.seating.length < 5 && table.state !== "Finished" && !isCancelled}
                  <div class="mt-2 pt-2 border-t border-line">
                    {#if seatTargetTable === `${r}:${i}`}
                      <div class="flex flex-wrap gap-1">
                        {#each unseatedPlayers as player}
                          {@const puid = player.user_uid ?? ""}
                          <button
                            onclick={() => { doAction("SeatPlayer", { player_uid: puid, table: i, seat: table.seating.length, round: r }); seatTargetTable = null; }}
                            class="px-2 py-1 text-xs bg-surface-hover hover:bg-select-soft/60 text-ink hover:text-select rounded transition-colors"
                          >{seatDisplay(puid)}</button>
                        {/each}
                        <button onclick={() => seatTargetTable = null} class="px-2 py-1 text-xs text-ink-faint hover:text-ink">{m.common_cancel()}</button>
                      </div>
                    {:else}
                      <button
                        onclick={() => seatTargetTable = `${r}:${i}`}
                        class="text-xs text-ink-faint hover:text-select transition-colors"
                      >
                        <Plus class="w-3.5 h-3.5 inline mr-1" />{m.rounds_seat_player()}
                      </button>
                    {/if}
                  </div>
                {/if}
              </div>
            {/each}
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
