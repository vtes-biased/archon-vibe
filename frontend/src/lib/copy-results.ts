import type { Tournament } from "$lib/types";
import type { StandingEntry, PlayerInfoMap } from "$lib/tournament-utils";
import { generateResultsText } from "$lib/social-text";
import { showToast } from "$lib/stores/toast.svelte";
import * as m from "$lib/paraglide/messages.js";

/** Two call sites reach for this — the Tools sheet and the finished player view — and the
 * clipboard-plus-toast handling is what must not drift between them. */
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

export async function downloadResults(
  tournament: Tournament,
  playerInfo: PlayerInfoMap,
  standings: StandingEntry[],
): Promise<void> {
  try {
    const text = await generateResultsText(tournament, playerInfo, standings);
    const url = URL.createObjectURL(new Blob([text], { type: "text/plain;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `${tournament.event_code || tournament.uid}.txt`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } catch {
    showToast({ type: "error", message: m.share_results_error() });
  }
}
