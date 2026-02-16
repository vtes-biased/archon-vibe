<script lang="ts">
  import { goto } from "$app/navigation";
  import { createLeague } from "$lib/api";
  import { saveLeague } from "$lib/db";
  import { hasAnyRole } from "$lib/stores/auth.svelte";
  import { getCountries, getCountryFlag } from "$lib/geonames";
  import type { LeagueKind, LeagueStandingsMode } from "$lib/types";
  import { ArrowLeft } from "lucide-svelte";

  const canCreate = $derived(hasAnyRole("IC", "NC"));
  const countries = getCountries();

  let name = $state("");
  let kind = $state<LeagueKind>("League");
  let standingsMode = $state<LeagueStandingsMode>("RTP");
  let format = $state<string>("");
  let online = $state(false);
  let country = $state("");
  let startDate = $state("");
  let finishDate = $state("");
  let timezone = $state(Intl.DateTimeFormat().resolvedOptions().timeZone);
  let description = $state("");
  let allowNoFinals = $state(false);

  let isSubmitting = $state(false);
  let error = $state<string | null>(null);

  async function handleSubmit() {
    if (!name.trim()) {
      error = "Name is required";
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
        online,
        country: country || null,
        start: startDate || null,
        finish: finishDate || null,
        timezone,
        description,
        allow_no_finals: allowNoFinals,
      });
      await saveLeague(league);
      goto(`/leagues/${league.uid}`);
    } catch (e) {
      error = e instanceof Error ? e.message : "Failed to create league";
    } finally {
      isSubmitting = false;
    }
  }
</script>

<svelte:head>
  <title>New League - Archon</title>
</svelte:head>

<div class="p-4 sm:p-8">
  <div class="max-w-2xl mx-auto">
    <div class="flex items-center gap-3 mb-6">
      <a href="/leagues" class="text-ash-400 hover:text-bone-100">
        <ArrowLeft class="w-5 h-5" />
      </a>
      <h1 class="text-3xl font-light text-crimson-500">New League</h1>
    </div>

    {#if !canCreate}
      <div class="bg-crimson-900/20 border border-crimson-800 rounded-lg p-4">
        <p class="text-crimson-300">Only NCs and ICs can create leagues.</p>
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
            <label for="name" class="block text-sm font-medium text-ash-400 mb-1">Name *</label>
            <input id="name" type="text" bind:value={name} required
              class="w-full px-3 py-2 border border-ash-600 rounded-lg bg-dusk-950 text-ash-200" />
          </div>

          <!-- Kind -->
          <div>
            <label for="kind" class="block text-sm font-medium text-ash-400 mb-1">Kind</label>
            <select id="kind" bind:value={kind}
              class="w-full px-3 py-2 border border-ash-600 rounded-lg bg-dusk-950 text-ash-200">
              <option value="League">League</option>
              <option value="Meta-League">Meta-League</option>
            </select>
            {#if kind === "Meta-League"}
              <p class="text-xs text-ash-500 mt-1">A meta-league groups child leagues. Add children after creation.</p>
            {/if}
          </div>

          <!-- Standings mode -->
          <div>
            <label for="standings" class="block text-sm font-medium text-ash-400 mb-1">Standings Mode</label>
            <select id="standings" bind:value={standingsMode}
              class="w-full px-3 py-2 border border-ash-600 rounded-lg bg-dusk-950 text-ash-200">
              <option value="RTP">Rating Points (RTP)</option>
              <option value="Score">GW/VP/TP (prelims only)</option>
              <option value="GP">Grand Prix (position-based)</option>
            </select>
          </div>

          <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <!-- Format restriction -->
            <div>
              <label for="format" class="block text-sm font-medium text-ash-400 mb-1">Format</label>
              <select id="format" bind:value={format}
                class="w-full px-3 py-2 border border-ash-600 rounded-lg bg-dusk-950 text-ash-200">
                <option value="">Any format</option>
                <option value="Standard">Standard</option>
                <option value="V5">V5</option>
                <option value="Limited">Limited</option>
              </select>
            </div>

            <!-- Country -->
            <div>
              <label for="country" class="block text-sm font-medium text-ash-400 mb-1">Country</label>
              <select id="country" bind:value={country}
                class="w-full px-3 py-2 border border-ash-600 rounded-lg bg-dusk-950 text-ash-200">
                <option value="">Worldwide</option>
                {#each Object.entries(countries) as [code, c]}
                  <option value={code}>{c.name} {getCountryFlag(code)}</option>
                {/each}
              </select>
            </div>
          </div>

          <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <!-- Start date -->
            <div>
              <label for="start" class="block text-sm font-medium text-ash-400 mb-1">Start Date</label>
              <input id="start" type="date" bind:value={startDate}
                class="w-full px-3 py-2 border border-ash-600 rounded-lg bg-dusk-950 text-ash-200" />
            </div>

            <!-- End date -->
            <div>
              <label for="finish" class="block text-sm font-medium text-ash-400 mb-1">End Date</label>
              <input id="finish" type="date" bind:value={finishDate}
                class="w-full px-3 py-2 border border-ash-600 rounded-lg bg-dusk-950 text-ash-200" />
              <p class="text-xs text-ash-500 mt-1">Leave empty for ongoing league</p>
            </div>
          </div>

          <!-- Description -->
          <div>
            <label for="desc" class="block text-sm font-medium text-ash-400 mb-1">Description</label>
            <textarea id="desc" bind:value={description} rows={3}
              class="w-full px-3 py-2 border border-ash-600 rounded-lg bg-dusk-950 text-ash-200 resize-y"></textarea>
          </div>

          <!-- Options -->
          <div class="flex flex-wrap gap-6">
            <label class="flex items-center gap-2 text-sm text-ash-400 cursor-pointer">
              <input type="checkbox" bind:checked={online}
                class="rounded border-ash-600 bg-dusk-950 text-crimson-500" />
              Online
            </label>
            <label class="flex items-center gap-2 text-sm text-ash-400 cursor-pointer">
              <input type="checkbox" bind:checked={allowNoFinals}
                class="rounded border-ash-600 bg-dusk-950 text-crimson-500" />
              Allow tournaments without finals
            </label>
          </div>
        </div>

        <div class="flex justify-end gap-3">
          <a href="/leagues" class="px-4 py-2 text-sm font-medium text-ash-400 hover:text-bone-100 transition-colors">
            Cancel
          </a>
          <button
            type="submit"
            disabled={isSubmitting}
            class="px-6 py-2 text-sm font-medium text-white bg-emerald-700 hover:bg-emerald-600 rounded-lg transition-colors shadow-md disabled:opacity-50"
          >
            {isSubmitting ? "Creating..." : "Create League"}
          </button>
        </div>
      </form>
    {/if}
  </div>
</div>
