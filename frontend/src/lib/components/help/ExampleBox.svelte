<script lang="ts">
  import type { Snippet } from "svelte";
  import * as m from "$lib/paraglide/messages.js";
  let { children }: { children: Snippet } = $props();
</script>

<div class="not-prose my-6 rounded-lg border border-line-strong bg-surface-muted/50 overflow-hidden">
  <div class="px-3 py-1.5 bg-surface-hover/50 border-b border-line-strong">
    <span class="text-xs font-medium text-ink-faint uppercase tracking-wider">{m.example_box_label()}</span>
  </div>
  <div class="p-4 pointer-events-none select-none" aria-hidden="true">
    {@render children()}
  </div>
</div>
