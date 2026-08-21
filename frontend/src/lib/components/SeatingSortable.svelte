<script lang="ts">
  import { OctagonX, TriangleAlert, Info, ArrowRightLeft, X, RotateCcw, UserMinus, Plus } from "@lucide/svelte";
  import { seatDisplay as seatDisplayUtil } from "$lib/tournament-utils";
  import { tableLabel as tableLabelUtil } from "$lib/engine";
  import * as m from '$lib/paraglide/messages.js';
  import { tick } from 'svelte';

  let {
    tables = $bindable(),
    playerInfo,
    playerIssues,
    isFinals = false,
    tableRooms,
    online = false,
    pool = [],
    onchange,
  }: {
    tables: string[][];
    playerInfo: Record<string, { name: string; nickname: string | null; vekn: string | null; display_name?: string | null }>;
    playerIssues: Map<string, { level: number; message: string }>;
    isFinals: boolean;
    tableRooms?: { name: string; count: number }[];
    online?: boolean;
    pool?: { uid: string; note: string }[];
    onchange: () => void;
  } = $props();

  // The finals player set is fixed by the card-drawing ritual, so the draft
  // there rearranges only.
  const canEditPlayerSet = $derived(!isFinals);
  let poolTarget = $state<number | null>(null);

  // Tap-to-rearrange: select a seat, then tap another seat to swap (same table
  // = reorder, other table = cross-table swap) or an open seat to move. No drag.
  let selected: { table: number; seat: number } | null = $state(null);
  // Polite screen-reader announcement of the last selection/swap/move.
  let announce = $state('');

  function seatDisplay(uid: string): string {
    return seatDisplayUtil(uid, playerInfo, online);
  }

  function tableLabel(t: number): string {
    return tableLabelUtil(tableRooms, t) ?? m.rounds_table_n({ n: String(t + 1) });
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

  // Per-move undo: snapshot before each swap/move, so one wrong tap doesn't force Cancel (which
  // discards ALL draft moves). Component remounts per alter session, so the stack scopes itself.
  let undoStack = $state<string[][][]>([]);
  function snapshot() {
    undoStack = [...undoStack, tables.map(t => [...t])];
  }
  function undo() {
    const prev = undoStack.at(-1);
    if (!prev) return;
    undoStack = undoStack.slice(0, -1);
    tables = prev.map(t => [...t]);
    selected = null;
    announce = m.rounds_seating_undone();
    onchange();
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
    snapshot();
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

  function unseat(t: number, s: number) {
    snapshot();
    const [uid] = tables[t]!.splice(s, 1);
    selected = null;
    tables = [...tables];
    announce = m.rounds_seating_unseated({ name: seatDisplay(uid!) });
    onchange();
  }

  function seatFromPool(t: number, uid: string) {
    if (tables[t]!.length >= 5) return;
    snapshot();
    tables[t]!.push(uid);
    poolTarget = null;
    tables = [...tables];
    announce = m.rounds_seating_seated({ name: seatDisplay(uid), table: tableLabel(t) });
    onchange();
    focusSeat(uid);
  }

  function tapOpenSeat(t: number) {
    if (!selected || selected.table === t || tables[t]!.length >= 5) return;
    snapshot();
    const src = tables[selected.table]!;
    const [movingUid] = src.splice(selected.seat, 1);
    tables[t]!.push(movingUid!);
    announce = m.rounds_seating_moved({ name: seatDisplay(movingUid!), table: tableLabel(t) });
    selected = null;
    tables = [...tables];
    onchange();
    focusSeat(movingUid!);
  }

  // Ordinal seating-issue severity → colour + a shape-distinct icon + screen-reader tier name.
  // `level` is the VEKN rule index: 0 (R1 predator-prey) blocks; lower = more severe.
  type IssueTier = { color: string; Icon: typeof Info; sr: string };
  function issueTier(level: number): IssueTier {
    if (level === 0) return { color: 'text-link', Icon: OctagonX, sr: m.seating_severity_blocking() };
    if (level <= 4) return { color: 'text-highlight', Icon: TriangleAlert, sr: m.seating_severity_strong() };
    return { color: 'text-warn', Icon: Info, sr: m.seating_severity_soft() };
  }
</script>

<svelte:window onkeydown={(e) => { if (e.key === 'Escape' && selected) { e.preventDefault(); clearSelection(); } }} />

<div aria-live="polite" class="sr-only">{announce}</div>

{#if undoStack.length > 0}
  <div class="mb-3">
    <button
      type="button"
      onclick={undo}
      class="inline-flex items-center gap-1 min-h-[44px] px-3 text-sm text-ink border border-line-strong rounded-lg hover:bg-surface-hover/50 hover:text-ink-strong transition-colors"
    >
      <RotateCcw class="w-4 h-4" aria-hidden="true" />
      {m.rounds_seating_undo({ count: String(undoStack.length) })}
    </button>
  </div>
{/if}

{#if selected}
  {@const selName = seatDisplay(tables[selected.table]?.[selected.seat] ?? '')}
  <!-- Sticky resolves against the scrollport, NOT the shell's padding box, so a bare offset here
       parks this behind the status bar under viewport-fit=cover. -->
  <div class="sticky top-[calc(0.5rem+var(--spacing-safe-t))] z-10 mb-3 flex items-center justify-between gap-2 bg-surface-hover border border-select-border rounded-lg px-3 py-2 text-sm shadow-lg">
    <span class="text-select">
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
        <div class="flex items-center gap-1">
          <button
            type="button"
            data-seat-uid={uid}
            onclick={() => tapSeat(t, s)}
            aria-pressed={isSelected}
            aria-label={m.rounds_seat_n({ n: String(s + 1), name: seatDisplay(uid) })}
            class="flex-1 min-h-[44px] py-1.5 px-1 -mx-1 flex items-center gap-2 text-sm text-left rounded transition-colors
              {isSelected ? 'ring-2 ring-select bg-select-soft/40' : isSwapTarget ? 'ring-1 ring-inset ring-select-border hover:bg-select-soft/20' : 'hover:bg-surface-hover/60'}"
          >
            <span class="w-5 text-center text-xs text-ink-faint tabular-nums">{s + 1}</span>
            <span class="flex-1 text-ink">{seatDisplay(uid)}</span>
            {#if issue}
              {@const tier = issueTier(issue.level)}
              {@const TierIcon = tier.Icon}
              <span class="inline-flex items-center gap-1 {tier.color}" title={issue.message}>
                <TierIcon class="w-4 h-4 shrink-0" aria-hidden="true" />
                <span class="text-xs">{issue.message}</span>
                <span class="sr-only">{tier.sr}</span>
              </span>
            {:else}
              <ArrowRightLeft class="w-4 h-4 shrink-0 {isSelected ? 'text-select' : 'text-ink-faint'}" />
            {/if}
          </button>
          {#if canEditPlayerSet}
            <button
              type="button"
              onclick={() => unseat(t, s)}
              aria-label={m.rounds_seating_unseat({ name: seatDisplay(uid) })}
              title={m.rounds_seating_unseat({ name: seatDisplay(uid) })}
              class="shrink-0 min-h-[44px] px-2 flex items-center text-ink-faint hover:text-link transition-colors"
            >
              <UserMinus class="w-4 h-4" aria-hidden="true" />
            </button>
          {/if}
        </div>
      {/each}
      {#if !isFinals && table.length < 5}
        {@const canMoveHere = selected != null && selected.table !== t}
        {#if canMoveHere}
          <button
            type="button"
            onclick={() => tapOpenSeat(t)}
            class="w-full py-3 min-h-[44px] flex items-center justify-center gap-1.5 text-xs border border-dashed border-select text-select hover:bg-select-soft/30 rounded mt-1.5 transition-colors"
          >
            <ArrowRightLeft class="w-3.5 h-3.5" />{m.rounds_seating_move_here()}
          </button>
        {:else if poolTarget === t}
          <div class="mt-1.5 flex flex-wrap items-center gap-2">
            {#each pool as entry (entry.uid)}
              <button
                type="button"
                onclick={() => seatFromPool(t, entry.uid)}
                class="inline-flex items-center gap-1.5 min-h-[44px] px-3 text-sm border border-select-border text-ink rounded-lg hover:bg-select-soft/30 hover:text-ink-strong transition-colors"
              >
                {seatDisplay(entry.uid)}
                {#if entry.note}<span class="text-xs text-ink-faint">{entry.note}</span>{/if}
              </button>
            {/each}
            <button
              type="button"
              onclick={() => (poolTarget = null)}
              class="inline-flex items-center gap-1 min-h-[44px] px-2 text-sm text-ink hover:text-ink-strong"
            >
              <X class="w-4 h-4" aria-hidden="true" />{m.common_cancel()}
            </button>
          </div>
        {:else}
          <div class="w-full flex items-center gap-2 mt-1.5">
            <div class="flex-1 py-3 min-h-[44px] flex items-center justify-center text-xs border border-dashed border-line-strong text-ink-faint rounded">
              {m.rounds_seating_open_seat()}
            </div>
            {#if canEditPlayerSet && pool.length > 0}
              <button
                type="button"
                onclick={() => (poolTarget = t)}
                class="shrink-0 py-3 min-h-[44px] px-3 flex items-center gap-1.5 text-xs border border-dashed border-line-strong text-ink hover:bg-surface-hover/50 hover:text-ink-strong rounded transition-colors"
              >
                <Plus class="w-3.5 h-3.5" aria-hidden="true" />{m.rounds_seating_add_player({ count: String(pool.length) })}
              </button>
            {/if}
          </div>
        {/if}
      {/if}
    </div>
  </div>
{/each}
