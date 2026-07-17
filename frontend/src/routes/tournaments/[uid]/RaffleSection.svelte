<script lang="ts">
  import type { TournamentEventType } from "$lib/engine";
  import type { Tournament, RafflePool, Promo } from "$lib/types";
  import { getAllPromos } from "$lib/db";
  import { seatDisplay as seatDisplayUtil, type PlayerInfoMap } from "$lib/tournament-utils";
  import { Dices, Undo2, Trash2 } from "@lucide/svelte";
  import Button from '$lib/components/Button.svelte';
  import * as m from '$lib/paraglide/messages.js';

  const API_BASE = import.meta.env.VITE_API_URL ?? "";

  let {
    tournament,
    playerInfo,
    isOrganizer,
    doAction,
    actionLoading,
  }: {
    tournament: Tournament;
    playerInfo: PlayerInfoMap;
    isOrganizer: boolean;
    doAction?: (action: TournamentEventType, body?: any) => Promise<string | null>;
    actionLoading?: boolean;
  } = $props();

  let label = $state("");
  let pool = $state<RafflePool>("AllPlayers");
  let excludeDrawn = $state(true);
  let count = $state(1);
  let prizePromoUid = $state("");

  // Promo catalog: the organizer picks a prize from it, and both views resolve
  // a draw's prize_promo_uid to a name + image.
  let promoCatalog = $state<Promo[]>([]);
  $effect(() => {
    getAllPromos().then(promos => { promoCatalog = promos; });
  });

  // Same hard filter as the distribution report picker: active promos whose
  // gating matches this tournament (empty gating = unrestricted).
  const eligiblePromos = $derived(promoCatalog.filter(p =>
    p.active
    && (p.allowed_ranks.length === 0 || p.allowed_ranks.includes(tournament.rank))
    && (p.league_uids.length === 0
      || (!!tournament.league_uid && p.league_uids.includes(tournament.league_uid)))
  ));

  function promoByUid(uid: string | null | undefined): Promo | undefined {
    return uid ? promoCatalog.find(p => p.uid === uid) : undefined;
  }

  function seatDisplay(uid: string): string {
    return seatDisplayUtil(uid, playerInfo, tournament.online);
  }

  // Raffle base: players seated in any round, plus players currently present
  // (Checked-in/Playing) not yet seated — so a raffle at check-in, before the
  // first round, still draws from the checked-in players. Mirrors engine
  // raffle.rs get_raffle_base_uids().
  const baseUids = $derived.by(() => {
    const set = new Set<string>();
    for (const round of tournament.rounds ?? []) {
      for (const table of round) {
        for (const seat of table.seating) {
          if (seat.player_uid) set.add(seat.player_uid);
        }
      }
    }
    for (const p of tournament.players ?? []) {
      if ((p.state === "Checked-in" || p.state === "Playing") && p.user_uid) {
        set.add(p.user_uid);
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

  // Live GW/VP map: uid -> { gw, vp }, summed from per-seat round results.
  // Do NOT use tournament.standings here: it only refreshes on FinishRound,
  // so it misses GW/VP earned in the round in progress.
  const standingsMap = $derived.by(() => {
    const map = new Map<string, { gw: number; vp: number }>();
    for (const round of tournament.rounds ?? []) {
      for (const table of round) {
        for (const seat of table.seating) {
          if (!seat.player_uid) continue;
          const e = map.get(seat.player_uid) ?? { gw: 0, vp: 0 };
          e.gw += seat.result.gw ?? 0;
          e.vp += seat.result.vp ?? 0;
          map.set(seat.player_uid, e);
        }
      }
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
  // NOTE: Pool filtering logic must match engine raffle.rs get_raffle_pool()
  function eligibleForPool(p: RafflePool): number {
    let uids: string[];
    const base = [...baseUids];
    switch (p) {
      case "AllPlayers": uids = base; break;
      case "NonFinalists": uids = base.filter(u => !finalistUids.has(u)); break;
      case "GameWinners": uids = base.filter(u => (standingsMap.get(u)?.gw ?? 0) > 0); break;
      case "NoGameWin": uids = base.filter(u => (standingsMap.get(u)?.gw ?? 0) === 0); break;
      case "NoVictoryPoint": uids = base.filter(u => (standingsMap.get(u)?.vp ?? 0) === 0); break;
      default: uids = base;
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
      prize_promo_uid: prizePromoUid || undefined,
    });
    label = "";
    prizePromoUid = "";
  }

  const raffles = $derived(tournament.raffles ?? []);
  const hasRaffles = $derived(raffles.length > 0);
</script>

<div class="space-y-3">

  {#if isOrganizer && doAction}
    <!-- Organizer controls -->
    <div class="space-y-2">
      <input
        type="text"
        bind:value={label}
        placeholder={m.raffle_label_placeholder()}
        class="w-full px-3 py-2 text-sm bg-surface-hover border border-line-strong rounded-lg text-ink-strong placeholder-ink-faint focus:outline-none focus:border-line-strong"
      />
      <div class="flex flex-wrap gap-2 items-center">
        <select
          bind:value={pool}
          class="px-2 py-1.5 text-sm bg-surface-hover border border-line-strong rounded-lg text-ink-strong"
        >
          {#each poolOptions as opt}
            <option value={opt.value}>{opt.labelFn()} ({eligibleForPool(opt.value)})</option>
          {/each}
        </select>
        <label class="flex items-center gap-1.5 text-sm text-ink">
          <input type="checkbox" bind:checked={excludeDrawn} class="rounded border-line-strong" />
          {m.raffle_exclude_drawn()}
        </label>
        {#if eligiblePromos.length > 0}
          <select
            bind:value={prizePromoUid}
            aria-label={m.raffle_prize_select()}
            class="px-2 py-1.5 text-sm bg-surface-hover border border-line-strong rounded-lg text-ink-strong"
          >
            <option value="">{m.raffle_prize_none()}</option>
            {#each eligiblePromos as promo (promo.uid)}
              <option value={promo.uid}>{promo.name}</option>
            {/each}
          </select>
        {/if}
      </div>
      <div class="flex items-center gap-2">
        <label class="text-sm text-ink-muted">
          {m.raffle_winners()}:
          <input
            type="number"
            bind:value={count}
            min="1"
            max={Math.max(currentEligible, 1)}
            class="ml-1 w-16 px-2 py-1 text-sm bg-surface-hover border border-line-strong rounded text-ink-strong"
          />
        </label>
        <Button
          variant="primary"
          onclick={handleDraw}
          disabled={actionLoading || !label.trim() || currentEligible === 0}
        >
          <Dices class="w-4 h-4" />
          {m.raffle_draw()}
        </Button>
        {#if hasRaffles}
          <Button
            variant="ghost"
            onclick={() => doAction!("RaffleUndo")}
            disabled={actionLoading}
            title={m.raffle_undo()}
          >
            <Undo2 class="w-3.5 h-3.5" />
            {m.raffle_undo()}
          </Button>
          <Button
            variant="danger"
            onclick={() => { if (confirm(m.raffle_clear_confirm())) doAction!("RaffleClear"); }}
            disabled={actionLoading}
            title={m.raffle_clear()}
          >
            <Trash2 class="w-3.5 h-3.5" />
            {m.raffle_clear()}
          </Button>
        {/if}
      </div>
    </div>
  {/if}

  <!-- Raffle results -->
  {#if hasRaffles}
    <div class="space-y-2">
      {#each [...raffles].reverse() as draw}
        <div class="bg-surface-muted/50 rounded-lg p-3">
          <div class="text-sm font-medium text-ink-strong mb-1">{draw.label}</div>
          {#if draw.prize_promo_uid}
            {@const prize = promoByUid(draw.prize_promo_uid)}
            {#if prize}
              <div class="flex items-center gap-2 mb-2">
                {#if prize.image_path}
                  <img
                    src="{API_BASE}{prize.image_path}"
                    alt={prize.name}
                    loading="lazy"
                    class="w-12 rounded shadow"
                  />
                {/if}
                <span class="text-xs text-ink-muted">{m.raffle_prize_won({ name: prize.name })}</span>
              </div>
            {/if}
          {/if}
          <div class="flex flex-wrap gap-1.5">
            {#each draw.winners as winner}
              <span class="px-2 py-0.5 text-xs badge-highlight rounded">{seatDisplay(winner)}</span>
            {/each}
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>
