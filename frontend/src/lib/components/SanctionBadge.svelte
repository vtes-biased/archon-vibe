<script lang="ts">
  import type { Sanction, SanctionLevel } from "$lib/types";
  import Icon from "@iconify/svelte";

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
    score_adjustment: {
      bg: "bg-gray-800/60",
      text: "text-gray-200",
    },
  };

  const levelLabels: Record<SanctionLevel, string> = {
    caution: "Caution",
    warning: "Warning",
    disqualification: "DQ",
    suspension: "Suspension",
    probation: "Probation",
    score_adjustment: "Score Adj",
  };

  const colors = $derived(SANCTION_COLORS[sanction.level]);
  const label = $derived(levelLabels[sanction.level]);

  // Format date for tooltip
  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString();
  };

  const tooltipText = $derived(() => {
    let text = `${label}: ${sanction.description}\nIssued: ${formatDate(sanction.issued_at)}`;
    if (sanction.expires_at) {
      text += `\nExpires: ${formatDate(sanction.expires_at)}`;
    }
    if (isLifted && sanction.lifted_at) {
      text += `\nLifted: ${formatDate(sanction.lifted_at)}`;
    }
    if (isPermanent) {
      text += "\nPermanent ban";
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
    <Icon icon="lucide:ban" class="w-3 h-3" />
  {/if}
  {label}
  {#if isLifted}
    <span title="Lifted"><Icon icon="lucide:check" class="w-3 h-3" /></span>
  {:else if isExpired()}
    <span title="Expired"><Icon icon="lucide:clock" class="w-3 h-3" /></span>
  {/if}
</span>
