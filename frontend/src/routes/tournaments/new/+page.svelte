<script lang="ts">
  import { toUserMessage } from '$lib/errors';
  import { goto } from "$app/navigation";
  import { createTournament, createTournamentOffline, isOnline } from "$lib/api";
  import { saveTournament } from "$lib/db";
  import TournamentFields, { type TournamentFieldValues } from "$lib/components/TournamentFields.svelte";
  import { getAuthState } from "$lib/stores/auth.svelte";
  import { canCreateTournament } from "$lib/engine";
  import Button from '$lib/components/Button.svelte';
  import { ArrowLeft, WifiOff } from "@lucide/svelte";
  import * as m from '$lib/paraglide/messages.js';

  const auth = $derived(getAuthState());
  const canCreate = $derived(canCreateTournament(auth.user).allowed);

  const veknPush = import.meta.env.VITE_VEKN_PUSH === "true";

  let values = $state<TournamentFieldValues>({
    name: "",
    format: "Standard",
    rank: "",
    open_rounds: false,
    max_rounds: veknPush ? 3 : 0,
    max_players: 0,
    self_organized_rounds: false,
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
    round_time: 7200,
    finals_time: 0,
  });

  let isSubmitting = $state(false);
  let error = $state<string | null>(null);

  // Required-path fields still empty — names the reason the create button is
  // disabled instead of leaving it silently grey.
  const missingFields = $derived([
    ...(!values.name.trim() ? [m.tfield_name_label()] : []),
    ...(!values.start ? [m.tfield_start()] : []),
    ...(!values.online && !values.country ? [m.common_country()] : []),
  ]);

  // Offline creation routes to the local WASM engine and the tournament is born
  // locked to this device (pushed at go-online); actual connectivity decides,
  // no manual offline toggle.
  let offline = $state(!isOnline());
  $effect(() => {
    const on = () => (offline = false);
    const off = () => (offline = true);
    window.addEventListener('online', on);
    window.addEventListener('offline', off);
    return () => {
      window.removeEventListener('online', on);
      window.removeEventListener('offline', off);
    };
  });

  async function handleSubmit() {
    if (!values.name.trim()) {
      error = m.tournament_new_error_name_required();
      return;
    }
    if (!values.start) {
      error = m.tournament_new_error_start_required();
      return;
    }
    if (!values.online && !values.country) {
      error = m.tournament_new_error_country_required();
      return;
    }
    if (veknPush && !values.open_rounds && (values.max_rounds < 2 || values.max_rounds > 4)) {
      error = m.tournament_new_error_max_rounds();
      return;
    }

    isSubmitting = true;
    error = null;

    try {
      const data = {
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
        max_players: values.max_players,
        open_rounds: values.open_rounds,
        self_organized_rounds: values.self_organized_rounds,
        standings_mode: values.standings_mode,
        decklists_mode: values.decklists_mode,
        proxies: values.proxies,
        multideck: values.multideck,
        decklist_required: values.decklist_required,
        league_uid: values.league_uid || null,
        round_time: values.round_time,
        finals_time: values.finals_time,
      };
      // createTournamentOffline saves to IndexedDB and marks the device lock itself
      const tournament = offline
        ? await createTournamentOffline(data)
        : await createTournament(data, { suppressErrorToast: true });
      if (!offline) await saveTournament(tournament);
      goto(`/tournaments/${tournament.uid}`);
    } catch (e) {
      error = toUserMessage(e, m.tournament_error_create());
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
      <a href="/tournaments" class="text-ink-muted hover:text-ink-bright">
        <ArrowLeft class="w-5 h-5" />
      </a>
      <h1 class="text-3xl font-semibold text-accent">{m.tournament_new_title()}</h1>
    </div>

    {#if !canCreate}
      <div class="bg-accent-soft/20 border border-accent-soft-border rounded-lg p-4">
        <p class="text-link-soft">{m.tournament_new_no_permission()}</p>
      </div>
    {:else}
      <form onsubmit={(e) => { e.preventDefault(); handleSubmit(); }} class="space-y-6">
        <div class="bg-surface-card rounded-lg shadow p-6 border border-line space-y-4">
          {#if offline}
            <div class="banner-warn border rounded-lg p-3 flex items-start gap-2">
              <WifiOff class="w-4 h-4 shrink-0 mt-0.5" aria-hidden="true" />
              <p class="text-sm">{m.tournament_new_offline_notice()}</p>
            </div>
          {/if}
          {#if error}
            <div class="bg-accent-soft/20 border border-accent-soft-border rounded-lg p-3">
              <p class="text-link-soft text-sm">{error}</p>
            </div>
          {/if}

          <TournamentFields bind:values disabled={isSubmitting} mode="create" />
        </div>

        <div class="flex flex-col items-end gap-1.5">
          {#if missingFields.length > 0}
            <p class="text-xs text-ink-faint">{m.tournament_new_missing_fields({ fields: missingFields.join(", ") })}</p>
          {/if}
          <div class="flex gap-3 justify-end">
            <a href="/tournaments" class="px-4 py-2 text-sm font-medium text-ink bg-surface-hover hover:bg-surface-active rounded-lg transition-colors">
              {m.common_cancel()}
            </a>
            <Button
              type="submit"
              variant="primary"
              size="lg"
              class="shadow-md"
              loading={isSubmitting}
              disabled={missingFields.length > 0}
            >
              {isSubmitting ? m.tournament_new_creating() : m.tournament_new_create_btn()}
            </Button>
          </div>
        </div>
      </form>
    {/if}
  </div>
</div>
