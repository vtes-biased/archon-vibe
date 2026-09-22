<script lang="ts">
  import type { User, Tournament, DeckObject } from "$lib/types";
  import type { TournamentListItem } from "$lib/db";
  import { getTournamentListItems, getDecksByUser, getTournament, getTournamentsNaming, getSanctionsForTournament } from "$lib/db";
  import { getAuthState } from "$lib/stores/auth.svelte";
  import { getCountryFlag } from "$lib/geonames";
  import { computeStandings, playedPlayerUids } from "$lib/tournament-utils";
  import DeckDisplay from "$lib/components/DeckDisplay.svelte";
  import RankCell from "$lib/components/RankCell.svelte";
  import { TriangleAlert, ChevronDown, ChevronRight } from "@lucide/svelte";
  import * as m from '$lib/paraglide/messages.js';

  let { user }: { user: User | undefined } = $props();

  interface PlayedEvent {
    tournament: Tournament;
    place: number | null;
    won: boolean;
    finalist: boolean;
    deck: DeckObject | undefined;
  }

  let events = $state<PlayedEvent[]>([]);
  let undocumented = $state<TournamentListItem[]>([]);
  let expandedDeck = $state<string | null>(null);
  const winCount = $derived(events.filter(e => e.won).length);
  const finalCount = $derived(events.filter(e => e.won || e.finalist).length);
  const hofWins = $derived(new Set(user?.wins ?? []));
  let viewedUid: string | undefined;

  function day(t: { start: string | null }): string {
    return t.start?.slice(0, 10) ?? "";
  }

  async function playedEvent(t: Tournament, uid: string, deck: DeckObject | undefined): Promise<PlayedEvent | null> {
    const entry = computeStandings(t, await getSanctionsForTournament(t.uid)).find(e => e.user_uid === uid);
    const played = t.rounds?.length ? playedPlayerUids(t).has(uid) : !!entry && !entry.unplaced;
    if (!played && !deck && t.winner !== uid) return null;
    const place = entry && !entry.unplaced ? entry.rank : null;
    return { tournament: t, place, won: t.winner === uid || place === 1, finalist: !!entry?.finalist, deck };
  }

  async function load(uid: string, owner: boolean) {
    const mine = await getDecksByUser(uid);
    const shown = new Map(mine
      .filter(d => owner || (d.public && (d.attribution.kind !== "Anonymous" || d.winner)))
      .map(d => [d.tournament_uid, d]));
    const named = new Map((await getTournamentsNaming(uid)).map(t => [t.uid, t]));
    for (const tuid of shown.keys()) {
      if (!named.has(tuid)) {
        const t = await getTournament(tuid);
        if (t) named.set(tuid, t);
      }
    }
    const finished = [...named.values()].filter(t => !t.deleted_at && t.state === "Finished");
    const played = await Promise.all(finished.map(t => playedEvent(t, uid, shown.get(t.uid))));
    if (uid !== viewedUid) return;
    events = played
      .filter((e): e is PlayedEvent => !!e)
      .sort((a, b) => day(b.tournament).localeCompare(day(a.tournament)));

    if (!owner) {
      undocumented = [];
      return;
    }
    const owned = new Set(mine.map(d => d.tournament_uid));
    const listed = await getTournamentListItems();
    if (uid !== viewedUid) return;
    undocumented = listed
      .filter(t => t.winner === uid && !t.deleted_at && !owned.has(t.uid))
      .sort((a, b) => day(b).localeCompare(day(a)));
  }

  $effect(() => {
    const uid = user?.uid;
    viewedUid = uid;
    if (!uid) {
      events = [];
      undocumented = [];
      return;
    }
    load(uid, getAuthState().user?.uid === uid);
  });
</script>

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

{#if events.length}
  <section class="mt-6">
    <h2 class="text-lg font-semibold text-ink-bright">
      {m.user_detail_events({ count: String(events.length) })}
    </h2>
    <p class="text-sm text-ink-muted mb-3 flex flex-wrap items-center gap-x-3 gap-y-1">
      <span class="whitespace-nowrap">{m.user_detail_wins_count({ count: String(winCount) })}</span>
      {#if hofWins.size}
        <span class="whitespace-nowrap text-[10px] px-1 py-0.5 rounded badge-highlight">{m.user_detail_hof_count({ count: String(hofWins.size) })}</span>
      {/if}
      <span class="whitespace-nowrap">{m.user_detail_finals_count({ count: String(finalCount) })}</span>
    </p>
    <ul class="bg-surface-card border border-line rounded-lg divide-y divide-line">
      {#each events as { tournament: t, place, won, finalist, deck } (t.uid)}
        {@const open = !!deck && expandedDeck === deck.uid}
        <li class="px-4 py-2 text-sm">
          <div class="flex flex-wrap items-center gap-x-2">
            {#if deck}
              <button
                type="button"
                onclick={() => expandedDeck = open ? null : deck.uid}
                aria-expanded={open}
                aria-label={m.user_detail_show_deck({ name: deck.name || t.name })}
                class="-ml-3 min-h-[44px] min-w-[44px] flex items-center justify-center shrink-0 text-ink-muted hover:text-link"
              >
                {#if open}<ChevronDown class="w-4 h-4" aria-hidden="true" />{:else}<ChevronRight class="w-4 h-4" aria-hidden="true" />{/if}
              </button>
            {/if}
            <a href="/tournaments/{t.uid}" class="min-w-0 text-ink-strong hover:text-link">{t.name}</a>
            {#if hofWins.has(t.uid)}
              <span class="shrink-0 text-[10px] px-1 py-0.5 rounded badge-highlight">{m.hof_page_title()}</span>
            {/if}
            <span class="text-xs text-ink-faint ml-auto whitespace-nowrap">
              <span class="tabular-nums text-ink-muted mr-1">{#if won}<RankCell rank={1} hash />{:else if place === null}—{:else}<RankCell rank={place} {finalist} hash />{/if}</span>
              {#if t.country}{getCountryFlag(t.country)}{/if}
              {day(t)}
            </span>
          </div>
          {#if open && deck}
            <div class="mt-3 mb-2">
              {#if deck.name}<p class="font-medium text-ink mb-2">{deck.name}</p>{/if}
              <!-- No `format`: validation is read-only noise here, and a 2005 archive
                   deck fails today's legality rules for reasons its player cannot act on. -->
              <DeckDisplay {deck} />
            </div>
          {/if}
        </li>
      {/each}
    </ul>
  </section>
{/if}
