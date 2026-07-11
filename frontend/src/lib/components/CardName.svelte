<script lang="ts">
  import { ADVANCED_ICON, groupCircle } from '$lib/vtes-icons';
  import type { VtesCard } from '$lib/types';

  let { card, class: cls = '' }: {
    card: Pick<VtesCard, 'printed_name' | 'full_name' | 'group' | 'adv'>;
    class?: string;
  } = $props();

  const circle = $derived(groupCircle(card.group ?? ''));

  // Advanced badge uses the Ankha-font glyph; until that font is ready show a plain
  // "A". The font is bundled + service-worker-precached, so this only covers the
  // brief first-paint FOUT — offline it's always there.
  let fontReady = $state(false);
  $effect(() => {
    const fonts = document.fonts;
    if (!fonts || fonts.check('1em "Ankha VTES"')) {
      fontReady = true;
      return;
    }
    fonts.load('1em "Ankha VTES"').then(() => (fontReady = true)).catch(() => {});
  });
</script>

<!-- full_name is the disambiguated accessible name; the printed_name + badges are
     decorative (two cards can share printed_name, differing only by group/adv). -->
<span class="inline-flex items-baseline gap-1 min-w-0 {cls}" aria-label={card.full_name} title={card.full_name}>
  <span class="truncate" aria-hidden="true">{card.printed_name}</span>
  {#if circle}
    <span class="text-ink-muted shrink-0" aria-hidden="true">{circle}</span>
  {/if}
  {#if card.adv}
    {#if fontReady}
      <span class="vtes-d text-ink-muted shrink-0" aria-hidden="true">{ADVANCED_ICON}</span>
    {:else}
      <span class="text-ink-muted shrink-0 font-semibold" aria-hidden="true">A</span>
    {/if}
  {/if}
</span>
