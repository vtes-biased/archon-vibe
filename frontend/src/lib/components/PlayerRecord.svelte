<script lang="ts">
  import type { User, Tournament, DeckObject } from "$lib/types";
  import type { TournamentListItem } from "$lib/db";
  import { getTournamentListItems, getDecksByUser, getTournament } from "$lib/db";
  import { getCountryFlag } from "$lib/geonames";
  import DeckAccordion from "$lib/components/DeckAccordion.svelte";
  import DeckDisplay from "$lib/components/DeckDisplay.svelte";
  import { Trophy, TriangleAlert } from "@lucide/svelte";
  import * as m from '$lib/paraglide/messages.js';

  let { user, self = false }: { user: User | undefined; self?: boolean } = $props();

  let wins = $state<Tournament[]>([]);
  let decks = $state<{ deck: DeckObject; tournament: Tournament | undefined }[]>([]);
  let undocumented = $state<TournamentListItem[]>([]);
  let expandedDeck = $state<string | null>(null);

  function day(t: { start: string | null } | undefined): string {
    return t?.start?.slice(0, 10) ?? "";
  }

  async function load(uid: string, winUids: string[], withMissing: boolean) {
    const won = await Promise.all(winUids.map(u => getTournament(u)));
    wins = won
      .filter((t): t is Tournament => !!t)
      .sort((a, b) => day(b).localeCompare(day(a)));

    const mine = await getDecksByUser(uid);
    decks = (await Promise.all(
      mine.map(async d => ({ deck: d, tournament: await getTournament(d.tournament_uid) })),
    )).sort((a, b) => day(b.tournament).localeCompare(day(a.tournament)));

    // Not the Hall of Fame rule inverted — that is server-side and stays there.
    // This asks only "you won it and no deck of yours is on it".
    if (!withMissing) {
      undocumented = [];
      return;
    }
    const owned = new Set(mine.map(d => d.tournament_uid));
    undocumented = (await getTournamentListItems())
      .filter(t => t.winner === uid && !t.deleted_at && !owned.has(t.uid))
      .sort((a, b) => day(b).localeCompare(day(a)));
  }

  $effect(() => {
    const uid = user?.uid;
    const winUids = user?.wins ?? [];
    if (!uid) {
      wins = [];
      decks = [];
      undocumented = [];
      return;
    }
    load(uid, winUids, self);
  });
</script>

{#if wins.length}
  <section class="mt-6">
    <h2 class="text-lg font-semibold text-ink-bright mb-3">
      {m.user_detail_wins({ count: String(wins.length) })}
    </h2>
    <ul class="bg-surface-card border border-line rounded-lg divide-y divide-line">
      {#each wins as t}
        <li class="px-4 py-2 text-sm flex items-baseline gap-2">
          <Trophy class="w-3.5 h-3.5 shrink-0 text-highlight self-center" aria-hidden="true" />
          <a href="/tournaments/{t.uid}" class="text-ink-strong hover:text-link">{t.name}</a>
          <span class="text-xs text-ink-faint ml-auto whitespace-nowrap">
            {#if t.country}{getCountryFlag(t.country)}{/if}
            {day(t)}
          </span>
        </li>
      {/each}
    </ul>
  </section>
{/if}

{#if undocumented.length}
  <section class="mt-6 rounded-lg border border-accent-strong/50 bg-accent-soft/30 p-4 space-y-2">
    <p class="text-sm text-link-soft flex items-start gap-2">
      <TriangleAlert class="w-4 h-4 shrink-0 mt-0.5" aria-hidden="true" />
      {m.profile_wins_no_deck()}
    </p>
    <ul class="text-sm space-y-1">
      {#each undocumented as t}
        <li>
          <a href="/tournaments/{t.uid}" class="text-link hover:text-link-soft">{t.name}</a>
          <span class="text-xs text-ink-faint ml-1">{day(t)}</span>
        </li>
      {/each}
    </ul>
  </section>
{/if}

{#if decks.length}
  <section class="mt-6">
    <h2 class="text-lg font-semibold text-ink-bright mb-3">
      {m.user_detail_decks({ count: String(decks.length) })}
    </h2>
    <div class="space-y-2">
      {#each decks as { deck, tournament } (deck.uid)}
        {@const label = deck.name || tournament?.name || day(tournament)}
        <DeckAccordion
          expanded={expandedDeck === deck.uid}
          ontoggle={() => expandedDeck = expandedDeck === deck.uid ? null : deck.uid}
          roundLabel={label}
          bgClass="bg-surface-card border border-line"
        >
          {#snippet headerExtra()}
            <span class="text-xs text-ink-faint ml-auto whitespace-nowrap">{day(tournament)}</span>
          {/snippet}
          {#if tournament}
            <a href="/tournaments/{tournament.uid}" class="text-sm text-link hover:text-link-soft">
              {tournament.name}
            </a>
          {/if}
          <!-- No `format`: validation is read-only noise here, and a 2005 archive
               deck fails today's legality rules for reasons its player cannot act on. -->
          <DeckDisplay {deck} />
        </DeckAccordion>
      {/each}
    </div>
  </section>
{/if}
