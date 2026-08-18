<script lang="ts">
  import { onMount } from "svelte";
  import { dialogPanel } from "$lib/actions/dialog";
  import { renderMarkdown } from "$lib/markdown";
  import { unseenEntries, markSeen, type ChangelogEntry } from "$lib/changelog";
  import { getLocale } from "$lib/paraglide/runtime.js";
  import * as m from "$lib/paraglide/messages.js";
  import Button from "$lib/components/Button.svelte";

  let pending = $state<ChangelogEntry[]>([]);

  onMount(() => {
    pending = unseenEntries();
  });

  function dismiss() {
    markSeen();
    pending = [];
  }

  function formatDate(iso: string): string {
    // Date-only is parsed as UTC, so a bare `new Date(iso)` renders the day before west of it.
    return new Date(`${iso}T00:00`).toLocaleDateString(getLocale(), { year: "numeric", month: "short", day: "numeric" });
  }
</script>

{#if pending.length > 0}
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
  <div
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4"
    role="presentation"
    onclick={dismiss}
    onkeydown={(e) => { if (e.key === 'Escape') dismiss(); }}
  >
    <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
    <div
      use:dialogPanel={dismiss}
      class="bg-surface-card rounded-lg shadow-xl border border-line w-full max-w-lg mx-4 max-h-[85dvh] flex flex-col"
      onclick={(e) => e.stopPropagation()}
      onkeydown={(e) => e.stopPropagation()}
      role="dialog"
      aria-modal="true"
      aria-labelledby="whats-new-title"
      tabindex="-1"
    >
      <div class="p-6 border-b border-line">
        <h2 id="whats-new-title" class="text-xl font-medium text-ink-strong">{m.whatsnew_title()}</h2>
      </div>
      <div class="p-6 overflow-y-auto space-y-6">
        {#each pending as entry (entry.version)}
          <section>
            <h3 class="text-sm font-semibold text-ink-strong mb-2">
              v{entry.version} · {formatDate(entry.date)}
            </h3>
            <div class="doc-prose prose prose-sm max-w-none">{@html renderMarkdown(entry.body)}</div>
          </section>
        {/each}
      </div>
      <div class="p-6 border-t border-line">
        <Button variant="primary" size="lg" block onclick={dismiss}>{m.common_close()}</Button>
      </div>
    </div>
  </div>
{/if}
