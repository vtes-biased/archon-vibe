<script lang="ts">
  import type { Tournament, SanctionLevel, SanctionCategory, SanctionSubcategory, Sanction } from "$lib/types";
  import { SUBCATEGORIES_BY_CATEGORY, BASELINE_PENALTIES, ESCALATION_SEQUENCE } from "$lib/types";
  import { createSanction } from "$lib/api";
  import { getPlayerSanctionsInTournament } from "$lib/db";
  import { showToast } from "$lib/stores/toast.svelte";
  import { TriangleAlert, CircleArrowDown } from "lucide-svelte";
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

  // Available subcategories for selected category
  const availableSubcategories = $derived(
    SUBCATEGORIES_BY_CATEGORY[category] ?? []
  );

  // Reset subcategory when category changes
  $effect(() => {
    const subs = SUBCATEGORIES_BY_CATEGORY[category];
    if (subs && subcategory && !subs.includes(subcategory)) {
      subcategory = null;
    }
  });

  // Baseline penalty hint
  const baselinePenalty = $derived(
    subcategory ? BASELINE_PENALTIES[subcategory] : null
  );

  // Severity ordering for level comparison
  const LEVEL_SEVERITY: Record<SanctionLevel, number> = {
    caution: 0, warning: 1, standings_adjustment: 2,
    disqualification: 3, suspension: 4, probation: 4,
  };

  // Escalation hint: count prior sanctions and suggest next level
  const activePrior = $derived(
    priorSanctions.filter(s => !s.lifted_at && !s.deleted_at)
  );
  const activePriorCount = $derived(activePrior.length);
  const suggestedLevel = $derived<SanctionLevel>(
    activePriorCount < ESCALATION_SEQUENCE.length
      ? ESCALATION_SEQUENCE[activePriorCount]!
      : "disqualification"
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

  // Round options
  const roundOptions = $derived.by(() => {
    const opts: { value: number; label: string }[] = [];
    const numRounds = tournament.rounds?.length ?? 0;
    for (let i = 0; i < numRounds; i++) {
      opts.push({ value: i, label: m.sanction_round_label({ round: String(i + 1) }) });
    }
    return opts;
  });

  // SA requires round_number
  const roundRequired = $derived(level === "standings_adjustment");

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
    if (roundRequired && roundNumber === null) return;
    creating = true;
    try {
      await createSanction({
        user_uid: playerUid,
        level,
        category,
        subcategory: subcategory ?? undefined,
        round_number: roundNumber,
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
    class="bg-dusk-950 rounded-lg shadow-xl border border-crimson-800/50 w-full max-w-md mx-4 max-h-[90vh] overflow-y-auto"
  >
    <div class="p-6 border-b border-ash-800">
      <h2 id="tournament-sanction-title" class="text-xl font-medium text-crimson-400">
        {m.sanction_tournament_issue_title()}
      </h2>
      <p class="mt-2 text-sm text-ash-400">
        {m.sanction_mgr_issue_to({ name: playerName })}
      </p>
    </div>

    <form
      onsubmit={(e) => { e.preventDefault(); handleSubmit(); }}
      class="p-6 space-y-4"
    >
      <!-- Escalation hint -->
      {#if activePriorCount > 0}
        <div class="p-3 rounded banner-amber border text-sm">
          <div class="flex items-center gap-2">
            <TriangleAlert class="w-4 h-4 shrink-0" />
            {m.sanction_escalation_hint({ count: String(activePriorCount), suggested: levelLabel(suggestedLevel) })}
          </div>
        </div>
      {/if}
      <!-- Downgrade warning -->
      {#if isDowngrade && highestExisting}
        <div class="p-3 rounded bg-crimson-900/30 border border-crimson-800/50 text-sm">
          <div class="flex items-center gap-2 text-crimson-300">
            <CircleArrowDown class="w-4 h-4 shrink-0" />
            {m.sanction_downgrade_warning({ existing: levelLabel(highestExisting) })}
          </div>
        </div>
      {/if}

      <!-- Level -->
      <div>
        <label for="ts-level" class="block text-sm font-medium text-ash-400 mb-1">
          {m.common_level()} *
        </label>
        <select
          id="ts-level"
          bind:value={level}
          class="w-full px-3 py-2 border border-ash-600 rounded bg-dusk-950 text-ash-200 focus:ring-2 focus:ring-crimson-500 focus:border-transparent"
        >
          <option value="caution">{m.sanction_level_caution()}</option>
          <option value="warning">{m.sanction_level_warning()}</option>
          <option value="standings_adjustment">{m.sanction_level_sa()}</option>
          <option value="disqualification">{m.sanction_level_dq()}</option>
        </select>
      </div>

      <!-- Category -->
      <div>
        <label for="ts-category" class="block text-sm font-medium text-ash-400 mb-1">
          {m.common_category()} *
        </label>
        <select
          id="ts-category"
          bind:value={category}
          class="w-full px-3 py-2 border border-ash-600 rounded bg-dusk-950 text-ash-200 focus:ring-2 focus:ring-crimson-500 focus:border-transparent"
        >
          <option value="procedural_error">{m.sanction_cat_procedural_error()}</option>
          <option value="tournament_error">{m.sanction_cat_tournament_error()}</option>
          <option value="unsportsmanlike_conduct">{m.sanction_cat_unsportsmanlike_conduct()}</option>
        </select>
      </div>

      <!-- Subcategory -->
      <div>
        <label for="ts-subcategory" class="block text-sm font-medium text-ash-400 mb-1">
          {m.sanction_subcategory()}
        </label>
        <select
          id="ts-subcategory"
          bind:value={subcategory}
          class="w-full px-3 py-2 border border-ash-600 rounded bg-dusk-950 text-ash-200 focus:ring-2 focus:ring-crimson-500 focus:border-transparent"
        >
          <option value={null}>—</option>
          {#each availableSubcategories as sub}
            <option value={sub}>{subcategoryLabel(sub)}</option>
          {/each}
        </select>
        {#if baselinePenalty}
          <p class="mt-1 text-xs text-ash-500">
            {m.sanction_baseline_hint({ level: levelLabel(baselinePenalty) })}
          </p>
        {/if}
      </div>

      <!-- Round -->
      {#if roundOptions.length > 0}
        <div>
          <label for="ts-round" class="block text-sm font-medium text-ash-400 mb-1">
            {m.sanction_round()} {roundRequired ? "*" : ""}
          </label>
          <select
            id="ts-round"
            bind:value={roundNumber}
            required={roundRequired}
            class="w-full px-3 py-2 border border-ash-600 rounded bg-dusk-950 text-ash-200 focus:ring-2 focus:ring-crimson-500 focus:border-transparent"
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
        <label for="ts-description" class="block text-sm font-medium text-ash-400 mb-1">
          {m.common_description()} *
        </label>
        <textarea
          id="ts-description"
          bind:value={description}
          rows="3"
          placeholder={m.sanction_mgr_description_placeholder()}
          required
          class="w-full px-3 py-2 border border-ash-600 rounded bg-dusk-950 text-ash-200 focus:ring-2 focus:ring-crimson-500 focus:border-transparent resize-none"
        ></textarea>
      </div>

      <!-- Actions -->
      <div class="flex gap-2 pt-2">
        <button
          type="submit"
          disabled={creating || !description.trim() || (roundRequired && roundNumber === null)}
          class="flex-1 px-4 py-2 bg-crimson-700 hover:bg-crimson-600 disabled:bg-ash-800 disabled:text-ash-500 text-white rounded font-medium transition-colors"
        >
          {creating ? m.sanction_mgr_issuing() : m.sanction_mgr_issue_btn()}
        </button>
        <button
          type="button"
          onclick={onClose}
          disabled={creating}
          class="px-4 py-2 bg-ash-700 hover:bg-ash-600 text-ash-200 rounded font-medium transition-colors"
        >
          {m.common_cancel()}
        </button>
      </div>
    </form>
  </div>
</div>
