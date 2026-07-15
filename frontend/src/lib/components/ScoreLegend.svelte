<script lang="ts">
  import { CircleHelp } from "@lucide/svelte";
  import * as m from "$lib/paraglide/messages.js";

  // showRtp: only where an RtP column is on screen (finished standings).
  let { showRtp = false }: { showRtp?: boolean } = $props();
</script>

<!-- One-tap legend spelling out the GW/VP/TP score abbreviations for newcomers (progressive disclosure). -->
<details class="mb-2 text-xs">
  <summary
    class="list-none [&::-webkit-details-marker]:hidden cursor-pointer inline-flex items-center gap-1 text-ink-faint hover:text-ink transition-colors"
  >
    <CircleHelp class="w-3.5 h-3.5 shrink-0" aria-hidden="true" />
    {showRtp ? m.score_legend_summary_rtp() : m.score_legend_summary()}
  </summary>
  <dl class="mt-1.5 grid grid-cols-[auto_1fr] gap-x-2 gap-y-0.5 text-ink font-normal">
    <dt class="font-medium text-ink-strong">GW</dt><dd>{m.score_legend_gw()}</dd>
    <dt class="font-medium text-ink-strong">VP</dt><dd>{m.score_legend_vp()}</dd>
    <dt class="font-medium text-ink-strong">TP</dt><dd>{m.score_legend_tp()}</dd>
    {#if showRtp}
      <dt class="font-medium text-ink-strong">RtP</dt>
      <dd>{m.score_legend_rtp()} <a href="/rankings" class="text-link hover:underline">{m.score_legend_rtp_link()}</a></dd>
    {/if}
  </dl>
</details>
