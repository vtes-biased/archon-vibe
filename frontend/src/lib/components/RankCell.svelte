<script lang="ts">
  import { Trophy } from "@lucide/svelte";
  import * as m from "$lib/paraglide/messages.js";

  // Single-sources the tied-for-2nd "Finalist" pill presentation (VEKN §3.7.5) so it reads as a
  // deliberate band, not a glitch. `total` also forces the winner's NUMBER to render as "#1 / 43" — the trophy alone would leave a denominator with no numerator.
  let { rank, finalist = false, hash = false, total = undefined }: {
    rank: number;
    finalist?: boolean;
    hash?: boolean;
    total?: number;
  } = $props();

  let num = $derived(`${hash ? "#" : ""}${rank}${total === undefined ? "" : ` / ${total}`}`);
  // Spoken by the sr-only sentence instead; the pill stays audible on its own.
  let muted = $derived(total === undefined ? undefined : true);
</script>

{#if total !== undefined}
  <span class="sr-only">{m.user_detail_placement({ rank, total })}</span>
{/if}
{#if rank === 1}
  <Trophy
    class="w-3.5 h-3.5 inline align-middle text-highlight"
    aria-label={total === undefined ? m.tournament_winner() : undefined}
    aria-hidden={muted}
  />
  {#if total !== undefined}<span class="whitespace-nowrap" aria-hidden="true">{num}</span>{/if}
{:else if finalist}
  <span class="text-ink-faint whitespace-nowrap" aria-hidden={muted}>{num}</span>
  <span class="ml-1 text-[10px] px-1 py-0.5 rounded badge-highlight align-middle">{m.tournament_finalist()}</span>
{:else}
  <span class="whitespace-nowrap" aria-hidden={muted}>{num}</span>
{/if}
