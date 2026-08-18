<script lang="ts">
  import { toUserMessage } from '$lib/errors';
  import type { Tournament } from "$lib/types";
  import { tournamentAction } from "$lib/tournament-actions";
  import TournamentFields, { type TournamentFieldValues } from "$lib/components/TournamentFields.svelte";
  import TableRoomsEditor from "./TableRoomsEditor.svelte";
  import { RefreshCw, Check } from "@lucide/svelte";
  import * as m from '$lib/paraglide/messages.js';

  const DISCORD_VENUE = "Official Discord";
  const DISCORD_URL = "https://discord.com/invite/vampire-the-eternal-struggle-official-887471681277399091";

  let {
    tournament = $bindable(),
    isOrganizer,
    inSheet = false,
  }: {
    tournament: Tournament;
    isOrganizer: boolean;
    // Set when rendered inside a scrolling sheet: the sheet already covers the
    // bottom nav, so the save chip must not reserve clearance for it.
    inSheet?: boolean;
  } = $props();

  let saving = $state(false);
  let error = $state<string | null>(null);
  // Transient saved-confirmation for the sticky chip (auto-save has no submit
  // button, so without it a successful save is silent).
  let savedFlash = $state(false);
  let savedTimer: ReturnType<typeof setTimeout> | undefined;
  function flashSaved() {
    savedFlash = true;
    clearTimeout(savedTimer);
    savedTimer = setTimeout(() => (savedFlash = false), 2000);
  }

  // Stash location fields when toggling online mode, so we can restore on toggle-back
  let stashedPhysical = $state<{ country: string; venue: string; venue_url: string; address: string; map_url: string } | null>(null);
  let stashedOnline = $state<{ venue: string; venue_url: string } | null>(null);

  let fieldValues = $state<TournamentFieldValues>({
    name: tournament.name,
    format: tournament.format,
    rank: tournament.rank,
    open_rounds: tournament.open_rounds ?? false,
    max_rounds: (tournament.max_rounds ?? 0),
    max_players: (tournament.max_players ?? 0),
    self_organized_rounds: tournament.self_organized_rounds ?? false,
    online: tournament.online,
    country: tournament.country ?? "",
    venue: tournament.venue ?? "",
    venue_url: tournament.venue_url ?? "",
    address: tournament.address ?? "",
    map_url: tournament.map_url ?? "",
    start: tournament.start ? tournament.start.slice(0, 16) : "",
    finish: tournament.finish ? tournament.finish.slice(0, 16) : "",
    timezone: tournament.timezone,
    description: tournament.description ?? "",
    standings_mode: tournament.standings_mode ?? "Private",
    decklists_mode: tournament.decklists_mode ?? "Winner",
    proxies: tournament.proxies ?? false,
    multideck: tournament.multideck ?? false,
    decklist_required: tournament.decklist_required ?? false,
    league_uid: tournament.league_uid ?? "",
    round_time: tournament.round_time ?? 0,
    finals_time: tournament.finals_time ?? 0,
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
        open_rounds: t.open_rounds ?? false,
        max_rounds: (t.max_rounds ?? 0),
        max_players: (t.max_players ?? 0),
        self_organized_rounds: t.self_organized_rounds ?? false,
        online: t.online,
        country: t.country ?? "",
        venue: t.venue ?? "",
        venue_url: t.venue_url ?? "",
        address: t.address ?? "",
        map_url: t.map_url ?? "",
        start: t.start ? t.start.slice(0, 16) : "",
        finish: t.finish ? t.finish.slice(0, 16) : "",
        timezone: t.timezone,
        description: t.description ?? "",
        standings_mode: t.standings_mode ?? "Private",
        decklists_mode: t.decklists_mode ?? "Winner",
        proxies: t.proxies ?? false,
        multideck: t.multideck ?? false,
        decklist_required: t.decklist_required ?? false,
        league_uid: t.league_uid ?? "",
        round_time: t.round_time ?? 0,
        finals_time: t.finals_time ?? 0,
      };
    }
  });

  async function save(field: string, value: any) {
    if (!isOrganizer) return;
    saving = true;
    error = null;
    try {
      tournament = await tournamentAction(tournament.uid, 'UpdateConfig', { config: { [field]: value } });
      flashSaved();
    } catch (e) {
      error = toUserMessage(e, m.config_error_save());
    } finally {
      saving = false;
    }
  }

  async function saveMultiple(fields: Record<string, any>) {
    if (!isOrganizer) return;
    saving = true;
    error = null;
    try {
      tournament = await tournamentAction(tournament.uid, 'UpdateConfig', { config: fields });
      flashSaved();
    } catch (e) {
      error = toUserMessage(e, m.config_error_save());
    } finally {
      saving = false;
    }
  }

  const started = $derived(
    tournament.state === "Waiting" || tournament.state === "Playing" || tournament.state === "Finished"
  );
  const pushedToVekn = $derived(!!tournament.external_ids?.vekn);
  const disabledFields = $derived.by(() => {
    const s = new Set<string>();
    if (started || pushedToVekn) { s.add("open_rounds"); s.add("max_rounds"); }
    // VEKN identity freeze: post-push edits to these silently diverge from
    // vekn.net (engine rejects them too); proxies joins them because the sync
    // reads it back, so a local change would revert rather than diverge.
    if (pushedToVekn) { s.add("rank"); s.add("format"); s.add("start"); s.add("proxies"); }
    return s;
  });

  let debounceTimer: ReturnType<typeof setTimeout> | undefined;
  function debouncedSave(field: string, value: any) {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => save(field, value), 500);
  }

  const debouncedFields = new Set(["name", "venue", "venue_url", "address", "map_url", "description"]);

  function handleFieldChange(field: string, value: any) {
    if (field === "open_rounds") {
      // Toggling open_rounds also coerces max_rounds + self_organized_rounds
      // (see TournamentFields.handleOpenRoundsToggle) — persist all three together.
      saveMultiple({
        open_rounds: value,
        max_rounds: fieldValues.max_rounds,
        self_organized_rounds: fieldValues.self_organized_rounds,
      });
      return;
    }
    if (field === "online") {
      handleToggleOnline(value);
      return;
    }
    if (field === "rank" && value) {
      // Selecting a rank also clears proxies/multideck (see TournamentFields
      // rank onchange) — persist together, or the rank-only save hits the
      // engine's rank-legality gate against stale flags.
      saveMultiple({ rank: value, proxies: false, multideck: false });
      return;
    }
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
      stashedPhysical = {
        country: tournament.country ?? "",
        venue: tournament.venue ?? "",
        venue_url: tournament.venue_url ?? "",
        address: tournament.address ?? "",
        map_url: tournament.map_url ?? "",
      };
      const restored = stashedOnline ?? { venue: DISCORD_VENUE, venue_url: DISCORD_URL };
      stashedOnline = null;
      await saveMultiple({
        online: true,
        country: null,
        address: "",
        map_url: "",
        venue: restored.venue,
        venue_url: restored.venue_url,
      });
    } else {
      stashedOnline = {
        venue: tournament.venue ?? "",
        venue_url: tournament.venue_url ?? "",
      };
      const restored = stashedPhysical ?? { country: "", venue: "", venue_url: "", address: "", map_url: "" };
      stashedPhysical = null;
      await saveMultiple({
        online: false,
        country: restored.country || null,
        venue: restored.venue,
        venue_url: restored.venue_url,
        address: restored.address,
        map_url: restored.map_url,
      });
    }
  }
</script>

{#snippet venueExtra()}
  <TableRoomsEditor
    tournamentUid={tournament.uid}
    tableRooms={tournament.table_rooms ?? []}
    onupdate={(t) => { tournament = t; }}
  />
{/snippet}

<!-- space-y-4 matches the gap between the sections themselves, so the form's
     sections and the section around it (organizers) sit on one rhythm. -->
<div class="space-y-4">
  {#if error}
    <div class="bg-accent-soft/20 border border-accent-soft-border rounded-lg p-3">
      <p class="text-link-soft text-sm">{error}</p>
    </div>
  {/if}

  {#if !isOrganizer}
    <p class="text-ink-muted">{m.config_no_permission()}</p>
  {:else}
    <div class="space-y-4">
      <TournamentFields
        bind:values={fieldValues}
        onchange={handleFieldChange}
        onvenueselect={(fields) => saveMultiple(fields)}
        {disabledFields}
        idPrefix="cfg"
        {venueExtra}
      />
    </div>

    <!-- Sticky resolves against the scrollport, not the shell's padding box: on
         the page it must clear the bottom nav (z-40) or the nav paints over it,
         while in a sheet the same clearance strands the chip. -->
    {#if saving || savedFlash}
      <div class="sticky {inSheet ? 'bottom-4' : 'bottom-[calc(1rem+var(--spacing-navbar))] sm:bottom-[calc(1rem+var(--spacing-safe-b))]'} flex justify-end pointer-events-none">
        <div class="bg-surface-card border border-line rounded-full shadow px-3 py-1.5 text-xs text-ink-muted flex items-center gap-1.5">
          {#if saving}
            <RefreshCw class="w-3 h-3 animate-spin" aria-hidden="true" />
            {m.config_saving()}
          {:else}
            <Check class="w-3 h-3 text-info" aria-hidden="true" />
            {m.config_saved()}
          {/if}
        </div>
      </div>
    {/if}
  {/if}
</div>
