<script lang="ts">
  import type { Promo } from "#lib/types.ts";
  import { getUser } from "#lib/db.ts";
  import { getPromoLedger } from "#lib/api.ts";
  import { holdingRows } from "#lib/promo-utils.ts";
  import { buildCsv } from "#lib/csv.ts";
  import { downloadBlob } from "#lib/utils.ts";
  import { isBrowserOnline } from "#lib/stores/connectivity.svelte.ts";
  import { syncQueryParams, currentParams } from "#lib/url-filters.ts";
  import Button from "#lib/components/Button.svelte";
  import PromoLedgerList from "./PromoLedgerList.svelte";
  import RecordMovementModal from "./RecordMovementModal.svelte";
  import { Boxes, Download } from "@lucide/svelte";
  import FoldableSection from "#lib/components/FoldableSection.svelte";
  import * as m from '#lib/paraglide/messages.js';

  let {
    promos,
    canManagePromo = false,
  }: {
    promos: Promo[];
    canManagePromo?: boolean;
  } = $props();

  const online = $derived(isBrowserOnline());
  const activePromos = $derived(promos.filter((p) => p.active));

  let showMovement = $state(false);
  let ledgerOpen = $state(false);
  let ledgerRefreshKey = $state(0);
  let exporting = $state(false);

  let grouping = $state<"promo" | "holder">(currentParams().get("inventory") === "holder" ? "holder" : "promo");
  $effect(() => {
    syncQueryParams({ inventory: grouping === "holder" ? grouping : null });
  });

  const holdingBlocks = $derived(
    promos
      .map((promo) => ({ promo, rows: holdingRows(promo) }))
      .filter((b) => b.rows.length > 0)
      .sort((a, b) => a.promo.name.localeCompare(b.promo.name))
  );

  const holderBlocks = $derived.by(() => {
    const byHolder = new Map<string, { promo: Promo; remaining: number; assigned: number }[]>();
    for (const block of holdingBlocks) {
      for (const row of block.rows) {
        const list = byHolder.get(row.uid) ?? [];
        list.push({ promo: block.promo, remaining: row.remaining, assigned: row.assigned });
        byHolder.set(row.uid, list);
      }
    }
    return [...byHolder.entries()]
      .map(([uid, items]) => ({ uid, items }))
      .sort((a, b) => (names[a.uid] ?? a.uid).localeCompare(names[b.uid] ?? b.uid));
  });

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
          // Intake flows into from_uid — keep the name columns directional.
          e.kind === "intake" ? "BCP" : (resolved[e.from_uid] ?? e.from_uid),
          e.kind === "intake"
            ? (resolved[e.from_uid] ?? e.from_uid)
            : e.to_uid
              ? (resolved[e.to_uid] ?? e.to_uid)
              : "",
          e.note ?? "",
          resolved[e.created_by] ?? e.created_by,
          e.created_at,
        ]),
      ];
      downloadBlob(new Blob([buildCsv(rows)], { type: "text/csv;charset=utf-8" }), `promo-ledger-${new Date().toISOString().slice(0, 10)}.csv`);
    } catch {
      // Error toast shown by apiRequest
    } finally {
      exporting = false;
    }
  }
</script>

{#snippet retired(promo: Promo)}
  {#if !promo.active}
    <span class="px-1.5 py-0.5 text-xs font-normal rounded badge-slate">{m.promo_retired()}</span>
  {/if}
{/snippet}

{#snippet counts(remaining: number, assigned: number)}
  <span class="text-xs shrink-0">
    {#if remaining === 0}
      <span class="text-ink-faint">{m.promo_holdings_none_left()}</span>
    {:else}
      <span class="text-ink-muted">{m.promo_holdings_remaining({ count: String(remaining) })}</span>
    {/if}
    <span class="text-ink-faint"> · {m.promo_holdings_received({ count: String(assigned) })}</span>
  </span>
{/snippet}

<div class="bg-surface-card rounded-lg shadow border border-line p-5">
  <div class="flex items-center gap-2 mb-3">
    <Boxes class="w-5 h-5 text-accent" aria-hidden="true" />
    <h2 class="text-lg font-medium text-ink-strong">{m.promo_inventory_title()}</h2>
  </div>

  {#if !online}
    <p class="text-xs text-ink-muted mb-3">{m.promo_inventory_offline()}</p>
  {/if}

  <div class="flex flex-wrap gap-2 mb-4">
    <Button variant="secondary" disabled={!online || activePromos.length === 0} onclick={() => (showMovement = true)}>
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
    <div class="inline-flex w-fit mb-4 bg-surface-muted rounded-lg border border-line p-1">
      {#each [["promo", m.promo_inventory_by_promo()], ["holder", m.promo_inventory_by_holder()]] as [value, label] (value)}
        <button
          onclick={() => (grouping = value as "promo" | "holder")}
          aria-pressed={grouping === value}
          class="px-3 py-1.5 text-sm font-medium rounded-md transition-colors {grouping === value ? 'bg-accent-strong text-white' : 'text-ink-muted hover:text-ink-bright'}"
        >
          {label}
        </button>
      {/each}
    </div>
    <div class="space-y-4">
      {#if grouping === "promo"}
        {#each holdingBlocks as block (block.promo.uid)}
          <div>
            <h3 class="text-sm font-medium text-ink-strong flex items-center gap-2">
              {block.promo.name}
              {@render retired(block.promo)}
            </h3>
            <div class="divide-y divide-line/50">
              {#each block.rows as row (row.uid)}
                <div class="flex items-center justify-between gap-2 py-1.5 text-sm">
                  <span class="text-ink min-w-0 truncate">{names[row.uid] ?? row.uid}</span>
                  {@render counts(row.remaining, row.assigned)}
                </div>
              {/each}
            </div>
          </div>
        {/each}
      {:else}
        {#each holderBlocks as block (block.uid)}
          <div>
            <h3 class="text-sm font-medium text-ink-strong truncate">{names[block.uid] ?? block.uid}</h3>
            <div class="divide-y divide-line/50">
              {#each block.items as item (item.promo.uid)}
                <div class="flex items-center justify-between gap-2 py-1.5 text-sm">
                  <span class="text-ink min-w-0 truncate flex items-center gap-2">
                    {item.promo.name}
                    {@render retired(item.promo)}
                  </span>
                  {@render counts(item.remaining, item.assigned)}
                </div>
              {/each}
            </div>
          </div>
        {/each}
      {/if}
    </div>
  {/if}

  <div class="mt-4">
    <FoldableSection title={m.promo_ledger_title()} bind:open={ledgerOpen} disabled={!online}>
      {#if online}
        <PromoLedgerList {promos} refreshKey={ledgerRefreshKey} />
      {/if}
    </FoldableSection>
  </div>
</div>

{#if showMovement}
  <RecordMovementModal
    promos={activePromos}
    {canManagePromo}
    onclose={() => (showMovement = false)}
    onrecorded={() => (ledgerRefreshKey += 1)}
  />
{/if}
