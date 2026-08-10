<script lang="ts">
  // The pre-event workspace. Organizers and table rooms use the same section
  // shell as the settings form's own sections, so all eight read as peers —
  // that shared shell is the whole point, since without it they drift back into
  // separate tiers. Everything here is also listed in the Tools sheet, which
  // stays the durable index; the tab is the current moment's promotion of it.
  //
  // An "add co-organizer" chip used to live in the masthead purely because this
  // section was buried; with organizers on screen where the work happens, the
  // chip had no job left.
  import type { Tournament } from "$lib/types";
  import { addTournamentOrganizer, removeTournamentOrganizer } from "$lib/api";
  import TournamentDetailsForm from "./TournamentDetailsForm.svelte";
  import FoldableSection from "$lib/components/FoldableSection.svelte";
  import OrganizerManager from "$lib/components/OrganizerManager.svelte";
  import TableRoomsEditor from "./TableRoomsEditor.svelte";
  import * as m from '$lib/paraglide/messages.js';

  let {
    tournament = $bindable(),
    isOrganizer,
  }: {
    tournament: Tournament;
    isOrganizer: boolean;
  } = $props();

  let organizersOpen = $state(false);
  let roomsOpen = $state(false);
</script>

<div class="space-y-4">
  <TournamentDetailsForm bind:tournament {isOrganizer} />

  <FoldableSection title={m.organizers_title()} bind:open={organizersOpen}>
    <OrganizerManager
      organizerUids={tournament.organizers_uids ?? []}
      onadd={async (userUid) => { await addTournamentOrganizer(tournament.uid, userUid); }}
      onremove={async (userUid) => { await removeTournamentOrganizer(tournament.uid, userUid); }}
    />
  </FoldableSection>

  <FoldableSection title={m.rooms_title()} bind:open={roomsOpen}>
    <TableRoomsEditor
      tournamentUid={tournament.uid}
      tableRooms={tournament.table_rooms ?? []}
      onupdate={(t) => { tournament = t; }}
    />
  </FoldableSection>
</div>
