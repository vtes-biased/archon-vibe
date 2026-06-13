<script lang="ts">
  // Subtle in-memoriam marker rendered before a member's name in list views.
  // Renders nothing unless the member is deceased.
  import { Flower2 } from "@lucide/svelte";
  import * as m from '$lib/paraglide/messages.js';

  let { deceased }: { deceased?: string | null } = $props();
</script>

{#if deceased}
  <Flower2
    class="inline-block w-3.5 h-3.5 text-ash-400 mr-1 align-[-0.15em] shrink-0"
    aria-label={m.deceased_badge_title()}
  />
{/if}
