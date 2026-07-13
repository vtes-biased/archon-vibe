<script lang="ts">
  import { toUserMessage } from '$lib/errors';
  import type { Tournament } from "$lib/types";
  import { tournamentAction } from "$lib/tournament-actions";
  import { addTournamentOrganizer, removeTournamentOrganizer } from "$lib/api";
  import TournamentFields, { type TournamentFieldValues } from "$lib/components/TournamentFields.svelte";
  import OrganizerManager from "$lib/components/OrganizerManager.svelte";
  import TableRoomsEditor from "./TableRoomsEditor.svelte";
  import { RefreshCw, ChevronDown, ChevronRight } from "@lucide/svelte";
  import * as m from '$lib/paraglide/messages.js';

  const DISCORD_VENUE = "Official Discord";
  const DISCORD_URL = "https://discord.com/invite/vampire-the-eternal-struggle-official-887471681277399091";

  let {
    tournament = $bindable(),
    isOrganizer,
    expandOrganizers = false,
  }: {
    tournament: Tournament;
    isOrganizer: boolean;
    /** Open the organizers section on mount (header add-co-organizer chip). */
    expandOrganizers?: boolean;
  } = $props();

  let saving = $state(false);
  let error = $state<string | null>(null);

  // Re-homed setup sections (foldable, collapsed by default). Initial-value
  // capture is intended: the tab remounts on every switch, so the chip's
  // expand request applies at mount.
  // svelte-ignore state_referenced_locally
  let organizersExpanded = $state(expandOrganizers);
  let roomsExpanded = $state(false);

  // Stash location fields when toggling online mode, so we can restore on toggle-back
  let stashedPhysical = $state<{ country: string; venue: string; venue_url: string; address: string; map_url: string } | null>(null);
  let stashedOnline = $state<{ venue: string; venue_url: string } | null>(null);

  // Derive field values from tournament for the shared component
  let fieldValues = $state<TournamentFieldValues>({
    name: tournament.name,
    format: tournament.format,
    rank: tournament.rank,
    open_rounds: tournament.open_rounds ?? false,
    max_rounds: (tournament.max_rounds ?? 0),
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
    // VEKN identity freeze: calendar create is write-once — post-push edits
    // to these silently diverge from vekn.net (engine rejects them too).
    if (pushedToVekn) { s.add("rank"); s.add("format"); s.add("start"); }
    return s;
  });

  // Debounced save for text inputs
  let debounceTimer: ReturnType<typeof setTimeout> | undefined;
  function debouncedSave(field: string, value: any) {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => save(field, value), 500);
  }

  // Text fields that need debouncing
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
      // Selecting a championship rank also clears proxies/multideck (see
      // TournamentFields rank onchange) — persist together, or the rank-only
      // save would hit the engine's rank-legality gate against the old flags.
      saveMultiple({ rank: value, proxies: false, multideck: false });
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
      // Stash physical-location fields, restore any stashed online fields
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
      // Stash online venue fields, restore any stashed physical fields
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

<div class="space-y-6">
  {#if error}
    <div class="bg-accent-soft/20 border border-accent-soft-border rounded-lg p-3">
      <p class="text-link-soft text-sm">{error}</p>
    </div>
  {/if}

  {#if !isOrganizer}
    <p class="text-ink-muted">{m.config_no_permission()}</p>
  {:else}
    <!-- Organizers + table rooms first: operational levers, most needed as the
         event nears or starts (re-homed from the former Overview tab). -->
    <div class="space-y-3">
      <div class="bg-surface-muted/30 rounded-lg p-4">
        <button onclick={() => organizersExpanded = !organizersExpanded}
          aria-expanded={organizersExpanded}
          class="flex items-center gap-2 py-2 text-sm font-medium text-ink w-full text-left">
          {#if organizersExpanded}<ChevronDown class="w-4 h-4" />{:else}<ChevronRight class="w-4 h-4" />{/if}
          {m.organizers_title()}
        </button>
        {#if organizersExpanded}
          <div class="mt-3">
            <OrganizerManager
              organizerUids={tournament.organizers_uids ?? []}
              onadd={async (userUid) => { await addTournamentOrganizer(tournament.uid, userUid); }}
              onremove={async (userUid) => { await removeTournamentOrganizer(tournament.uid, userUid); }}
            />
          </div>
        {/if}
      </div>
      <div class="bg-surface-muted/30 rounded-lg p-4">
        <button onclick={() => roomsExpanded = !roomsExpanded}
          aria-expanded={roomsExpanded}
          class="flex items-center gap-2 py-2 text-sm font-medium text-ink w-full text-left">
          {#if roomsExpanded}<ChevronDown class="w-4 h-4" />{:else}<ChevronRight class="w-4 h-4" />{/if}
          {m.rooms_title()}
        </button>
        {#if roomsExpanded}
          <div class="mt-3">
            <TableRoomsEditor
              tournamentUid={tournament.uid}
              tableRooms={tournament.table_rooms ?? []}
              onupdate={(t) => { tournament = t; }}
            />
          </div>
        {/if}
      </div>
    </div>

    <!-- Tournament settings -->
    <div class="space-y-4 pt-4 border-t border-line">
      <TournamentFields
        bind:values={fieldValues}
        onchange={handleFieldChange}
        onvenueselect={(fields) => saveMultiple(fields)}
        {disabledFields}
        idPrefix="cfg"
      />
    </div>

    {#if saving}
      <div class="text-xs text-ink-faint flex items-center gap-1">
        <RefreshCw class="w-3 h-3 animate-spin" />
        {m.config_saving()}
      </div>
    {/if}
  {/if}
</div>
