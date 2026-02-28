<script lang="ts">
  import type { Tournament, TimeExtensionPolicy } from "$lib/types";
  import { timerStart, timerPause, timerReset, timerAddTime, timerClockStop, timerClockResume } from "$lib/api";
  import { Play, Pause, RotateCcw, Clock, PauseCircle, PlayCircle } from "lucide-svelte";
  import * as m from '$lib/paraglide/messages.js';

  let {
    tournament,
    isOrganizer = false,
    tableIndex,
  }: {
    tournament: Tournament;
    isOrganizer?: boolean;
    tableIndex?: number;
  } = $props();

  let now = $state(Date.now());
  let loading = $state(false);

  // Tick every second
  $effect(() => {
    const interval = setInterval(() => { now = Date.now(); }, 1000);
    return () => clearInterval(interval);
  });

  const roundTime = $derived(
    tournament.finals != null
      ? (tournament.finals_time || tournament.round_time || 0)
      : (tournament.round_time || 0)
  );

  const timerActive = $derived(roundTime > 0 && tournament.state === "Playing");

  // Base elapsed seconds
  const baseElapsed = $derived.by(() => {
    const t = tournament.timer;
    if (!t) return 0;
    let elapsed = t.elapsed_before_pause;
    if (!t.paused && t.started_at) {
      elapsed += (now - new Date(t.started_at).getTime()) / 1000;
    }
    return elapsed;
  });

  const baseRemaining = $derived(Math.max(0, roundTime - baseElapsed));

  // Per-table remaining (includes extensions)
  const tableRemaining = $derived.by(() => {
    if (tableIndex == null) return baseRemaining;
    const key = String(tableIndex);
    const extra = tournament.table_extra_time?.[key] ?? 0;
    const pausedAt = tournament.table_paused_at?.[key];
    let clockStopBonus = 0;
    if (pausedAt) {
      clockStopBonus = (now - new Date(pausedAt).getTime()) / 1000;
    }
    return Math.max(0, roundTime - baseElapsed + extra + clockStopBonus);
  });

  const displaySeconds = $derived(tableIndex != null ? tableRemaining : baseRemaining);
  const expired = $derived(displaySeconds <= 0 && baseElapsed > 0);
  const warning = $derived(displaySeconds > 0 && displaySeconds <= 300); // <5 min

  function formatTime(secs: number): string {
    const total = Math.ceil(secs);
    const m = Math.floor(total / 60);
    const s = total % 60;
    return `${m}:${s.toString().padStart(2, '0')}`;
  }

  const policy = $derived(tournament.time_extension_policy ?? "additions");
  const showAdditions = $derived(policy === "additions" || policy === "both");
  const showClockStop = $derived(policy === "clock_stop" || policy === "both");
  const tableKey = $derived(tableIndex != null ? String(tableIndex) : "");
  const tableIsPaused = $derived(tableKey ? !!tournament.table_paused_at?.[tableKey] : false);
  const tableExtraTime = $derived(tableKey ? (tournament.table_extra_time?.[tableKey] ?? 0) : 0);
  const isPaused = $derived(tournament.timer?.paused ?? true);

  async function doStart() {
    loading = true;
    try { await timerStart(tournament.uid); } catch {} finally { loading = false; }
  }
  async function doPause() {
    loading = true;
    try { await timerPause(tournament.uid); } catch {} finally { loading = false; }
  }
  async function doReset() {
    loading = true;
    try { await timerReset(tournament.uid); } catch {} finally { loading = false; }
  }
  async function doAddTime(secs: number) {
    loading = true;
    try { await timerAddTime(tournament.uid, tableKey, secs); } catch {} finally { loading = false; }
  }
  async function doClockStop() {
    loading = true;
    try { await timerClockStop(tournament.uid, tableKey); } catch {} finally { loading = false; }
  }
  async function doClockResume() {
    loading = true;
    try { await timerClockResume(tournament.uid, tableKey); } catch {} finally { loading = false; }
  }
</script>

{#if timerActive}
  <div class="flex flex-col items-center gap-2">
    <!-- Timer display -->
    <div class="flex items-center gap-2">
      <Clock class="w-4 h-4 {expired ? 'text-crimson-400' : warning ? 'text-amber-400' : 'text-emerald-400'}" />
      <span class="font-mono text-2xl font-bold tabular-nums {expired ? 'text-crimson-400 animate-pulse' : warning ? 'text-amber-400' : 'text-emerald-400'}">
        {#if expired}
          -{formatTime(baseElapsed - roundTime - (tableIndex != null ? (tournament.table_extra_time?.[tableKey] ?? 0) + (tableIsPaused ? (now - new Date(tournament.table_paused_at![tableKey]!).getTime()) / 1000 : 0) : 0))}
        {:else}
          {formatTime(displaySeconds)}
        {/if}
      </span>
      {#if isPaused && baseElapsed > 0}
        <span class="text-xs badge-amber px-1.5 py-0.5 rounded">{m.timer_paused()}</span>
      {/if}
    </div>

    <!-- Table extensions info -->
    {#if tableIndex != null && (tableExtraTime > 0 || tableIsPaused)}
      <div class="text-xs text-ash-400 flex items-center gap-2">
        {#if tableExtraTime > 0}
          <span>+{Math.floor(tableExtraTime / 60)}:{(tableExtraTime % 60).toString().padStart(2, '0')} {m.timer_extra_time()}</span>
        {/if}
        {#if tableIsPaused}
          <span class="badge-amber px-1.5 py-0.5 rounded">{m.timer_clock_stopped()}</span>
        {/if}
      </div>
    {/if}

    <!-- Organizer global controls -->
    {#if isOrganizer && tableIndex == null}
      <div class="flex items-center gap-2">
        {#if isPaused}
          <button onclick={doStart} disabled={loading} class="px-3 py-1.5 text-xs btn-emerald rounded-lg flex items-center gap-1" title={m.timer_start()}>
            <Play class="w-3 h-3" /> {m.timer_start()}
          </button>
        {:else}
          <button onclick={doPause} disabled={loading} class="px-3 py-1.5 text-xs btn-amber rounded-lg flex items-center gap-1" title={m.timer_pause()}>
            <Pause class="w-3 h-3" /> {m.timer_pause()}
          </button>
        {/if}
        <button onclick={doReset} disabled={loading} class="px-3 py-1.5 text-xs text-ash-400 hover:text-ash-200 border border-ash-700 rounded-lg flex items-center gap-1" title={m.timer_reset()}>
          <RotateCcw class="w-3 h-3" /> {m.timer_reset()}
        </button>
      </div>
    {/if}

    <!-- Organizer per-table controls -->
    {#if isOrganizer && tableIndex != null}
      <div class="flex items-center gap-1 flex-wrap">
        {#if showAdditions}
          {#each [60, 120, 180, 300] as secs}
            <button onclick={() => doAddTime(secs)} disabled={loading || tableExtraTime + secs > 600}
              class="px-2 py-1 text-xs text-ash-300 hover:text-bone-100 border border-ash-700 hover:border-ash-600 rounded transition-colors">
              +{secs / 60}min
            </button>
          {/each}
        {/if}
        {#if showClockStop}
          {#if tableIsPaused}
            <button onclick={doClockResume} disabled={loading}
              class="px-2 py-1 text-xs btn-emerald rounded flex items-center gap-1">
              <PlayCircle class="w-3 h-3" /> {m.timer_clock_resume()}
            </button>
          {:else}
            <button onclick={doClockStop} disabled={loading}
              class="px-2 py-1 text-xs btn-amber rounded flex items-center gap-1">
              <PauseCircle class="w-3 h-3" /> {m.timer_clock_stop()}
            </button>
          {/if}
        {/if}
      </div>
    {/if}
  </div>
{/if}
