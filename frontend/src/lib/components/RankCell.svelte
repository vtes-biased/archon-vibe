<script lang="ts">
  import { Trophy } from "@lucide/svelte";
  import * as m from "$lib/paraglide/messages.js";

  // Renders a final-placement rank: a trophy for the winner (rank 1), a dimmed
  // number + "Finalist" pill for the tied-for-2nd finalists (VEKN §3.7.5), and a
  // plain number otherwise. Single-sources the "2,2,2,2" tie presentation so it
  // reads as a deliberate band, not a glitch.
  //
  // `total` makes the cell a self-contained placement ("#1 / 43") for lists with no
  // rank column to supply that meaning. It also forces the winner's NUMBER to render
  // — the trophy alone would leave a denominator with no numerator — and carries the
  // spoken sentence, since a rendered "/" does not read as "of".
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
