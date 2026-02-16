<script lang="ts">
  import type { Tournament, TournamentState } from "$lib/types";
  import { formatScore } from "$lib/utils";
  import { computeRatingPoints } from "$lib/engine";
  import { getStateBadgeClass, seatDisplay as seatDisplayUtil } from "$lib/tournament-utils";
  import { addTournamentOrganizer, removeTournamentOrganizer } from "$lib/api";
  import OrganizerManager from "$lib/components/OrganizerManager.svelte";

  import * as m from '$lib/paraglide/messages.js';

  interface StandingEntry {
    user_uid: string;
    gw: number;
    vp: number;
    tp: number;
    toss: number;
    rank: number;
    finals?: string;
  }

  let {
    tournament,
    playerInfo,
    standings,
    isOrganizer,
    actionLoading,
    doAction,
  }: {
    tournament: Tournament;
    playerInfo: Record<string, { name: string; nickname: string | null; vekn: string | null }>;
    standings: StandingEntry[];
    isOrganizer: boolean;
    actionLoading: boolean;
    doAction: (action: string, body?: any) => Promise<void>;
  } = $props();

  function seatDisplay(uid: string): string {
    return seatDisplayUtil(uid, playerInfo);
  }

  const hasRounds = $derived((tournament?.rounds?.length ?? 0) > 0);
  const hasFinalsCandidate = $derived(standings.length >= 5 && (tournament?.rounds?.length ?? 0) >= 2);
  const finishedPlayerCount = $derived(tournament?.players?.filter(p => p.state === "Finished").length ?? 0);
  const checkedInCount = $derived(tournament?.players?.filter(p => p.state === "Checked-in").length ?? 0);
  const registeredCount = $derived(tournament?.players?.length ?? 0);

  function top5HasTies(): boolean {
    if (standings.length < 5) return false;
    for (let i = 0; i < 5; i++) {
      for (let j = i + 1; j < 5; j++) {
        const a = standings[i]!, b = standings[j]!;
        if (a.gw === b.gw && a.vp === b.vp && a.tp === b.tp && a.toss === b.toss) return true;
      }
    }
    const fifth = standings[4]!;
    for (let k = 5; k < standings.length; k++) {
      const s = standings[k]!;
      if (s.gw === fifth.gw && s.vp === fifth.vp && s.tp === fifth.tp && s.toss === fifth.toss) return true;
    }
    return false;
  }

  const finalsReady = $derived(hasFinalsCandidate && !top5HasTies());
  const isFinals = $derived(tournament?.finals != null && (tournament?.state === "Playing" || tournament?.state === "Finished"));
  const hasFinals = $derived(standings.some(e => e.finals));
  const isFinished = $derived(tournament.state === "Finished");

  function getRatingPts(entry: StandingEntry): number {
    if (!isFinished) return 0;
    const finalistPos = entry.user_uid === tournament.winner ? 1
      : (tournament.finals?.seating.some(s => s.player_uid === entry.user_uid) ? 2 : 0);
    return computeRatingPoints(entry.vp, entry.gw, finalistPos, standings.length, tournament.rank);
  }
</script>

<div class="space-y-4">
  <!-- State badge + summary -->
  <div class="flex items-center gap-3">
    <span class="px-3 py-1.5 rounded text-sm font-medium {getStateBadgeClass(tournament.state)}">
      {tournament.state}
    </span>
    <span class="text-sm text-ash-400">
      {m.overview_player_count({ count: String(registeredCount) })}
      {#if hasRounds}
        · {m.overview_round_count({ count: String(tournament.rounds!.length) })}
      {/if}
      {#if isFinals}
        · {m.overview_finals_in_progress()}
      {/if}
    </span>
  </div>

  <!-- Winner display -->
  {#if tournament.winner}
    <div class="bg-emerald-900/20 border border-emerald-800 rounded-lg p-4">
      <div class="text-ash-500 text-sm">{m.tournament_winner()}</div>
      <div class="text-xl font-medium text-bone-100">{seatDisplay(tournament.winner)}</div>
    </div>
  {/if}

  <!-- Transition actions (organizer only) -->
  {#if isOrganizer}
    <div class="bg-ash-900/30 rounded-lg p-4 space-y-3">
      <h3 class="text-sm font-medium text-ash-300">{m.overview_actions()}</h3>

      {#if tournament.state === "Planned"}
        <button
          onclick={() => doAction("OpenRegistration")}
          disabled={actionLoading}
          class="px-4 py-2 text-sm font-medium text-white bg-emerald-700 hover:bg-emerald-600 disabled:bg-ash-700 rounded-lg transition-colors"
        >{actionLoading ? "..." : m.overview_open_registration()}</button>

      {:else if tournament.state === "Registration"}
        <div class="flex flex-wrap gap-2">
          <button
            onclick={() => doAction("CloseRegistration")}
            disabled={actionLoading}
            class="px-4 py-2 text-sm font-medium text-white bg-amber-700 hover:bg-amber-600 disabled:bg-ash-700 rounded-lg transition-colors"
          >{m.overview_close_registration()}</button>
          <button
            onclick={() => doAction("CancelRegistration")}
            disabled={actionLoading}
            class="px-3 py-1.5 text-sm text-ash-300 border border-ash-700 hover:border-ash-600 hover:text-ash-200 rounded-lg transition-colors"
          >{m.overview_back_to_planning()}</button>
        </div>

      {:else if tournament.state === "Waiting"}
        <div class="space-y-2">
          <!-- Guidance -->
          <div class="text-sm text-ash-300">
            {#if hasFinalsCandidate}
              {m.overview_round_complete({ n: String(tournament.rounds!.length) })}
              {#if top5HasTies()}
                <span class="text-amber-300">{m.overview_resolve_ties()}</span>
              {:else}
                <span class="text-emerald-300">{m.overview_finals_ready()}</span>
              {/if}
            {:else if hasRounds}
              {m.overview_round_complete_checkin({ n: String(tournament.rounds!.length) })}
            {:else}
              {m.overview_checkin_to_start()}
            {/if}
          </div>

          <div class="flex flex-wrap gap-2">
            <span class="text-sm text-ash-400">{m.overview_checked_in_count({ checked: String(checkedInCount), total: String(registeredCount - finishedPlayerCount) })}</span>
          </div>

          <div class="flex flex-wrap gap-2">
            {#if hasRounds}
              <button
                onclick={() => doAction("ResetCheckIn")}
                disabled={actionLoading}
                class="px-3 py-1.5 text-sm text-ash-300 bg-ash-800 hover:bg-ash-700 rounded-lg transition-colors"
              >{m.overview_reset_checkin()}</button>
            {/if}
            <button
              onclick={() => doAction("CheckInAll")}
              disabled={actionLoading}
              class="px-3 py-1.5 text-sm text-ash-300 bg-ash-800 hover:bg-ash-700 rounded-lg transition-colors"
            >{m.overview_check_all_in()}</button>
            <button
              onclick={() => doAction("MarkAllPaid")}
              disabled={actionLoading}
              class="px-3 py-1.5 text-sm text-ash-300 bg-ash-800 hover:bg-ash-700 rounded-lg transition-colors"
            >{m.payment_mark_all_paid()}</button>
            <button
              onclick={() => doAction("StartRound")}
              disabled={actionLoading || checkedInCount < 4}
              class="px-4 py-2 text-sm font-medium text-white bg-emerald-700 hover:bg-emerald-600 disabled:bg-ash-700 rounded-lg transition-colors"
            >{m.overview_start_round({ n: String((tournament.rounds?.length ?? 0) + 1) })}</button>
            {#if finalsReady}
              <button
                onclick={() => doAction("StartFinals")}
                disabled={actionLoading}
                class="px-4 py-2 text-sm font-medium text-white bg-emerald-700 hover:bg-emerald-600 disabled:bg-ash-700 rounded-lg transition-colors"
              >{m.overview_start_finals()}</button>
            {/if}
          </div>

          <!-- Seating warnings -->
          {#if [6, 7, 11].includes(checkedInCount)}
            <div class="bg-amber-900/20 border border-amber-800 rounded-lg p-3">
              <p class="text-amber-300 text-sm">{m.overview_seating_warning({ count: String(checkedInCount) })}</p>
            </div>
          {/if}

          <!-- Finish tournament / Reopen registration -->
          <div class="pt-3 border-t border-ash-800 flex flex-wrap gap-2">
            <button
              onclick={() => doAction("FinishTournament")}
              disabled={actionLoading}
              class="px-4 py-2 text-sm text-crimson-400 hover:text-crimson-300 border border-crimson-800 hover:border-crimson-700 rounded-lg transition-colors"
            >{m.overview_finish_tournament()}</button>
            <button
              onclick={() => doAction("ReopenRegistration")}
              disabled={actionLoading}
              class="px-3 py-1.5 text-sm text-ash-300 border border-ash-700 hover:border-ash-600 hover:text-ash-200 rounded-lg transition-colors"
            >{m.overview_reopen_registration()}</button>
          </div>
        </div>

      {:else if tournament.state === "Playing"}
        <p class="text-ash-400 text-sm">
          {#if isFinals}
            {m.overview_finals_manage()}
          {:else}
            {m.overview_round_manage({ n: String(tournament.rounds!.length) })}
          {/if}
        </p>

      {:else if tournament.state === "Finished"}
        <p class="text-ash-400 text-sm">{m.overview_tournament_finished()}</p>
        <div class="flex flex-wrap gap-2 mt-2">
          <button
            onclick={() => doAction("ReopenTournament")}
            disabled={actionLoading}
            class="px-3 py-1.5 text-sm text-ash-300 border border-ash-700 hover:border-ash-600 hover:text-ash-200 rounded-lg transition-colors"
          >{m.overview_reopen_tournament()}</button>
        </div>
      {/if}
    </div>
  {/if}

  <!-- Organizers -->
  {#if isOrganizer}
    <div class="bg-ash-900/30 rounded-lg p-4">
      <OrganizerManager
        organizerUids={tournament.organizers_uids ?? []}
        onadd={async (userUid) => { await addTournamentOrganizer(tournament.uid, userUid); }}
        onremove={async (userUid) => { await removeTournamentOrganizer(tournament.uid, userUid); }}
      />
    </div>
  {:else if tournament.organizers_uids?.length}
    <div class="bg-ash-900/30 rounded-lg p-4">
      <h4 class="text-sm font-medium text-ash-300 mb-2">{m.organizers_title()}</h4>
      <div class="flex flex-wrap gap-2">
        {#each tournament.organizers_uids as uid}
          <span class="text-sm text-bone-100">{seatDisplay(uid)}</span>
        {/each}
      </div>
    </div>
  {/if}

  <!-- Summary standings (top 5) -->
  {#if standings.length > 0}
    <div class="bg-ash-900/30 rounded-lg p-4">
      <h3 class="text-sm font-medium text-ash-300 mb-2">{m.overview_top_standings()}</h3>
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
          {#each standings.slice(0, 5) as entry}
            <tr class="text-bone-100 border-t border-ash-800">
              <td class="py-1 pr-2 text-ash-500">{entry.rank}</td>
              <td class="py-1 pr-2">{seatDisplay(entry.user_uid)}</td>
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
  {/if}
</div>
