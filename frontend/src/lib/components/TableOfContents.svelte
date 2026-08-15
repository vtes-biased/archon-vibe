<script lang="ts">
  import { List, X } from "@lucide/svelte";
  import { replaceState } from "$app/navigation";
  import type { TocEntry } from "$lib/help-docs";
  import * as m from '$lib/paraglide/messages.js';
  import { dialogPanel } from "$lib/actions/dialog";

  interface Props {
    entries: TocEntry[];
    activeHeading: string;
  }
  let { entries, activeHeading }: Props = $props();

  let mobileOpen = $state(false);

  function handleClick(id: string) {
    mobileOpen = false;
    const el = document.getElementById(id);
    if (el) {
      el.scrollIntoView({ behavior: "smooth" });
      replaceState(`#${id}`, {});
    }
  }
</script>

<!-- Desktop: sticky sidebar -->
<aside class="hidden lg:block w-64 shrink-0">
  <div class="sticky top-4 max-h-[calc(100vh-2rem)] overflow-y-auto">
    <h3 class="text-sm font-medium text-ink-muted uppercase tracking-wide mb-3">{m.help_toc_title()}</h3>
    <nav class="space-y-0.5">
      {#each entries as entry}
        <button
          onclick={() => handleClick(entry.id)}
          class="block w-full text-left text-sm py-1 transition-colors truncate
            {entry.depth === 1 ? 'pl-0 font-medium' : entry.depth === 2 ? 'pl-3' : 'pl-6 text-xs'}
            {activeHeading === entry.id ? 'text-link' : 'text-ink-muted hover:text-ink-strong'}"
        >
          {entry.text}
        </button>
      {/each}
    </nav>
  </div>
</aside>

<!-- Mobile: floating button + drawer -->
<div class="lg:hidden">
  <!-- Floating TOC button -->
  <button
    onclick={() => (mobileOpen = true)}
    class="fixed bottom-20 right-4 z-30 w-12 h-12 rounded-full bg-accent-strong text-white shadow-lg flex items-center justify-center hover:bg-accent-strong-hover transition-colors"
    title={m.help_toc_title()}
  >
    <List class="w-5 h-5" />
  </button>

  <!-- Drawer backdrop -->
  {#if mobileOpen}
    <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
    <div
      class="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm"
      role="presentation"
      onclick={() => (mobileOpen = false)}
      onkeydown={(e) => { if (e.key === 'Escape') mobileOpen = false; }}
    >
      <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
      <div
        class="absolute bottom-0 left-0 right-0 max-h-[70vh] bg-surface-card border-t border-line rounded-t-2xl overflow-y-auto"
        onclick={(e) => e.stopPropagation()}
        onkeydown={(e) => e.stopPropagation()}
        use:dialogPanel={() => mobileOpen = false}
        role="dialog"
        aria-modal="true"
        tabindex="-1"
      >
        <div class="sticky top-0 bg-surface-card px-4 py-3 border-b border-line flex items-center justify-between">
          <h3 class="text-sm font-medium text-ink-muted uppercase tracking-wide">{m.help_toc_title()}</h3>
          <button onclick={() => (mobileOpen = false)} class="p-1 text-ink-muted hover:text-ink-strong">
            <X class="w-5 h-5" />
          </button>
        </div>
        <nav class="p-4 space-y-1">
          {#each entries as entry}
            <button
              onclick={() => handleClick(entry.id)}
              class="block w-full text-left text-sm py-1.5 transition-colors
                {entry.depth === 1 ? 'pl-0 font-medium' : entry.depth === 2 ? 'pl-4' : 'pl-8 text-xs'}
                {activeHeading === entry.id ? 'text-link' : 'text-ink-muted hover:text-ink-strong'}"
            >
              {entry.text}
            </button>
          {/each}
        </nav>
      </div>
    </div>
  {/if}
</div>
