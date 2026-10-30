<script lang="ts">
  import type { User, Tournament, DeckObject, RatingCategory } from "$lib/types";
  import type { TournamentListItem } from "$lib/db";
  import { getTournamentListItems, getDecksByUser, getTournament, getTournamentsNaming, getSanctionsForTournament } from "$lib/db";
  import { getAuthState } from "$lib/stores/auth.svelte";
  import { getCountryFlag } from "$lib/geonames";
  import { computeStandings, eighteenMonthsAgo, playedPlayerUids, getStateTone, translateTournamentState, RATING_CATEGORIES, ratingCategoryLabel } from "$lib/tournament-utils";
  import { attestedPlayerCount, playerGameRecord, ratingCategory } from "$lib/engine";
  import type { PlayerGameRecord } from "$lib/engine";
  import DeckDisplay from "$lib/components/DeckDisplay.svelte";
  import RankCell from "$lib/components/RankCell.svelte";
  import Badge from "$lib/components/Badge.svelte";
  import { TriangleAlert, ChevronDown, ChevronRight } from "@lucide/svelte";
  import { getLocale } from '$lib/paraglide/runtime.js';
  import * as m from '$lib/paraglide/messages.js';

  let { user }: { user: User | undefined } = $props();

  interface PlayedEvent {
    tournament: Tournament;
    place: number | null;
    field: number | undefined;
    won: boolean;
    finalist: boolean;
    deck: DeckObject | undefined;
    category: RatingCategory;
    games: PlayerGameRecord;
  }

  let events = $state<PlayedEvent[]>([]);
  let undocumented = $state<TournamentListItem[]>([]);
  let organised = $state<TournamentListItem[]>([]);
  let expandedDeck = $state<string | null>(null);
  let category = $state<RatingCategory | "">("");
  let recentOnly = $state(false);
  const categories = $derived(RATING_CATEGORIES.filter(c => events.some(e => e.category === c)));
  const windowStart = $derived(recentOnly ? eighteenMonthsAgo() : "");
  const shown = $derived(events.filter(e => (!category || e.category === category) && eventDay(e.tournament) >= windowStart));
  const winCount = $derived(shown.filter(e => e.won).length);
  const finalCount = $derived(shown.filter(e => e.won || e.finalist).length);
  const hofWins = $derived(new Set(user?.wins ?? []));
  const hofCount = $derived(shown.filter(e => hofWins.has(e.tournament.uid)).length);
  const counted = $derived(shown.filter(e => !e.games.left_out));
  const gameCount = $derived(counted.reduce((sum, e) => sum + e.games.games, 0));
  const leftOutCount = $derived(shown.filter(e => e.games.left_out === "withdrawn").length);
  const unknownRoundsCount = $derived(shown.filter(e => e.games.left_out === "unknown_rounds").length);
  let viewedUid: string | undefined;

  function day(t: { start: string | null }): string {
    return t.start?.slice(0, 10) ?? "";
  }

  function eventDay(t: Tournament): string {
    return (t.finish ?? t.start)?.slice(0, 10) ?? "";
  }

  function perGame(total: number): string {
    return gameCount ? (total / gameCount).toLocaleString(getLocale(), { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : "—";
  }

  async function playedEvent(t: Tournament, uid: string, deck: DeckObject | undefined): Promise<PlayedEvent | null> {
    const sanctions = await getSanctionsForTournament(t.uid);
    const entry = computeStandings(t, sanctions).find(e => e.user_uid === uid);
    const played = t.rounds?.length ? playedPlayerUids(t).has(uid) : !!entry && !entry.unplaced;
    if (!played && !deck && t.winner !== uid) return null;
    const place = entry && !entry.unplaced ? entry.rank : null;
    return { tournament: t, place, field: attestedPlayerCount(t) || undefined, won: t.winner === uid || place === 1, finalist: !!entry?.finalist, deck, category: ratingCategory(t.format, t.online), games: playerGameRecord(t, sanctions, uid) };
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
    category = "";
    events = played
      .filter((e): e is PlayedEvent => !!e)
      .sort((a, b) => day(b.tournament).localeCompare(day(a.tournament)));

    const listed = await getTournamentListItems();
    if (uid !== viewedUid) return;
    organised = listed
      .filter(t => !t.deleted_at && t.organizers_uids?.includes(uid))
      .sort((a, b) => (b.start ?? b.modified).localeCompare(a.start ?? a.modified));

    if (!owner) {
      undocumented = [];
      return;
    }
    const owned = new Set(mine.map(d => d.tournament_uid));
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
      organised = [];
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
      {m.user_detail_events({ count: String(shown.length) })}
    </h2>
    <div class="flex flex-wrap items-center gap-3 my-2 text-sm">
      <select bind:value={category} aria-label={m.user_detail_filter_category()} class="bg-surface-card border border-line rounded-lg px-3 py-2 text-sm text-ink-bright min-h-[44px]">
        <option value="">{m.user_detail_filter_all_categories()}</option>
        {#each categories as c}
          <option value={c}>{ratingCategoryLabel(c)}</option>
        {/each}
      </select>
      <label class="flex items-center gap-2 text-ink-muted min-h-[44px]">
        <input type="checkbox" bind:checked={recentOnly} />
        {m.user_detail_filter_18_months()}
      </label>
    </div>
    <p class="text-sm text-ink-muted flex flex-wrap items-center gap-x-3 gap-y-1">
      <span class="whitespace-nowrap">{m.user_detail_wins_count({ count: String(winCount) })}</span>
      {#if hofCount}
        <span class="whitespace-nowrap text-[10px] px-1 py-0.5 rounded badge-highlight">{m.user_detail_hof_count({ count: String(hofCount) })}</span>
      {/if}
      <span class="whitespace-nowrap">{m.user_detail_finals_count({ count: String(finalCount) })}</span>
      {#if shown.length}
        <span class="whitespace-nowrap">{m.user_detail_win_rate({ rate: String(Math.round(winCount / shown.length * 100)) })}</span>
      {/if}
      <span class="whitespace-nowrap">{m.user_detail_gw_per_game({ value: perGame(counted.reduce((sum, e) => sum + e.games.gw, 0)) })}</span>
      <span class="whitespace-nowrap">{m.user_detail_vp_per_game({ value: perGame(counted.reduce((sum, e) => sum + e.games.vp, 0)) })}</span>
    </p>
    {#if leftOutCount || unknownRoundsCount}
      <p class="text-xs text-ink-faint mt-1">
        {#if leftOutCount}{m.user_detail_left_out_withdrawn({ count: String(leftOutCount) })}{/if}
        {#if unknownRoundsCount}{m.user_detail_left_out_unknown_rounds({ count: String(unknownRoundsCount) })}{/if}
      </p>
    {/if}
    <ul class="mt-3 bg-surface-card border border-line rounded-lg divide-y divide-line">
      {#each shown as { tournament: t, place, field, won, finalist, deck } (t.uid)}
        {@const open = !!deck && expandedDeck === deck.uid}
        <li class="px-4 py-2 text-sm">
          <div class="flex flex-wrap items-center gap-x-2">
            {#if deck}
              <button
                type="button"
                onclick={() => expandedDeck = open ? null : deck.uid}
                aria-expanded={open}
                aria-label={m.user_detail_show_deck({ name: deck.name || t.name })}
                class="-ml-3 -my-2 min-h-[44px] w-8 flex items-center justify-center shrink-0 text-ink-muted hover:text-link"
              >
                {#if open}<ChevronDown class="w-4 h-4" aria-hidden="true" />{:else}<ChevronRight class="w-4 h-4" aria-hidden="true" />{/if}
              </button>
            {:else}
              <span class="-ml-3 w-8 shrink-0" aria-hidden="true"></span>
            {/if}
            <a href="/tournaments/{t.uid}" class="min-w-0 text-ink-strong hover:text-link">{t.name}</a>
            {#if hofWins.has(t.uid)}
              <span class="shrink-0 text-[10px] px-1 py-0.5 rounded badge-highlight">{m.hof_page_title()}</span>
            {/if}
            <span class="text-xs text-ink-faint ml-auto whitespace-nowrap">
              <span class="tabular-nums text-ink-muted mr-1">{#if won}<RankCell rank={1} hash total={field} />{:else if place === null}—{:else}<RankCell rank={place} {finalist} hash total={field} />{/if}</span>
              {#if t.country}{getCountryFlag(t.country)}{/if}
              {day(t)}
            </span>
          </div>
          {#if open && deck}
            <div class="mt-3 mb-2">
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

{#if organised.length}
  <section class="mt-6">
    <h2 class="text-lg font-semibold text-ink-bright mb-3">
      {m.user_detail_organised({ count: String(organised.length) })}
    </h2>
    <ul class="bg-surface-card border border-line rounded-lg divide-y divide-line">
      {#each organised as t (t.uid)}
        <li class="px-4 py-2 text-sm flex flex-wrap items-center gap-x-2">
          <a href="/tournaments/{t.uid}" class="min-w-0 text-ink-strong hover:text-link">{t.name}</a>
          {#if t.state !== "Finished"}
            <Badge kind="status" tone={getStateTone(t.state)}>{translateTournamentState(t.state)}</Badge>
          {/if}
          <span class="text-xs text-ink-faint ml-auto whitespace-nowrap">
            {#if t.country}{getCountryFlag(t.country)}{/if}
            {day(t)}
          </span>
        </li>
      {/each}
    </ul>
  </section>
{/if}
