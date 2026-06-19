<script lang="ts">
  import { RefreshCw } from "@lucide/svelte";
  import Button from "$lib/components/Button.svelte";
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
    <Button variant="brand" size="lg" loading={isSyncing} onclick={handleResync}>
      {#if !isSyncing}<RefreshCw class="w-4 h-4" />{/if}
      {isSyncing ? m.profile_resyncing() : m.profile_resync_btn()}
    </Button>
  </div>
</div>

<!-- Logout -->
<div class="p-6 border-t border-ash-800">
  <Button variant="secondary" size="lg" block onclick={onLogout}>
    {m.profile_sign_out()}
  </Button>
</div>
