<script lang="ts">
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
