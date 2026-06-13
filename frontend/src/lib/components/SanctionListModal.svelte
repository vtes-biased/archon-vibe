<script lang="ts">
  import type { Sanction } from "$lib/types";
  import { deleteSanctionApi } from "$lib/api";
  import { showToast } from "$lib/stores/toast.svelte";
  import SanctionBadge from "./SanctionBadge.svelte";
  import { Trash2 } from "@lucide/svelte";
  import * as m from '$lib/paraglide/messages.js';

  let {
    playerName,
    sanctions,
    tournamentUid,
    canManage,
    onClose,
  }: {
    playerName: string;
    sanctions: Sanction[];
    tournamentUid: string;
    canManage: boolean;
    onClose: () => void;
  } = $props();

  let deleting = $state(false);

  // Same filter as the SanctionIndicator dot
  const active = $derived(sanctions.filter(s => !s.lifted_at && !s.deleted_at));

  function focusOnMount(node: HTMLElement) {
    node.focus();
  }

  async function handleDelete(uid: string) {
    if (!confirm(m.sanction_delete_confirm())) return;
    deleting = true;
    try {
      await deleteSanctionApi(uid);
      showToast({ type: "success", message: m.sanction_mgr_deleted() });
      // The list refreshes via the SSE sanction event -> sanctions prop
    } catch {
      // Error toast shown by apiRequest
    } finally {
      deleting = false;
    }
  }
</script>

<div
  role="presentation"
  class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
  onclick={(e) => { e.stopPropagation(); if (e.target === e.currentTarget) onClose(); }}
>
  <div
    role="dialog"
    aria-modal="true"
    aria-labelledby="sanction-list-title"
    tabindex="-1"
    use:focusOnMount
    onkeydown={(e) => e.key === 'Escape' && onClose()}
    class="bg-dusk-950 rounded-lg shadow-xl border border-ash-800 w-full max-w-md mx-4 max-h-[90vh] overflow-y-auto"
  >
    <div class="p-6 border-b border-ash-800">
      <h2 id="sanction-list-title" class="text-xl font-medium text-bone-100">{m.sanction_mgr_title()}</h2>
      <p class="mt-1 text-sm text-ash-400">{playerName}</p>
    </div>
    <div class="p-6 space-y-2">
      {#each active as sanction (sanction.uid)}
        <div class="flex items-start justify-between gap-2 p-3 bg-dusk-900 rounded border border-ash-700">
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2 flex-wrap">
              <SanctionBadge {sanction} />
              {#if sanction.tournament_uid !== tournamentUid}
                <span class="text-xs px-1.5 py-0.5 rounded bg-ash-800 text-ash-400">{m.sanction_other_event()}</span>
              {:else if sanction.round_number !== null && sanction.round_number !== undefined}
                <span class="text-xs text-ash-500">{m.sanction_round_label({ round: String(sanction.round_number + 1) })}</span>
              {/if}
            </div>
            <p class="mt-1 text-sm text-ash-300">{sanction.description}</p>
            <p class="mt-1 text-xs text-ash-500">{m.sanction_issued({ date: new Date(sanction.issued_at).toLocaleDateString() })}</p>
          </div>
          <!-- Organizer delete is scoped to this tournament's own sanctions -->
          {#if canManage && sanction.tournament_uid === tournamentUid}
            <button
              type="button"
              onclick={() => handleDelete(sanction.uid)}
              disabled={deleting}
              class="shrink-0 p-2 text-crimson-400 hover:text-crimson-300 border border-crimson-800 hover:border-crimson-700 rounded-lg transition-colors disabled:opacity-40"
              title={m.common_delete()}
            >
              <Trash2 class="w-4 h-4" />
            </button>
          {/if}
        </div>
      {:else}
        <p class="text-sm text-ash-400">{m.sanction_list_empty()}</p>
      {/each}
      <div class="pt-2">
        <button
          type="button"
          onclick={onClose}
          class="w-full px-4 py-2 bg-ash-700 hover:bg-ash-600 text-ash-200 rounded font-medium transition-colors"
        >
          {m.common_close()}
        </button>
      </div>
    </div>
  </div>
</div>
