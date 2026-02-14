<script lang="ts">
  import { goto } from '$app/navigation';
  import { onMount } from 'svelte';

  // Redirect to users page on mount
  onMount(() => {
    goto('/tournaments', { replaceState: true });
  });
</script>

<div class="flex items-center justify-center min-h-screen">
  <div class="text-center">
    <h1 class="text-4xl font-light text-crimson-500 mb-4">Archon</h1>
    <p class="text-ash-400">Loading...</p>
  </div>
</div>
