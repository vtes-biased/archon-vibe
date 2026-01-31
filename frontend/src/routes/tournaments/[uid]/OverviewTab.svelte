<script lang="ts">
  import type { Tournament, TournamentState } from "$lib/types";
  import { formatScore } from "$lib/utils";
  import { computeRatingPoints } from "$lib/engine";
  import Icon from "@iconify/svelte";

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
    const info = playerInfo[uid];
    if (!info) return uid;
    const display = info.nickname || info.name;
    return info.vekn ? `${display} (${info.vekn})` : display;
  }

  function getStateBadgeClass(state: TournamentState): string {
    switch (state) {
      case "Planned": return "bg-ash-800 text-ash-300";
      case "Registration": return "bg-emerald-900/60 text-emerald-300";
      case "Waiting": return "bg-amber-900/60 text-amber-300";
      case "Playing": return "bg-crimson-900/60 text-crimson-300";
      case "Finished": return "bg-ash-700 text-ash-400";
      default: return "bg-ash-800 text-ash-300";
    }
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
      {registeredCount} player{registeredCount !== 1 ? "s" : ""}
      {#if hasRounds}
        · {tournament.rounds.length} round{tournament.rounds.length !== 1 ? "s" : ""}
      {/if}
      {#if isFinals}
        · Finals in progress
      {/if}
    </span>
  </div>

  <!-- Winner display -->
  {#if tournament.winner}
    <div class="bg-emerald-900/20 border border-emerald-800 rounded-lg p-4">
      <div class="text-ash-500 text-sm">Winner</div>
      <div class="text-xl font-medium text-bone-100">{seatDisplay(tournament.winner)}</div>
    </div>
  {/if}

  <!-- Transition actions (organizer only) -->
  {#if isOrganizer}
    <div class="bg-ash-900/30 rounded-lg p-4 space-y-3">
      <h3 class="text-sm font-medium text-ash-300">Actions</h3>

      {#if tournament.state === "Planned"}
        <button
          onclick={() => doAction("open-registration")}
          disabled={actionLoading}
          class="px-4 py-2 text-sm font-medium text-bone-100 bg-emerald-700 hover:bg-emerald-600 disabled:bg-ash-700 rounded-lg transition-colors"
        >{actionLoading ? "..." : "Open Registration"}</button>

      {:else if tournament.state === "Registration"}
        <div class="flex flex-wrap gap-2">
          <button
            onclick={() => doAction("close-registration")}
            disabled={actionLoading}
            class="px-4 py-2 text-sm font-medium text-bone-100 bg-amber-700 hover:bg-amber-600 disabled:bg-ash-700 rounded-lg transition-colors"
          >Close Registration & Start Check-in</button>
          <button
            onclick={() => doAction("cancel-registration")}
            disabled={actionLoading}
            class="px-3 py-1.5 text-sm text-ash-300 border border-ash-700 hover:border-ash-600 hover:text-ash-200 rounded-lg transition-colors"
          >Back to Planning</button>
        </div>

      {:else if tournament.state === "Waiting"}
        <div class="space-y-2">
          <!-- Guidance -->
          <div class="text-sm text-ash-300">
            {#if hasFinalsCandidate}
              Round {tournament.rounds.length} complete.
              {#if top5HasTies()}
                <span class="text-amber-300">Resolve ties in top 5 before starting finals.</span>
              {:else}
                <span class="text-emerald-300">Finals ready!</span>
              {/if}
            {:else if hasRounds}
              Round {tournament.rounds.length} complete. Check in players for the next round.
            {:else}
              Check in registered players to start.
            {/if}
          </div>

          <div class="flex flex-wrap gap-2">
            <span class="text-sm text-ash-400">{checkedInCount} / {registeredCount - finishedPlayerCount} checked in</span>
          </div>

          <div class="flex flex-wrap gap-2">
            {#if hasRounds}
              <button
                onclick={() => doAction("reset-checkin")}
                disabled={actionLoading}
                class="px-3 py-1.5 text-sm text-ash-300 bg-ash-800 hover:bg-ash-700 rounded-lg transition-colors"
              >Reset Check-In</button>
            {/if}
            <button
              onclick={() => doAction("checkin-all")}
              disabled={actionLoading}
              class="px-3 py-1.5 text-sm text-ash-300 bg-ash-800 hover:bg-ash-700 rounded-lg transition-colors"
            >Check All In</button>
            <button
              onclick={() => doAction("rounds/start")}
              disabled={actionLoading || checkedInCount < 4}
              class="px-4 py-2 text-sm font-medium text-bone-100 bg-emerald-700 hover:bg-emerald-600 disabled:bg-ash-700 rounded-lg transition-colors"
            >Start Round {(tournament.rounds?.length ?? 0) + 1}</button>
            {#if finalsReady}
              <button
                onclick={() => doAction("action", { type: "StartFinals" })}
                disabled={actionLoading}
                class="px-4 py-2 text-sm font-medium text-bone-100 bg-emerald-700 hover:bg-emerald-600 disabled:bg-ash-700 rounded-lg transition-colors"
              >Start Finals</button>
            {/if}
          </div>

          <!-- Seating warnings -->
          {#if [6, 7, 11].includes(checkedInCount)}
            <div class="bg-amber-900/20 border border-amber-800 rounded-lg p-3">
              <p class="text-amber-300 text-sm">{checkedInCount} players cannot be seated (impossible configuration).</p>
            </div>
          {/if}

          <!-- Finish tournament / Reopen registration -->
          <div class="pt-3 border-t border-ash-800 flex flex-wrap gap-2">
            <button
              onclick={() => doAction("finish")}
              disabled={actionLoading}
              class="px-4 py-2 text-sm text-crimson-400 hover:text-crimson-300 border border-crimson-800 hover:border-crimson-700 rounded-lg transition-colors"
            >Finish Tournament</button>
            <button
              onclick={() => doAction("reopen-registration")}
              disabled={actionLoading}
              class="px-3 py-1.5 text-sm text-ash-300 border border-ash-700 hover:border-ash-600 hover:text-ash-200 rounded-lg transition-colors"
            >Reopen Registration</button>
          </div>
        </div>

      {:else if tournament.state === "Playing"}
        <p class="text-ash-400 text-sm">
          {#if isFinals}
            Finals in progress. Manage scoring in the Finals tab.
          {:else}
            Round {tournament.rounds.length} in progress. Manage scoring in the Rounds tab.
          {/if}
        </p>

      {:else if tournament.state === "Finished"}
        <p class="text-ash-400 text-sm">Tournament is finished.</p>
        <div class="flex flex-wrap gap-2 mt-2">
          <button
            onclick={() => doAction("reopen")}
            disabled={actionLoading}
            class="px-3 py-1.5 text-sm text-ash-300 border border-ash-700 hover:border-ash-600 hover:text-ash-200 rounded-lg transition-colors"
          >Reopen Tournament</button>
        </div>
      {/if}
    </div>
  {/if}

  <!-- Summary standings (top 5) -->
  {#if standings.length > 0}
    <div class="bg-ash-900/30 rounded-lg p-4">
      <h3 class="text-sm font-medium text-ash-300 mb-2">Top Standings</h3>
      <table class="w-full text-sm">
        <thead>
          <tr class="text-ash-500 text-xs">
            <th class="text-left py-1 pr-2">#</th>
            <th class="text-left py-1 pr-2">Player</th>
            <th class="text-right py-1 px-2">Score</th>
            {#if hasFinals}
              <th class="text-right py-1 px-2">Finals</th>
            {/if}
            {#if isFinished}
              <th class="text-right py-1 px-2">Rating</th>
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
