<script module lang="ts">
  import { SvelteSet } from "svelte/reactivity";
  import type { Tournament, DeckObject } from "$lib/types";
  import { getAuthState } from "$lib/stores/auth.svelte";

  const revealedDecks = new SvelteSet<string>();

  export function isDeckBehindViewLog(deck: DeckObject, tournament: Tournament, organizer: boolean): boolean {
    return organizer
      && deck.user_uid !== (getAuthState().user?.uid ?? "")
      && tournament.state !== "Finished"
      && !revealedDecks.has(deck.uid);
  }
</script>

<script lang="ts">
  import type { TournamentEventType } from "$lib/engine";
  import DeckDisplay from "$lib/components/DeckDisplay.svelte";
  import DeckViews from "$lib/components/DeckViews.svelte";
  import Button from "$lib/components/Button.svelte";
  import { Eye } from "@lucide/svelte";
  import * as m from '$lib/paraglide/messages.js';

  let {
    deck,
    tournament,
    organizer,
    doAction,
    onreplace,
  }: {
    deck: DeckObject;
    tournament: Tournament;
    organizer: boolean;
    doAction: (action: TournamentEventType, body?: any) => Promise<string | null>;
    onreplace?: () => void;
  } = $props();

  function viewDeck() {
    revealedDecks.add(deck.uid);
    const myUid = getAuthState().user?.uid ?? "";
    if (!deck.views?.some(v => v.user_uid === myUid)) {
      doAction("ViewDeck", { player_uid: deck.user_uid, round: deck.round });
    }
  }
</script>

{#if isDeckBehindViewLog(deck, tournament, organizer)}
  <div class="space-y-2">
    <p class="text-sm text-ink-strong">{deck.name || m.decks_unnamed()}</p>
    <div class="flex flex-wrap gap-2">
      <Button variant="secondary" size="lg" onclick={viewDeck}>
        <Eye class="w-4 h-4" />
        {m.decks_view_decklist()}
      </Button>
      {#if onreplace}
        <Button variant="secondary" size="lg" onclick={onreplace}>{m.decks_replace()}</Button>
      {/if}
    </div>
    <p class="text-xs text-ink-faint">{m.decks_view_logged_hint()}</p>
  </div>
{:else}
  <DeckDisplay {deck} editable={!!onreplace} tournamentUid={tournament.uid} {organizer} multideck={!!tournament.multideck} {onreplace} />
{/if}
{#if organizer}
  <DeckViews views={deck.views ?? []} roundCount={tournament.rounds?.length ?? 0} />
{/if}
