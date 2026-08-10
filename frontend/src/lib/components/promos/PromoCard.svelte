<script lang="ts">
  import type { Promo } from "$lib/types";
  import { promoImageUrl, promoKindLabel } from "$lib/promo-utils";
  import { rankBadgeLabel } from "$lib/tournament-utils";
  import ActionMenu from "$lib/components/ActionMenu.svelte";
  import { RectangleVertical, Package, Gift, Pencil, Archive, ArchiveRestore, Trash2 } from "@lucide/svelte";
  import * as m from '$lib/paraglide/messages.js';

  let {
    promo,
    canManagePromo = false,
    onedit,
    ontoggleactive,
    ondelete,
  }: {
    promo: Promo;
    canManagePromo?: boolean;
    onedit?: (promo: Promo) => void;
    ontoggleactive?: (promo: Promo) => void;
    ondelete?: (promo: Promo) => void;
  } = $props();

  const KIND_ICONS = { card: RectangleVertical, pack: Package, other: Gift } as const;
  const KindIcon = $derived(KIND_ICONS[promo.kind] ?? Gift);

  const src = $derived(promoImageUrl(promo));
  let broken = $state(false);
  // A new/changed image path gets a fresh chance to load (clone TournamentBanner).
  $effect(() => {
    void promo.image_path;
    broken = false;
  });

  const releaseDate = $derived(
    promo.release_date
      ? new Date(promo.release_date).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" })
      : null
  );
</script>

<!-- Retired dimming applies to artwork only — the IC ActionMenu and badge stay
     at full opacity (an official managing a retired promo needs AA contrast). -->
<div class="relative flex flex-col rounded-lg border border-line bg-surface-card p-2">
  <div class="relative aspect-[5/7] rounded-md bg-surface-muted overflow-hidden">
    {#if src && !broken}
      <img
        {src}
        alt={promo.name}
        loading="lazy"
        class="w-full h-full object-contain {promo.active ? '' : 'opacity-60'}"
        onerror={() => (broken = true)}
      />
    {:else}
      <!-- Missing/broken image: neutral tile with kind glyph + name, never a broken img -->
      <div class="w-full h-full flex flex-col items-center justify-center gap-2 px-2 text-center {promo.active ? '' : 'opacity-60'}">
        <KindIcon class="w-8 h-8 text-ink-faint" aria-hidden="true" />
        <span class="text-xs text-ink-muted break-words">{promo.name}</span>
      </div>
    {/if}
    {#if !promo.active}
      <span class="absolute top-1.5 left-1.5 px-1.5 py-0.5 text-xs rounded badge-slate">{m.promo_retired()}</span>
    {/if}
    {#if canManagePromo}
      <div class="absolute top-1 right-1">
        <ActionMenu
          label={m.common_more()}
          align="right"
          items={[
            { label: m.common_edit(), icon: Pencil, onclick: () => onedit?.(promo) },
            promo.active
              ? { label: m.promo_retire(), icon: Archive, onclick: () => ontoggleactive?.(promo) }
              : { label: m.promo_reactivate(), icon: ArchiveRestore, onclick: () => ontoggleactive?.(promo) },
            { label: m.common_delete(), icon: Trash2, onclick: () => ondelete?.(promo) },
          ]}
        />
      </div>
    {/if}
  </div>
  <div class="mt-2 min-w-0 {promo.active ? '' : 'opacity-60'}">
    <div class="text-sm font-semibold text-ink-strong truncate" title={promo.name}>{promo.name}</div>
    <div class="text-xs text-ink-muted">{promoKindLabel(promo.kind)}{releaseDate ? ` · ${releaseDate}` : ''}</div>
    {#if promo.allowed_ranks.length > 0 || promo.league_uids.length > 0}
      <div class="mt-1 flex flex-wrap gap-1">
        {#each promo.allowed_ranks as rank (rank)}
          <span class="px-1.5 py-0.5 text-xs rounded badge-amethyst">{rankBadgeLabel(rank)}</span>
        {/each}
        {#if promo.league_uids.length > 0}
          <span class="px-1.5 py-0.5 text-xs rounded badge-blue">{m.promo_leagues_count({ count: String(promo.league_uids.length) })}</span>
        {/if}
      </div>
    {/if}
  </div>
</div>
