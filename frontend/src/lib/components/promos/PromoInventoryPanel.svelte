<script lang="ts">
  // Officials-only inventory: per-promo holdings (synced, offline-capable) plus
  // the online-only ledger controls (record movement, CSV export, ledger list).
  import type { Promo } from "$lib/types";
  import { getUser } from "$lib/db";
  import { getPromoLedger } from "$lib/api";
  import { holdingRows } from "$lib/promo-utils";
  import { buildCsv, downloadCsv } from "$lib/promo-csv";
  import { isBrowserOnline } from "$lib/stores/connectivity.svelte";
  import Button from "$lib/components/Button.svelte";
  import PromoLedgerList from "./PromoLedgerList.svelte";
  import RecordMovementModal from "./RecordMovementModal.svelte";
  import { Boxes, ChevronDown, ChevronRight, Download } from "@lucide/svelte";
  import * as m from '$lib/paraglide/messages.js';

  let {
    promos,
    isIC = false,
  }: {
    promos: Promo[];
    isIC?: boolean;
  } = $props();

  const online = $derived(isBrowserOnline());
  const activePromos = $derived(promos.filter((p) => p.active));

  let showMovement = $state(false);
  let ledgerOpen = $state(false);
  let ledgerRefreshKey = $state(0);
  let exporting = $state(false);

  const holdingBlocks = $derived(
    promos
      .map((promo) => ({ promo, rows: holdingRows(promo) }))
      .filter((b) => b.rows.length > 0)
      .sort((a, b) => a.promo.name.localeCompare(b.promo.name))
  );

  // Resolve holder names defensively: missing/soft-deleted users show their uid.
  let names = $state<Record<string, string>>({});
  const requested = new Set<string>();
  $effect(() => {
    for (const block of holdingBlocks) {
      for (const row of block.rows) {
        if (requested.has(row.uid)) continue;
        requested.add(row.uid);
        getUser(row.uid).then((u) => {
          names = { ...names, [row.uid]: u && !u.deleted_at ? u.name : row.uid };
        });
      }
    }
  });

  async function exportCsv() {
    exporting = true;
    try {
      const entries = await getPromoLedger();
      const uids = new Set<string>();
      for (const e of entries) {
        uids.add(e.from_uid);
        if (e.to_uid) uids.add(e.to_uid);
        uids.add(e.created_by);
      }
      const resolved: Record<string, string> = {};
      await Promise.all(
        [...uids].map(async (uid) => {
          const u = await getUser(uid);
          resolved[uid] = u && !u.deleted_at ? u.name : uid;
        })
      );
      const promoNames = new Map(promos.map((p) => [p.uid, p.name]));
      const rows: string[][] = [
        ["happened_at", "kind", "promo_name", "qty", "from_name", "to_name", "note", "created_by", "created_at"],
        ...entries.map((e) => [
          e.happened_at,
          e.kind,
          promoNames.get(e.promo_uid) ?? e.promo_uid,
          String(e.qty),
          resolved[e.from_uid] ?? e.from_uid,
          e.to_uid ? (resolved[e.to_uid] ?? e.to_uid) : "",
          e.note ?? "",
          resolved[e.created_by] ?? e.created_by,
          e.created_at,
        ]),
      ];
      downloadCsv(buildCsv(rows), `promo-ledger-${new Date().toISOString().slice(0, 10)}.csv`);
    } catch {
      // Error toast shown by apiRequest
    } finally {
      exporting = false;
    }
  }
</script>

<div class="bg-surface-card rounded-lg shadow border border-line p-5">
  <div class="flex items-center gap-2 mb-3">
    <Boxes class="w-5 h-5 text-accent" aria-hidden="true" />
    <h2 class="text-lg font-medium text-ink-strong">{m.promo_inventory_title()}</h2>
  </div>

  {#if !online}
    <p class="text-xs text-ink-muted mb-3">{m.promo_inventory_offline()}</p>
  {/if}

  <div class="flex flex-wrap gap-2 mb-4">
    <Button variant="secondary" disabled={!online} onclick={() => (showMovement = true)}>
      {m.promo_record_movement()}
    </Button>
    <Button variant="ghost" disabled={!online} loading={exporting} onclick={exportCsv}>
      <Download class="w-4 h-4" aria-hidden="true" />
      {m.promo_export_csv()}
    </Button>
  </div>

  <!-- Holdings (from synced Promo.holdings — stays available offline) -->
  {#if holdingBlocks.length === 0}
    <p class="text-sm text-ink-muted">{m.promo_inventory_no_holdings()}</p>
  {:else}
    <div class="space-y-4">
      {#each holdingBlocks as block (block.promo.uid)}
        <div>
          <h3 class="text-sm font-medium text-ink-strong flex items-center gap-2">
            {block.promo.name}
            {#if !block.promo.active}
              <span class="px-1.5 py-0.5 text-xs font-normal rounded badge-slate">{m.promo_retired()}</span>
            {/if}
          </h3>
          <div class="divide-y divide-line/50">
            {#each block.rows as row (row.uid)}
              <div class="flex items-center justify-between gap-2 py-1.5 text-sm">
                <span class="text-ink min-w-0 truncate">{names[row.uid] ?? row.uid}</span>
                <span class="text-xs shrink-0">
                  {#if row.remaining === 0}
                    <span class="text-ink-faint">{m.promo_holdings_none_left()}</span>
                  {:else}
                    <span class="text-ink-muted">{m.promo_holdings_remaining({ count: String(row.remaining) })}</span>
                  {/if}
                  <span class="text-ink-faint"> · {m.promo_holdings_assigned({ count: String(row.assigned) })}</span>
                </span>
              </div>
            {/each}
          </div>
        </div>
      {/each}
    </div>
  {/if}

  <!-- Ledger (collapsed by default; online-only fetch) -->
  <div class="mt-4 border-t border-line pt-3">
    <button
      type="button"
      onclick={() => (ledgerOpen = !ledgerOpen)}
      disabled={!online}
      class="flex items-center gap-1.5 min-h-[44px] text-sm font-medium text-ink-muted enabled:hover:text-ink-strong transition-colors disabled:opacity-40"
    >
      {#if ledgerOpen}
        <ChevronDown class="w-4 h-4" aria-hidden="true" />
      {:else}
        <ChevronRight class="w-4 h-4" aria-hidden="true" />
      {/if}
      {ledgerOpen ? m.promo_ledger_hide() : m.promo_ledger_show()}
    </button>
    {#if ledgerOpen && online}
      <PromoLedgerList {promos} refreshKey={ledgerRefreshKey} />
    {/if}
  </div>
</div>

{#if showMovement}
  <RecordMovementModal
    promos={activePromos}
    {isIC}
    onclose={() => (showMovement = false)}
    onrecorded={() => (ledgerRefreshKey += 1)}
  />
{/if}
