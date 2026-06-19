<script lang="ts">
  import { toUserMessage } from '$lib/errors';
  import { goto } from "$app/navigation";
  import { createLeague } from "$lib/api";
  import { saveLeague, getAllLeagues } from "$lib/db";
  import { hasAnyRole } from "$lib/stores/auth.svelte";
  import { getCountries, getCountryFlag } from "$lib/geonames";
  import type { League, LeagueKind, LeagueStandingsMode } from "$lib/types";
  import Button from '$lib/components/Button.svelte';
  import { ArrowLeft } from "@lucide/svelte";
  import * as m from '$lib/paraglide/messages.js';

  const canCreate = $derived(hasAnyRole("IC", "NC"));
  const countries = getCountries();

  let name = $state("");
  let kind = $state<LeagueKind>("League");
  let standingsMode = $state<LeagueStandingsMode>("RTP");
  let format = $state<string>("");
  let country = $state("");
  let startDate = $state("");
  let finishDate = $state("");
  let description = $state("");
  let parentUid = $state("");

  let metaLeagues = $state<League[]>([]);

  $effect(() => {
    getAllLeagues().then(all => {
      metaLeagues = all.filter(l => l.kind === "Meta-League" && !l.deleted_at);
    });
  });

  // Reset parent when switching to Meta-League
  $effect(() => {
    if (kind === "Meta-League") parentUid = "";
  });

  let isSubmitting = $state(false);
  let error = $state<string | null>(null);

  async function handleSubmit() {
    if (!name.trim()) {
      error = m.tournament_new_error_name_required();
      return;
    }
    if (!startDate) {
      error = m.tournament_new_error_start_required();
      return;
    }
    isSubmitting = true;
    error = null;
    try {
      const league = await createLeague({
        name: name.trim(),
        kind,
        standings_mode: standingsMode,
        format: format || null,
        country: country || null,
        start: startDate || null,
        finish: finishDate || null,
        description,
        parent_uid: parentUid || null,
      }, { suppressErrorToast: true });
      await saveLeague(league);
      goto(`/leagues/${league.uid}`);
    } catch (e) {
      error = toUserMessage(e, m.league_error_create());
    } finally {
      isSubmitting = false;
    }
  }
</script>

<svelte:head>
  <title>{m.league_new_title()} - Archon</title>
</svelte:head>

<div class="p-4 sm:p-8">
  <div class="max-w-2xl mx-auto">
    <div class="flex items-center gap-3 mb-6">
      <a href="/leagues" class="text-ash-400 hover:text-bone-100">
        <ArrowLeft class="w-5 h-5" />
      </a>
      <h1 class="text-3xl font-light text-crimson-500">{m.league_new_title()}</h1>
    </div>

    {#if !canCreate}
      <div class="bg-crimson-900/20 border border-crimson-800 rounded-lg p-4">
        <p class="text-crimson-300">{m.league_new_no_permission()}</p>
      </div>
    {:else}
      {#if error}
        <div class="bg-crimson-900/20 border border-crimson-800 rounded-lg p-4 mb-6">
          <p class="text-crimson-300">{error}</p>
        </div>
      {/if}

      <form onsubmit={(e) => { e.preventDefault(); handleSubmit(); }} class="space-y-6">
        <div class="bg-dusk-950 rounded-lg shadow p-6 border border-ash-800 space-y-4">
          <!-- Name -->
          <div>
            <label for="name" class="block text-sm text-ash-400 mb-1">{m.tfield_name_label()} <span class="text-crimson-400 text-xs">({m.common_required()})</span></label>
            <input id="name" type="text" bind:value={name} required
              class="w-full px-3 py-2 text-sm border rounded-lg bg-dusk-950 text-ash-200 focus:outline-none {name.trim() ? 'border-ash-700 focus:border-ash-500' : 'border-crimson-700/50 focus:border-crimson-500'}" />
          </div>

          <!-- Kind -->
          <div>
            <label for="kind" class="block text-sm text-ash-400 mb-1">{m.league_kind_label()}</label>
            <select id="kind" bind:value={kind}
              class="w-full px-3 py-2 text-sm border border-ash-700 rounded-lg bg-dusk-950 text-ash-200">
              <option value="League">{m.league_kind_league()}</option>
              <option value="Meta-League">{m.league_kind_meta()}</option>
            </select>
            {#if kind === "Meta-League"}
              <p class="text-xs text-ash-500 mt-1">{m.league_kind_meta_hint()}</p>
            {/if}
          </div>

          <!-- Parent league (only for regular leagues) -->
          {#if kind === "League" && metaLeagues.length > 0}
            <div>
              <label for="parent" class="block text-sm text-ash-400 mb-1">{m.league_parent_label()}</label>
              <select id="parent" bind:value={parentUid}
                class="w-full px-3 py-2 text-sm border border-ash-700 rounded-lg bg-dusk-950 text-ash-200">
                <option value="">{m.common_none()}</option>
                {#each metaLeagues as ml (ml.uid)}
                  <option value={ml.uid}>{ml.name}</option>
                {/each}
              </select>
              <p class="text-xs text-ash-500 mt-1">{m.league_parent_hint()}</p>
            </div>
          {/if}

          <!-- Standings mode -->
          <div>
            <label for="standings" class="block text-sm text-ash-400 mb-1">{m.league_standings_mode_label()}</label>
            <select id="standings" bind:value={standingsMode}
              class="w-full px-3 py-2 text-sm border border-ash-700 rounded-lg bg-dusk-950 text-ash-200">
              <option value="RTP">{m.league_standings_rtp_opt()}</option>
              <option value="Score">{m.league_standings_score_opt()}</option>
              <option value="GP">{m.league_standings_gp_opt()}</option>
            </select>
          </div>

          <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <!-- Format restriction -->
            <div>
              <label for="format" class="block text-sm text-ash-400 mb-1">{m.tfield_format()}</label>
              <select id="format" bind:value={format}
                class="w-full px-3 py-2 text-sm border border-ash-700 rounded-lg bg-dusk-950 text-ash-200">
                <option value="">{m.tfield_format_any()}</option>
                <option value="Standard">Standard</option>
                <option value="V5">V5</option>
                <option value="Limited">Limited</option>
              </select>
            </div>

            <!-- Country -->
            <div>
              <label for="country" class="block text-sm text-ash-400 mb-1">{m.common_country()}</label>
              <select id="country" bind:value={country}
                class="w-full px-3 py-2 text-sm border border-ash-700 rounded-lg bg-dusk-950 text-ash-200">
                <option value="">{m.league_worldwide()}</option>
                {#each Object.entries(countries) as [code, c]}
                  <option value={code}>{c.name} {getCountryFlag(code)}</option>
                {/each}
              </select>
            </div>
          </div>

          <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <!-- Start date -->
            <div>
              <label for="start" class="block text-sm text-ash-400 mb-1">{m.tfield_start()} <span class="text-crimson-400 text-xs">({m.common_required()})</span></label>
              <input id="start" type="date" bind:value={startDate} required
                class="w-full px-3 py-2 text-sm border rounded-lg bg-dusk-950 text-ash-200 focus:outline-none {startDate ? 'border-ash-700 focus:border-ash-500' : 'border-crimson-700/50 focus:border-crimson-500'}" />
            </div>

            <!-- End date -->
            <div>
              <label for="finish" class="block text-sm text-ash-400 mb-1">{m.tfield_finish()}</label>
              <input id="finish" type="date" bind:value={finishDate}
                class="w-full px-3 py-2 text-sm border border-ash-700 rounded-lg bg-dusk-950 text-ash-200" />
              <p class="text-xs text-ash-500 mt-1">{m.league_finish_hint()}</p>
            </div>
          </div>

          <!-- Description -->
          <div>
            <label for="desc" class="block text-sm text-ash-400 mb-1">{m.common_description()}</label>
            <span class="text-xs text-ash-500 mb-1 block">
              {@html m.tfield_markdown_support({ link: '<a href="https://www.markdownguide.org/basic-syntax/" target="_blank" rel="noopener noreferrer" class="underline text-ash-400 hover:text-ash-200">Markdown</a>' })}
            </span>
            <textarea id="desc" bind:value={description} rows={10}
              class="w-full px-3 py-2 text-sm border border-ash-700 rounded-lg bg-dusk-950 text-ash-200 resize-y"></textarea>
          </div>

        </div>

        <div class="flex justify-end gap-3">
          <a href="/leagues" class="px-4 py-2 text-sm font-medium text-ash-400 hover:text-bone-100 transition-colors">
            {m.common_cancel()}
          </a>
          <Button
            type="submit"
            variant="primary"
            size="lg"
            class="shadow-md"
            loading={isSubmitting}
            disabled={!name.trim() || !startDate}
          >
            {isSubmitting ? m.league_new_creating() : m.league_new_create_btn()}
          </Button>
        </div>
      </form>
    {/if}
  </div>
</div>
