<script lang="ts">
  import { ADVANCED_ICON, groupCircle } from '$lib/vtes-icons';
  import type { VtesCard } from '$lib/types';

  let { card, class: cls = '' }: {
    card: Pick<VtesCard, 'printed_name' | 'full_name' | 'group' | 'adv'>;
    class?: string;
  } = $props();

  const circle = $derived(groupCircle(card.group ?? ''));
</script>

<!-- full_name is the disambiguated accessible name; the printed_name + badges are
     decorative (two cards can share printed_name, differing only by group/adv). -->
<span class="inline-flex items-baseline gap-1 min-w-0 {cls}" aria-label={card.full_name} title={card.full_name}>
  <span class="truncate" aria-hidden="true">{card.printed_name}</span>
  {#if circle}
    <span class="text-ink-muted shrink-0" aria-hidden="true">{circle}</span>
  {/if}
  {#if card.adv}
    <span class="vtes-d text-ink-muted shrink-0" aria-hidden="true">{ADVANCED_ICON}</span>
  {/if}
</span>
