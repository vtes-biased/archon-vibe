<script lang="ts">
  import { ChevronDown, ChevronRight } from "@lucide/svelte";
  import { slide } from "svelte/transition";
  import type { Snippet } from "svelte";

  let {
    title,
    open = $bindable(false),
    ontoggle,
    disabled = false,
    level,
    header,
    children,
  }: {
    title: string;
    open?: boolean;
    ontoggle?: () => void;
    disabled?: boolean;
    level?: 2 | 3 | 4;
    header?: Snippet;
    children: Snippet;
  } = $props();
</script>

<div class="bg-surface-muted/30 rounded-lg p-4">
  <svelte:element this={level ? `h${level}` : "div"}>
    <button
      type="button"
      {disabled}
      onclick={() => (ontoggle ? ontoggle() : (open = !open))}
      aria-expanded={open}
      class="flex w-full items-center gap-2 text-left text-sm font-medium text-ink min-h-[44px] disabled:opacity-40"
    >
      {#if open}<ChevronDown class="w-4 h-4 shrink-0" aria-hidden="true" />{:else}<ChevronRight class="w-4 h-4 shrink-0" aria-hidden="true" />{/if}
      <span class="min-w-0">{title}</span>
      {#if header}{@render header()}{/if}
    </button>
  </svelte:element>
  {#if open}
    <div class="mt-3 space-y-4" transition:slide={{ duration: 150 }}>
      {@render children()}
    </div>
  {/if}
</div>
