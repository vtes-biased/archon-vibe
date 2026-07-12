<script lang="ts">
  import type { Tournament, DeckObject } from "$lib/types";
  import type { StandingEntry, PlayerInfoMap } from "$lib/tournament-utils";
  import Button from "$lib/components/Button.svelte";
  import { TriangleAlert } from "@lucide/svelte";
  import * as m from '$lib/paraglide/messages.js';

  // Pre-finish confirmation: FinishTournament computes the winner, writes
  // ratings, publishes decklists and triggers the write-once VEKN results
  // push — summarize that and surface client-side warnings. Warnings never
  // block: running the event wins over reporting.
  let {
    tournament,
    standings,
    playerInfo,
    decksByUser,
    actionLoading,
    onConfirm,
    onClose,
  }: {
    tournament: Tournament;
    standings: StandingEntry[];
    playerInfo: PlayerInfoMap;
    decksByUser: Record<string, DeckObject[]>;
    actionLoading: boolean;
    onConfirm: () => void;
    onClose: () => void;
  } = $props();

  const veknPush = import.meta.env.VITE_VEKN_PUSH === "true";
  // Mirrors batch_push's guard: only tournaments with in-app play data are pushed.
  const willPushVekn = $derived(veknPush && (tournament.rounds?.length ?? 0) > 0);
  const hasDecks = $derived(Object.values(decksByUser).some(d => d.length > 0));

  const unscoredTables = $derived.by(() => {
    let count = 0;
    for (const round of tournament.rounds ?? []) {
      for (const table of round) {
        // Soft-cancelled tables are legitimately unfinished — not a warning.
        if (table.state !== "Finished" && table.state !== "Cancelled") count++;
      }
    }
    return count;
  });
  const missingVeknIds = $derived(
    standings.filter(e => !playerInfo[e.user_uid]?.vekn).length
  );
  const missingDecks = $derived(
    tournament.decklist_required
      ? standings.filter(e => !decksByUser[e.user_uid]?.length).length
      : 0
  );
  const warnings = $derived([
    ...(unscoredTables > 0 ? [m.finish_confirm_warn_tables({ count: String(unscoredTables) })] : []),
    ...(willPushVekn && missingVeknIds > 0 ? [m.finish_confirm_warn_vekn_ids({ count: String(missingVeknIds) })] : []),
    ...(missingDecks > 0 ? [m.finish_confirm_warn_decks({ count: String(missingDecks) })] : []),
  ]);

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
    class="bg-surface-card rounded-lg shadow-xl border border-line w-full max-w-md mx-4 max-h-[90vh] overflow-y-auto"
    onclick={(e) => e.stopPropagation()}
    onkeydown={(e) => e.key === 'Escape' && onClose()}
    role="dialog"
    aria-modal="true"
    aria-labelledby="finish-confirm-title"
    tabindex="-1"
    use:focusOnMount
  >
    <div class="p-6 border-b border-line">
      <h2 id="finish-confirm-title" class="text-xl font-medium text-link">{m.finish_confirm_title()}</h2>
    </div>
    <div class="p-6">
      <p class="text-ink mb-3">{m.finish_confirm_intro()}</p>
      <ul class="space-y-1.5 text-sm text-ink list-disc pl-5 mb-4">
        <li>{m.finish_confirm_players({ count: String(standings.length) })}</li>
        {#if willPushVekn}
          <li>{m.finish_confirm_vekn()}</li>
        {/if}
        {#if tournament.decklists_mode && hasDecks}
          <li>
            {#if tournament.decklists_mode === "Winner"}{m.finish_confirm_decks_winner()}
            {:else if tournament.decklists_mode === "Finalists"}{m.finish_confirm_decks_finalists()}
            {:else}{m.finish_confirm_decks_all()}{/if}
          </li>
        {/if}
      </ul>
      {#if warnings.length > 0}
        <div class="banner-warn border rounded-lg p-3 mb-4 text-sm">
          {#each warnings as warning}
            <div class="flex items-start gap-2 py-0.5">
              <TriangleAlert class="w-4 h-4 mt-0.5 shrink-0" aria-hidden="true" />
              <span>{warning}</span>
            </div>
          {/each}
        </div>
      {/if}
      <div class="flex gap-2">
        <Button variant="danger" size="lg" class="flex-1 min-h-[44px]" loading={actionLoading} onclick={onConfirm}>
          <TriangleAlert class="w-4 h-4" aria-hidden="true" />
          {actionLoading ? m.common_loading() : m.overview_finish_tournament()}
        </Button>
        <Button variant="secondary" size="lg" class="min-h-[44px]" disabled={actionLoading} onclick={onClose}>{m.common_cancel()}</Button>
      </div>
    </div>
  </div>
</div>
