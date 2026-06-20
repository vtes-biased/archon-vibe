<script lang="ts">
  import type { Tournament } from "$lib/types";
  import { timerStart, timerPause, timerReset, timerAddTime } from "$lib/api";
  import { Play, Pause, RotateCcw, Clock } from "@lucide/svelte";
  import Button from '$lib/components/Button.svelte';
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
    return Math.max(0, elapsed);
  });

  const baseRemaining = $derived(Math.max(0, roundTime - baseElapsed));

  // Per-table remaining (includes extensions)
  const tableRemaining = $derived.by(() => {
    if (tableIndex == null) return baseRemaining;
    const key = String(tableIndex);
    const extra = tournament.table_extra_time?.[key] ?? 0;
    return Math.max(0, roundTime - baseElapsed + extra);
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

  const tableKey = $derived(tableIndex != null ? String(tableIndex) : "");
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
</script>

{#if timerActive}
  <div class="flex flex-col items-center gap-2">
    <!-- Timer display -->
    <div class="flex items-center gap-2">
      <Clock class="w-4 h-4 {expired ? 'text-crimson-400' : warning ? 'text-amber-400' : 'text-emerald-400'}" />
      <span class="font-mono text-2xl font-bold tabular-nums {expired ? 'text-crimson-400 animate-pulse' : warning ? 'text-amber-400' : 'text-emerald-400'}">
        {#if expired}
          -{formatTime(baseElapsed - roundTime - (tableIndex != null ? (tournament.table_extra_time?.[tableKey] ?? 0) : 0))}
        {:else}
          {formatTime(displaySeconds)}
        {/if}
      </span>
      {#if isPaused && baseElapsed > 0}
        <span class="text-xs badge-amber px-1.5 py-0.5 rounded">{m.timer_paused()}</span>
      {/if}
    </div>

    <!-- Table extensions info -->
    {#if tableIndex != null && tableExtraTime > 0}
      <div class="text-xs text-ash-400 flex items-center gap-2">
        <span>+{Math.floor(tableExtraTime / 60)}:{(tableExtraTime % 60).toString().padStart(2, '0')} {m.timer_extra_time()}</span>
      </div>
    {/if}

    <!-- Organizer global controls -->
    {#if isOrganizer && tableIndex == null}
      <div class="flex items-center gap-2">
        {#if isPaused}
          <Button variant="primary" size="sm" onclick={doStart} disabled={loading} title={m.timer_start()}>
            <Play class="w-3 h-3" /> {m.timer_start()}
          </Button>
        {:else}
          <Button variant="secondary" size="sm" onclick={doPause} disabled={loading} title={m.timer_pause()}>
            <Pause class="w-3 h-3" /> {m.timer_pause()}
          </Button>
        {/if}
        <Button variant="ghost" size="sm" onclick={doReset} disabled={loading} title={m.timer_reset()}>
          <RotateCcw class="w-3 h-3" /> {m.timer_reset()}
        </Button>
      </div>
    {/if}

    <!-- Organizer per-table controls -->
    {#if isOrganizer && tableIndex != null}
      <div class="flex items-center gap-1 flex-wrap">
        {#each [60, 120, 180, 300] as secs}
          <Button variant="ghost" size="sm" onclick={() => doAddTime(secs)} disabled={loading || tableExtraTime + secs > 600}>
            +{secs / 60}min
          </Button>
        {/each}
      </div>
    {/if}
  </div>
{/if}
