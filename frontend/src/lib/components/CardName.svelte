<script lang="ts">
  import { ADVANCED_ICON, groupCircle } from '$lib/vtes-icons';

  let { card, class: cls = '' }: {
    card: { printed_name: string; group?: string; adv?: boolean };
    class?: string;
  } = $props();

  const circle = $derived(groupCircle(card.group ?? ''));
</script>

<span class="inline-flex items-baseline gap-1 min-w-0 {cls}">
  <span class="truncate">{card.printed_name}</span>
  {#if circle}
    <span class="text-ink-faint shrink-0" title={`Group ${card.group}`}>{circle}</span>
  {/if}
  {#if card.adv}
    <span class="vtes-d text-ink-faint shrink-0" title="Advanced">{ADVANCED_ICON}</span>
  {/if}
</span>
