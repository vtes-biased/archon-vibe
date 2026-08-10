<script lang="ts">
  import type { Tournament } from "$lib/types";
  import type { StandingEntry, PlayerInfoMap } from "$lib/tournament-utils";
  import { copyResults } from "$lib/copy-results";
  import { ClipboardCopy } from "@lucide/svelte";
  import Button from "$lib/components/Button.svelte";
  import * as m from "$lib/paraglide/messages.js";

  // The generated results IMAGE that used to sit beside this is gone: sharing
  // the tournament link already renders a proper cover, because backend/src/og.py
  // serves a per-tournament og:image built from the banner. Organizers copy from
  // the Tools sheet; this is the player-facing button.
  let {
    tournament,
    playerInfo,
    standings,
  }: {
    tournament: Tournament;
    playerInfo: PlayerInfoMap;
    standings: StandingEntry[];
  } = $props();
</script>

<Button variant="secondary" size="md" onclick={() => copyResults(tournament, playerInfo, standings)}>
  <ClipboardCopy class="w-4 h-4" />
  {m.share_results_text()}
</Button>
