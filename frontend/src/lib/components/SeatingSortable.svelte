<script lang="ts">
  import { CircleAlert, ArrowRightLeft, X } from "@lucide/svelte";
  import { seatDisplay as seatDisplayUtil, resolveTableLabel } from "$lib/tournament-utils";
  import * as m from '$lib/paraglide/messages.js';
  import { tick } from 'svelte';

  let {
    tables = $bindable(),
    playerInfo,
    playerIssues,
    isFinals = false,
    tableRooms,
    onchange,
  }: {
    tables: string[][];
    playerInfo: Record<string, { name: string; nickname: string | null; vekn: string | null }>;
    playerIssues: Map<string, { level: number; message: string }>;
    isFinals: boolean;
    tableRooms?: { name: string; count: number }[];
    onchange: () => void;
  } = $props();

  // Tap-to-rearrange: select a seat, then tap another seat to swap (same table
  // = reorder, other table = cross-table swap) or an open seat to move. No drag.
  let selected: { table: number; seat: number } | null = $state(null);
  // Polite screen-reader announcement of the last selection/swap/move.
  let announce = $state('');

  function seatDisplay(uid: string): string {
    return seatDisplayUtil(uid, playerInfo);
  }

  function tableLabel(t: number): string {
    return resolveTableLabel(tableRooms, t) ?? m.rounds_table_n({ n: String(t + 1) });
  }

  // Restore keyboard focus to the moved player's new seat after the list reflows.
  async function focusSeat(uid: string) {
    await tick();
    const el = document.querySelector(`[data-seat-uid="${uid}"]`);
    if (el instanceof HTMLElement) el.focus();
  }

  function clearSelection() {
    selected = null;
    announce = '';
  }

  function tapSeat(t: number, s: number) {
    const uid = tables[t]![s]!;
    if (!selected) {
      selected = { table: t, seat: s };
      announce = isFinals
        ? m.rounds_seating_moving_finals({ name: seatDisplay(uid) })
        : m.rounds_seating_moving({ name: seatDisplay(uid) });
      return;
    }
    if (selected.table === t && selected.seat === s) {
      clearSelection(); // re-tap to deselect
      return;
    }
    const src = tables[selected.table]!;
    const dst = tables[t]!;
    const movingUid = src[selected.seat]!;
    const targetUid = dst[s]!;
    [src[selected.seat], dst[s]] = [targetUid, movingUid];
    announce = m.rounds_seating_swapped({ a: seatDisplay(movingUid), b: seatDisplay(targetUid) });
    selected = null;
    tables = [...tables];
    onchange();
    focusSeat(movingUid);
  }

  function tapOpenSeat(t: number) {
    if (!selected || selected.table === t || tables[t]!.length >= 5) return;
    const src = tables[selected.table]!;
    const [movingUid] = src.splice(selected.seat, 1);
    tables[t]!.push(movingUid!);
    announce = m.rounds_seating_moved({ name: seatDisplay(movingUid!), table: tableLabel(t) });
    selected = null;
    tables = [...tables];
    onchange();
    focusSeat(movingUid!);
  }

  function issueColor(level: number): string {
    if (level === 0) return 'text-link';
    if (level <= 6) return 'text-purple-400';
    return 'text-sky-400';
  }
</script>

<svelte:window onkeydown={(e) => { if (e.key === 'Escape' && selected) { e.preventDefault(); clearSelection(); } }} />

<div aria-live="polite" class="sr-only">{announce}</div>

{#if selected}
  {@const selName = seatDisplay(tables[selected.table]?.[selected.seat] ?? '')}
  <div class="sticky top-2 z-10 mb-3 flex items-center justify-between gap-2 bg-surface-hover border border-blue-700 rounded-lg px-3 py-2 text-sm shadow-lg">
    <span class="text-blue-300">
      {isFinals ? m.rounds_seating_moving_finals({ name: selName }) : m.rounds_seating_moving({ name: selName })}
    </span>
    <button
      type="button"
      onclick={clearSelection}
      class="inline-flex items-center gap-1 shrink-0 text-ink hover:text-ink-strong"
    >
      <X class="w-4 h-4" />{m.common_cancel()}
    </button>
  </div>
{/if}

{#each tables as table, t}
  <div class="bg-surface-muted/50 rounded-lg p-4">
    <h3 class="text-sm font-medium text-ink-strong mb-2 flex items-center gap-2">
      {isFinals ? m.finals_table() : tableLabel(t)}
      {#if !isFinals && table.length > 0 && table.length < 4}
        <span class="text-xs font-normal text-link">{m.rounds_n_players({ count: String(table.length) })}</span>
      {/if}
    </h3>
    <div class="divide-y divide-line">
      {#each table as uid, s (uid)}
        {@const issue = playerIssues.get(uid)}
        {@const isSelected = selected?.table === t && selected?.seat === s}
        {@const isSwapTarget = selected != null && !isSelected}
        <button
          type="button"
          data-seat-uid={uid}
          onclick={() => tapSeat(t, s)}
          aria-pressed={isSelected}
          aria-label={m.rounds_seat_n({ n: String(s + 1), name: seatDisplay(uid) })}
          class="w-full min-h-[44px] py-1.5 px-1 -mx-1 flex items-center gap-2 text-sm text-left rounded transition-colors
            {isSelected ? 'ring-2 ring-blue-500 bg-blue-900/30' : isSwapTarget ? 'ring-1 ring-inset ring-blue-800/50 hover:bg-blue-900/20' : 'hover:bg-surface-hover/60'}"
        >
          <span class="w-5 text-center text-xs text-ink-faint tabular-nums">{s + 1}</span>
          <span class="flex-1 text-ink">{seatDisplay(uid)}</span>
          {#if issue}
            <span class="inline-flex items-center gap-1 {issueColor(issue.level)}" title={issue.message}>
              <CircleAlert class="w-4 h-4 shrink-0" />
              <span class="text-xs">{issue.message}</span>
            </span>
          {:else}
            <ArrowRightLeft class="w-4 h-4 shrink-0 {isSelected ? 'text-blue-400' : 'text-ink-faint'}" />
          {/if}
        </button>
      {/each}
      {#if !isFinals && table.length < 5}
        {@const canMoveHere = selected != null && selected.table !== t}
        {#if canMoveHere}
          <button
            type="button"
            onclick={() => tapOpenSeat(t)}
            class="w-full py-3 min-h-[44px] flex items-center justify-center gap-1.5 text-xs border border-dashed border-blue-500 text-blue-300 hover:bg-blue-900/30 rounded mt-1.5 transition-colors"
          >
            <ArrowRightLeft class="w-3.5 h-3.5" />{m.rounds_seating_move_here()}
          </button>
        {:else}
          <div class="w-full py-3 min-h-[44px] flex items-center justify-center text-xs border border-dashed border-line-strong text-ink-faint rounded mt-1.5">
            {m.rounds_seating_open_seat()}
          </div>
        {/if}
      {/if}
    </div>
  </div>
{/each}
