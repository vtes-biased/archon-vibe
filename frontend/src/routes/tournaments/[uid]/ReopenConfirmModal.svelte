<script lang="ts">
  import type { Tournament } from "$lib/types";
  import type { TournamentEventType } from "$lib/engine";
  import { TriangleAlert } from "@lucide/svelte";
  import Button from "$lib/components/Button.svelte";
  import * as m from '$lib/paraglide/messages.js';

  let {
    tournament,
    actionLoading = false,
    doAction,
    onClose,
  }: {
    tournament: Tournament;
    actionLoading?: boolean;
    doAction?: (action: TournamentEventType, body?: any) => Promise<string | null>;
    onClose: () => void;
  } = $props();

  function focusOnMount(node: HTMLElement) {
    node.focus();
  }
</script>

<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
<div
  class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
  role="presentation"
  onclick={onClose}
>
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
  <div
    class="bg-surface-card rounded-lg shadow-xl border border-line w-full max-w-md mx-4 max-h-[85dvh] overflow-y-auto"
    onclick={(e) => e.stopPropagation()}
    onkeydown={(e) => e.key === 'Escape' && onClose()}
    role="dialog"
    aria-modal="true"
    aria-labelledby="reopen-confirm-title"
    tabindex="-1"
    use:focusOnMount
  >
    <div class="p-6 border-b border-line">
      <h2 id="reopen-confirm-title" class="text-xl font-medium text-link">{m.reopen_confirm_title()}</h2>
    </div>
    <div class="p-6">
      <p class="text-ink mb-4">{m.reopen_confirm_msg()}</p>
      {#if tournament.vekn_pushed_at}
        <!-- The VEKN results push is write-once: corrections never reach
             vekn.net via API — manual admin fixes only. -->
        <div class="banner-warn border rounded-lg p-3 mb-4 text-sm flex items-start gap-2">
          <TriangleAlert class="w-4 h-4 mt-0.5 shrink-0" aria-hidden="true" />
          <span>{m.reopen_confirm_vekn_warn()}</span>
        </div>
      {/if}
      <div class="flex gap-2">
        <Button
          variant="danger"
          size="lg"
          class="flex-1 min-h-[44px]"
          loading={actionLoading}
          onclick={async () => { await doAction?.("ReopenTournament"); onClose(); }}
        >
          <TriangleAlert class="w-4 h-4" aria-hidden="true" />
          {actionLoading ? m.common_loading() : m.overview_reopen_tournament()}
        </Button>
        <Button variant="secondary" size="lg" class="min-h-[44px]" disabled={actionLoading} onclick={onClose}>{m.common_cancel()}</Button>
      </div>
    </div>
  </div>
</div>
