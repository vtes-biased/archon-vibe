<script lang="ts">
  import { toUserMessage } from '$lib/errors';
  import { goto } from "$app/navigation";
  import { createLeague } from "$lib/api";
  import { saveLeague, getAllLeagues } from "$lib/db";
  import { getAuthState } from "$lib/stores/auth.svelte";
  import { canManageLeagues } from "$lib/engine";
  import { getSortedCountries, getCountryFlag } from "$lib/geonames";
  import type { League, LeagueKind, LeagueStandingsMode } from "$lib/types";
  import Button from '$lib/components/Button.svelte';
  import { ArrowLeft } from "@lucide/svelte";
  import * as m from '$lib/paraglide/messages.js';

  const auth = $derived(getAuthState());
  const canCreate = $derived(canManageLeagues(auth.user).allowed);
  const countries = getSortedCountries();

  let name = $state("");
  let kind = $state<LeagueKind>("League");
  let standingsMode = $state<LeagueStandingsMode>("RTP");
  let format = $state<string>("");
  let country = $state("");
  let startDate = $state("");
  let finishDate = $state("");
  let description = $state("");
  let parentUid = $state("");
  let openToCountryPrinces = $state(false);

  let metaLeagues = $state<League[]>([]);

  $effect(() => {
    getAllLeagues().then(all => {
      metaLeagues = all.filter(l => l.kind === "Meta-League" && !l.deleted_at);
    });
  });

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
        // Inert without a country — never persist it on a worldwide league.
        open_to_country_princes: country ? openToCountryPrinces : false,
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
      <a href="/leagues" class="text-ink-muted hover:text-ink-strong">
        <ArrowLeft class="w-5 h-5" />
      </a>
      <h1 class="text-3xl font-semibold text-accent">{m.league_new_title()}</h1>
    </div>

    {#if !canCreate}
      <div class="bg-accent-soft/20 border border-accent-soft-border rounded-lg p-4">
        <p class="text-link-soft">{m.league_new_no_permission()}</p>
      </div>
    {:else}
      {#if error}
        <div class="bg-accent-soft/20 border border-accent-soft-border rounded-lg p-4 mb-6">
          <p class="text-link-soft">{error}</p>
        </div>
      {/if}

      <form onsubmit={(e) => { e.preventDefault(); handleSubmit(); }} class="space-y-6">
        <div class="bg-surface-card rounded-lg shadow p-6 border border-line space-y-4">
          <div>
            <label for="name" class="block text-sm text-ink-muted mb-1">{m.tfield_name_label()} <span class="text-link text-xs">({m.common_required()})</span></label>
            <input id="name" type="text" bind:value={name} required
              class="w-full px-3 py-2 text-sm border rounded-lg bg-surface-card text-ink-bright focus:outline-none {name.trim() ? 'border-line-strong focus:border-line-strong' : 'border-accent-strong/50 focus:border-accent'}" />
          </div>

          <div>
            <label for="kind" class="block text-sm text-ink-muted mb-1">{m.league_kind_label()}</label>
            <select id="kind" bind:value={kind}
              class="w-full px-3 py-2 text-sm border border-line-strong rounded-lg bg-surface-card text-ink-bright">
              <option value="League">{m.league_kind_league()}</option>
              <option value="Meta-League">{m.league_kind_meta()}</option>
            </select>
            {#if kind === "Meta-League"}
              <p class="text-xs text-ink-faint mt-1">{m.league_kind_meta_hint()}</p>
            {/if}
          </div>

          {#if kind === "League" && metaLeagues.length > 0}
            <div>
              <label for="parent" class="block text-sm text-ink-muted mb-1">{m.league_parent_label()}</label>
              <select id="parent" bind:value={parentUid}
                class="w-full px-3 py-2 text-sm border border-line-strong rounded-lg bg-surface-card text-ink-bright">
                <option value="">{m.common_none()}</option>
                {#each metaLeagues as ml (ml.uid)}
                  <option value={ml.uid}>{ml.name}</option>
                {/each}
              </select>
              <p class="text-xs text-ink-faint mt-1">{m.league_parent_hint()}</p>
            </div>
          {/if}

          <div>
            <label for="standings" class="block text-sm text-ink-muted mb-1">{m.league_standings_mode_label()}</label>
            <select id="standings" bind:value={standingsMode}
              class="w-full px-3 py-2 text-sm border border-line-strong rounded-lg bg-surface-card text-ink-bright">
              <option value="RTP">{m.league_standings_rtp_opt()}</option>
              <option value="Score">{m.league_standings_score_opt()}</option>
              <option value="GP">{m.league_standings_gp_opt()}</option>
            </select>
            <p class="mt-1 text-xs text-ink-faint">
              {standingsMode === "RTP" ? m.league_mode_hint_rtp() : standingsMode === "GP" ? m.league_mode_hint_gp() : m.league_mode_hint_score()}
            </p>
          </div>

          <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label for="format" class="block text-sm text-ink-muted mb-1">{m.tfield_format()}</label>
              <select id="format" bind:value={format}
                class="w-full px-3 py-2 text-sm border border-line-strong rounded-lg bg-surface-card text-ink-bright">
                <option value="">{m.tfield_format_any()}</option>
                <option value="Standard">Standard</option>
                <option value="V5">V5</option>
                <option value="Limited">Limited</option>
              </select>
            </div>

            <div>
              <label for="country" class="block text-sm text-ink-muted mb-1">{m.common_country()}</label>
              <select id="country" bind:value={country}
                class="w-full px-3 py-2 text-sm border border-line-strong rounded-lg bg-surface-card text-ink-bright">
                <option value="">{m.league_worldwide()}</option>
                {#each countries as c}
                  <option value={c.iso_code}>{c.name} {getCountryFlag(c.iso_code)}</option>
                {/each}
              </select>
            </div>
          </div>

          {#if kind === "League" && country}
            <div>
              <label class="flex items-start gap-2 text-sm text-ink-bright">
                <input type="checkbox" bind:checked={openToCountryPrinces}
                  class="w-5 h-5 mt-0.5 shrink-0 rounded border-line-strong bg-surface-card text-accent focus:ring-accent" />
                <span>
                  {m.league_open_princes_label()}
                  <span class="block text-xs text-ink-faint mt-0.5">{m.league_open_princes_hint()}</span>
                </span>
              </label>
              <p class="text-xs text-ink-faint mt-2">{m.league_new_princes_hint()}</p>
            </div>
          {/if}

          <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label for="start" class="block text-sm text-ink-muted mb-1">{m.tfield_start()} <span class="text-link text-xs">({m.common_required()})</span></label>
              <input id="start" type="date" bind:value={startDate} required
                class="w-full px-3 py-2 text-sm border rounded-lg bg-surface-card text-ink-bright focus:outline-none {startDate ? 'border-line-strong focus:border-line-strong' : 'border-accent-strong/50 focus:border-accent'}" />
            </div>

            <div>
              <label for="finish" class="block text-sm text-ink-muted mb-1">{m.tfield_finish()}</label>
              <input id="finish" type="date" bind:value={finishDate}
                class="w-full px-3 py-2 text-sm border border-line-strong rounded-lg bg-surface-card text-ink-bright" />
              <p class="text-xs text-ink-faint mt-1">{m.league_finish_hint()}</p>
            </div>
          </div>

          <div>
            <label for="desc" class="block text-sm text-ink-muted mb-1">{m.common_description()}</label>
            <span class="text-xs text-ink-faint mb-1 block">
              {@html m.tfield_markdown_support({ link: '<a href="https://www.markdownguide.org/basic-syntax/" target="_blank" rel="noopener noreferrer" class="underline text-ink-muted hover:text-ink-bright">Markdown</a>' })}
            </span>
            <textarea id="desc" bind:value={description} rows={10}
              class="w-full px-3 py-2 text-sm border border-line-strong rounded-lg bg-surface-card text-ink-bright resize-y"></textarea>
          </div>

        </div>

        <div class="flex justify-end gap-3">
          <a href="/leagues" class="px-4 py-2 text-sm font-medium text-ink-muted hover:text-ink-strong transition-colors">
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
