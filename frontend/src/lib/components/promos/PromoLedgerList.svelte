<script lang="ts">
  // Online-only ledger read (the sanctioned SYNC.md carve-out) with simple
  // client-side filters. Rendered inside the inventory panel.
  import type { Promo, PromoLedgerEntry, PromoLedgerKind } from "$lib/types";
  import { getPromoLedger } from "$lib/api";
  import { getUser } from "$lib/db";
  import * as m from '$lib/paraglide/messages.js';

  let {
    promos,
    refreshKey = 0,
  }: {
    promos: Promo[];
    refreshKey?: number;
  } = $props();

  let entries = $state<PromoLedgerEntry[]>([]);
  let loading = $state(true);
  let loadFailed = $state(false);
  let names = $state<Record<string, string>>({});
  const requested = new Set<string>();

  $effect(() => {
    void refreshKey; // re-fetch after a recorded movement
    loading = true;
    loadFailed = false;
    getPromoLedger()
      .then((rows) => {
        entries = [...rows].sort((a, b) => b.happened_at.localeCompare(a.happened_at));
      })
      .catch(() => {
        // Error toast shown by apiRequest
        loadFailed = true;
      })
      .finally(() => {
        loading = false;
      });
  });

  // Resolve party names defensively: missing/soft-deleted users show their uid.
  $effect(() => {
    for (const e of entries) {
      for (const uid of [e.from_uid, e.to_uid]) {
        if (!uid || requested.has(uid)) continue;
        requested.add(uid);
        getUser(uid).then((u) => {
          names = { ...names, [uid]: u && !u.deleted_at ? u.name : uid };
        });
      }
    }
  });

  const promoNames = $derived(new Map(promos.map((p) => [p.uid, p.name])));

  let filterPromo = $state("");
  let filterKind = $state("");
  let filterFrom = $state("");
  let filterTo = $state("");

  const filtered = $derived(
    entries.filter(
      (e) =>
        (!filterPromo || e.promo_uid === filterPromo) &&
        (!filterKind || e.kind === filterKind) &&
        (!filterFrom || e.happened_at.slice(0, 10) >= filterFrom) &&
        (!filterTo || e.happened_at.slice(0, 10) <= filterTo)
    )
  );

  function fmtDate(iso: string): string {
    return new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
  }

  const kindLabels: Record<PromoLedgerKind, () => string> = {
    intake: m.promo_ledger_kind_intake,
    assignment: m.promo_ledger_kind_assignment,
    distribution: m.promo_ledger_kind_distribution,
  };
  const kindBadges: Record<PromoLedgerKind, string> = {
    intake: "badge-amethyst",
    assignment: "badge-blue",
    distribution: "badge-fuchsia",
  };

  const selectClass =
    'px-2 py-1 min-h-[44px] text-sm bg-surface-card border border-line-strong rounded-lg text-ink-bright focus:ring-2 focus:ring-accent focus:border-transparent';
</script>

<div>
  <!-- Filters -->
  <div class="flex flex-wrap gap-2 mb-3">
    <select bind:value={filterPromo} aria-label={m.promo_ledger_filter_promo()} class={selectClass}>
      <option value="">{m.promo_ledger_all_promos()}</option>
      {#each promos as promo (promo.uid)}
        <option value={promo.uid}>{promo.name}</option>
      {/each}
    </select>
    <select bind:value={filterKind} aria-label={m.promo_ledger_filter_kind()} class={selectClass}>
      <option value="">{m.promo_ledger_all_kinds()}</option>
      <option value="intake">{m.promo_ledger_kind_intake()}</option>
      <option value="assignment">{m.promo_ledger_kind_assignment()}</option>
      <option value="distribution">{m.promo_ledger_kind_distribution()}</option>
    </select>
    <input type="date" bind:value={filterFrom} aria-label={m.promo_ledger_filter_from()} class={selectClass} />
    <input type="date" bind:value={filterTo} aria-label={m.promo_ledger_filter_to()} class={selectClass} />
  </div>

  {#if loading}
    <p class="text-sm text-ink-muted py-2">{m.common_loading()}</p>
  {:else if loadFailed}
    <p class="text-sm text-ink-muted py-2">{m.promo_ledger_error()}</p>
  {:else if filtered.length === 0}
    <p class="text-sm text-ink-muted py-2">{m.promo_ledger_empty()}</p>
  {:else}
    <div class="divide-y divide-line/50">
      {#each filtered as entry (entry.uid)}
        <div class="py-2 text-sm">
          <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span class="text-xs text-ink-muted">{fmtDate(entry.happened_at)}</span>
            <span class="px-1.5 py-0.5 text-xs rounded {kindBadges[entry.kind]}">
              {kindLabels[entry.kind]()}
            </span>
            <span class="font-medium text-ink-strong">{promoNames.get(entry.promo_uid) ?? entry.promo_uid}</span>
            <span class={entry.qty < 0 ? 'text-warn' : 'text-ink'}>×{entry.qty}</span>
          </div>
          <div class="text-xs text-ink-muted mt-0.5">
            <!-- Intake flows into from_uid (the receiving holder), out otherwise -->
            {#if entry.kind === "intake"}
              {m.promo_ledger_source_bcp()}
              →
              {names[entry.from_uid] ?? entry.from_uid}
            {:else}
              {names[entry.from_uid] ?? entry.from_uid}
              →
              {entry.to_uid ? (names[entry.to_uid] ?? entry.to_uid) : m.promo_ledger_to_players()}
            {/if}
          </div>
          {#if entry.note}
            <div class="text-xs text-ink-faint mt-0.5">{entry.note}</div>
          {/if}
        </div>
      {/each}
    </div>
  {/if}
</div>
