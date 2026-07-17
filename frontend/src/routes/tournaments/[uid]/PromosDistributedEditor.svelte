<script lang="ts">
  import type { Tournament, Promo, PromoDistribution } from "$lib/types";
  import { getAllPromos, getUser } from "$lib/db";
  import { tournamentAction } from "$lib/tournament-actions";
  import { getAuthState } from "$lib/stores/auth.svelte";
  import { showToast } from "$lib/stores/toast.svelte";
  import { Plus, X } from "@lucide/svelte";
  import * as m from '$lib/paraglide/messages.js';

  let {
    tournament,
    onupdate,
  }: {
    tournament: Tournament;
    onupdate: (tournament: Tournament) => void;
  } = $props();

  // svelte-ignore state_referenced_locally
  const initial = tournament.promos_distributed ?? [];
  let rows = $state<PromoDistribution[]>(initial.map(r => ({ ...r })));
  // svelte-ignore state_referenced_locally
  let stockSource = $state(
    tournament.promo_stock_source_uid || getAuthState().user?.uid || ""
  );

  let catalog = $state<Promo[]>([]);
  let organizerNames = $state<Record<string, string>>({});

  $effect(() => {
    getAllPromos().then(promos => { catalog = promos; });
  });

  const organizers = $derived(tournament.organizers_uids ?? []);
  $effect(() => {
    for (const uid of organizers) {
      if (!(uid in organizerNames)) {
        getUser(uid).then(u => {
          if (u) organizerNames = { ...organizerNames, [uid]: u.name };
        });
      }
    }
  });

  // Hard filter: active promos whose gating matches this tournament (empty
  // gating = unrestricted; rank and league gating compose with AND).
  const eligible = $derived(catalog.filter(p =>
    p.active
    && (p.allowed_ranks.length === 0 || p.allowed_ranks.includes(tournament.rank))
    && (p.league_uids.length === 0
      || (!!tournament.league_uid && p.league_uids.includes(tournament.league_uid)))
  ));

  // One row per promo: a row's options exclude promos chosen in other rows but
  // always include its own current pick (even retired or re-gated) so an
  // existing report keeps rendering.
  function optionsFor(index: number): Promo[] {
    const chosen = new Set(rows.filter((_, i) => i !== index).map(r => r.promo_uid));
    const opts = eligible.filter(p => !chosen.has(p.uid));
    const current = rows[index]?.promo_uid;
    if (current && !opts.some(p => p.uid === current)) {
      const cur = catalog.find(p => p.uid === current);
      if (cur) opts.unshift(cur);
    }
    return opts;
  }

  // Cleared qty binds to null; promo may be unpicked on a fresh row. Saving is
  // suspended while any row is invalid — say so instead of silently no-oping.
  const hasInvalidRow = $derived(rows.some(r => !r.promo_uid || !(r.qty >= 1)));

  let saving = $state(false);

  async function save() {
    if (hasInvalidRow) return;
    saving = true;
    try {
      const updated = await tournamentAction(tournament.uid, 'ReportPromos', {
        promos: rows.map(r => ({ promo_uid: r.promo_uid, qty: r.qty })),
        stock_source_uid: stockSource || undefined,
      });
      onupdate(updated);
    } catch {
      showToast({ type: "error", message: m.promos_error_save() });
    } finally {
      saving = false;
    }
  }

  function addRow() {
    rows = [...rows, { promo_uid: "", qty: 1 }];
  }

  function removeRow(index: number) {
    rows = rows.filter((_, i) => i !== index);
    save();
  }
</script>

<div>
  {#if organizers.length > 1}
    <div class="mb-3">
      <label class="block text-xs text-ink-faint mb-1" for="promo-stock-source">{m.promos_stock_source()}</label>
      <select
        id="promo-stock-source"
        bind:value={stockSource}
        onchange={() => { if (rows.length > 0) save(); }}
        class="w-full px-2 py-1 min-h-[44px] text-sm bg-surface-muted border border-line-strong rounded text-ink-strong focus:border-accent-strong-hover focus:outline-none"
      >
        {#each organizers as uid}
          <option value={uid}>{organizerNames[uid] ?? uid}</option>
        {/each}
      </select>
      <p class="text-xs text-ink-faint mt-1">{m.promos_stock_source_hint()}</p>
    </div>
  {/if}

  {#if rows.length > 0}
    <div class="space-y-2 mb-3">
      {#each rows as row, i}
        <div class="flex items-center gap-1">
          <select
            bind:value={row.promo_uid}
            onchange={() => save()}
            aria-label={m.promos_select()}
            class="flex-1 min-w-0 px-2 py-1 min-h-[44px] text-sm bg-surface-muted border rounded text-ink-strong focus:border-accent-strong-hover focus:outline-none {row.promo_uid ? 'border-line-strong' : 'border-warn'}"
          >
            <option value="" disabled>{m.promos_select()}</option>
            {#each optionsFor(i) as promo (promo.uid)}
              <option value={promo.uid}>{promo.name}</option>
            {/each}
          </select>
          <input
            type="number"
            bind:value={row.qty}
            onchange={() => save()}
            min={1}
            max={999}
            aria-label={m.promos_qty()}
            class="w-16 px-2 py-1 min-h-[44px] text-sm bg-surface-muted border rounded text-ink-strong text-center focus:border-accent-strong-hover focus:outline-none {row.qty >= 1 ? 'border-line-strong' : 'border-warn'}"
          />
          <button
            onclick={() => removeRow(i)}
            disabled={saving}
            class="min-w-[44px] min-h-[44px] flex items-center justify-center text-ink-faint hover:text-link transition-colors"
            aria-label={m.promos_remove()}
          ><X class="w-4 h-4" /></button>
        </div>
      {/each}
    </div>
    {#if hasInvalidRow}
      <p class="text-xs text-warn mb-2">{m.promos_validation_hint()}</p>
    {/if}
    <p class="text-xs text-ink-faint mb-2">{m.promos_hint()}</p>
  {:else}
    <p class="text-xs text-ink-faint mb-2">{m.promos_empty_state()}</p>
  {/if}

  <button
    onclick={addRow}
    disabled={saving}
    class="flex items-center gap-1 min-h-[44px] text-sm text-ink-muted hover:text-ink-strong transition-colors"
  >
    <Plus class="w-4 h-4" />
    {m.promos_add()}
  </button>
</div>
