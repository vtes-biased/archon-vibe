<script lang="ts">
  import type { Tournament } from "$lib/types";
  import { rankedStatus } from "$lib/tournament-utils";
  import InlineNotice from "$lib/components/InlineNotice.svelte";
  import Badge from "$lib/components/Badge.svelte";
  import * as m from "$lib/paraglide/messages.js";

  // chip: one word in the header row. note: the reason, unranked only, where
  // touch can read it — title= cannot be reached without a pointer.
  let { tournament, variant = "chip" }: { tournament: Tournament; variant?: "chip" | "note" } = $props();

  const status = $derived(rankedStatus(tournament));
  const reasonLabel = $derived.by(() => {
    if (!status || status.ranked) return "";
    switch (status.reason) {
      case "few_players": return m.tournament_unranked_reason_few_players();
      case "no_final": return m.tournament_unranked_reason_no_final();
      case "open_rounds": return m.tournament_unranked_reason_open_rounds();
      case "no_results": return m.tournament_unranked_reason_no_results();
      case "storyline": return m.tournament_unranked_reason_storyline();
    }
  });
  const hint = $derived(status?.ranked ? m.tournament_ranked_hint() : reasonLabel);
</script>

{#if status && variant === "chip"}
  <!-- Identity, not status — and not blue, which the league link owns here. -->
  <Badge tone={status.ranked ? "neutral" : "slate"} title={hint}>
    {status.ranked ? m.tournament_ranked_badge() : m.tournament_unranked_badge()}
  </Badge>
{:else if status && variant === "note" && !status.ranked}
  <InlineNotice>
    <span class="font-medium">{m.tournament_unranked_badge()}</span> — {reasonLabel}
  </InlineNotice>
{/if}
