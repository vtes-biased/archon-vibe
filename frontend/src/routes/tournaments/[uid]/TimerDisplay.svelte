<script lang="ts">
  import type { Tournament } from "$lib/types";
  import { timerStart, timerPause, timerReset, timerAddTime } from "$lib/api";
  import { activateClock, getClockOffset, getClockSkewAdvisory } from "$lib/stores/clock.svelte";
  import { Play, Pause, RotateCcw, Clock, TriangleAlert } from "@lucide/svelte";
  import Button from '$lib/components/Button.svelte';
  import ConfirmActionModal from '$lib/components/ConfirmActionModal.svelte';
  import * as m from '$lib/paraglide/messages.js';

  // VEKN sets no cap on judge-granted extra time; 30 min is a sanity bound,
  // not a rules limit. Mirrored server-side (timer/add-time).
  const MAX_EXTRA_TIME = 1800;

  let {
    tournament,
    isOrganizer = false,
    tableIndex,
    finals = false,
    showAdvisory = true,
  }: {
    tournament: Tournament;
    isOrganizer?: boolean;
    tableIndex?: number;
    finals?: boolean;
    // Suppress the device-clock advisory on secondary per-table timers so it
    // renders once per view, not once per table (RoundsTab's per-table copies).
    showAdvisory?: boolean;
  } = $props();

  // Keep the server-clock offset synced while any timer is on screen (see the
  // clock store): corrects Date.now()'s skew so a mis-set
  // device clock doesn't show phantom elapsed time.
  $effect(() => activateClock());

  // The final is a single table (index 0): its widget needs BOTH the global
  // start/pause/reset controls and per-table time extensions, so it counts down
  // finals_time (via roundTime below) with the finals-table extension applied.
  const effTableIndex = $derived(finals ? 0 : tableIndex);

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
      // (now + offset) aligns the client wall clock with the server clock that
      // stamped started_at, so a skewed device clock cancels out.
      elapsed += (now + getClockOffset() - new Date(t.started_at).getTime()) / 1000;
    }
    return Math.max(0, elapsed);
  });

  const baseRemaining = $derived(Math.max(0, roundTime - baseElapsed));

  // Per-table remaining (includes extensions)
  const tableRemaining = $derived.by(() => {
    if (effTableIndex == null) return baseRemaining;
    const key = String(effTableIndex);
    const extra = tournament.table_extra_time?.[key] ?? 0;
    return Math.max(0, roundTime - baseElapsed + extra);
  });

  const displaySeconds = $derived(effTableIndex != null ? tableRemaining : baseRemaining);
  const expired = $derived(displaySeconds <= 0 && baseElapsed > 0);
  const warning = $derived(displaySeconds > 0 && displaySeconds <= 300); // <5 min

  function formatTime(secs: number): string {
    const total = Math.ceil(secs);
    const m = Math.floor(total / 60);
    const s = total % 60;
    return `${m}:${s.toString().padStart(2, '0')}`;
  }

  const tableKey = $derived(effTableIndex != null ? String(effTableIndex) : "");
  const tableExtraTime = $derived(tableKey ? (tournament.table_extra_time?.[tableKey] ?? 0) : 0);
  const isPaused = $derived(tournament.timer?.paused ?? true);

  // Non-blocking notice when THIS device's clock is far enough off that the user
  // should fix it (it also breaks their auth-token timing/calendar). The timer
  // itself is already corrected via the offset — this just surfaces the fault.
  const clockSkewMs = $derived(showAdvisory ? getClockSkewAdvisory() : null);
  const clockSkewLabel = $derived.by(() => {
    if (clockSkewMs == null) return "";
    const s = Math.round(Math.abs(clockSkewMs) / 1000);
    return s >= 60 ? `${Math.floor(s / 60)}:${(s % 60).toString().padStart(2, "0")}` : `${s}s`;
  });

  async function doStart() {
    loading = true;
    try { await timerStart(tournament.uid); } catch {} finally { loading = false; }
  }
  async function doPause() {
    loading = true;
    try { await timerPause(tournament.uid); } catch {} finally { loading = false; }
  }
  // Reset wipes the round clock for every table with no undo — confirm first
  // (it sits one tap away from Pause).
  let showResetConfirm = $state(false);
  async function doReset() {
    loading = true;
    try { await timerReset(tournament.uid); } finally { loading = false; }
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
      <Clock class="w-4 h-4 {expired ? 'text-link' : warning ? 'text-warn' : 'text-info'}" />
      <span class="font-mono text-2xl font-bold tabular-nums {expired ? 'text-link animate-pulse' : warning ? 'text-warn' : 'text-info'}">
        {#if expired}
          -{formatTime(baseElapsed - roundTime - (effTableIndex != null ? (tournament.table_extra_time?.[tableKey] ?? 0) : 0))}
        {:else}
          {formatTime(displaySeconds)}
        {/if}
      </span>
      {#if isPaused && baseElapsed > 0}
        <span class="text-xs badge-pending px-1.5 py-0.5 rounded">{m.timer_paused()}</span>
      {/if}
    </div>

    <!-- Table extensions info -->
    {#if effTableIndex != null && tableExtraTime > 0}
      <div class="text-xs text-ink-muted flex items-center gap-2">
        <span>+{Math.floor(tableExtraTime / 60)}:{(tableExtraTime % 60).toString().padStart(2, '0')} {m.timer_extra_time()}</span>
      </div>
    {/if}

    <!-- Organizer global controls (also for the single-table final) -->
    {#if isOrganizer && (tableIndex == null || finals)}
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
        <Button variant="ghost" size="sm" onclick={() => (showResetConfirm = true)} disabled={loading} title={m.timer_reset()}>
          <RotateCcw class="w-3 h-3" /> {m.timer_reset()}
        </Button>
      </div>
    {/if}

    <!-- Organizer per-table controls (time extensions) -->
    {#if isOrganizer && effTableIndex != null}
      <div class="flex items-center gap-1 flex-wrap">
        {#each [60, 120, 300, 600] as secs}
          <Button variant="ghost" size="sm" onclick={() => doAddTime(secs)} disabled={loading || tableExtraTime + secs > MAX_EXTRA_TIME}>
            +{secs / 60}min
          </Button>
        {/each}
      </div>
    {/if}

    <!-- Device-clock advisory (the timer stays corrected; this nudges a fix).
         role=status: it appears async after the first sync resolves, so a live
         region is what announces it to screen readers. -->
    {#if clockSkewMs != null}
      <div role="status" class="text-xs text-warn flex items-center gap-1.5 text-center max-w-xs">
        <TriangleAlert class="w-3.5 h-3.5 shrink-0" aria-hidden="true" />
        <span>{m.timer_clock_skew_advisory({ amount: clockSkewLabel })}</span>
      </div>
    {/if}
  </div>
{/if}

{#if showResetConfirm}
  <ConfirmActionModal
    title={m.timer_reset_confirm_title()}
    body={m.timer_reset_confirm_body()}
    confirmLabel={m.timer_reset()}
    action={doReset}
    reportResult={false}
    onClose={() => (showResetConfirm = false)}
  />
{/if}
