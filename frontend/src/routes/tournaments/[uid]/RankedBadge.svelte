<script lang="ts">
  import type { Tournament } from "$lib/types";
  import { rankedStatus } from "$lib/tournament-utils";
  import { Info } from "@lucide/svelte";
  import * as m from "$lib/paraglide/messages.js";

  // chip: header badge (Ranked, or Unranked · reason, hint in title=).
  // note: finished-results inline line, unranked only — title= is hover-only and
  // unreadable on touch, and the missing winner bonus must read as a rule.
  let { tournament, variant = "chip" }: { tournament: Tournament; variant?: "chip" | "note" } = $props();

  const status = $derived(rankedStatus(tournament));
  const reasonLabel = $derived.by(() => {
    if (!status || status.ranked) return "";
    switch (status.reason) {
      case "few_players": return m.tournament_unranked_reason_few_players();
      case "no_final": return m.tournament_unranked_reason_no_final();
      case "open_rounds": return m.tournament_unranked_reason_open_rounds();
    }
  });
  const hint = $derived.by(() => {
    if (!status) return "";
    if (status.ranked) return m.tournament_ranked_hint();
    switch (status.reason) {
      case "few_players": return m.tournament_unranked_hint_few_players();
      case "no_final": return m.tournament_unranked_hint_no_final();
      case "open_rounds": return m.tournament_unranked_hint_open_rounds();
    }
  });
</script>

{#if status && variant === "chip"}
  {#if status.ranked}
    <span class="px-2 py-0.5 rounded text-xs font-medium badge-blue" title={hint}>
      {m.tournament_ranked_badge()}
    </span>
  {:else}
    <span class="px-2 py-0.5 rounded text-xs font-medium badge-slate" title={hint}>
      {m.tournament_unranked_badge()} · {reasonLabel}
    </span>
  {/if}
{:else if status && variant === "note" && !status.ranked}
  <div class="bg-surface-muted/50 border border-line rounded-lg p-3 text-sm text-ink flex items-start gap-2">
    <Info class="w-4 h-4 mt-0.5 shrink-0" aria-hidden="true" />
    <span><span class="font-medium">{m.tournament_unranked_badge()}</span> — {hint}</span>
  </div>
{/if}
