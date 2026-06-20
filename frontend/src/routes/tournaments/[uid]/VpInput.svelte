<script lang="ts">
  import { Loader2, Check } from "@lucide/svelte";
  import * as m from "$lib/paraglide/messages.js";

  let {
    value,
    options,
    label,
    disabled = false,
    saving = false,
    onchange,
  }: {
    value: number;
    options: number[];
    /** Seat/player name, woven into the group's accessible name so a screen
     *  reader knows whose VP this picker sets (rows are otherwise unlabelled). */
    label?: string;
    disabled?: boolean;
    saving?: boolean;
    onchange: (v: number) => void;
  } = $props();

  const groupLabel = $derived(label ? `${label} — ${m.vp_label()}` : m.vp_label());

  // Flash a brief "saved" check when an in-flight save for this seat completes.
  let justSaved = $state(false);
  // Intentionally a plain (non-reactive) local: it only carries the previous
  // `saving` across effect runs. Making it $state would re-trigger this effect.
  let prevSaving = false;
  let savedTimer: ReturnType<typeof setTimeout> | undefined;
  $effect(() => {
    if (prevSaving && !saving) {
      justSaved = true;
      clearTimeout(savedTimer);
      savedTimer = setTimeout(() => { justSaved = false; }, 1200);
    }
    prevSaving = saving;
    return () => clearTimeout(savedTimer);
  });
</script>

<div class="flex flex-wrap items-center gap-1" role="group" aria-label={groupLabel}>
  {#each options as opt (opt)}
    <button
      type="button"
      onclick={() => { if (opt !== value) onchange(opt); }}
      {disabled}
      aria-pressed={opt === value}
      class="h-11 min-w-11 px-2 rounded-lg border text-sm font-semibold tabular-nums transition-colors disabled:opacity-40
        {opt === value
          ? 'bg-accent-strong text-white border-accent-strong-hover ring-2 ring-accent'
          : 'bg-surface-hover text-ink-strong border-line-strong hover:border-line-strong'}"
    >{opt}</button>
  {/each}
  <span class="w-5 h-5 ml-0.5 flex items-center justify-center" aria-live="polite">
    {#if saving}
      <Loader2 class="w-4 h-4 text-ink-muted animate-spin" aria-hidden="true" />
      <span class="sr-only">{m.common_saving()}</span>
    {:else if justSaved}
      <Check class="w-4 h-4 text-blue-400" aria-hidden="true" />
      <span class="sr-only">{m.common_saved()}</span>
    {/if}
  </span>
</div>
