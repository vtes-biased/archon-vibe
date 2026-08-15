<script lang="ts">
  // One entry point for everything that is NOT the current action. The action
  // bar answers "what do I do now"; this answers "where is that thing".
  //
  // Rows are grouped and the groups run in EVENT CHRONOLOGY — set up, at the
  // door, wrap up. That order is fixed (an event's chronology is fixed) so
  // muscle memory holds; only which group starts open follows tournament state.
  // A flat list would be the hamburger trap: finding anything means reading
  // everything.
  import type { Component } from "svelte";
  import type { Tournament } from "$lib/types";
  import { addTournamentOrganizer, removeTournamentOrganizer } from "$lib/api";
  import TournamentDetailsForm from "./TournamentDetailsForm.svelte";
  import OrganizerManager from "$lib/components/OrganizerManager.svelte";
  import PromosDistributedEditor from "./PromosDistributedEditor.svelte";
  import QrCheckinDisplay from "$lib/components/QrCheckinDisplay.svelte";
  import RaffleSection from "./RaffleSection.svelte";
  import ReopenConfirmModal from "./ReopenConfirmModal.svelte";
  import FinishConfirmModal from "./FinishConfirmModal.svelte";
  import Button from "$lib/components/Button.svelte";
  import { copyResults } from "$lib/copy-results";
  import type { StandingEntry, PlayerInfoMap } from "$lib/tournament-utils";
  import type { TournamentEventType } from "$lib/engine";
  import { ChevronDown, ChevronRight, X, Settings2, Users, Upload, CloudUpload, QrCode, Gift, Ticket, ClipboardCopy, Download, Undo2, Trash2, Image, TriangleAlert } from "@lucide/svelte";
  import type { DeckObject } from "$lib/types";
  import * as m from '$lib/paraglide/messages.js';

  const API_BASE = import.meta.env.VITE_API_URL ?? "";

  type ActionItem = { label: string; icon?: Component<any>; onclick: () => void; disabled?: boolean };
  type GroupId = "setup" | "door" | "wrapup";
  // Table rooms left this sheet: they are part of the venue, so they live at the
  // foot of Details > Venue instead of as a peer row.
  type PanelId = "details" | "organizers" | "qr" | "promos" | "raffle";
  const PANEL_GROUP: Record<PanelId, GroupId> = {
    details: "setup", organizers: "setup", qr: "door",
    promos: "wrapup", raffle: "wrapup",
  };

  let {
    open = $bindable(false),
    requestPanel = $bindable(null),
    tournament = $bindable(),
    isOrganizer,
    playerInfo,
    standings,
    decksByUser,
    doAction,
    actionLoading = false,
    bannerItem,
    csvImportItem,
    archonImportItem,
    syncVeknItem,
    canDelete,
    onDelete,
  }: {
    open?: boolean;
    /** Open the sheet straight onto one panel (deep links from the console). */
    requestPanel?: PanelId | null;
    tournament: Tournament;
    isOrganizer: boolean;
    playerInfo: PlayerInfoMap;
    standings: StandingEntry[];
    /** Only for the finish-confirmation modal's winner-deck warning. */
    decksByUser: Record<string, DeckObject[]>;
    doAction: (action: TournamentEventType, body?: any) => Promise<string | null>;
    actionLoading?: boolean;
    bannerItem: ActionItem;
    csvImportItem: ActionItem;
    archonImportItem: ActionItem;
    /** Carries its own group: the same row is "add to calendar" during Set up
        and "report results" during Wrap up. */
    syncVeknItem: (ActionItem & { group: GroupId }) | null;
    canDelete: boolean;
    onDelete: () => void;
  } = $props();

  let showReopenConfirm = $state(false);
  let showFinishConfirm = $state(false);
  // Ending WITHOUT a final is the exception; the normal path is the action
  // bar's Start finals -> Finish finals.
  const canFinishEarly = $derived(tournament.state === "Waiting");
  const hasStandings = $derived(standings.length > 0);
  const isFinished = $derived(tournament.state === "Finished");
  // The raffle is drawn in front of players at the end, so it only appears once
  // there is an event to draw at.
  const raffleAvailable = $derived(
    tournament.state === "Waiting" || tournament.state === "Playing" || isFinished
  );

  function downloadEventCopy() {
    const a = document.createElement("a");
    a.href = `${API_BASE}/api/tournaments/${tournament.uid}/report`;
    a.download = "";
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  // Which group the current moment belongs to. Order never changes; this only
  // decides what is already unfolded when the sheet opens.
  const currentGroup = $derived.by((): GroupId => {
    switch (tournament.state) {
      case "Planned":
      case "Registration": return "setup";
      case "Waiting":
      case "Playing": return "door";
      default: return "wrapup";
    }
  });

  let openGroup = $state<GroupId | null>(null);
  // One panel at a time: the sheet is a directory, not a workspace.
  let openPanel = $state<PanelId | null>(null);

  // Opening the sheet re-seats it on the current moment — or on the panel a
  // deep link asked for. Closing forgets, so it never reopens showing whatever
  // was last poked at.
  $effect(() => {
    if (!open) { openPanel = null; return; }
    const asked = requestPanel;
    if (asked) {
      openGroup = PANEL_GROUP[asked];
      openPanel = asked;
      requestPanel = null;
    } else {
      openGroup = currentGroup;
    }
  });

  const qrAvailable = $derived(!tournament.online && !!tournament.checkin_code);

  function runAction(item: ActionItem) {
    if (item.disabled) return;
    open = false;
    item.onclick();
  }
  function toggleGroup(id: GroupId) {
    openGroup = openGroup === id ? null : id;
    openPanel = null;
  }
  function togglePanel(id: PanelId) {
    openPanel = openPanel === id ? null : id;
  }
</script>

{#snippet groupHeader(id: GroupId, title: string)}
  <button
    type="button"
    onclick={() => toggleGroup(id)}
    aria-expanded={openGroup === id}
    class="flex w-full items-center gap-2 px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-ink-muted hover:text-ink-bright"
  >
    {#if openGroup === id}<ChevronDown class="w-4 h-4" aria-hidden="true" />{:else}<ChevronRight class="w-4 h-4" aria-hidden="true" />{/if}
    {title}
  </button>
{/snippet}

{#snippet actionRow(item: ActionItem, Icon: Component<any>)}
  <button
    type="button"
    disabled={item.disabled}
    onclick={() => runAction(item)}
    class="flex w-full items-center gap-3 px-4 py-3 text-left text-sm text-ink-bright enabled:hover:bg-surface-hover disabled:text-ink-faint min-h-[44px]"
  >
    <Icon class="w-4 h-4 shrink-0" aria-hidden="true" />
    {item.label}
  </button>
{/snippet}

{#snippet panelRow(id: PanelId, title: string, Icon: Component<any>, body: import("svelte").Snippet)}
  <button
    type="button"
    onclick={() => togglePanel(id)}
    aria-expanded={openPanel === id}
    class="flex w-full items-center gap-3 px-4 py-3 text-left text-sm text-ink-bright hover:bg-surface-hover min-h-[44px]"
  >
    <Icon class="w-4 h-4 shrink-0" aria-hidden="true" />
    <span class="flex-1">{title}</span>
    {#if openPanel === id}<ChevronDown class="w-4 h-4 shrink-0 text-ink-faint" aria-hidden="true" />{:else}<ChevronRight class="w-4 h-4 shrink-0 text-ink-faint" aria-hidden="true" />{/if}
  </button>
  {#if openPanel === id}
    <div class="border-y border-line bg-surface-muted/30 px-4 py-4">
      {@render body()}
    </div>
  {/if}
{/snippet}

{#if open}
  <div class="fixed inset-0 z-50 flex items-end sm:items-center justify-center">
    <!-- Scrim: click-away close. The panel below stops propagation implicitly by
         sitting outside this element. -->
    <button type="button" class="absolute inset-0 bg-black/60" aria-label={m.common_close()} onclick={() => (open = false)}></button>

    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="tools-sheet-title"
      class="relative flex max-h-[85dvh] w-full flex-col overflow-hidden rounded-t-2xl border border-line bg-surface-card shadow-xl pb-safe-b sm:pb-0 sm:max-w-lg sm:rounded-2xl"
    >
      <div class="flex items-center justify-between border-b border-line px-4 py-3">
        <h2 id="tools-sheet-title" class="text-sm font-semibold text-ink-strong">{m.tools_title()}</h2>
        <button type="button" onclick={() => (open = false)} aria-label={m.common_close()} class="rounded-lg p-1.5 text-ink-muted hover:bg-surface-hover hover:text-ink-bright">
          <X class="w-5 h-5" aria-hidden="true" />
        </button>
      </div>

      <div class="min-h-0 flex-1 overflow-y-auto">
        <!-- SET UP -->
        {@render groupHeader("setup", m.tools_group_setup())}
        {#if openGroup === "setup"}
          {@render panelRow("details", m.tools_details(), Settings2, detailsPanel)}
          {@render panelRow("organizers", m.organizers_title(), Users, organizersPanel)}
          {@render actionRow(bannerItem, Image)}
          {@render actionRow(csvImportItem, Upload)}
          {@render actionRow(archonImportItem, Upload)}
          {#if syncVeknItem?.group === "setup"}{@render actionRow(syncVeknItem, CloudUpload)}{/if}
        {/if}

        <!-- AT THE DOOR -->
        {@render groupHeader("door", m.tools_group_door())}
        {#if openGroup === "door"}
          {#if qrAvailable}
            {@render panelRow("qr", m.checkin_qr_show_code(), QrCode, qrPanel)}
          {:else}
            <p class="px-4 py-3 text-sm text-ink-faint">{m.tools_group_door_empty()}</p>
          {/if}
        {/if}

        <!-- WRAP UP -->
        {@render groupHeader("wrapup", m.tools_group_wrapup())}
        {#if openGroup === "wrapup"}
          {#if raffleAvailable}
            {@render panelRow("raffle", m.raffle_title(), Ticket, rafflePanel)}
          {/if}
          {@render panelRow("promos", m.promos_title(), Gift, promosPanel)}
          {#if hasStandings}
            {@render actionRow({ label: m.tools_copy_results(), onclick: () => copyResults(tournament, playerInfo, standings) }, ClipboardCopy)}
            {@render actionRow({ label: m.tools_download_event(), onclick: downloadEventCopy }, Download)}
          {/if}
          {#if syncVeknItem?.group === "wrapup"}{@render actionRow(syncVeknItem, CloudUpload)}{/if}
          {#if canFinishEarly}
            {@render actionRow({ label: m.overview_finish_tournament(), onclick: () => (showFinishConfirm = true), disabled: actionLoading }, TriangleAlert)}
          {/if}
          {#if isFinished}
            {@render actionRow({ label: m.overview_reopen_tournament(), onclick: () => (showReopenConfirm = true), disabled: actionLoading }, Undo2)}
          {/if}
        {/if}

        {#if canDelete}
          <div class="border-t border-line p-4">
            <Button variant="danger" size="md" onclick={() => { open = false; onDelete(); }}>
              <Trash2 class="w-4 h-4" aria-hidden="true" />
              {m.common_delete()}
            </Button>
          </div>
        {/if}
      </div>
    </div>
  </div>
{/if}

{#snippet detailsPanel()}
  <TournamentDetailsForm bind:tournament {isOrganizer} inSheet />
{/snippet}

{#snippet organizersPanel()}
  <OrganizerManager
    organizerUids={tournament.organizers_uids ?? []}
    onadd={async (userUid) => { await addTournamentOrganizer(tournament.uid, userUid); }}
    onremove={async (userUid) => { await removeTournamentOrganizer(tournament.uid, userUid); }}
  />
{/snippet}


{#snippet qrPanel()}
  {#if tournament.checkin_code}
    <QrCheckinDisplay code={tournament.checkin_code} tournamentUid={tournament.uid} tournamentName={tournament.name} />
  {/if}
{/snippet}

{#snippet promosPanel()}
  <PromosDistributedEditor {tournament} onupdate={(t) => { tournament = t; }} />
{/snippet}

{#snippet rafflePanel()}
  <RaffleSection {tournament} {playerInfo} isOrganizer={true} {doAction} {actionLoading} />
{/snippet}

{#if showFinishConfirm}
  <FinishConfirmModal
    {tournament}
    {standings}
    {playerInfo}
    {decksByUser}
    {actionLoading}
    onConfirm={async () => { await doAction("FinishTournament"); showFinishConfirm = false; open = false; }}
    onClose={() => (showFinishConfirm = false)}
  />
{/if}

{#if showReopenConfirm}
  <ReopenConfirmModal
    {tournament}
    {actionLoading}
    {doAction}
    onClose={() => (showReopenConfirm = false)}
  />
{/if}

<svelte:window onkeydown={(e) => { if (open && e.key === "Escape") open = false; }} />
