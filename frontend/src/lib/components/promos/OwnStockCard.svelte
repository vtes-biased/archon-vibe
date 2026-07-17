<script lang="ts">
  // View-only list of the viewer's own promo_stock (server-computed remaining).
  import type { Promo } from "$lib/types";
  import { Layers } from "@lucide/svelte";
  import * as m from '$lib/paraglide/messages.js';

  let {
    stock,
    promos,
  }: {
    stock: Record<string, number>;
    promos: Promo[];
  } = $props();

  // Entries whose promo can't resolve locally are hidden (defensive).
  const rows = $derived(
    Object.entries(stock)
      .map(([uid, remaining]) => ({ promo: promos.find((p) => p.uid === uid), remaining }))
      .filter((r): r is { promo: Promo; remaining: number } => !!r.promo)
      .sort((a, b) => a.promo.name.localeCompare(b.promo.name))
  );
</script>

{#if rows.length > 0}
  <div class="bg-surface-card rounded-lg shadow border border-line p-5">
    <div class="flex items-center gap-2 mb-3">
      <Layers class="w-5 h-5 text-accent" aria-hidden="true" />
      <h2 class="text-lg font-medium text-ink-strong">{m.promo_own_stock_title()}</h2>
    </div>
    <div class="divide-y divide-line/50">
      {#each rows as row (row.promo.uid)}
        <div class="flex items-center justify-between gap-2 py-1.5 text-sm">
          <span class="text-ink min-w-0 truncate">{row.promo.name}</span>
          <span class="text-xs shrink-0 {row.remaining === 0 ? 'text-ink-faint' : 'text-ink-muted'}">
            {row.remaining === 0 ? m.promo_holdings_none_left() : m.promo_holdings_remaining({ count: String(row.remaining) })}
          </span>
        </div>
      {/each}
    </div>
  </div>
{/if}
