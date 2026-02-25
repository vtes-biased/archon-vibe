<script lang="ts">
  import type { Tournament } from "$lib/types";
  import { tournamentAction } from "$lib/api";
  import { showToast } from "$lib/stores/toast.svelte";
  import { Plus, X, ChevronUp, ChevronDown } from "lucide-svelte";
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

  let saving = $state(false);

  async function save() {
    // Validate
    for (const room of rooms) {
      if (!room.name.trim()) return;
      if (room.count < 1) return;
    }
    saving = true;
    try {
      const cleaned = rooms.map(r => ({ name: r.name.trim(), count: r.count }));
      const updated = await tournamentAction(tournamentUid, 'UpdateConfig', { config: { table_rooms: cleaned } });
      onupdate(updated);
    } catch {
      showToast({ type: "error", message: "Failed to save rooms" });
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
      <span class="text-xs text-ash-500">{m.rooms_total({ count: String(totalCount) })}</span>
    </div>
  {/if}

  {#if rooms.length > 0}
    <div class="space-y-2 mb-3">
      {#each rooms as room, i}
        <div class="flex items-center gap-2">
          <div class="flex flex-col gap-0.5">
            <button
              onclick={() => moveUp(i)}
              disabled={i === 0 || saving}
              class="p-0.5 text-ash-500 hover:text-bone-100 disabled:opacity-40 transition-colors"
              aria-label="Move up"
            ><ChevronUp class="w-3.5 h-3.5" /></button>
            <button
              onclick={() => moveDown(i)}
              disabled={i === rooms.length - 1 || saving}
              class="p-0.5 text-ash-500 hover:text-bone-100 disabled:opacity-40 transition-colors"
              aria-label="Move down"
            ><ChevronDown class="w-3.5 h-3.5" /></button>
          </div>
          <input
            type="text"
            bind:value={room.name}
            onblur={() => handleNameBlur(i)}
            placeholder={m.rooms_name()}
            maxlength={50}
            class="flex-1 min-w-0 px-2 py-1 text-sm bg-ash-900 border border-ash-700 rounded text-bone-100 placeholder-ash-600 focus:border-crimson-600 focus:outline-none"
          />
          <input
            type="number"
            bind:value={room.count}
            onchange={handleCountChange}
            min={1}
            max={99}
            class="w-16 px-2 py-1 text-sm bg-ash-900 border border-ash-700 rounded text-bone-100 text-center focus:border-crimson-600 focus:outline-none"
          />
          <button
            onclick={() => removeRoom(i)}
            disabled={saving}
            class="p-1 text-ash-500 hover:text-crimson-400 transition-colors"
            aria-label="Remove room"
          ><X class="w-4 h-4" /></button>
        </div>
      {/each}
    </div>
    <p class="text-xs text-ash-500 mb-2">{m.rooms_hint()}</p>
  {/if}

  <button
    onclick={addRoom}
    disabled={saving}
    class="flex items-center gap-1 text-sm text-ash-400 hover:text-bone-100 transition-colors"
  >
    <Plus class="w-4 h-4" />
    {m.rooms_add()}
  </button>
</div>
