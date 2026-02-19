<script lang="ts">
  import { GripVertical, CircleAlert } from "lucide-svelte";
  import { seatDisplay as seatDisplayUtil, resolveTableLabel } from "$lib/tournament-utils";
  import * as m from '$lib/paraglide/messages.js';
  import { onMount } from 'svelte';

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

  // Drag state
  let dragOrigin: { table: number; seat: number } | null = $state(null);
  let scrollDirection = 0;
  let scrollInterval: ReturnType<typeof setInterval> | null = null;
  let scrollHandler: ((ev: DragEvent) => void) | null = null;

  // Touch polyfill (side-effect import)
  onMount(async () => {
    // @ts-ignore -- side-effect import, no types needed
    await import('@dragdroptouch/drag-drop-touch');
  });

  function handleDragStart(e: DragEvent, tableIdx: number, seatIdx: number) {
    dragOrigin = { table: tableIdx, seat: seatIdx };
    if (e.dataTransfer) {
      e.dataTransfer.effectAllowed = 'move';
      e.dataTransfer.setData('text/plain', '');
    }
    // Auto-scroll
    scrollHandler = (ev: DragEvent) => {
      const vh = window.innerHeight;
      if (ev.clientY < 60) scrollDirection = -1;
      else if (ev.clientY > vh - 60) scrollDirection = 1;
      else scrollDirection = 0;
    };
    document.addEventListener('dragover', scrollHandler);
    scrollInterval = setInterval(() => {
      if (scrollDirection !== 0) window.scrollTo(0, window.scrollY + scrollDirection * 12);
    }, 16);
  }

  function handleDragEnter(e: DragEvent, tableIdx: number, seatIdx: number) {
    e.preventDefault();
    if (!dragOrigin) return;
    if (dragOrigin.table === tableIdx && dragOrigin.seat === seatIdx) return;

    if (dragOrigin.table === tableIdx) {
      // Same table: only swap with adjacent (continuous reorder)
      if (Math.abs(seatIdx - dragOrigin.seat) !== 1) return;
      const t = tables[tableIdx]!;
      [t[dragOrigin.seat], t[seatIdx]] = [t[seatIdx]!, t[dragOrigin.seat]!];
      dragOrigin = { table: tableIdx, seat: seatIdx };
    } else {
      // Cross table: simple swap
      const src = tables[dragOrigin.table]!;
      const dst = tables[tableIdx]!;
      [src[dragOrigin.seat], dst[seatIdx]] = [dst[seatIdx]!, src[dragOrigin.seat]!];
      dragOrigin = { table: tableIdx, seat: seatIdx };
    }
    // Trigger Svelte reactivity
    tables = [...tables];
  }

  function handleDragOver(e: DragEvent) {
    e.preventDefault();
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'move';
  }

  function handleDragEnd() {
    dragOrigin = null;
    // Cleanup auto-scroll
    if (scrollHandler) {
      document.removeEventListener('dragover', scrollHandler);
      scrollHandler = null;
    }
    if (scrollInterval) {
      clearInterval(scrollInterval);
      scrollInterval = null;
    }
    scrollDirection = 0;
    onchange();
  }

  function seatDisplay(uid: string): string {
    return seatDisplayUtil(uid, playerInfo);
  }

  const RULE_LABELS: Record<number, () => string> = {
    0: () => m.rounds_r1(), 1: () => m.rounds_r2(), 2: () => m.rounds_r3(),
    3: () => m.rounds_r4(), 4: () => m.rounds_r5(), 5: () => m.rounds_r6(),
    6: () => m.rounds_r7(), 7: () => m.rounds_r8(), 8: () => m.rounds_r9(),
  };

  function issueColor(level: number): string {
    if (level === 0) return 'text-crimson-400';
    if (level <= 6) return 'text-amber-400';
    return 'text-sky-400';
  }
</script>

{#each tables as table, t}
  <div class="bg-ash-900/50 rounded-lg p-4">
    <h3 class="text-sm font-medium text-bone-100 mb-2">
      {isFinals ? m.finals_table() : resolveTableLabel(tableRooms, t) ?? m.rounds_table_n({ n: String(t + 1) })}
    </h3>
    <div class="divide-y divide-ash-800">
      {#each table as uid, s (uid)}
        {@const issue = playerIssues.get(uid)}
        {@const isDragging = dragOrigin?.table === t && dragOrigin?.seat === s}
        <div
          class="seat-row py-1.5 flex items-center gap-2 text-sm {isDragging ? 'opacity-50' : ''}"
          role="listitem"
          ondragenter={(e) => handleDragEnter(e, t, s)}
          ondragover={handleDragOver}
        >
          <!-- Drag handle -->
          <span
            class="drag-handle flex items-center justify-center text-ash-500"
            draggable="true"
            ondragstart={(e) => handleDragStart(e, t, s)}
            ondragend={handleDragEnd}
          >
            <GripVertical class="w-5 h-5" />
          </span>
          <!-- Player name -->
          <span class="flex-1 text-ash-300">{seatDisplay(uid)}</span>
          <!-- Issue indicator -->
          {#if issue}
            <span class="inline-flex items-center gap-1 {issueColor(issue.level)}" title={issue.message}>
              <CircleAlert class="w-4 h-4 shrink-0" />
              <span class="text-xs">{issue.message}</span>
            </span>
          {/if}
        </div>
      {/each}
    </div>
  </div>
{/each}
