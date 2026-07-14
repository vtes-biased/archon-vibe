<script lang="ts">
  import type { Tournament, SanctionLevel, SanctionCategory, SanctionSubcategory, Sanction } from "$lib/types";
  import { getSanctionReference } from "$lib/engine";
  import { issueTournamentSanction } from "$lib/sanction-actions";
  import { getPlayerSanctionsInTournament } from "$lib/db";
  import { showToast } from "$lib/stores/toast.svelte";
  import { TriangleAlert, CircleArrowDown } from "@lucide/svelte";
  import Button from '$lib/components/Button.svelte';
  import * as m from '$lib/paraglide/messages.js';

  let {
    tournament,
    playerUid,
    playerName,
    currentRound,
    onClose,
  }: {
    tournament: Tournament;
    playerUid: string;
    playerName: string;
    currentRound: number | null;
    onClose: () => void;
  } = $props();

  // Form state
  let level = $state<SanctionLevel>("caution");
  let category = $state<SanctionCategory>("procedural_error");
  let subcategory = $state<SanctionSubcategory | null>(null);
  // svelte-ignore state_referenced_locally — intentionally captures initial value
  let roundNumber = $state<number | null>(currentRound);
  let description = $state("");
  let creating = $state(false);

  // Escalation data
  let priorSanctions = $state<Sanction[]>([]);

  // Load prior sanctions for this player in this tournament
  $effect(() => {
    getPlayerSanctionsInTournament(playerUid, tournament.uid).then(s => {
      priorSanctions = s;
    });
  });

  // Judges-Guide tables from the engine (WASM is initialized well before a
  // judge can open this modal; null only in the engine-failed degraded state).
  const sanctionRef = getSanctionReference();

  // Available subcategories for selected category
  const availableSubcategories = $derived(
    sanctionRef?.subcategoriesByCategory[category] ?? []
  );

  // Reset subcategory when category changes
  $effect(() => {
    const subs = sanctionRef?.subcategoriesByCategory[category];
    if (subs && subcategory && !subs.includes(subcategory)) {
      subcategory = null;
    }
  });

  // Baseline penalty hint
  const baselinePenalty = $derived(
    subcategory ? (sanctionRef?.baselinePenalties[subcategory] ?? null) : null
  );

  // Severity ordering for level comparison
  const LEVEL_SEVERITY: Record<SanctionLevel, number> = {
    caution: 0, warning: 1, standings_adjustment: 2,
    disqualification: 3, suspension: 4, probation: 4,
  };

  // All active (non-lifted, non-deleted) prior sanctions in this tournament
  const activePrior = $derived(
    priorSanctions.filter(s => !s.lifted_at && !s.deleted_at)
  );

  // Escalation hint (v2 §1.2.1): the ladder enters at the subcategory baseline
  // and climbs one rung per prior offence of the same type, clamped at DQ.
  const sameInfractionCount = $derived(
    subcategory ? activePrior.filter(s => s.subcategory === subcategory).length : 0
  );
  const suggestedLevel = $derived.by<SanctionLevel>(() => {
    if (!subcategory || !sanctionRef) return "caution";
    const ladder = sanctionRef.escalationSequence;
    // A baseline outside the ladder (none today) would give indexOf -1: clamp to 0.
    const start = Math.max(0, ladder.indexOf(sanctionRef.baselinePenalties[subcategory]));
    const idx = Math.min(start + sameInfractionCount, ladder.length - 1);
    return ladder[idx]!;
  });
  // Blank-subcategory sanctions are invisible to escalation tracking — flag
  // same-category priors so the judge picks a subcategory instead.
  const sameCategoryPriorCount = $derived(
    activePrior.filter(s => s.category === category).length
  );

  // Warn if selected level is lower than the highest existing sanction
  const highestExisting = $derived.by(() => {
    let max: SanctionLevel | null = null;
    for (const s of activePrior) {
      if (!max || LEVEL_SEVERITY[s.level] > LEVEL_SEVERITY[max]) max = s.level;
    }
    return max;
  });
  const isDowngrade = $derived(
    highestExisting !== null && LEVEL_SEVERITY[level] < LEVEL_SEVERITY[highestExisting]
  );

  // Round options; len(rounds) is the finals sentinel, offered once finals exist
  const roundOptions = $derived.by(() => {
    const opts: { value: number; label: string }[] = [];
    const numRounds = tournament.rounds?.length ?? 0;
    for (let i = 0; i < numRounds; i++) {
      opts.push({ value: i, label: m.sanction_round_label({ round: String(i + 1) }) });
    }
    if (tournament.finals) {
      opts.push({ value: numRounds, label: m.finals_title() });
    }
    return opts;
  });

  // SA requires round_number
  const roundRequired = $derived(level === "standings_adjustment");

  // SA round is determined by tournament state, not chosen (JG v2 §1.1.3): the −1 VP
  // lands on the player's current game if one is in progress, else their most-recently
  // played game — i.e. the finals when the player is a seated finalist (sentinel
  // len(rounds)), else the highest round index in which they are seated. Frozen at
  // issue time onto the sanction; null when the player has not been seated yet.
  const saTargetRound = $derived.by(() => {
    const rounds = tournament.rounds ?? [];
    if (tournament.finals?.seating?.some(s => s.player_uid === playerUid)) {
      return rounds.length;
    }
    for (let i = rounds.length - 1; i >= 0; i--) {
      if (rounds[i]?.some(t => t.seating?.some(s => s.player_uid === playerUid))) return i;
    }
    return null;
  });
  const saTargetIsFinals = $derived(saTargetRound !== null && saTargetRound === (tournament.rounds?.length ?? 0));

  // Level label helper
  function levelLabel(lv: SanctionLevel): string {
    const labels: Record<SanctionLevel, () => string> = {
      caution: () => m.sanction_level_caution(),
      warning: () => m.sanction_level_warning(),
      standings_adjustment: () => m.sanction_level_sa(),
      disqualification: () => m.sanction_level_dq(),
      suspension: () => m.sanction_level_suspension(),
      probation: () => m.sanction_level_probation(),
    };
    return labels[lv]?.() ?? lv;
  }

  function subcategoryLabel(sub: SanctionSubcategory): string {
    const labels: Record<SanctionSubcategory, () => string> = {
      missed_mandatory_effect: () => m.sanction_sub_missed_mandatory_effect(),
      card_access_error: () => m.sanction_sub_card_access_error(),
      game_rule_violation: () => m.sanction_sub_game_rule_violation(),
      failure_to_maintain_game_state: () => m.sanction_sub_failure_to_maintain_game_state(),
      illegal_decklist: () => m.sanction_sub_illegal_decklist(),
      illegal_main_deck_legal_decklist: () => m.sanction_sub_illegal_main_deck_legal_decklist(),
      illegal_main_deck_no_decklist: () => m.sanction_sub_illegal_main_deck_no_decklist(),
      outside_assistance: () => m.sanction_sub_outside_assistance(),
      slow_play: () => m.sanction_sub_slow_play(),
      limited_procedure_violation: () => m.sanction_sub_limited_procedure_violation(),
      public_info_miscommunication: () => m.sanction_sub_public_info_miscommunication(),
      obscuring_game_state: () => m.sanction_sub_obscuring_game_state(),
      marked_cards: () => m.sanction_sub_marked_cards(),
      insufficient_shuffling: () => m.sanction_sub_insufficient_shuffling(),
      minor: () => m.sanction_sub_minor(),
      major: () => m.sanction_sub_major(),
      aggressive_behaviour: () => m.sanction_sub_aggressive_behaviour(),
      bribery_and_wagering: () => m.sanction_sub_bribery_and_wagering(),
      theft_of_tournament_material: () => m.sanction_sub_theft_of_tournament_material(),
      stalling: () => m.sanction_sub_stalling(),
      cheating: () => m.sanction_sub_cheating(),
      fraud: () => m.sanction_sub_fraud(),
      collusion: () => m.sanction_sub_collusion(),
      health_and_safety_disruption: () => m.sanction_sub_health_and_safety_disruption(),
      rage_quitting: () => m.sanction_sub_rage_quitting(),
      failure_to_play_to_win: () => m.sanction_sub_failure_to_play_to_win(),
    };
    return labels[sub]?.() ?? sub;
  }

  function focusOnMount(node: HTMLElement) {
    const input = node.querySelector<HTMLElement>("input:not(.hidden):not([type=hidden]), textarea, select");
    (input ?? node).focus();
  }

  async function handleSubmit() {
    if (!description.trim()) return;
    // SA round is auto-computed (saTargetRound); other levels use the informational picker.
    const targetRound = roundRequired ? saTargetRound : roundNumber;
    if (roundRequired && saTargetRound === null) return;
    creating = true;
    try {
      await issueTournamentSanction({
        user_uid: playerUid,
        level,
        category,
        subcategory: subcategory ?? undefined,
        round_number: targetRound,
        description: description.trim(),
        tournament_uid: tournament.uid,
      });
      showToast({ type: "success", message: m.sanction_mgr_issued_success() });
      onClose();
    } catch {
      // Error toast shown by apiRequest
    } finally {
      creating = false;
    }
  }
</script>

<div
  role="presentation"
  class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
  onclick={(e) => { e.stopPropagation(); if (e.target === e.currentTarget) onClose(); }}
>
  <div
    role="dialog"
    aria-modal="true"
    aria-labelledby="tournament-sanction-title"
    tabindex="-1"
    use:focusOnMount
    onkeydown={(e) => e.key === 'Escape' && onClose()}
    class="bg-surface-card rounded-lg shadow-xl border border-accent-soft-border/50 w-full max-w-md mx-4 max-h-[90vh] overflow-y-auto"
  >
    <div class="p-6 border-b border-line">
      <h2 id="tournament-sanction-title" class="text-xl font-medium text-link">
        {m.sanction_tournament_issue_title()}
      </h2>
      <p class="mt-2 text-sm text-ink-muted">
        {m.sanction_mgr_issue_to({ name: playerName })}
      </p>
    </div>

    <form
      onsubmit={(e) => { e.preventDefault(); handleSubmit(); }}
      class="p-6 space-y-4"
    >
      <!-- Escalation hint (per-infraction-type, v2 §1.2.1) -->
      {#if sameInfractionCount > 0}
        <div class="p-3 rounded banner-warn border text-sm">
          <div class="flex items-center gap-2">
            <TriangleAlert class="w-4 h-4 shrink-0" />
            {m.sanction_escalation_hint({ count: String(sameInfractionCount), suggested: levelLabel(suggestedLevel) })}
          </div>
          {#if activePrior.length > sameInfractionCount}
            <p class="mt-1 text-xs opacity-75">
              {m.sanction_other_infractions({ count: String(activePrior.length - sameInfractionCount) })}
            </p>
          {/if}
        </div>
      {:else if !subcategory && sameCategoryPriorCount > 0}
        <div class="p-3 rounded banner-warn border text-sm">
          <div class="flex items-center gap-2">
            <TriangleAlert class="w-4 h-4 shrink-0" />
            {m.sanction_escalation_needs_subcategory({ count: String(sameCategoryPriorCount) })}
          </div>
        </div>
      {/if}
      <!-- Downgrade warning -->
      {#if isDowngrade && highestExisting}
        <div class="p-3 rounded bg-accent-soft/30 border border-accent-soft-border/50 text-sm">
          <div class="flex items-center gap-2 text-link-soft">
            <CircleArrowDown class="w-4 h-4 shrink-0" />
            {m.sanction_downgrade_warning({ existing: levelLabel(highestExisting) })}
          </div>
        </div>
      {/if}

      <!-- Level -->
      <div>
        <label for="ts-level" class="block text-sm font-medium text-ink-muted mb-1">
          {m.common_level()} *
        </label>
        <select
          id="ts-level"
          bind:value={level}
          class="w-full px-3 py-2 border border-line-strong rounded bg-surface-card text-ink-bright focus:ring-2 focus:ring-accent focus:border-transparent"
        >
          <option value="caution">{m.sanction_level_caution()}</option>
          <option value="warning">{m.sanction_level_warning()}</option>
          <option value="standings_adjustment">{m.sanction_level_sa()}</option>
          <option value="disqualification">{m.sanction_level_dq()}</option>
        </select>
      </div>

      <!-- Category -->
      <div>
        <label for="ts-category" class="block text-sm font-medium text-ink-muted mb-1">
          {m.common_category()} *
        </label>
        <select
          id="ts-category"
          bind:value={category}
          class="w-full px-3 py-2 border border-line-strong rounded bg-surface-card text-ink-bright focus:ring-2 focus:ring-accent focus:border-transparent"
        >
          <option value="procedural_error">{m.sanction_cat_procedural_error()}</option>
          <option value="tournament_error">{m.sanction_cat_tournament_error()}</option>
          <option value="unsportsmanlike_conduct">{m.sanction_cat_unsportsmanlike_conduct()}</option>
        </select>
      </div>

      <!-- Subcategory -->
      <div>
        <label for="ts-subcategory" class="block text-sm font-medium text-ink-muted mb-1">
          {m.sanction_subcategory()}
        </label>
        <select
          id="ts-subcategory"
          bind:value={subcategory}
          class="w-full px-3 py-2 border border-line-strong rounded bg-surface-card text-ink-bright focus:ring-2 focus:ring-accent focus:border-transparent"
        >
          <option value={null}>—</option>
          {#each availableSubcategories as sub}
            <option value={sub}>{subcategoryLabel(sub)}</option>
          {/each}
        </select>
        {#if baselinePenalty}
          <p class="mt-1 text-xs text-ink-faint">
            {m.sanction_baseline_hint({ level: levelLabel(baselinePenalty) })}
          </p>
        {/if}
      </div>

      <!-- Round -->
      {#if roundRequired}
        <!-- SA target round is determined by state, not chosen (JG v2 §1.1.3). -->
        <div>
          <span class="block text-sm font-medium text-ink-muted mb-1">{m.sanction_round()}</span>
          {#if saTargetIsFinals}
            <p class="px-3 py-2 rounded bg-accent-soft/30 border border-accent-soft-border/50 text-sm text-ink-bright">
              {m.sanction_sa_applies_to_finals()}
            </p>
          {:else if saTargetRound !== null}
            <p class="px-3 py-2 rounded bg-accent-soft/30 border border-accent-soft-border/50 text-sm text-ink-bright">
              {m.sanction_sa_applies_to({ round: String(saTargetRound + 1) })}
            </p>
          {:else}
            <p class="px-3 py-2 rounded banner-warn border text-sm">
              {m.sanction_sa_no_round()}
            </p>
          {/if}
        </div>
      {:else if roundOptions.length > 0}
        <div>
          <label for="ts-round" class="block text-sm font-medium text-ink-muted mb-1">
            {m.sanction_round()}
          </label>
          <select
            id="ts-round"
            bind:value={roundNumber}
            class="w-full px-3 py-2 border border-line-strong rounded bg-surface-card text-ink-bright focus:ring-2 focus:ring-accent focus:border-transparent"
          >
            <option value={null}>—</option>
            {#each roundOptions as opt}
              <option value={opt.value}>{opt.label}</option>
            {/each}
          </select>
        </div>
      {/if}

      <!-- Description -->
      <div>
        <label for="ts-description" class="block text-sm font-medium text-ink-muted mb-1">
          {m.common_description()} *
        </label>
        <textarea
          id="ts-description"
          bind:value={description}
          rows="3"
          placeholder={m.sanction_mgr_description_placeholder()}
          required
          class="w-full px-3 py-2 border border-line-strong rounded bg-surface-card text-ink-bright focus:ring-2 focus:ring-accent focus:border-transparent resize-none"
        ></textarea>
      </div>

      <!-- Actions -->
      <div class="flex gap-2 pt-2">
        <Button
          type="submit"
          variant="primary"
          size="lg"
          class="flex-1"
          loading={creating}
          disabled={!description.trim() || (roundRequired && saTargetRound === null)}
        >
          {creating ? m.sanction_mgr_issuing() : m.sanction_mgr_issue_btn()}
        </Button>
        <Button variant="secondary" size="lg" disabled={creating} onclick={onClose}>
          {m.common_cancel()}
        </Button>
      </div>
    </form>
  </div>
</div>
