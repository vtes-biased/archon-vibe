<script lang="ts">
  import type { Tournament } from "$lib/types";
  import { seatDisplay as seatDisplayUtil, type StandingEntry, type PlayerInfoMap } from "$lib/tournament-utils";
  import { Upload, TriangleAlert, BookMarked, ExternalLink } from "@lucide/svelte";
  import InlineNotice from "$lib/components/InlineNotice.svelte";
  import Button from "$lib/components/Button.svelte";
  import RankedBadge from "./RankedBadge.svelte";
  import * as m from '$lib/paraglide/messages.js';

  // Organizer-only Finished-state panel: winner, deck nudge, sync/TWDA outcome.
  let {
    tournament,
    playerInfo,
    standings,
    winnerHasDeck = false,
    onImportArchon,
  }: {
    tournament: Tournament;
    playerInfo: PlayerInfoMap;
    standings: StandingEntry[];
    winnerHasDeck?: boolean;
    onImportArchon?: () => void;
  } = $props();

  function seatDisplay(uid: string): string {
    return seatDisplayUtil(uid, playerInfo, tournament.online);
  }

  const hasStandings = $derived(standings.length > 0);

  function twdaSkipReason(code: string): string {
    switch (code) {
      case "no_winner": return m.twda_reason_no_winner();
      case "limited": return m.twda_reason_limited();
      case "unranked":
      case "unsanctioned": // legacy stored reason from the pre-fix rank gate
        return m.twda_reason_unranked();
      case "too_few_players": return m.twda_reason_too_few_players();
      case "no_vekn_event": return m.twda_reason_no_vekn_event();
      case "not_configured": return m.twda_reason_not_configured();
      case "no_deck": return m.twda_reason_no_deck();
      default: return code;
    }
  }
</script>

<div class="space-y-3">
  {#if tournament.winner}
    <div class="banner-highlight border rounded-lg p-4">
      <div class="text-ink-faint text-sm">{m.tournament_winner()}</div>
      <div class="text-xl font-medium text-ink-strong">{seatDisplay(tournament.winner)}</div>
    </div>
  {/if}

  <!-- Every line below is one InlineNotice: tone splits by what's owed (warn)
       vs what merely happened (info). -->

  {#if tournament.winner && !winnerHasDeck}
    <InlineNotice tone="warn" icon={TriangleAlert}>
      {m.decks_winner_nudge_organizer({ name: seatDisplay(tournament.winner) })}
    </InlineNotice>
  {/if}

  <!-- Unranked events: state the reason inline so a missing winner/finalist
       bonus reads as a rule, not a bug -->
  <RankedBadge {tournament} variant="note" />

  <!-- Out-of-sync explanation inline (the header badge's title= is hover-only,
       unreadable on touch — the organizer at the venue is exactly who needs it) -->
  {#if tournament.vekn_results_stale}
    <InlineNotice tone="warn" icon={TriangleAlert}>{m.vekn_out_of_sync_hint()}</InlineNotice>
  {/if}

  <!-- TWDA outcome: the auto-submission is otherwise invisible — tell the
       organizer what happened to the winner's deck (and why, when skipped) -->
  {#if tournament.twda_status}
    {@const ts = tournament.twda_status}
    {#if ts.outcome === "submitted"}
      <InlineNotice icon={BookMarked}>
        {m.twda_status_submitted()}
        {#if ts.pr_url}
          <a href={ts.pr_url} target="_blank" rel="noopener noreferrer" class="inline-flex items-center gap-1 text-link underline">{m.twda_status_view_submission()}<ExternalLink class="w-3 h-3" aria-hidden="true" /></a>
        {/if}
      </InlineNotice>
    {:else if ts.outcome === "failed"}
      <InlineNotice tone="warn" icon={TriangleAlert}>{m.twda_status_failed()}</InlineNotice>
    {:else if ts.outcome === "skipped"}
      <InlineNotice>{m.twda_status_skipped({ reason: twdaSkipReason(ts.reason) })}</InlineNotice>
    {/if}
  {/if}

  <!-- This panel states the result; other actions (copy, export, promos, reopen)
       live in the Tools sheet. Import is the exception, shown only when there's
       nothing yet to state. -->
  {#if !hasStandings}
    <div>
      <Button variant="secondary" size="md" onclick={() => onImportArchon?.()}>
        <Upload class="w-4 h-4" />
        {m.archon_import_title()}
      </Button>
    </div>
  {/if}
</div>
