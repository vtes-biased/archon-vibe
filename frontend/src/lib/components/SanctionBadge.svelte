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

  // Gothic-inspired muted sanction colors — uses semantic badge-* classes from app.css
  const SANCTION_CLASSES: Record<SanctionLevel, string> = {
    caution: "badge-yellow",
    warning: "badge-orange",
    standings_adjustment: "badge-purple",
    disqualification: "badge-red",
    suspension: "bg-crimson-900/80 text-crimson-200", // crimson uses custom palette
    probation: "badge-rose",
  };

  const levelLabelFns: Record<SanctionLevel, () => string> = {
    caution: () => m.sanction_level_caution(),
    warning: () => m.sanction_level_warning(),
    standings_adjustment: () => m.sanction_level_sa(),
    disqualification: () => m.sanction_level_dq(),
    suspension: () => m.sanction_level_suspension(),
    probation: () => m.sanction_level_probation(),
  };

  const badgeClass = $derived(SANCTION_CLASSES[sanction.level]);
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
  class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium {badgeClass} {isInactive
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
