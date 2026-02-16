<script lang="ts">
  import { goto } from "$app/navigation";
  import { createTournament } from "$lib/api";
  import { saveTournament } from "$lib/db";
  import TournamentFields, { type TournamentFieldValues } from "$lib/components/TournamentFields.svelte";
  import { hasAnyRole } from "$lib/stores/auth.svelte";
  import { ArrowLeft } from "lucide-svelte";
  import * as m from '$lib/paraglide/messages.js';

  const canCreate = $derived(hasAnyRole("IC", "NC", "Prince"));

  let values = $state<TournamentFieldValues>({
    name: "",
    format: "Standard",
    rank: "",
    open_rounds: false,
    max_rounds: 0,
    online: false,
    country: "",
    venue: "",
    venue_url: "",
    address: "",
    map_url: "",
    start: "",
    finish: "",
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    description: "",
    standings_mode: "Private",
    decklists_mode: "Winner",
    proxies: false,
    multideck: false,
    decklist_required: false,
    league_uid: "",
  });

  let isSubmitting = $state(false);
  let error = $state<string | null>(null);

  async function handleSubmit() {
    if (!values.name.trim()) {
      error = m.tournament_new_error_name_required();
      return;
    }

    isSubmitting = true;
    error = null;

    try {
      const tournament = await createTournament({
        name: values.name.trim(),
        format: values.format,
        rank: values.rank,
        online: values.online,
        start: values.start || null,
        finish: values.finish || null,
        country: values.country || null,
        venue: values.venue,
        venue_url: values.venue_url,
        address: values.address,
        map_url: values.map_url,
        timezone: values.timezone,
        description: values.description,
        max_rounds: values.max_rounds,
        standings_mode: values.standings_mode,
        decklists_mode: values.decklists_mode,
        proxies: values.proxies,
        multideck: values.multideck,
        decklist_required: values.decklist_required,
        league_uid: values.league_uid || null,
      });
      await saveTournament(tournament);
      goto(`/tournaments/${tournament.uid}`);
    } catch (e) {
      error = e instanceof Error ? e.message : "Failed to create tournament";
    } finally {
      isSubmitting = false;
    }
  }
</script>

<svelte:head>
  <title>{m.tournament_new_page_title()} - Archon</title>
</svelte:head>

<div class="p-4 sm:p-8">
  <div class="max-w-2xl mx-auto">
    <div class="flex items-center gap-4 mb-6">
      <a href="/tournaments" class="text-ash-400 hover:text-ash-200">
        <ArrowLeft class="w-5 h-5" />
      </a>
      <h1 class="text-3xl font-light text-crimson-500">{m.tournament_new_title()}</h1>
    </div>

    {#if !canCreate}
      <div class="bg-crimson-900/20 border border-crimson-800 rounded-lg p-4">
        <p class="text-crimson-300">{m.tournament_new_no_permission()}</p>
      </div>
    {:else}
      <form onsubmit={(e) => { e.preventDefault(); handleSubmit(); }} class="space-y-6">
        <div class="bg-dusk-950 rounded-lg shadow p-6 border border-ash-800 space-y-4">
          {#if error}
            <div class="bg-crimson-900/20 border border-crimson-800 rounded-lg p-3">
              <p class="text-crimson-300 text-sm">{error}</p>
            </div>
          {/if}

          <TournamentFields bind:values disabled={isSubmitting} />
        </div>

        <!-- Actions -->
        <div class="flex gap-3 justify-end">
          <a href="/tournaments" class="px-4 py-2 text-sm font-medium text-ash-300 bg-ash-800 hover:bg-ash-700 rounded-lg transition-colors">
            {m.common_cancel()}
          </a>
          <button
            type="submit"
            disabled={isSubmitting || !values.name.trim()}
            class="px-4 py-2 text-sm font-medium text-white bg-emerald-700 hover:bg-emerald-600 disabled:bg-ash-700 rounded-lg transition-colors shadow-md disabled:cursor-not-allowed"
          >
            {isSubmitting ? m.tournament_new_creating() : m.tournament_new_create_btn()}
          </button>
        </div>
      </form>
    {/if}
  </div>
</div>
