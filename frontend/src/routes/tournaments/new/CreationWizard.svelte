<script lang="ts">
  import { ArrowLeft } from "@lucide/svelte";
  import type { TournamentFieldValues } from "$lib/components/TournamentFields.svelte";
  import { OFFICIAL_DISCORD_INVITE, OFFICIAL_DISCORD_VENUE } from "$lib/tournament-utils";
  import Button from "$lib/components/Button.svelte";
  import * as m from '$lib/paraglide/messages.js';

  export interface WizardAnswers {
    setting: "" | "irl" | "online";
    kind: "" | "local" | "big" | "series" | "sync" | "parallel";
    home: "" | "official" | "own" | "elsewhere";
    doors: "" | "free" | "gate" | "advance";
    offlineVenue: boolean;
  }

  let {
    answers = $bindable(),
    values = $bindable(),
    oncomplete,
    onskip,
  }: {
    answers: WizardAnswers;
    values: TournamentFieldValues;
    oncomplete: () => void;
    onskip: () => void;
  } = $props();

  let index = $state(0);

  const steps = $derived<string[]>(["setting", "kind", answers.setting === "online" ? "home" : "doors", "rules"]);
  const step = $derived(steps[index]);

  function next() {
    if (index === steps.length - 1) oncomplete();
    else index += 1;
  }

  function chooseSetting(v: "irl" | "online") {
    answers = { setting: v, kind: "", home: "", doors: "", offlineVenue: false };
    values.online = v === "online";
    if (v === "online") {
      values.proxies = false;
      values.country = "";
    } else {
      values.venue = "";
      values.venue_url = "";
    }
    next();
  }

  function chooseKind(v: WizardAnswers["kind"]) {
    answers.kind = v;
    const open = v === "series";
    const untimed = open || v === "parallel";
    values.open_rounds = open;
    values.self_organized_rounds = false;
    values.max_rounds = open ? 0 : 3;
    values.round_time = untimed ? 0 : 7200;
    next();
  }

  function chooseHome(v: WizardAnswers["home"]) {
    answers.home = v;
    values.venue = v === "official" ? OFFICIAL_DISCORD_VENUE : "";
    values.venue_url = v === "official" ? OFFICIAL_DISCORD_INVITE : "";
    next();
  }

  const settingChoices = $derived([
    { value: "irl", label: m.tournament_wiz_setting_irl(), desc: m.tournament_wiz_setting_irl_desc() },
    { value: "online", label: m.tournament_wiz_setting_online(), desc: m.tournament_wiz_setting_online_desc() },
  ]);

  const kindChoices = $derived(
    answers.setting === "online"
      ? [
          { value: "sync", label: m.tournament_wiz_kind_sync(), desc: m.tournament_wiz_kind_sync_desc() },
          { value: "parallel", label: m.tournament_wiz_kind_parallel(), desc: m.tournament_wiz_kind_parallel_desc() },
          { value: "series", label: m.tournament_wiz_kind_series(), desc: m.tournament_wiz_kind_series_desc() },
        ]
      : [
          { value: "local", label: m.tournament_wiz_kind_local(), desc: m.tournament_wiz_kind_local_desc() },
          { value: "big", label: m.tournament_wiz_kind_big(), desc: m.tournament_wiz_kind_big_desc() },
          { value: "series", label: m.tournament_wiz_kind_series(), desc: m.tournament_wiz_kind_series_desc() },
        ]
  );

  const homeChoices = $derived([
    { value: "official", label: m.tournament_wiz_home_official(), desc: m.tournament_wiz_home_official_desc() },
    { value: "own", label: m.tournament_wiz_home_own(), desc: m.tournament_wiz_home_own_desc() },
    { value: "elsewhere", label: m.tournament_wiz_home_elsewhere(), desc: m.tournament_wiz_home_elsewhere_desc() },
  ]);

  const feeChoices = $derived([
    { value: "free", label: m.tournament_wiz_doors_free() },
    { value: "gate", label: m.tournament_wiz_doors_gate() },
    { value: "advance", label: m.tournament_wiz_doors_advance() },
  ]);
</script>

{#snippet card(label: string, desc: string, selected: boolean, onclick: () => void)}
  <button
    type="button"
    {onclick}
    class="w-full text-left p-4 rounded-lg border transition-colors {selected
      ? 'border-accent bg-accent-soft/20'
      : 'border-line bg-surface-card hover:bg-surface-hover'}"
  >
    <span class="block text-base font-medium text-ink-strong">{label}</span>
    <span class="block text-sm text-ink-muted mt-0.5">{desc}</span>
  </button>
{/snippet}

{#snippet check(label: string, desc: string | null, checked: boolean, onchange: (v: boolean) => void)}
  <div>
    <label class="flex items-center gap-3 cursor-pointer min-h-[44px]">
      <input
        type="checkbox"
        {checked}
        onchange={(e) => onchange((e.target as HTMLInputElement).checked)}
        class="w-5 h-5 rounded border-line-strong bg-surface-card text-accent focus:ring-accent"
      />
      <span class="text-sm text-ink-bright">{label}</span>
    </label>
    {#if desc}
      <p class="text-xs text-ink-faint ml-8 -mt-1">{desc}</p>
    {/if}
  </div>
{/snippet}

<div class="bg-surface-card rounded-lg shadow p-6 border border-line space-y-6">
  <div class="flex items-center gap-3">
    <div class="flex-1 flex gap-1" aria-hidden="true">
      {#each steps as _, i}
        <span class="h-1 flex-1 rounded-full {i <= index ? 'bg-accent' : 'bg-surface-muted'}"></span>
      {/each}
    </div>
    <span class="text-xs text-ink-faint whitespace-nowrap">
      {m.tournament_wiz_step({ current: index + 1, total: steps.length })}
    </span>
  </div>

  {#if step === "setting"}
    <div class="space-y-4">
      <h2 class="text-xl font-medium text-ink-strong">{m.tournament_wiz_setting_q()}</h2>
      <p class="text-sm text-ink-muted">{m.tournament_wiz_lead()}</p>
      <div class="space-y-3">
        {#each settingChoices as c}
          {@render card(c.label, c.desc, answers.setting === c.value, () => chooseSetting(c.value as "irl" | "online"))}
        {/each}
      </div>
    </div>
  {:else if step === "kind"}
    <div class="space-y-4">
      <h2 class="text-xl font-medium text-ink-strong">{m.tournament_wiz_kind_q()}</h2>
      <div class="space-y-3">
        {#each kindChoices as c}
          {@render card(c.label, c.desc, answers.kind === c.value, () => chooseKind(c.value as WizardAnswers["kind"]))}
        {/each}
      </div>
    </div>
  {:else if step === "home"}
    <div class="space-y-4">
      <h2 class="text-xl font-medium text-ink-strong">{m.tournament_wiz_home_q()}</h2>
      <div class="space-y-3">
        {#each homeChoices as c}
          {@render card(c.label, c.desc, answers.home === c.value, () => chooseHome(c.value as WizardAnswers["home"]))}
        {/each}
      </div>
    </div>
  {:else if step === "doors"}
    <div class="space-y-4">
      <h2 class="text-xl font-medium text-ink-strong">{m.tournament_wiz_doors_q()}</h2>
      <fieldset class="border-0 p-0 m-0 space-y-2">
        <legend class="text-sm text-ink-muted mb-2">{m.tournament_wiz_doors_fee()}</legend>
        {#each feeChoices as c}
          <label class="flex items-center gap-3 cursor-pointer min-h-[44px]">
            <input
              type="radio"
              name="entry-fee"
              value={c.value}
              checked={answers.doors === c.value}
              onchange={() => (answers.doors = c.value as WizardAnswers["doors"])}
              class="w-5 h-5 border-line-strong bg-surface-card text-accent focus:ring-accent"
            />
            <span class="text-sm text-ink-bright">{c.label}</span>
          </label>
        {/each}
      </fieldset>
      <div class="pt-4 border-t border-line">
        {@render check(m.tournament_wiz_doors_offline(), null, answers.offlineVenue, (v) => (answers.offlineVenue = v))}
      </div>
    </div>
  {:else}
    <div class="space-y-4">
      <h2 class="text-xl font-medium text-ink-strong">{m.tournament_wiz_rules_q()}</h2>
      <p class="text-sm text-ink-muted">{m.tournament_wiz_rules_desc()}</p>
      <div class="space-y-3">
        {@render check(m.tfield_multideck(), null, values.multideck, (v) => (values.multideck = v))}
        {@render check(m.tfield_decklist_required(), null, values.decklist_required, (v) => (values.decklist_required = v))}
        {#if answers.setting === "irl"}
          {@render check(m.tfield_allow_proxies(), null, values.proxies, (v) => (values.proxies = v))}
        {/if}
        {#if values.open_rounds}
          {@render check(
            m.tfield_self_organized_rounds(),
            m.tfield_self_organized_rounds_desc(),
            values.self_organized_rounds,
            (v) => (values.self_organized_rounds = v)
          )}
        {/if}
      </div>
    </div>
  {/if}

  <div class="flex items-center justify-between gap-3 pt-2">
    {#if index > 0}
      <Button variant="ghost" onclick={() => (index -= 1)}>
        <ArrowLeft class="w-4 h-4" aria-hidden="true" />{m.tournament_wiz_back()}
      </Button>
    {:else}
      <span></span>
    {/if}
    {#if step === "doors" || step === "rules"}
      <Button variant="primary" onclick={next} disabled={step === "doors" && !answers.doors}>{m.common_next()}</Button>
    {/if}
  </div>
</div>

<p class="text-center mt-4">
  <button type="button" onclick={onskip} class="text-sm text-ink-muted hover:text-ink-bright underline">
    {m.tournament_wiz_skip()}
  </button>
</p>
