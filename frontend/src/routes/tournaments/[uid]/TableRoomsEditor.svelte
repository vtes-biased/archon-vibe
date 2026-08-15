<script lang="ts">
  import type { Tournament } from "$lib/types";
  import { tournamentAction } from "$lib/tournament-actions";
  import { showToast } from "$lib/stores/toast.svelte";
  import { Plus, X, ChevronUp, ChevronDown } from "@lucide/svelte";
  import * as m from '$lib/paraglide/messages.js';

  let {
    tournamentUid,
    tableRooms,
    onupdate,
  }: {
    tournamentUid: string;
    tableRooms: { name: string; count: number }[];
    onupdate: (tournament: Tournament) => void;
  } = $props();

  // svelte-ignore state_referenced_locally
  const initialRooms = tableRooms;
  let rooms = $state<{ name: string; count: number }[]>(
    initialRooms?.length ? initialRooms.map(r => ({ ...r })) : []
  );

  const totalCount = $derived(rooms.reduce((sum, r) => sum + r.count, 0));

  // Cleared count binds to null; name may be blank on a fresh row. Saving is
  // suspended while any row is invalid — say so instead of silently no-oping.
  const hasInvalidRow = $derived(rooms.some(r => !r.name.trim() || !(r.count >= 1)));

  let saving = $state(false);

  async function save() {
    if (hasInvalidRow) return;
    saving = true;
    try {
      const cleaned = rooms.map(r => ({ name: r.name.trim(), count: r.count }));
      const updated = await tournamentAction(tournamentUid, 'UpdateConfig', { config: { table_rooms: cleaned } });
      onupdate(updated);
    } catch {
      showToast({ type: "error", message: m.table_rooms_error_save() });
    } finally {
      saving = false;
    }
  }

  function addRoom() {
    rooms = [...rooms, { name: "", count: 1 }];
  }

  function removeRoom(index: number) {
    rooms = rooms.filter((_, i) => i !== index);
    save();
  }

  function moveUp(index: number) {
    if (index === 0) return;
    const copy = [...rooms];
    [copy[index - 1], copy[index]] = [copy[index]!, copy[index - 1]!];
    rooms = copy;
    save();
  }

  function moveDown(index: number) {
    if (index >= rooms.length - 1) return;
    const copy = [...rooms];
    [copy[index], copy[index + 1]] = [copy[index + 1]!, copy[index]!];
    rooms = copy;
    save();
  }

  function handleNameBlur(index: number) {
    if (rooms[index]?.name.trim()) save();
  }

  function handleCountChange() {
    save();
  }
</script>

<div>
  {#if rooms.length > 0}
    <div class="flex items-center justify-end mb-2">
      <span class="text-xs text-ink-faint">{m.rooms_total({ count: String(totalCount) })}</span>
    </div>
  {/if}

  {#if rooms.length > 0}
    <div class="space-y-2 mb-3">
      {#each rooms as room, i}
        <!-- Side-by-side 44px reorder + remove targets (wiki/design.md touch floor) -->
        <div class="flex items-center gap-1">
          <button
            onclick={() => moveUp(i)}
            disabled={i === 0 || saving}
            class="min-w-[44px] min-h-[44px] flex items-center justify-center text-ink-faint hover:text-ink-strong disabled:opacity-40 transition-colors"
            aria-label={m.rooms_move_up()}
          ><ChevronUp class="w-4 h-4" /></button>
          <button
            onclick={() => moveDown(i)}
            disabled={i === rooms.length - 1 || saving}
            class="min-w-[44px] min-h-[44px] flex items-center justify-center text-ink-faint hover:text-ink-strong disabled:opacity-40 transition-colors"
            aria-label={m.rooms_move_down()}
          ><ChevronDown class="w-4 h-4" /></button>
          <input
            type="text"
            bind:value={room.name}
            onblur={() => handleNameBlur(i)}
            placeholder={m.rooms_name()}
            maxlength={50}
            class="flex-1 min-w-0 px-2 py-1 min-h-[44px] text-sm bg-surface-muted border rounded text-ink-strong placeholder-ink-faint focus:border-accent-strong-hover focus:outline-none {room.name.trim() ? 'border-line-strong' : 'border-warn'}"
          />
          <input
            type="number"
            bind:value={room.count}
            onchange={handleCountChange}
            min={1}
            max={99}
            class="w-16 px-2 py-1 min-h-[44px] text-sm bg-surface-muted border rounded text-ink-strong text-center focus:border-accent-strong-hover focus:outline-none {room.count >= 1 ? 'border-line-strong' : 'border-warn'}"
          />
          <button
            onclick={() => removeRoom(i)}
            disabled={saving}
            class="min-w-[44px] min-h-[44px] flex items-center justify-center text-ink-faint hover:text-link transition-colors"
            aria-label={m.rooms_remove()}
          ><X class="w-4 h-4" /></button>
        </div>
      {/each}
    </div>
    {#if hasInvalidRow}
      <p class="text-xs text-warn mb-2">{m.rooms_validation_hint()}</p>
    {/if}
    <p class="text-xs text-ink-faint mb-2">{m.rooms_hint()}</p>
  {:else}
    <p class="text-xs text-ink-faint mb-2">{m.rooms_empty_state()}</p>
  {/if}

  <button
    onclick={addRoom}
    disabled={saving}
    class="flex items-center gap-1 min-h-[44px] text-sm text-ink-muted hover:text-ink-strong transition-colors"
  >
    <Plus class="w-4 h-4" />
    {m.rooms_add()}
  </button>
</div>
