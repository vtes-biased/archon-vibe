<script lang="ts">
  import type { Sanction, SanctionLevel } from "$lib/types";
  import * as m from '$lib/paraglide/messages.js';

  let { sanctions, onclick }: { sanctions: Sanction[]; onclick?: () => void } = $props();

  // Only show active (non-lifted, non-deleted) sanctions
  const activeSanctions = $derived(
    sanctions.filter(s => !s.lifted_at && !s.deleted_at)
  );

  // Ordinal severity ramp (amethyst → fuchsia → crimson) — dot-* classes from app.css
  const DOT_COLORS: Record<SanctionLevel, string> = {
    caution: "dot-pending",
    warning: "dot-pending",
    standings_adjustment: "dot-highlight",
    disqualification: "dot-danger",
    suspension: "dot-danger",
    probation: "dot-danger",
  };

  // Highest severity sanction determines dot color
  const SEVERITY_ORDER: SanctionLevel[] = [
    "disqualification", "suspension", "probation",
    "standings_adjustment", "warning", "caution",
  ];

  const highestLevel = $derived.by(() => {
    for (const lv of SEVERITY_ORDER) {
      if (activeSanctions.some(s => s.level === lv)) return lv;
    }
    return "caution" as SanctionLevel;
  });

  const dotColor = $derived(DOT_COLORS[highestLevel] ?? "dot-pending");

  function levelLabel(lv: SanctionLevel): string {
    const labels: Record<SanctionLevel, () => string> = {
      caution: () => m.sanction_level_caution(),
      warning: () => m.sanction_level_warning(),
      standings_adjustment: () => m.sanction_level_sa(),
      disqualification: () => m.sanction_level_dq(),
      suspension: () => m.sanction_level_suspension(),
      probation: () => m.sanction_level_probation(),
    };
    return labels[lv]?.() ?? lv;
  }

  const tooltipText = $derived(
    activeSanctions.map(s => {
      let text = levelLabel(s.level);
      if (s.round_number !== null && s.round_number !== undefined) {
        text += ` (R${s.round_number + 1})`;
      }
      return text;
    }).join(', ')
  );
</script>

{#snippet dot()}
  <span class="w-2 h-2 rounded-full {dotColor}"></span>
  {#if activeSanctions.length > 1}
    <span class="text-[10px] text-ash-400">{activeSanctions.length}</span>
  {/if}
{/snippet}

{#if activeSanctions.length > 0}
  {#if onclick}
    <!-- Tap target padded to ~44px on mobile; negative margin keeps inline layout tight. Tooltip is desktop-only. -->
    <button
      type="button"
      {onclick}
      class="inline-flex items-center justify-center gap-0.5 -m-3 p-3 min-w-[44px] min-h-[44px] sm:min-w-0 sm:min-h-0 sm:-m-2 sm:p-2"
      title={tooltipText}
      aria-label={tooltipText}
    >
      {@render dot()}
    </button>
  {:else}
    <span
      class="inline-flex items-center gap-0.5 cursor-help"
      title={tooltipText}
    >
      {@render dot()}
    </span>
  {/if}
{/if}
