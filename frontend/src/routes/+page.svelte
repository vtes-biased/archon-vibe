<script lang="ts">
  import { goto } from '$app/navigation';
  import { onMount } from 'svelte';
  import * as m from '$lib/paraglide/messages.js';

  // Redirect to users page on mount
  onMount(() => {
    goto('/tournaments', { replaceState: true });
  });
</script>

<div class="flex items-center justify-center min-h-shell">
  <div class="text-center">
    <h1 class="text-4xl font-light text-accent mb-4">Archon</h1>
    <p class="text-ink-muted">{m.common_loading()}</p>
  </div>
</div>
