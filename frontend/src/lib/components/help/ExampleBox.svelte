<script lang="ts">
  import type { Snippet } from "svelte";
  let { children }: { children: Snippet } = $props();
</script>

<div class="not-prose my-6 rounded-lg border border-ash-700 bg-dusk-900/50 overflow-hidden">
  <div class="px-3 py-1.5 bg-dusk-800/50 border-b border-ash-700">
    <span class="text-xs font-medium text-ash-500 uppercase tracking-wider">Example</span>
  </div>
  <div class="p-4 pointer-events-none select-none" aria-hidden="true">
    {@render children()}
  </div>
</div>
