<script lang="ts">
  import type { TournamentEventType } from "$lib/engine";
  import type { Tournament } from "$lib/types";
  import { seatDisplay as seatDisplayUtil, type StandingEntry, type PlayerInfoMap } from "$lib/tournament-utils";
  import { generateResultsCard } from "$lib/social-card";
  import { generateResultsText } from "$lib/social-text";
  import { showToast } from "$lib/stores/toast.svelte";
  import { Share2, ClipboardCopy, Download, Upload, TriangleAlert } from "@lucide/svelte";
  import Button from "$lib/components/Button.svelte";
  import ActionMenu from "$lib/components/ActionMenu.svelte";
  import RankedBadge from "./RankedBadge.svelte";
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

  function focusOnMount(node: HTMLElement) {
    node.focus();
  }

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
  let showReopenConfirm = $state(false);

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

  <!-- Unranked events: state the rule inline so a missing winner/finalist
       bonus reads as a rule, not a bug -->
  <RankedBadge {tournament} variant="note" />

  <!-- Out-of-sync explanation inline (the header badge's title= is hover-only,
       unreadable on touch — the organizer at the venue is exactly who needs it) -->
  {#if tournament.vekn_results_stale}
    <div class="banner-warn border rounded-lg p-3 text-sm flex items-start gap-2">
      <TriangleAlert class="w-4 h-4 mt-0.5 shrink-0" aria-hidden="true" />
      <span>{m.vekn_out_of_sync_hint()}</span>
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
    <Button variant="ghost" size="md" disabled={actionLoading} onclick={() => (showReopenConfirm = true)}>
      {m.overview_reopen_tournament()}
    </Button>
  </div>
</div>

{#if showReopenConfirm}
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
  <div
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
    role="presentation"
    onclick={() => (showReopenConfirm = false)}
  >
    <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
    <div
      class="bg-surface-card rounded-lg shadow-xl border border-line w-full max-w-md mx-4 max-h-[90vh] overflow-y-auto"
      onclick={(e) => e.stopPropagation()}
      onkeydown={(e) => e.key === 'Escape' && (showReopenConfirm = false)}
      role="dialog"
      aria-modal="true"
      aria-labelledby="reopen-confirm-title"
      tabindex="-1"
      use:focusOnMount
    >
      <div class="p-6 border-b border-line">
        <h2 id="reopen-confirm-title" class="text-xl font-medium text-link">{m.reopen_confirm_title()}</h2>
      </div>
      <div class="p-6">
        <p class="text-ink mb-4">{m.reopen_confirm_msg()}</p>
        {#if tournament.vekn_pushed_at}
          <!-- The VEKN results push is write-once: corrections never reach
               vekn.net via API — manual admin fixes only. -->
          <div class="banner-warn border rounded-lg p-3 mb-4 text-sm flex items-start gap-2">
            <TriangleAlert class="w-4 h-4 mt-0.5 shrink-0" aria-hidden="true" />
            <span>{m.reopen_confirm_vekn_warn()}</span>
          </div>
        {/if}
        <div class="flex gap-2">
          <Button
            variant="danger"
            size="lg"
            class="flex-1 min-h-[44px]"
            loading={actionLoading}
            onclick={async () => { await doAction?.("ReopenTournament"); showReopenConfirm = false; }}
          >
            <TriangleAlert class="w-4 h-4" aria-hidden="true" />
            {actionLoading ? m.common_loading() : m.overview_reopen_tournament()}
          </Button>
          <Button variant="secondary" size="lg" class="min-h-[44px]" disabled={actionLoading} onclick={() => (showReopenConfirm = false)}>{m.common_cancel()}</Button>
        </div>
      </div>
    </div>
  </div>
{/if}
