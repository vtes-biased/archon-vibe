<script lang="ts">
  import * as m from '$lib/paraglide/messages.js';

  let {
    showDeleteConfirm = $bindable(false),
    showGoOfflineConfirm = $bindable(false),
    showGoOnlineConfirm = $bindable(false),
    showForceTakeoverConfirm = $bindable(false),
    offlineActionLoading,
    onDelete,
    onGoOffline,
    onGoOnline,
    onForceTakeover,
  }: {
    showDeleteConfirm: boolean;
    showGoOfflineConfirm: boolean;
    showGoOnlineConfirm: boolean;
    showForceTakeoverConfirm: boolean;
    offlineActionLoading: boolean;
    onDelete: () => void;
    onGoOffline: () => void;
    onGoOnline: () => void;
    onForceTakeover: () => void;
  } = $props();
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
      class="bg-dusk-950 rounded-lg shadow-xl border border-ash-800 w-full max-w-md mx-4"
      onclick={(e) => e.stopPropagation()}
      onkeydown={(e) => e.stopPropagation()}
      role="dialog"
      aria-modal="true"
      tabindex="-1"
    >
      <div class="p-6 border-b border-ash-800">
        <h2 class="text-xl font-medium text-crimson-400">{m.tournament_delete_title()}</h2>
      </div>
      <div class="p-6">
        <p class="text-ash-300 mb-6">{m.tournament_delete_msg()}</p>
        <div class="flex gap-2">
          <button
            onclick={onDelete}
            class="flex-1 px-4 py-2 bg-crimson-700 hover:bg-crimson-600 text-white rounded font-medium transition-colors"
          >{m.common_delete()}</button>
          <button
            onclick={() => (showDeleteConfirm = false)}
            class="px-4 py-2 bg-ash-700 hover:bg-ash-600 text-ash-200 rounded font-medium transition-colors"
          >{m.common_cancel()}</button>
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
      class="bg-dusk-950 rounded-lg shadow-xl border border-ash-800 w-full max-w-md mx-4"
      onclick={(e) => e.stopPropagation()}
      onkeydown={(e) => e.stopPropagation()}
      role="dialog"
      aria-modal="true"
      tabindex="-1"
    >
      <div class="p-6 border-b border-ash-800">
        <h2 class="text-xl font-medium text-amber-400">{m.offline_go_offline_title()}</h2>
      </div>
      <div class="p-6">
        <p class="text-ash-300 mb-6">{m.offline_go_offline_msg()}</p>
        <div class="flex gap-2">
          <button
            onclick={onGoOffline}
            disabled={offlineActionLoading}
            class="flex-1 px-4 py-2 btn-amber disabled:bg-ash-700 rounded font-medium transition-colors"
          >{offlineActionLoading ? m.common_loading() : m.offline_go_offline_confirm()}</button>
          <button
            onclick={() => (showGoOfflineConfirm = false)}
            class="px-4 py-2 bg-ash-700 hover:bg-ash-600 text-ash-200 rounded font-medium transition-colors"
          >{m.common_cancel()}</button>
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
      class="bg-dusk-950 rounded-lg shadow-xl border border-ash-800 w-full max-w-md mx-4"
      onclick={(e) => e.stopPropagation()}
      onkeydown={(e) => e.stopPropagation()}
      role="dialog"
      aria-modal="true"
      tabindex="-1"
    >
      <div class="p-6 border-b border-ash-800">
        <h2 class="text-xl font-medium text-emerald-400">{m.offline_go_online_title()}</h2>
      </div>
      <div class="p-6">
        <p class="text-ash-300 mb-6">{m.offline_go_online_msg()}</p>
        <div class="flex gap-2">
          <button
            onclick={onGoOnline}
            disabled={offlineActionLoading}
            class="flex-1 px-4 py-2 btn-emerald disabled:bg-ash-700 rounded font-medium transition-colors"
          >{offlineActionLoading ? m.common_loading() : m.offline_go_online_confirm()}</button>
          <button
            onclick={() => (showGoOnlineConfirm = false)}
            class="px-4 py-2 bg-ash-700 hover:bg-ash-600 text-ash-200 rounded font-medium transition-colors"
          >{m.common_cancel()}</button>
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
      class="bg-dusk-950 rounded-lg shadow-xl border border-ash-800 w-full max-w-md mx-4"
      onclick={(e) => e.stopPropagation()}
      onkeydown={(e) => e.stopPropagation()}
      role="dialog"
      aria-modal="true"
      tabindex="-1"
    >
      <div class="p-6 border-b border-ash-800">
        <h2 class="text-xl font-medium text-amber-400">{m.offline_force_takeover_title()}</h2>
      </div>
      <div class="p-6">
        <p class="text-ash-300 mb-6">{m.offline_force_takeover_msg()}</p>
        <div class="flex gap-2">
          <button
            onclick={onForceTakeover}
            disabled={offlineActionLoading}
            class="flex-1 px-4 py-2 btn-amber disabled:bg-ash-700 rounded font-medium transition-colors"
          >{offlineActionLoading ? m.common_loading() : m.offline_force_takeover_confirm()}</button>
          <button
            onclick={() => (showForceTakeoverConfirm = false)}
            class="px-4 py-2 bg-ash-700 hover:bg-ash-600 text-ash-200 rounded font-medium transition-colors"
          >{m.common_cancel()}</button>
        </div>
      </div>
    </div>
  </div>
{/if}
