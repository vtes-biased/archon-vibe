<script lang="ts">
  import type { Promo } from "$lib/types";
  import PromoCard from "./PromoCard.svelte";
  import Button from "$lib/components/Button.svelte";
  import { Gift, Plus } from "@lucide/svelte";
  import * as m from '$lib/paraglide/messages.js';

  let {
    promos,
    isIC = false,
    isOfficial = false,
    onedit,
    ontoggleactive,
    ondelete,
    oncreate,
  }: {
    promos: Promo[];
    isIC?: boolean;
    isOfficial?: boolean;
    onedit?: (promo: Promo) => void;
    ontoggleactive?: (promo: Promo) => void;
    ondelete?: (promo: Promo) => void;
    oncreate?: () => void;
  } = $props();

  let showRetired = $state(false);
  const retiredCount = $derived(promos.filter((p) => !p.active).length);
  const displayed = $derived(showRetired ? promos : promos.filter((p) => p.active));
</script>

{#if isOfficial && retiredCount > 0}
  <label class="flex items-center gap-2 mb-3 min-h-[44px] w-fit cursor-pointer">
    <input
      type="checkbox"
      bind:checked={showRetired}
      class="w-5 h-5 rounded border-line-strong bg-surface-card text-accent focus:ring-accent"
    />
    <span class="text-sm text-ink-muted">{m.promo_show_retired()} ({retiredCount})</span>
  </label>
{/if}

{#if displayed.length > 0}
  <div class="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
    {#each displayed as promo (promo.uid)}
      <PromoCard {promo} {isIC} {onedit} {ontoggleactive} {ondelete} />
    {/each}
  </div>
{:else}
  <div class="text-center py-12">
    <Gift class="mx-auto h-12 w-12 text-ink-faint mb-4" aria-hidden="true" />
    <h3 class="text-lg font-medium text-ink-strong mb-2">{m.promo_gallery_empty()}</h3>
    <p class="text-ink-muted text-sm">{m.promo_gallery_empty_hint()}</p>
    {#if isIC}
      <div class="mt-4">
        <Button variant="primary" onclick={() => oncreate?.()}>
          <Plus class="w-4 h-4" aria-hidden="true" />
          {m.promo_gallery_empty_cta()}
        </Button>
      </div>
    {/if}
  </div>
{/if}
