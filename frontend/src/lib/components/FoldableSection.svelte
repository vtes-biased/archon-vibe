<script lang="ts">
  import { ChevronDown, ChevronRight } from "@lucide/svelte";
  import type { Snippet } from "svelte";

  // One shell for every configuration section, so the setup surfaces read as
  // peers instead of the three tiers they grew into (always-visible headings,
  // disclosures, and headings nested inside disclosures).
  //
  // Sections open independently and stay open: this is a workspace, not a
  // directory. You compare across sections while configuring — round count
  // against timer length, rank against the rules it disables — and the form
  // auto-saves, so its "Saved" chip is the only confirmation there is; closing
  // a section on you would hide it.
  let {
    title,
    open = $bindable(false),
    children,
  }: {
    title: string;
    open?: boolean;
    children: Snippet;
  } = $props();
</script>

<div class="bg-surface-muted/30 rounded-lg p-4">
  <button
    type="button"
    onclick={() => (open = !open)}
    aria-expanded={open}
    class="flex w-full items-center gap-2 text-left text-sm font-medium text-ink min-h-[44px]"
  >
    {#if open}<ChevronDown class="w-4 h-4 shrink-0" aria-hidden="true" />{:else}<ChevronRight class="w-4 h-4 shrink-0" aria-hidden="true" />{/if}
    {title}
  </button>
  {#if open}
    <div class="mt-3 space-y-4">
      {@render children()}
    </div>
  {/if}
</div>
