<script lang="ts">
  import type { Tournament, TournamentState } from "$lib/types";
  import { formatScore } from "$lib/utils";
  import { computeRatingPoints } from "$lib/engine";
  import { getStateBadgeClass, seatDisplay as seatDisplayUtil, translateTournamentState, type StandingEntry } from "$lib/tournament-utils";
  import { addTournamentOrganizer, removeTournamentOrganizer, importArchonFile, type ArchonImportResult } from "$lib/api";
  import { showToast } from "$lib/stores/toast.svelte";
  import { generateResultsCard } from "$lib/social-card";
  import { generateResultsText } from "$lib/social-text";
  import OrganizerManager from "$lib/components/OrganizerManager.svelte";
  import TableRoomsEditor from "./TableRoomsEditor.svelte";
  import RaffleSection from "./RaffleSection.svelte";
  import { Share2, ClipboardCopy, Upload, Download, ChevronDown, ChevronRight } from "lucide-svelte";

  import * as m from '$lib/paraglide/messages.js';

  const API_BASE = import.meta.env.VITE_API_URL || "";

  let {
    tournament = $bindable(),
    playerInfo,
    standings,
    isOrganizer,
    doAction,
    actionLoading,
  }: {
    tournament: Tournament;
    playerInfo: Record<string, { name: string; nickname: string | null; vekn: string | null }>;
    standings: StandingEntry[];
    isOrganizer: boolean;
    doAction?: (action: string, body?: any) => Promise<void>;
    actionLoading?: boolean;
  } = $props();

  function seatDisplay(uid: string): string {
    return seatDisplayUtil(uid, playerInfo);
  }

  const hasRounds = $derived((tournament?.rounds?.length ?? 0) > 0);
  const isFinals = $derived(tournament?.finals != null && (tournament?.state === "Playing" || tournament?.state === "Finished"));
  const hasFinals = $derived(standings.some(e => e.finals));
  const isFinished = $derived(tournament.state === "Finished");

  // Archon import state
  let archonExpanded = $state(false);
  let archonFile = $state<File | null>(null);
  let archonUploading = $state(false);
  let archonResult = $state<ArchonImportResult | null>(null);
  let archonConfirmOverwrite = $state(false);

  async function handleArchonImport() {
    if (!archonFile) return;
    // Confirm overwrite if tournament already has rounds
    if (hasRounds && !archonConfirmOverwrite) {
      archonConfirmOverwrite = true;
      return;
    }
    archonUploading = true;
    archonResult = null;
    archonConfirmOverwrite = false;
    try {
      const result = await importArchonFile(tournament.uid, archonFile);
      archonResult = result;
      if (result.success) {
        showToast({ type: "success", message: m.archon_import_success() });
        archonFile = null;
        // Reset file input
        const input = document.getElementById("archon-file-input") as HTMLInputElement;
        if (input) input.value = "";
      }
    } catch (e) {
      archonResult = {
        success: false,
        errors: [e instanceof Error ? e.message : "Unknown error"],
        warnings: [],
        players_matched: 0,
        rounds_imported: 0,
        has_finals: false,
      };
    } finally {
      archonUploading = false;
    }
  }

  let sharingImage = $state(false);

  async function shareImage() {
    sharingImage = true;
    try {
      const blob = await generateResultsCard(tournament, playerInfo, standings);
      const file = new File([blob], `${tournament.name.replace(/[^a-z0-9]/gi, "_")}.png`, { type: "image/png" });
      if (navigator.canShare?.({ files: [file] })) {
        await navigator.share({ files: [file] });
      } else {
        // Desktop fallback: download
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = file.name;
        a.click();
        URL.revokeObjectURL(url);
        showToast({ type: "success", message: m.share_results_downloaded() });
      }
    } catch (e) {
      if (e instanceof Error && e.name === "AbortError") return; // user cancelled share sheet
      showToast({ type: "error", message: m.share_results_error() });
    } finally {
      sharingImage = false;
    }
  }

  async function copyText() {
    try {
      const text = await generateResultsText(tournament, playerInfo, standings);
      await navigator.clipboard.writeText(text);
      showToast({ type: "success", message: m.share_results_copied() });
    } catch {
      showToast({ type: "error", message: m.share_results_error() });
    }
  }

  function getRatingPts(entry: StandingEntry): number {
    if (!isFinished) return 0;
    const finalistPos = entry.user_uid === tournament.winner ? 1
      : (tournament.finals?.seating.some(s => s.player_uid === entry.user_uid) ? 2 : 0);
    return computeRatingPoints(entry.vp, entry.gw, finalistPos, standings.length, tournament.rank);
  }
</script>

<div class="space-y-4">
  <!-- State badge + summary -->
  <div class="flex items-center gap-3">
    <span class="px-3 py-1.5 rounded text-sm font-medium {getStateBadgeClass(tournament.state)}">
      {translateTournamentState(tournament.state)}
    </span>
    <span class="text-sm text-ash-400">
      {m.overview_player_count({ count: tournament.players?.length ?? 0 })}
      {#if hasRounds}
        · {m.overview_round_count({ count: tournament.rounds!.length })}
      {/if}
      {#if isFinals}
        · {m.overview_finals_in_progress()}
      {/if}
    </span>
  </div>

  <!-- Winner display -->
  {#if tournament.winner}
    <div class="banner-emerald border rounded-lg p-4">
      <div class="text-ash-500 text-sm">{m.tournament_winner()}</div>
      <div class="text-xl font-medium text-bone-100">{seatDisplay(tournament.winner)}</div>
    </div>
  {/if}

  <!-- Share buttons (finished tournaments with standings) -->
  {#if isFinished && standings.length > 0}
    <div class="flex gap-2">
      <button onclick={shareImage} disabled={sharingImage}
        class="flex items-center gap-2 px-3 py-1.5 text-sm bg-ash-800 hover:bg-ash-700 text-ash-200 rounded-lg transition-colors disabled:opacity-50">
        <Share2 class="w-4 h-4" />
        {sharingImage ? m.common_loading() : m.share_results_image()}
      </button>
      <button onclick={copyText}
        class="flex items-center gap-2 px-3 py-1.5 text-sm bg-ash-800 hover:bg-ash-700 text-ash-200 rounded-lg transition-colors">
        <ClipboardCopy class="w-4 h-4" />
        {m.share_results_text()}
      </button>
    </div>
  {/if}

  <!-- Organizers -->
  {#if isOrganizer}
    <div class="bg-ash-900/30 rounded-lg p-4">
      <OrganizerManager
        organizerUids={tournament.organizers_uids ?? []}
        onadd={async (userUid) => { await addTournamentOrganizer(tournament.uid, userUid); }}
        onremove={async (userUid) => { await removeTournamentOrganizer(tournament.uid, userUid); }}
      />
    </div>
    <div class="bg-ash-900/30 rounded-lg p-4">
      <TableRoomsEditor
        tournamentUid={tournament.uid}
        tableRooms={tournament.table_rooms ?? []}
        onupdate={(t) => { tournament = t; }}
      />
    </div>
    <!-- Archon Import -->
    <div class="bg-ash-900/30 rounded-lg p-4">
      <button onclick={() => archonExpanded = !archonExpanded}
        class="flex items-center gap-2 text-sm font-medium text-ash-300 w-full text-left">
        {#if archonExpanded}<ChevronDown class="w-4 h-4" />{:else}<ChevronRight class="w-4 h-4" />{/if}
        {m.archon_import_title()}
      </button>
      {#if archonExpanded}
        <div class="mt-3 space-y-3">
          <p class="text-xs text-ash-400">{m.archon_import_description()}</p>
          <a href="{API_BASE}/api/tournaments/archon-template" download
            class="inline-flex items-center gap-2 text-sm text-blood-400 hover:text-blood-300">
            <Download class="w-4 h-4" />
            {m.archon_download_template()}
          </a>
          <div class="flex items-center gap-2">
            <input id="archon-file-input" type="file" accept=".xlsx"
              onchange={(e) => { archonFile = (e.target as HTMLInputElement).files?.[0] ?? null; archonResult = null; archonConfirmOverwrite = false; }}
              class="text-sm text-ash-300 file:mr-2 file:py-1 file:px-3 file:rounded file:border-0 file:text-sm file:bg-ash-700 file:text-ash-200 hover:file:bg-ash-600" />
            <button onclick={handleArchonImport} disabled={!archonFile || archonUploading}
              class="flex items-center gap-2 px-3 py-1.5 text-sm bg-blood-600 hover:bg-blood-500 text-bone-100 rounded transition-colors disabled:opacity-50">
              <Upload class="w-4 h-4" />
              {archonUploading ? m.archon_uploading() : m.archon_upload_file()}
            </button>
          </div>
          {#if archonConfirmOverwrite}
            <div class="bg-amber-900/30 border border-amber-700 rounded p-3 text-sm text-amber-200">
              <p>{m.archon_import_confirm_overwrite()}</p>
              <div class="flex gap-2 mt-2">
                <button onclick={handleArchonImport}
                  class="px-3 py-1 text-sm bg-amber-600 hover:bg-amber-500 text-bone-100 rounded">
                  {m.common_confirm()}
                </button>
                <button onclick={() => archonConfirmOverwrite = false}
                  class="px-3 py-1 text-sm bg-ash-700 hover:bg-ash-600 text-ash-200 rounded">
                  {m.common_cancel()}
                </button>
              </div>
            </div>
          {/if}
          {#if archonResult}
            {#if archonResult.success}
              <div class="bg-emerald-900/30 border border-emerald-700 rounded p-3 text-sm text-emerald-200">
                <p>{m.archon_import_success()}</p>
                <p class="text-xs mt-1">{m.archon_players_matched({ count: archonResult.players_matched })} · {m.archon_rounds_imported({ count: archonResult.rounds_imported })}{archonResult.has_finals ? " · Finals" : ""}</p>
              </div>
            {:else}
              <div class="bg-red-900/30 border border-red-700 rounded p-3 text-sm text-red-200">
                <p class="font-medium">{m.archon_import_error()}</p>
                <ul class="mt-1 text-xs space-y-0.5">
                  {#each archonResult.errors as error}
                    <li>· {error}</li>
                  {/each}
                </ul>
              </div>
            {/if}
          {/if}
        </div>
      {/if}
    </div>
  {:else if tournament.organizers_uids?.length}
    <div class="bg-ash-900/30 rounded-lg p-4">
      <h4 class="text-sm font-medium text-ash-300 mb-2">{m.organizers_title()}</h4>
      <div class="flex flex-wrap gap-2">
        {#each tournament.organizers_uids as uid}
          <span class="text-sm text-bone-100">{seatDisplay(uid)}</span>
        {/each}
      </div>
    </div>
  {/if}

  <!-- Summary standings (top 5) -->
  {#if standings.length > 0}
    <div class="bg-ash-900/30 rounded-lg p-4">
      <h3 class="text-sm font-medium text-ash-300 mb-2">{m.overview_top_standings()}</h3>
      <table class="w-full text-sm">
        <thead>
          <tr class="text-ash-500 text-xs">
            <th class="text-left py-1 pr-2">{m.tournament_col_rank()}</th>
            <th class="text-left py-1 pr-2">{m.tournament_col_player()}</th>
            <th class="text-right py-1 px-2">{m.tournament_col_score()}</th>
            {#if hasFinals}
              <th class="text-right py-1 px-2">{m.tournament_col_finals()}</th>
            {/if}
            {#if isFinished}
              <th class="text-right py-1 px-2">{m.tournament_col_rating()}</th>
            {/if}
          </tr>
        </thead>
        <tbody>
          {#each standings.slice(0, 5) as entry}
            <tr class="text-bone-100 border-t border-ash-800">
              <td class="py-1 pr-2 text-ash-500">{entry.rank}</td>
              <td class="py-1 pr-2">{seatDisplay(entry.user_uid)}</td>
              <td class="text-right py-1 px-2">{formatScore(entry.gw, entry.vp, entry.tp)}</td>
              {#if hasFinals}
                <td class="text-right py-1 px-2">{entry.finals ?? ""}</td>
              {/if}
              {#if isFinished}
                <td class="text-right py-1 px-2 text-ash-400">{getRatingPts(entry)}</td>
              {/if}
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}

  <!-- Raffle section (Waiting, Playing, or Finished) -->
  {#if tournament.state === "Waiting" || tournament.state === "Playing" || tournament.state === "Finished"}
    <RaffleSection
      {tournament}
      {playerInfo}
      standings={tournament.standings ?? []}
      {isOrganizer}
      {doAction}
      {actionLoading}
    />
  {/if}
</div>
