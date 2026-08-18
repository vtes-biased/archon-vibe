<script lang="ts">
  import { previewScoresSync, checkTableVpsSync, finalsQualification, type TournamentEventType } from "$lib/engine";
  import { vpIssueText } from "$lib/vpIssue";
  import { toUserMessage } from '$lib/errors';
  import type { Tournament, Sanction } from "$lib/types";
  import { formatScore } from "$lib/utils";
  import { tournamentAction } from "$lib/tournament-actions";
  import SeatingSortable from "$lib/components/SeatingSortable.svelte";
  import TournamentSanctionModal from "$lib/components/TournamentSanctionModal.svelte";
  import VpInput from "./VpInput.svelte";
  import TimerDisplay from "./TimerDisplay.svelte";
  import Button from '$lib/components/Button.svelte';
  import { ArrowRightLeft, ShieldCheck, Lock, TriangleAlert } from "@lucide/svelte";
  import { seatDisplay as seatDisplayUtil, vpOptions, translateTableState, type StandingEntry, type PlayerInfoMap } from "$lib/tournament-utils";
  import * as m from '$lib/paraglide/messages.js';

  let {
    tournament = $bindable(),
    playerInfo,
    standings,
    isOrganizer,
    actionLoading,
    doAction,
    loadPlayerNames,
    setFinalsVp,
    scoreSaving,
    scoreSavingSeat,
    tournamentSanctions,
  }: {
    tournament: Tournament;
    playerInfo: PlayerInfoMap;
    standings: StandingEntry[];
    isOrganizer: boolean;
    actionLoading: boolean;
    doAction: (action: TournamentEventType, body?: any) => Promise<string | null>;
    loadPlayerNames: () => Promise<void>;
    setFinalsVp: (playerUid: string, vp: number, seating: Array<{ player_uid: string; result: { vp: number } }>) => Promise<void>;
    scoreSaving: number | null;
    scoreSavingSeat: string | null;
    tournamentSanctions?: Sanction[];
  } = $props();

  let error = $state<string | null>(null);

  let alterMode = $state(false);

  const canEditSeating = $derived(
    isOrganizer && (tournament.state === "Playing" || tournament.state === "Finished" || tournament.state === "Waiting")
  );

  function enterAlterMode() {
    alterTables = [tournament.finals!.seating.map(s => s.player_uid)];
    alterMode = true;
  }

  function cancelAlterMode() {
    alterMode = false;
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
  let sanctionTarget = $state<{ uid: string; name: string } | null>(null);

  function seatDisplay(uid: string): string {
    return seatDisplayUtil(uid, playerInfo, tournament.online);
  }


  const finalsQual = $derived(finalsQualification(tournament?.players ?? [], standings));
  const hasFinalsCandidate = $derived(finalsQual.candidates.length >= 5 && (tournament?.rounds?.length ?? 0) >= 2);
</script>

<div class="space-y-4">
  {#if error}
    <div class="bg-accent-soft/20 border border-accent-soft-border rounded-lg p-3">
      <p class="text-link-soft text-sm">{error}</p>
    </div>
  {/if}

  {#if !hasFinalsCandidate}
    <p class="text-ink-muted">{m.finals_require_rounds()}</p>
  {:else if !tournament.finals}
    <!-- Deliberately no Start Finals button: finishing without a final is
         legitimate (VEKN §3.1.6), and the action bar already owns state
         transitions and the toss-needed warning. -->
    <p class="text-ink-muted text-sm">{m.finals_seeding_projected()}</p>
    <div class="bg-surface-muted/50 rounded-lg p-4 space-y-1.5">
      {#each standings.slice(0, 5) as e, i}
        <div class="flex items-center gap-2 text-sm">
          <span class="w-5 shrink-0 text-xs text-ink-faint">{i + 1}.</span>
          <span class="min-w-0 truncate text-ink">{seatDisplayUtil(e.user_uid, playerInfo, tournament.online)}</span>
          <span class="flex-1"></span>
          <span class="shrink-0 text-xs text-ink-muted">{formatScore(e.gw, e.vp, e.tp)}</span>
        </div>
      {/each}
    </div>
  {:else}
    <h3 class="text-lg font-medium text-ink-strong">{m.finals_title()}</h3>

    {#if (tournament.finals_time || tournament.round_time || 0) > 0 && tournament.state === "Playing"}
      <div class="bg-surface-muted/50 rounded-lg p-4 flex justify-center">
        <TimerDisplay {tournament} {isOrganizer} finals />
      </div>
    {/if}

    <div class="bg-surface-muted/50 rounded-lg p-4">
      <div class="flex items-center justify-between mb-2">
        <div class="flex items-center gap-2">
          <h3 class="text-sm font-medium text-ink-strong">{m.finals_table()}</h3>
          {#if canEditSeating && !alterMode}
            <Button variant="secondary" size="sm" onclick={enterAlterMode}>
              <ArrowRightLeft class="w-3.5 h-3.5" />{m.rounds_alter_seating()}
            </Button>
          {/if}
        </div>
        <span class="text-xs px-2 py-0.5 rounded {tournament.finals.state === 'Finished' ? 'badge-success' : tournament.finals.state === 'Invalid' ? 'bg-accent-soft/60 text-link-soft' : 'badge-pending'}">
          {translateTableState(tournament.finals.state)}
        </span>
      </div>
      {#if alterMode}
        <p class="text-sm text-ink mb-2">{m.rounds_alter_hint()}</p>
        <p class="text-xs text-ink-muted mb-2">
          {m.finals_seating_procedure_hint()}
          <a href="/help/tournament-rules#313-final-round-seating" class="text-link hover:underline">{m.finals_seating_procedure_link()}</a>
        </p>
        <SeatingSortable
          bind:tables={alterTables}
          {playerInfo}
          playerIssues={new Map()}
          isFinals={true}
          online={tournament.online}
          onchange={() => {}}
        />
        <div class="flex gap-2 mt-3">
          <Button variant="primary" size="lg" onclick={saveAlterSeating} disabled={actionLoading}>{m.rounds_save_seating()}</Button>
          <Button variant="secondary" size="lg" onclick={cancelAlterMode}>{m.common_cancel()}</Button>
        </div>
      {:else}
      <div class="divide-y divide-line">
        {#each tournament.finals.seating as seat, j}
          {@const tVps = tournament.finals.seating.map(s => s.result.vp)}
          <!-- Finished finals: stored gw/tp are the engine-refreshed, SA-adjusted truth. -->
          {@const scored = tournament.finals.state === 'Finished'}
          {@const preview = scored ? null : previewScoresSync(tournament, tournamentSanctions, tournament.rounds?.length ?? 0, 0, tVps)}
          {@const tGws = preview ? preview.gw : tournament.finals.seating.map(s => s.result.gw)}
          {@const tTps = preview ? preview.tp : tournament.finals.seating.map(s => s.result.tp)}
          {@const seedIdx = tournament.finals.seed_order.indexOf(seat.player_uid) + 1}
          {@const seedStanding = standings.find(s => s.user_uid === seat.player_uid)}
          <div class="py-2.5">
            <div class="flex items-center justify-between gap-2 text-sm">
              <div class="min-w-0">
                <span class="text-ink truncate">{seatDisplay(seat.player_uid)}</span>
                <div class="text-xs text-ink-faint">{m.finals_seed({ n: String(seedIdx) })}{#if seedStanding} · {formatScore(seedStanding.gw, seedStanding.vp, seedStanding.tp)}{/if}</div>
              </div>
              <div class="flex items-center gap-2 shrink-0">
                <span class="text-ink-faint text-xs">{tGws[j]}GW {tTps[j]}TP</span>
                {#if isOrganizer}
                  <button
                    onclick={() => sanctionTarget = { uid: seat.player_uid, name: seatDisplay(seat.player_uid) }}
                    class="p-2 sm:p-0.5 text-ink-faint hover:text-warn transition-colors"
                    title={m.players_sanction_btn()}
                  >
                    <TriangleAlert class="w-5 h-5 sm:w-3.5 sm:h-3.5" />
                  </button>
                {/if}
              </div>
            </div>
            <div class="mt-1.5">
              {#if !isOrganizer && tournament.finals.seating.some(s => s.judge_uid)}
                <span class="inline-flex items-center gap-1 text-xs text-ink-muted">
                  {seat.result.vp}VP
                  <Lock class="w-3.5 h-3.5" aria-hidden="true" />
                </span>
              {:else}
                <VpInput
                  value={seat.result.vp}
                  options={vpOptions(tournament.finals.seating.length, isOrganizer)}
                  label={seatDisplay(seat.player_uid)}
                  disabled={scoreSaving === -1}
                  saving={scoreSavingSeat === seat.player_uid && scoreSaving === -1}
                  onchange={(v) => setFinalsVp(seat.player_uid, v, tournament.finals!.seating)}
                />
              {/if}
            </div>
          </div>
        {/each}
      </div>
      {/if}

      <!-- Override controls, preceded by why the table is stuck (same reasoning as RoundsTab) -->
      {#if tournament.finals.state === 'Invalid' || tournament.finals.state === 'In Progress'}
        {@const vpIssue = checkTableVpsSync(tournament.finals.seating.map(s => s.result.vp))}
        {@const blocked = !!vpIssue && vpIssue.code !== 'incomplete'}
        {#if blocked}
          <div class="mt-2 banner-warn border rounded-lg p-3">
            <p class="text-xs flex items-start gap-1.5">
              <TriangleAlert class="w-4 h-4 shrink-0" />
              <span>{vpIssueText(vpIssue!, tournament.finals.seating.length)}</span>
            </p>
            {#if isOrganizer && overrideTable_ !== -1}
              <p class="text-xs mt-1.5">{m.vp_blocked_override_hint()}</p>
            {/if}
          </div>
        {/if}
        {#if isOrganizer}
        {#if overrideTable_ === -1}
          <div class="mt-2 pt-2 border-t border-line">
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
                onclick={async () => {
                  if (!overrideComment.trim()) return;
                  overrideSaving = true;
                  try {
                    tournament = await tournamentAction(tournament.uid, "Override", { round: tournament.rounds!.length, table: 0, comment: overrideComment.trim() });
                    await loadPlayerNames();
                    overrideTable_ = null;
                    overrideComment = "";
                  } catch (e) { error = toUserMessage(e, m.override_error()); } finally { overrideSaving = false; }
                }}
              >{overrideSaving ? m.common_saving() : m.override_save()}</Button>
            </div>
          </div>
        {:else if blocked}
          <div class="mt-2">
            <Button variant="primary" size="lg" block class="min-h-[44px]" onclick={() => { overrideTable_ = -1; overrideComment = ""; }}>
              <ShieldCheck class="w-4 h-4" />{m.vp_blocked_override_btn()}
            </Button>
          </div>
        {:else}
          <div class="mt-2 flex justify-end">
            <button
              onclick={() => { overrideTable_ = -1; overrideComment = ""; }}
              class="px-2 py-1 text-xs text-warn hover:opacity-80 transition-colors"
            >
              <ShieldCheck class="w-3.5 h-3.5 inline mr-1" />{m.override_btn()}
            </button>
          </div>
        {/if}
        {/if}
      {/if}
      {#if sanctionTarget && isOrganizer}
        <TournamentSanctionModal
          {tournament}
          playerUid={sanctionTarget.uid}
          playerName={sanctionTarget.name}
          currentRound={tournament.rounds!.length}
          onClose={() => sanctionTarget = null}
        />
      {/if}
      {#if isOrganizer && tournament.finals.override}
        <div class="mt-2 pt-2 border-t border-line flex items-center justify-between">
          <span class="text-xs text-warn">
            <ShieldCheck class="w-3.5 h-3.5 inline mr-1" />
            {m.override_overridden({ comment: tournament.finals.override.comment })}
          </span>
          <button
            onclick={async () => {
              overrideSaving = true;
              try {
                tournament = await tournamentAction(tournament.uid, "Unoverride", { round: tournament.rounds!.length, table: 0 });
                await loadPlayerNames();
              } catch (e) { error = toUserMessage(e, m.override_remove_error()); } finally { overrideSaving = false; }
            }}
            disabled={overrideSaving}
            class="px-2 py-1 text-xs text-ink-faint hover:text-link transition-colors"
          >{m.override_remove()}</button>
        </div>
      {/if}
    </div>
  {/if}
</div>
