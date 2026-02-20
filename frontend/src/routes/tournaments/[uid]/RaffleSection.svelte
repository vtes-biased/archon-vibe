<script lang="ts">
  import type { Tournament, Standing, RafflePool } from "$lib/types";
  import { seatDisplay as seatDisplayUtil } from "$lib/tournament-utils";
  import { Dices, Undo2, Trash2 } from "lucide-svelte";
  import * as m from '$lib/paraglide/messages.js';

  let {
    tournament,
    playerInfo,
    standings,
    isOrganizer,
    doAction,
    actionLoading,
  }: {
    tournament: Tournament;
    playerInfo: Record<string, { name: string; nickname: string | null; vekn: string | null }>;
    standings: Standing[];
    isOrganizer: boolean;
    doAction?: (action: string, body?: any) => Promise<void>;
    actionLoading?: boolean;
  } = $props();

  let label = $state("");
  let pool = $state<RafflePool>("AllPlayers");
  let excludeDrawn = $state(true);
  let count = $state(1);

  function seatDisplay(uid: string): string {
    return seatDisplayUtil(uid, playerInfo);
  }

  // Collect UIDs of players who appeared in any round seating
  const playedUids = $derived.by(() => {
    const set = new Set<string>();
    for (const round of tournament.rounds ?? []) {
      for (const table of round) {
        for (const seat of table.seating) {
          if (seat.player_uid) set.add(seat.player_uid);
        }
      }
    }
    return set;
  });

  // Finalists set
  const finalistUids = $derived.by(() => {
    const set = new Set<string>();
    if (tournament.finals) {
      for (const seat of tournament.finals.seating) {
        set.add(seat.player_uid);
      }
    }
    return set;
  });

  // Standings map: uid -> { gw, vp }
  const standingsMap = $derived.by(() => {
    const map = new Map<string, { gw: number; vp: number }>();
    for (const s of standings) {
      map.set(s.user_uid, { gw: s.gw, vp: s.vp });
    }
    return map;
  });

  // Already-drawn UIDs
  const drawnUids = $derived.by(() => {
    const set = new Set<string>();
    for (const draw of tournament.raffles ?? []) {
      for (const w of draw.winners) set.add(w);
    }
    return set;
  });

  // Compute eligible count per pool
  // NOTE: Pool filtering logic must match engine/src/tournament.rs get_raffle_pool()
  function eligibleForPool(p: RafflePool): number {
    let uids: string[];
    const played = [...playedUids];
    switch (p) {
      case "AllPlayers": uids = played; break;
      case "NonFinalists": uids = played.filter(u => !finalistUids.has(u)); break;
      case "GameWinners": uids = played.filter(u => (standingsMap.get(u)?.gw ?? 0) > 0); break;
      case "NoGameWin": uids = played.filter(u => (standingsMap.get(u)?.gw ?? 0) === 0); break;
      case "NoVictoryPoint": uids = played.filter(u => (standingsMap.get(u)?.vp ?? 0) === 0); break;
      default: uids = played;
    }
    if (excludeDrawn) {
      uids = uids.filter(u => !drawnUids.has(u));
    }
    return uids.length;
  }

  const currentEligible = $derived(eligibleForPool(pool));

  // Pool options with labels
  const poolOptions: { value: RafflePool; labelFn: () => string }[] = [
    { value: "AllPlayers", labelFn: () => m.raffle_pool_all_players() },
    { value: "NonFinalists", labelFn: () => m.raffle_pool_non_finalists() },
    { value: "GameWinners", labelFn: () => m.raffle_pool_game_winners() },
    { value: "NoGameWin", labelFn: () => m.raffle_pool_no_game_win() },
    { value: "NoVictoryPoint", labelFn: () => m.raffle_pool_no_victory_point() },
  ];

  async function handleDraw() {
    if (!doAction || !label.trim() || currentEligible === 0) return;
    const seed = crypto.getRandomValues(new Uint32Array(1))[0]!;
    await doAction("RaffleDraw", {
      label: label.trim(),
      pool,
      exclude_drawn: excludeDrawn,
      count: Math.min(count, currentEligible),
      seed,
    });
    label = "";
  }

  const raffles = $derived(tournament.raffles ?? []);
  const hasRaffles = $derived(raffles.length > 0);
</script>

<div class="bg-ash-900/30 rounded-lg p-4 space-y-3">
  <h3 class="text-sm font-medium text-ash-300">{m.raffle_title()}</h3>

  {#if isOrganizer && doAction}
    <!-- Organizer controls -->
    <div class="space-y-2">
      <input
        type="text"
        bind:value={label}
        placeholder={m.raffle_label_placeholder()}
        class="w-full px-3 py-2 text-sm bg-ash-800 border border-ash-700 rounded-lg text-bone-100 placeholder-ash-500 focus:outline-none focus:border-ash-500"
      />
      <div class="flex flex-wrap gap-2 items-center">
        <select
          bind:value={pool}
          class="px-2 py-1.5 text-sm bg-ash-800 border border-ash-700 rounded-lg text-bone-100"
        >
          {#each poolOptions as opt}
            <option value={opt.value}>{opt.labelFn()} ({eligibleForPool(opt.value)})</option>
          {/each}
        </select>
        <label class="flex items-center gap-1.5 text-sm text-ash-300">
          <input type="checkbox" bind:checked={excludeDrawn} class="rounded border-ash-600" />
          {m.raffle_exclude_drawn()}
        </label>
      </div>
      <div class="flex items-center gap-2">
        <label class="text-sm text-ash-400">
          {m.raffle_winners()}:
          <input
            type="number"
            bind:value={count}
            min="1"
            max={Math.max(currentEligible, 1)}
            class="ml-1 w-16 px-2 py-1 text-sm bg-ash-800 border border-ash-700 rounded text-bone-100"
          />
        </label>
        <button
          onclick={handleDraw}
          disabled={actionLoading || !label.trim() || currentEligible === 0}
          class="flex items-center gap-1.5 px-3 py-1.5 text-sm btn-amber disabled:bg-ash-700 rounded-lg transition-colors"
        >
          <Dices class="w-4 h-4" />
          {m.raffle_draw()}
        </button>
        {#if hasRaffles}
          <button
            onclick={() => doAction!("RaffleUndo")}
            disabled={actionLoading}
            class="flex items-center gap-1 px-2 py-1.5 text-sm text-ash-300 hover:text-bone-100 border border-ash-700 hover:border-ash-600 rounded-lg transition-colors"
            title={m.raffle_undo()}
          >
            <Undo2 class="w-3.5 h-3.5" />
            {m.raffle_undo()}
          </button>
          <button
            onclick={() => { if (confirm(m.raffle_clear_confirm())) doAction!("RaffleClear"); }}
            disabled={actionLoading}
            class="flex items-center gap-1 px-2 py-1.5 text-sm text-crimson-400 hover:text-crimson-300 border border-crimson-800 hover:border-crimson-700 rounded-lg transition-colors"
            title={m.raffle_clear()}
          >
            <Trash2 class="w-3.5 h-3.5" />
            {m.raffle_clear()}
          </button>
        {/if}
      </div>
    </div>
  {/if}

  <!-- Raffle results -->
  {#if hasRaffles}
    <div class="space-y-2">
      {#each [...raffles].reverse() as draw}
        <div class="bg-ash-900/50 rounded-lg p-3">
          <div class="text-sm font-medium text-bone-100 mb-1">{draw.label}</div>
          <div class="flex flex-wrap gap-1.5">
            {#each draw.winners as winner}
              <span class="px-2 py-0.5 text-xs badge-amber rounded">{seatDisplay(winner)}</span>
            {/each}
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>
