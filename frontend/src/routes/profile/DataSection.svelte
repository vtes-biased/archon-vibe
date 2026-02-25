<script lang="ts">
  import { RefreshCw } from "lucide-svelte";
  import * as m from '$lib/paraglide/messages.js';

  interface Props {
    onResync: () => Promise<void>;
    onLogout: () => void;
  }
  let { onResync, onLogout }: Props = $props();

  let isSyncing = $state(false);

  async function handleResync() {
    isSyncing = true;
    await onResync();
    isSyncing = false;
  }
</script>

<!-- Data -->
<div class="p-6 border-t border-ash-800 space-y-4">
  <h3 class="text-sm font-medium text-ash-400 uppercase tracking-wide">{m.profile_data()}</h3>
  <div class="flex items-center justify-between">
    <div>
      <p class="text-bone-100">{m.profile_resync_title()}</p>
      <p class="text-sm text-ash-400">{m.profile_resync_description()}</p>
    </div>
    <button
      onclick={handleResync}
      disabled={isSyncing}
      class="px-4 py-2 bg-crimson-700 hover:bg-crimson-600 disabled:bg-ash-800 disabled:text-ash-500 text-white rounded font-medium transition-colors flex items-center gap-2"
    >
      <RefreshCw class="w-4 h-4 {isSyncing ? 'animate-spin' : ''}" />
      {isSyncing ? m.profile_resyncing() : m.profile_resync_btn()}
    </button>
  </div>
</div>

<!-- Logout -->
<div class="p-6 border-t border-ash-800">
  <button
    onclick={onLogout}
    class="w-full px-6 py-3 bg-ash-800 hover:bg-ash-700 text-bone-100 rounded-lg font-medium transition-colors"
  >
    {m.profile_sign_out()}
  </button>
</div>
