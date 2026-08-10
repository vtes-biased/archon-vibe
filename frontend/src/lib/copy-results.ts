import type { Tournament } from "$lib/types";
import type { StandingEntry, PlayerInfoMap } from "$lib/tournament-utils";
import { generateResultsText } from "$lib/social-text";
import { showToast } from "$lib/stores/toast.svelte";
import * as m from "$lib/paraglide/messages.js";

/**
 * Copy the standings as shareable text. Two call sites reach for it — the Tools
 * sheet (organizer) and the finished player view (players post their own
 * placement) — and the clipboard-plus-toast handling is what must not drift
 * between them.
 */
export async function copyResults(
  tournament: Tournament,
  playerInfo: PlayerInfoMap,
  standings: StandingEntry[],
): Promise<void> {
  try {
    const text = await generateResultsText(tournament, playerInfo, standings);
    await navigator.clipboard.writeText(text);
    showToast({ type: "success", message: m.share_results_copied() });
  } catch {
    showToast({ type: "error", message: m.share_results_error() });
  }
}
