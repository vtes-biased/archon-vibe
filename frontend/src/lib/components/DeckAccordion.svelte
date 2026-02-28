<script lang="ts">
  import { ChevronDown, ChevronRight } from "lucide-svelte";
  import { slide } from "svelte/transition";
  import type { Snippet } from "svelte";

  let {
    expanded,
    ontoggle,
    roundLabel,
    bgClass = 'bg-ash-900/50',
    headerExtra,
    children,
  }: {
    expanded: boolean;
    ontoggle: () => void;
    roundLabel: string;
    bgClass?: string;
    headerExtra?: Snippet;
    children: Snippet;
  } = $props();
</script>

<div class="rounded-lg {bgClass}">
  <button
    class="w-full flex items-center gap-2 p-2.5 text-left text-sm min-h-[44px]"
    onclick={ontoggle}
    aria-expanded={expanded}
  >
    <span class="text-ash-400 shrink-0">
      {#if expanded}<ChevronDown class="w-4 h-4" />{:else}<ChevronRight class="w-4 h-4" />{/if}
    </span>
    <span class="font-medium text-ash-300">{roundLabel}</span>
    {#if headerExtra}
      {@render headerExtra()}
    {/if}
  </button>
  {#if expanded}
    <div class="px-2.5 pb-2.5" transition:slide={{ duration: 150 }}>
      {@render children()}
    </div>
  {/if}
</div>
