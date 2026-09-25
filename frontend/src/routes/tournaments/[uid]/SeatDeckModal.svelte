<script lang="ts">
  import type { Tournament, DeckObject } from "$lib/types";
  import type { TournamentEventType } from "$lib/engine";
  import { dialogPanel } from "$lib/actions/dialog";
  import Button from "$lib/components/Button.svelte";
  import OrganizerDeck from "./OrganizerDeck.svelte";
  import * as m from '$lib/paraglide/messages.js';

  let {
    deck,
    tournament,
    playerName,
    doAction,
    onClose,
  }: {
    deck: DeckObject;
    tournament: Tournament;
    playerName: string;
    doAction: (action: TournamentEventType, body?: any) => Promise<string | null>;
    onClose: () => void;
  } = $props();
</script>

<div
  class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
  role="presentation"
  onclick={(e) => { if (e.target === e.currentTarget) onClose(); }}
>
  <div
    use:dialogPanel={onClose}
    class="bg-surface-card rounded-lg shadow-xl border border-line w-full max-w-2xl mx-4 max-h-[85dvh] overflow-y-auto"
    role="dialog"
    aria-modal="true"
    aria-labelledby="seat-deck-title"
    tabindex="-1"
  >
    <div class="p-6 border-b border-line">
      <h2 id="seat-deck-title" class="text-xl font-medium text-ink-strong">{playerName}</h2>
    </div>
    <div class="p-6 space-y-4">
      <OrganizerDeck {deck} {tournament} organizer {doAction} />
      <Button variant="secondary" size="lg" block onclick={onClose}>{m.common_close()}</Button>
    </div>
  </div>
</div>
