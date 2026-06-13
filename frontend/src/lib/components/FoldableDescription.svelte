<script lang="ts">
  import { ChevronDown, ChevronRight } from "@lucide/svelte";
  import { renderMarkdown, stripLeadingTitle, descriptionExcerpt } from "$lib/markdown";
  import * as m from "$lib/paraglide/messages.js";

  // `title`, when given, strips a leading "# <title>" heading from the body
  // (the rendered card already shows a "Description" header).
  let { description, title = "" }: { description: string; title?: string } = $props();

  const bodyId = $props.id();
  let expanded = $state(false);
  const cleaned = $derived(title ? stripLeadingTitle(description, title) : description);
  const excerpt = $derived(descriptionExcerpt(cleaned));
</script>

<div class="bg-dusk-950 rounded-lg shadow border border-ash-800 mb-6">
  <button
    onclick={() => (expanded = !expanded)}
    aria-expanded={expanded}
    aria-controls={bodyId}
    class="w-full flex items-center gap-2 px-4 sm:px-6 py-3 text-left text-sm font-medium text-ash-300 hover:text-bone-100 transition-colors"
  >
    {#if expanded}<ChevronDown class="w-4 h-4 shrink-0" aria-hidden="true" />{:else}<ChevronRight class="w-4 h-4 shrink-0" aria-hidden="true" />{/if}
    {m.common_description()}
  </button>
  {#if expanded}
    <div id={bodyId} class="px-4 sm:px-6 pb-4 prose dark:prose-invert prose-sm max-w-none">{@html renderMarkdown(cleaned)}</div>
  {:else}
    <div id={bodyId} class="px-4 sm:px-6 pb-3 text-sm text-ash-400">{excerpt.text}{#if excerpt.truncated}<span aria-hidden="true">…</span>{/if}</div>
  {/if}
</div>
