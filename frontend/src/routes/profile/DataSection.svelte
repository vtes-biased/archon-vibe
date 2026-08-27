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

<div class="p-3 sm:p-6 space-y-4">
  <h3 class="text-sm font-medium text-ink-muted uppercase tracking-wide">{m.profile_data()}</h3>
  <div class="flex items-center justify-between">
    <div>
      <p class="text-ink-strong">{m.profile_resync_title()}</p>
      <p class="text-sm text-ink-muted">{m.profile_resync_description()}</p>
    </div>
    <Button variant="primary" size="lg" loading={isSyncing} onclick={handleResync}>
      {#if !isSyncing}<RefreshCw class="w-4 h-4" />{/if}
      {isSyncing ? m.profile_resyncing() : m.profile_resync_btn()}
    </Button>
  </div>
</div>

<div class="p-3 sm:p-6">
  <Button variant="secondary" size="lg" block onclick={onLogout}>
    {m.profile_sign_out()}
  </Button>
</div>
