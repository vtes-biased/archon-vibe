<script lang="ts">
  import { CircleHelp } from "@lucide/svelte";
  import * as m from "$lib/paraglide/messages.js";

  // showRtp: only where an RtP column is on screen (finished standings).
  // compact: icon only, for sitting inline beside a score.
  let { showRtp = false, compact = false }: { showRtp?: boolean; compact?: boolean } = $props();
  const summary = $derived(showRtp ? m.score_legend_summary_rtp() : m.score_legend_summary());
</script>

<!-- One-tap legend spelling out the GW/VP/TP score abbreviations for newcomers (progressive disclosure). -->
<details class="text-xs {compact ? 'relative' : 'mb-2'}">
  <summary
    class="list-none [&::-webkit-details-marker]:hidden cursor-pointer inline-flex items-center gap-1 text-ink-faint hover:text-ink transition-colors {compact ? 'h-5' : ''}"
    aria-label={compact ? summary : undefined}
    title={compact ? summary : undefined}
  >
    <CircleHelp class="w-3.5 h-3.5 shrink-0" aria-hidden="true" />
    {#if !compact}{summary}{/if}
  </summary>
  <!-- Compact floats, so it doesn't push the row it sits in apart. -->
  <dl
    class="mt-1.5 grid grid-cols-[auto_1fr] gap-x-2 gap-y-0.5 text-ink font-normal {compact
      ? 'absolute left-0 z-10 w-max max-w-64 rounded-lg border border-line bg-surface-card p-2 shadow'
      : ''}"
  >
    <dt class="font-medium text-ink-strong">GW</dt><dd>{m.score_legend_gw()}</dd>
    <dt class="font-medium text-ink-strong">VP</dt><dd>{m.score_legend_vp()}</dd>
    <dt class="font-medium text-ink-strong">TP</dt><dd>{m.score_legend_tp()}</dd>
    {#if showRtp}
      <dt class="font-medium text-ink-strong">RtP</dt>
      <dd>{m.score_legend_rtp()} <a href="/rankings" class="text-link hover:underline">{m.score_legend_rtp_link()}</a></dd>
    {/if}
  </dl>
</details>
