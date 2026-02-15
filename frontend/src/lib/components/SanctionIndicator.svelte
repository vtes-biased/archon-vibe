<script lang="ts">
  import type { Sanction, SanctionLevel } from "$lib/types";
  import * as m from '$lib/paraglide/messages.js';

  let { sanctions }: { sanctions: Sanction[] } = $props();

  // Only show active (non-lifted, non-deleted) sanctions
  const activeSanctions = $derived(
    sanctions.filter(s => !s.lifted_at && !s.deleted_at)
  );

  const DOT_COLORS: Record<SanctionLevel, string> = {
    caution: "bg-amber-400",
    warning: "bg-orange-400",
    standings_adjustment: "bg-purple-400",
    disqualification: "bg-red-500",
    suspension: "bg-crimson-500",
    probation: "bg-rose-400",
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

  const dotColor = $derived(DOT_COLORS[highestLevel] ?? "bg-amber-400");

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

{#if activeSanctions.length > 0}
  <span
    class="inline-flex items-center gap-0.5 cursor-help"
    title={tooltipText}
  >
    <span class="w-2 h-2 rounded-full {dotColor}"></span>
    {#if activeSanctions.length > 1}
      <span class="text-[10px] text-ash-400">{activeSanctions.length}</span>
    {/if}
  </span>
{/if}
