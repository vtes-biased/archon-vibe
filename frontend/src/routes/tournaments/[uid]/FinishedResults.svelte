<script lang="ts">
  import type { TournamentEventType } from "$lib/engine";
  import type { Tournament } from "$lib/types";
  import { seatDisplay as seatDisplayUtil, type StandingEntry, type PlayerInfoMap } from "$lib/tournament-utils";
  import { generateResultsCard } from "$lib/social-card";
  import { generateResultsText } from "$lib/social-text";
  import { showToast } from "$lib/stores/toast.svelte";
  import { Share2, ClipboardCopy, Download, Upload } from "@lucide/svelte";
  import Button from "$lib/components/Button.svelte";
  import ActionMenu from "$lib/components/ActionMenu.svelte";
  import * as m from '$lib/paraglide/messages.js';

  const API_BASE = import.meta.env.VITE_API_URL ?? "";

  // Organizer-only Finished-state results: winner, deck nudge, share/export, reopen.
  let {
    tournament,
    playerInfo,
    standings,
    winnerHasDeck = false,
    doAction,
    actionLoading = false,
    onImportArchon,
  }: {
    tournament: Tournament;
    playerInfo: PlayerInfoMap;
    standings: StandingEntry[];
    winnerHasDeck?: boolean;
    doAction?: (action: TournamentEventType, body?: any) => Promise<void>;
    actionLoading?: boolean;
    onImportArchon?: () => void;
  } = $props();

  function seatDisplay(uid: string): string {
    return seatDisplayUtil(uid, playerInfo, tournament.online);
  }

  const hasStandings = $derived(standings.length > 0);

  function downloadReport(format: "json" | "text" = "json") {
    const a = document.createElement("a");
    const qs = format === "json" ? "" : `?fmt=${format}`;
    a.href = `${API_BASE}/api/tournaments/${tournament.uid}/report${qs}`;
    a.download = "";
    document.body.appendChild(a);
    a.click();
    a.remove();
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
</script>

<div class="space-y-3">
  <!-- Winner -->
  {#if tournament.winner}
    <div class="banner-highlight border rounded-lg p-4">
      <div class="text-ink-faint text-sm">{m.tournament_winner()}</div>
      <div class="text-xl font-medium text-ink-strong">{seatDisplay(tournament.winner)}</div>
    </div>
  {/if}

  <!-- Winner deck nudge (no deck on file) -->
  {#if tournament.winner && !winnerHasDeck}
    <div class="banner-warn border rounded-lg p-3 text-sm">
      {m.decks_winner_nudge_organizer({ name: seatDisplay(tournament.winner) })}
    </div>
  {/if}

  <!-- Results actions. With standings: share + copy + More (report download) on one
       line. Without (empty finished shell): a direct Archon-import button, per #256. -->
  <div class="flex flex-wrap items-center gap-2">
    {#if hasStandings}
      <Button variant="secondary" size="md" loading={sharingImage} onclick={shareImage}>
        <Share2 class="w-4 h-4" />
        {sharingImage ? m.common_loading() : m.share_results_image()}
      </Button>
      <Button variant="secondary" size="md" onclick={copyText}>
        <ClipboardCopy class="w-4 h-4" />
        {m.share_results_text()}
      </Button>
      <ActionMenu label={m.common_more()} items={[
        { label: m.decks_download_report_json(), icon: Download, onclick: () => downloadReport("json") },
        { label: m.decks_download_report_text(), icon: Download, onclick: () => downloadReport("text") },
      ]} />
    {:else}
      <Button variant="secondary" size="md" onclick={() => onImportArchon?.()}>
        <Upload class="w-4 h-4" />
        {m.archon_import_title()}
      </Button>
    {/if}
  </div>

  <!-- Reopen: rare, semi-destructive rollback — set apart below the results -->
  <div class="pt-3 border-t border-line">
    <Button variant="ghost" size="md" disabled={actionLoading} onclick={() => doAction?.("ReopenTournament")}>
      {m.overview_reopen_tournament()}
    </Button>
  </div>
</div>
