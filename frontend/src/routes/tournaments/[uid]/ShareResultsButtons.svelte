<script lang="ts">
  import type { Tournament } from "$lib/types";
  import type { StandingEntry, PlayerInfoMap } from "$lib/tournament-utils";
  import { generateResultsCard } from "$lib/social-card";
  import { generateResultsText } from "$lib/social-text";
  import { showToast } from "$lib/stores/toast.svelte";
  import { Share2, ClipboardCopy } from "@lucide/svelte";
  import Button from "$lib/components/Button.svelte";
  import * as m from "$lib/paraglide/messages.js";

  // Share-image + copy-text pair, shared by the organizer FinishedResults view
  // and the finished player view (players are the ones posting their placement).
  let {
    tournament,
    playerInfo,
    standings,
  }: {
    tournament: Tournament;
    playerInfo: PlayerInfoMap;
    standings: StandingEntry[];
  } = $props();

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

<Button variant="secondary" size="md" loading={sharingImage} onclick={shareImage}>
  <Share2 class="w-4 h-4" />
  {sharingImage ? m.common_loading() : m.share_results_image()}
</Button>
<Button variant="secondary" size="md" onclick={copyText}>
  <ClipboardCopy class="w-4 h-4" />
  {m.share_results_text()}
</Button>
