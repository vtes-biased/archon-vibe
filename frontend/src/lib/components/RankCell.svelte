<script lang="ts">
  import { Trophy } from "lucide-svelte";
  import * as m from "$lib/paraglide/messages.js";

  // Renders a final-placement rank: a trophy for the winner (rank 1), a dimmed
  // number + "Finalist" pill for the tied-for-2nd finalists (VEKN §3.7.5), and a
  // plain number otherwise. Single-sources the "2,2,2,2" tie presentation so it
  // reads as a deliberate band, not a glitch.
  let { rank, finalist = false, hash = false }: {
    rank: number;
    finalist?: boolean;
    hash?: boolean;
  } = $props();
</script>

{#if rank === 1}
  <Trophy class="w-3.5 h-3.5 inline align-middle text-amber-400" aria-label={m.tournament_winner()} />
{:else if finalist}
  <span class="text-ash-600">{hash ? "#" : ""}{rank}</span>
  <span class="ml-1 text-[10px] px-1 py-0.5 rounded badge-amber align-middle">{m.tournament_finalist()}</span>
{:else}
  {hash ? "#" : ""}{rank}
{/if}
