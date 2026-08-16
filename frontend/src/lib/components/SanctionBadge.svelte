<script lang="ts">
  import type { Sanction, SanctionLevel } from "$lib/types";
  import { Ban, Check, Clock } from "@lucide/svelte";
  import Badge, { type BadgeTone } from "$lib/components/Badge.svelte";
  import * as m from '$lib/paraglide/messages.js';

  let { sanction }: { sanction: Sanction } = $props();

  const isLifted = $derived(sanction.lifted_at !== null);
  const isExpired = $derived.by(() => {
    if (!sanction.expires_at) return false;
    return new Date(sanction.expires_at) < new Date();
  });
  const isPermanent = $derived(
    sanction.level === "suspension" && !sanction.expires_at
  );
  const isInactive = $derived(isLifted || isExpired);

  // Ordinal severity ramp (amethyst → fuchsia → crimson): a sanction is STATUS,
  // so it is one of the few chips that earns a meaning-bearing colour.
  const SANCTION_TONES: Record<SanctionLevel, BadgeTone> = {
    caution: "pending",
    warning: "pending",
    standings_adjustment: "highlight",
    disqualification: "danger",
    suspension: "accent", // crimson uses the accent palette, not the badge one
    probation: "danger",
  };

  const levelLabelFns: Record<SanctionLevel, () => string> = {
    caution: () => m.sanction_level_caution(),
    warning: () => m.sanction_level_warning(),
    standings_adjustment: () => m.sanction_level_sa(),
    disqualification: () => m.sanction_level_dq(),
    suspension: () => m.sanction_level_suspension(),
    probation: () => m.sanction_level_probation(),
  };

  const tone = $derived(SANCTION_TONES[sanction.level]);
  const label = $derived(levelLabelFns[sanction.level]());

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
  };

  const tooltipText = $derived.by(() => {
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

<Badge kind="status" {tone} lapsed={isInactive} title={tooltipText}>
  {#if isPermanent}
    <Ban class="w-3 h-3" />
  {/if}
  {label}
  {#if isLifted}
    <span title={m.sanction_lifted()}><Check class="w-3 h-3" /></span>
  {:else if isExpired}
    <span title={m.sanction_expired()}><Clock class="w-3 h-3" /></span>
  {/if}
</Badge>
