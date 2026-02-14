<script lang="ts">
  import type { Tournament } from "$lib/types";
  import { updateTournament } from "$lib/api";
  import TournamentFields, { type TournamentFieldValues } from "$lib/components/TournamentFields.svelte";
  import Icon from "@iconify/svelte";
  import * as m from '$lib/paraglide/messages.js';

  const DISCORD_VENUE = "Official Discord";
  const DISCORD_URL = "https://discord.com/invite/vampire-the-eternal-struggle-official-887471681277399091";

  let {
    tournament = $bindable(),
    isOrganizer,
  }: {
    tournament: Tournament;
    isOrganizer: boolean;
  } = $props();

  let saving = $state(false);
  let error = $state<string | null>(null);

  // Derive field values from tournament for the shared component
  let fieldValues = $state<TournamentFieldValues>({
    name: tournament.name,
    format: tournament.format,
    rank: tournament.rank,
    open_rounds: tournament.max_rounds > 0,
    max_rounds: tournament.max_rounds,
    online: tournament.online,
    country: tournament.country ?? "",
    venue: tournament.venue,
    venue_url: tournament.venue_url,
    address: tournament.address,
    map_url: tournament.map_url,
    start: tournament.start ? tournament.start.slice(0, 16) : "",
    finish: tournament.finish ? tournament.finish.slice(0, 16) : "",
    timezone: tournament.timezone,
    description: tournament.description,
    standings_mode: tournament.standings_mode,
    decklists_mode: tournament.decklists_mode,
    proxies: tournament.proxies,
    multideck: tournament.multideck,
    decklist_required: tournament.decklist_required,
    league_uid: tournament.league_uid ?? "",
  });

  // Sync from tournament when it changes externally (but not while user is editing)
  $effect(() => {
    const t = tournament;
    const activeId = document.activeElement?.id ?? "";
    if (!activeId.startsWith("cfg-")) {
      fieldValues = {
        name: t.name,
        format: t.format,
        rank: t.rank,
        open_rounds: t.max_rounds > 0,
        max_rounds: t.max_rounds,
        online: t.online,
        country: t.country ?? "",
        venue: t.venue,
        venue_url: t.venue_url,
        address: t.address,
        map_url: t.map_url,
        start: t.start ? t.start.slice(0, 16) : "",
        finish: t.finish ? t.finish.slice(0, 16) : "",
        timezone: t.timezone,
        description: t.description,
        standings_mode: t.standings_mode,
        decklists_mode: t.decklists_mode,
        proxies: t.proxies,
        multideck: t.multideck,
        decklist_required: t.decklist_required,
        league_uid: t.league_uid ?? "",
      };
    }
  });

  async function save(field: string, value: any) {
    if (!isOrganizer) return;
    saving = true;
    error = null;
    try {
      tournament = await updateTournament(tournament.uid, { [field]: value });
    } catch (e) {
      error = e instanceof Error ? e.message : m.config_error_save();
    } finally {
      saving = false;
    }
  }

  async function saveMultiple(fields: Record<string, any>) {
    if (!isOrganizer) return;
    saving = true;
    error = null;
    try {
      tournament = await updateTournament(tournament.uid, fields);
    } catch (e) {
      error = e instanceof Error ? e.message : m.config_error_save();
    } finally {
      saving = false;
    }
  }

  const started = $derived(
    tournament.state === "Waiting" || tournament.state === "Playing" || tournament.state === "Finished"
  );
  const disabledFields = $derived(
    started ? new Set(["open_rounds", "max_rounds"]) : new Set<string>()
  );

  // Debounced save for text inputs
  let debounceTimer: ReturnType<typeof setTimeout> | undefined;
  function debouncedSave(field: string, value: any) {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => save(field, value), 500);
  }

  // Text fields that need debouncing
  const debouncedFields = new Set(["name", "venue", "venue_url", "address", "map_url", "description"]);

  function handleFieldChange(field: string, value: any) {
    if (field === "open_rounds") return; // UI-only toggle, max_rounds handles the save
    if (field === "online") {
      handleToggleOnline(value);
      return;
    }
    // Normalize empty strings to null for nullable fields
    const saveValue = (field === "country" || field === "start" || field === "finish" || field === "league_uid")
      ? (value || null)
      : value;
    if (debouncedFields.has(field)) {
      debouncedSave(field, saveValue);
    } else {
      save(field, saveValue);
    }
  }

  async function handleToggleOnline(checked: boolean) {
    if (checked) {
      await saveMultiple({
        online: true,
        country: null,
        address: "",
        map_url: "",
        venue: DISCORD_VENUE,
        venue_url: DISCORD_URL,
      });
    } else {
      const updates: Record<string, any> = { online: false };
      if (tournament.venue === DISCORD_VENUE) updates.venue = "";
      if (tournament.venue_url === DISCORD_URL) updates.venue_url = "";
      await saveMultiple(updates);
    }
  }
</script>

<div class="space-y-6">
  {#if error}
    <div class="bg-crimson-900/20 border border-crimson-800 rounded-lg p-3">
      <p class="text-crimson-300 text-sm">{error}</p>
    </div>
  {/if}

  {#if !isOrganizer}
    <p class="text-ash-400">{m.config_no_permission()}</p>
  {:else}
    <div class="space-y-4">
      <TournamentFields bind:values={fieldValues} onchange={handleFieldChange} {disabledFields} idPrefix="cfg" />
    </div>

    {#if saving}
      <div class="text-xs text-ash-500 flex items-center gap-1">
        <Icon icon="lucide:refresh-cw" class="w-3 h-3 animate-spin" />
        {m.config_saving()}
      </div>
    {/if}
  {/if}
</div>
