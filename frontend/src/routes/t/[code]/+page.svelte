<script lang="ts">
  import { page } from "$app/stores";
  import { goto } from "$app/navigation";
  import { getTournamentByCode } from "$lib/db";
  import { syncManager } from "$lib/sync";
  import * as m from "$lib/paraglide/messages.js";

  const code = $derived($page.params.code as string);
  let missing = $state(false);

  async function resolve(c: string) {
    const t = await getTournamentByCode(c);
    if (t) {
      // replaceState: the short link is a handle, not a step in the history a
      // back button should walk through.
      await goto(`/tournaments/${t.uid}`, { replaceState: true });
      return;
    }
    missing = true;
  }

  $effect(() => {
    const c = code;
    missing = false;
    resolve(c);
    // A first-ever visitor lands here before the snapshot does, so the code
    // resolves against an empty store. Retry when the corpus arrives.
    const onSync = (e: { type: string }) => {
      if (e.type === "sync_complete" || e.type === "tournament") resolve(c);
    };
    syncManager.addEventListener(onSync);
    return () => syncManager.removeEventListener(onSync);
  });
</script>

<svelte:head>
  <title>{code} - Archon</title>
</svelte:head>

<div class="max-w-2xl mx-auto p-6 text-center">
  {#if missing}
    <p class="text-ink-faint">{m.short_code_not_found({ code })}</p>
  {:else}
    <p class="text-ink-faint">{m.short_code_resolving()}</p>
  {/if}
</div>
