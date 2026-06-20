<script lang="ts">
  import * as m from '$lib/paraglide/messages.js';
  import Button from '$lib/components/Button.svelte';
  import { Trash2, TriangleAlert } from "@lucide/svelte";

  let {
    showDeleteConfirm = $bindable(false),
    showGoOfflineConfirm = $bindable(false),
    showGoOnlineConfirm = $bindable(false),
    showForceTakeoverConfirm = $bindable(false),
    showForceUnlockConfirm = $bindable(false),
    offlineActionLoading,
    onDelete,
    onGoOffline,
    onGoOnline,
    onForceTakeover,
    onForceUnlock,
  }: {
    showDeleteConfirm: boolean;
    showGoOfflineConfirm: boolean;
    showGoOnlineConfirm: boolean;
    showForceTakeoverConfirm: boolean;
    showForceUnlockConfirm: boolean;
    offlineActionLoading: boolean;
    onDelete: () => void;
    onGoOffline: () => void;
    onGoOnline: () => void;
    onForceTakeover: () => void;
    onForceUnlock: () => void;
  } = $props();

  // Data-loss acknowledgement gates: the destructive lock actions stay disabled
  // until the organizer/IC explicitly confirms. Reset whenever the modal closes.
  let takeoverAck = $state(false);
  let unlockAck = $state(false);
  $effect(() => { if (!showForceTakeoverConfirm) takeoverAck = false; });
  $effect(() => { if (!showForceUnlockConfirm) unlockAck = false; });
</script>

<!-- Delete Tournament Confirmation Modal -->
{#if showDeleteConfirm}
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
  <div
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
    role="presentation"
    onclick={() => (showDeleteConfirm = false)}
    onkeydown={(e) => { if (e.key === 'Escape') showDeleteConfirm = false; }}
  >
    <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
    <div
      class="bg-surface-card rounded-lg shadow-xl border border-line w-full max-w-md mx-4"
      onclick={(e) => e.stopPropagation()}
      onkeydown={(e) => e.stopPropagation()}
      role="dialog"
      aria-modal="true"
      tabindex="-1"
    >
      <div class="p-6 border-b border-line">
        <h2 class="text-xl font-medium text-link">{m.tournament_delete_title()}</h2>
      </div>
      <div class="p-6">
        <p class="text-ink mb-6">{m.tournament_delete_msg()}</p>
        <div class="flex gap-2">
          <Button variant="danger" size="lg" class="flex-1" onclick={onDelete}><Trash2 class="w-4 h-4" aria-hidden="true" />{m.common_delete()}</Button>
          <Button variant="secondary" size="lg" onclick={() => (showDeleteConfirm = false)}>{m.common_cancel()}</Button>
        </div>
      </div>
    </div>
  </div>
{/if}

<!-- Go Offline Confirmation Modal -->
{#if showGoOfflineConfirm}
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
  <div
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
    role="presentation"
    onclick={() => (showGoOfflineConfirm = false)}
    onkeydown={(e) => { if (e.key === 'Escape') showGoOfflineConfirm = false; }}
  >
    <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
    <div
      class="bg-surface-card rounded-lg shadow-xl border border-line w-full max-w-md mx-4"
      onclick={(e) => e.stopPropagation()}
      onkeydown={(e) => e.stopPropagation()}
      role="dialog"
      aria-modal="true"
      tabindex="-1"
    >
      <div class="p-6 border-b border-line">
        <h2 class="text-xl font-medium text-link">{m.offline_go_offline_title()}</h2>
      </div>
      <div class="p-6">
        <p class="text-ink mb-4">{m.offline_go_offline_msg()}</p>
        <div class="rounded-lg border border-line bg-surface-muted p-4 mb-6">
          <h3 class="text-sm font-semibold text-ink mb-2">{m.offline_explainer_title()}</h3>
          <ul class="space-y-2 text-sm text-ink list-disc pl-5">
            <li>{m.offline_explainer_single_device()}</li>
            <li>{m.offline_explainer_local_save()}</li>
            <li>{m.offline_explainer_takeover()}</li>
          </ul>
        </div>
        <div class="flex gap-2">
          <Button variant="primary" size="lg" class="flex-1" loading={offlineActionLoading} onclick={onGoOffline}>
            {offlineActionLoading ? m.common_loading() : m.offline_go_offline_confirm()}
          </Button>
          <Button variant="secondary" size="lg" onclick={() => (showGoOfflineConfirm = false)}>{m.common_cancel()}</Button>
        </div>
      </div>
    </div>
  </div>
{/if}

<!-- Go Online Confirmation Modal -->
{#if showGoOnlineConfirm}
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
  <div
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
    role="presentation"
    onclick={() => (showGoOnlineConfirm = false)}
    onkeydown={(e) => { if (e.key === 'Escape') showGoOnlineConfirm = false; }}
  >
    <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
    <div
      class="bg-surface-card rounded-lg shadow-xl border border-line w-full max-w-md mx-4"
      onclick={(e) => e.stopPropagation()}
      onkeydown={(e) => e.stopPropagation()}
      role="dialog"
      aria-modal="true"
      tabindex="-1"
    >
      <div class="p-6 border-b border-line">
        <h2 class="text-xl font-medium text-link">{m.offline_go_online_title()}</h2>
      </div>
      <div class="p-6">
        <p class="text-ink mb-6">{m.offline_go_online_msg()}</p>
        <div class="flex gap-2">
          <Button variant="primary" size="lg" class="flex-1" loading={offlineActionLoading} onclick={onGoOnline}>
            {offlineActionLoading ? m.common_loading() : m.offline_go_online_confirm()}
          </Button>
          <Button variant="secondary" size="lg" onclick={() => (showGoOnlineConfirm = false)}>{m.common_cancel()}</Button>
        </div>
      </div>
    </div>
  </div>
{/if}

<!-- Force Takeover Confirmation Modal -->
{#if showForceTakeoverConfirm}
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
  <div
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
    role="presentation"
    onclick={() => (showForceTakeoverConfirm = false)}
    onkeydown={(e) => { if (e.key === 'Escape') showForceTakeoverConfirm = false; }}
  >
    <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
    <div
      class="bg-surface-card rounded-lg shadow-xl border border-line w-full max-w-md mx-4"
      onclick={(e) => e.stopPropagation()}
      onkeydown={(e) => e.stopPropagation()}
      role="dialog"
      aria-modal="true"
      tabindex="-1"
    >
      <div class="p-6 border-b border-line">
        <h2 class="text-xl font-medium text-link">{m.offline_force_takeover_title()}</h2>
      </div>
      <div class="p-6">
        <p class="text-ink mb-4">{m.offline_force_takeover_msg()}</p>
        <label class="flex items-start gap-3 mb-6 py-2 min-h-11 text-sm text-ink cursor-pointer">
          <input type="checkbox" bind:checked={takeoverAck} class="w-5 h-5 mt-px shrink-0 rounded border-line-strong bg-surface-card text-accent" />
          <span>{m.offline_data_loss_ack()}</span>
        </label>
        <div class="flex gap-2">
          <Button variant="danger" size="lg" class="flex-1" disabled={!takeoverAck} loading={offlineActionLoading} onclick={onForceTakeover}>
            <TriangleAlert class="w-4 h-4" aria-hidden="true" />
            {offlineActionLoading ? m.common_loading() : m.offline_force_takeover_confirm()}
          </Button>
          <Button variant="secondary" size="lg" onclick={() => (showForceTakeoverConfirm = false)}>{m.common_cancel()}</Button>
        </div>
      </div>
    </div>
  </div>
{/if}

<!-- Force Unlock Confirmation Modal (IC emergency: clears the lock WITHOUT syncing) -->
{#if showForceUnlockConfirm}
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
  <div
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
    role="presentation"
    onclick={() => (showForceUnlockConfirm = false)}
    onkeydown={(e) => { if (e.key === 'Escape') showForceUnlockConfirm = false; }}
  >
    <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
    <div
      class="bg-surface-card rounded-lg shadow-xl border border-line w-full max-w-md mx-4"
      onclick={(e) => e.stopPropagation()}
      onkeydown={(e) => e.stopPropagation()}
      role="dialog"
      aria-modal="true"
      tabindex="-1"
    >
      <div class="p-6 border-b border-line">
        <h2 class="text-xl font-medium text-link">{m.offline_force_unlock_title()}</h2>
      </div>
      <div class="p-6">
        <p class="text-ink mb-4">{m.offline_force_unlock_msg()}</p>
        <label class="flex items-start gap-3 mb-6 py-2 min-h-11 text-sm text-ink cursor-pointer">
          <input type="checkbox" bind:checked={unlockAck} class="w-5 h-5 mt-px shrink-0 rounded border-line-strong bg-surface-card text-accent" />
          <span>{m.offline_data_loss_ack()}</span>
        </label>
        <div class="flex gap-2">
          <Button variant="danger" size="lg" class="flex-1" disabled={!unlockAck} loading={offlineActionLoading} onclick={onForceUnlock}>
            <TriangleAlert class="w-4 h-4" aria-hidden="true" />
            {offlineActionLoading ? m.common_loading() : m.offline_force_unlock_confirm()}
          </Button>
          <Button variant="secondary" size="lg" onclick={() => (showForceUnlockConfirm = false)}>{m.common_cancel()}</Button>
        </div>
      </div>
    </div>
  </div>
{/if}
