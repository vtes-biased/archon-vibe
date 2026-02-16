<script lang="ts">
  import type { Sanction, SanctionLevel } from "$lib/types";
  import { Ban, Check, Clock } from "lucide-svelte";
  import * as m from '$lib/paraglide/messages.js';

  let { sanction }: { sanction: Sanction } = $props();

  // Check if sanction is lifted or expired
  const isLifted = $derived(sanction.lifted_at !== null);
  const isExpired = $derived(() => {
    if (!sanction.expires_at) return false;
    return new Date(sanction.expires_at) < new Date();
  });
  const isPermanent = $derived(
    sanction.level === "suspension" && !sanction.expires_at
  );
  const isInactive = $derived(isLifted || isExpired());

  // Gothic-inspired muted sanction colors
  const SANCTION_COLORS: Record<SanctionLevel, { bg: string; text: string }> = {
    caution: {
      bg: "bg-yellow-900/60",
      text: "text-yellow-200",
    },
    warning: {
      bg: "bg-orange-900/60",
      text: "text-orange-200",
    },
    standings_adjustment: {
      bg: "bg-purple-900/60",
      text: "text-purple-200",
    },
    disqualification: {
      bg: "bg-red-900/60",
      text: "text-red-200",
    },
    suspension: {
      bg: "bg-crimson-900/80",
      text: "text-crimson-200",
    },
    probation: {
      bg: "bg-rose-900/60",
      text: "text-rose-200",
    },
  };

  const levelLabelFns: Record<SanctionLevel, () => string> = {
    caution: () => m.sanction_level_caution(),
    warning: () => m.sanction_level_warning(),
    standings_adjustment: () => m.sanction_level_sa(),
    disqualification: () => m.sanction_level_dq(),
    suspension: () => m.sanction_level_suspension(),
    probation: () => m.sanction_level_probation(),
  };

  const colors = $derived(SANCTION_COLORS[sanction.level]);
  const label = $derived(levelLabelFns[sanction.level]());

  // Format date for tooltip
  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString();
  };

  const tooltipText = $derived(() => {
    let text = `${label}: ${sanction.description}\n${m.sanction_issued({ date: formatDate(sanction.issued_at) })}`;
    if (sanction.expires_at) {
      text += `\n${m.sanction_expires({ date: formatDate(sanction.expires_at) })}`;
    }
    if (isLifted && sanction.lifted_at) {
      text += `\n${m.sanction_lifted_date({ date: formatDate(sanction.lifted_at) })}`;
    }
    if (isPermanent) {
      text += `\n${m.sanction_permanent_ban()}`;
    }
    return text;
  });
</script>

<span
  class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium {colors.bg} {colors.text} {isInactive
    ? 'line-through opacity-60'
    : ''}"
  title={tooltipText()}
>
  {#if isPermanent}
    <Ban class="w-3 h-3" />
  {/if}
  {label}
  {#if isLifted}
    <span title={m.sanction_lifted()}><Check class="w-3 h-3" /></span>
  {:else if isExpired()}
    <span title={m.sanction_expired()}><Clock class="w-3 h-3" /></span>
  {/if}
</span>
