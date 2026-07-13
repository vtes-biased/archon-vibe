<script lang="ts">
  import type { Sanction } from "$lib/types";
  import { deleteSanctionApi } from "$lib/api";
  import { showToast } from "$lib/stores/toast.svelte";
  import SanctionBadge from "./SanctionBadge.svelte";
  import Button from '$lib/components/Button.svelte';
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

  // No confirm: sanction deletes are soft and IC-recoverable for 30 days
  // (db cleanup job) — reversibility over confirmation, per the owner ruling.
  async function handleDelete(uid: string) {
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
    class="bg-surface-card rounded-lg shadow-xl border border-line w-full max-w-md mx-4 max-h-[90vh] overflow-y-auto"
  >
    <div class="p-6 border-b border-line">
      <h2 id="sanction-list-title" class="text-xl font-medium text-ink-strong">{m.sanction_mgr_title()}</h2>
      <p class="mt-1 text-sm text-ink-muted">{playerName}</p>
    </div>
    <div class="p-6 space-y-2">
      {#each active as sanction (sanction.uid)}
        <div class="flex items-start justify-between gap-2 p-3 bg-surface-muted rounded border border-line-strong">
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2 flex-wrap">
              <SanctionBadge {sanction} />
              {#if sanction.tournament_uid !== tournamentUid}
                <span class="text-xs px-1.5 py-0.5 rounded bg-surface-hover text-ink-muted">{m.sanction_other_event()}</span>
              {:else if sanction.round_number !== null && sanction.round_number !== undefined}
                <span class="text-xs text-ink-faint">{m.sanction_round_label({ round: String(sanction.round_number + 1) })}</span>
              {/if}
            </div>
            <p class="mt-1 text-sm text-ink">{sanction.description}</p>
            <p class="mt-1 text-xs text-ink-faint">{m.sanction_issued({ date: new Date(sanction.issued_at).toLocaleDateString() })}</p>
          </div>
          <!-- Organizer delete is scoped to this tournament's own sanctions -->
          {#if canManage && sanction.tournament_uid === tournamentUid}
            <button
              type="button"
              onclick={() => handleDelete(sanction.uid)}
              disabled={deleting}
              class="shrink-0 p-2 text-link hover:text-link-soft border border-accent-soft-border hover:border-accent-strong rounded-lg transition-colors disabled:opacity-40"
              title={m.common_delete()}
            >
              <Trash2 class="w-4 h-4" />
            </button>
          {/if}
        </div>
      {:else}
        <p class="text-sm text-ink-muted">{m.sanction_list_empty()}</p>
      {/each}
      <div class="pt-2">
        <Button variant="secondary" size="lg" block onclick={onClose}>
          {m.common_close()}
        </Button>
      </div>
    </div>
  </div>
</div>
