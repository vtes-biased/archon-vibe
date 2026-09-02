<script lang="ts">
  import type { User, RatingCategory, CategoryRating, TournamentRatingEntry } from "$lib/types";
  import FoldableSection from "$lib/components/FoldableSection.svelte";
  import RankCell from "$lib/components/RankCell.svelte";
  import { getLocale } from '$lib/paraglide/runtime.js';
  import * as m from '$lib/paraglide/messages.js';

  // showHeading=false when the parent supplies its own section header (profile).
  let { user, showHeading = true }: { user: User | undefined; showHeading?: boolean } = $props();

  let expandedCategories = $state<Set<RatingCategory>>(new Set());

  const categoryLabelFns: Record<RatingCategory, () => string> = {
    constructed_offline: () => m.rankings_cat_constructed(),
    constructed_online: () => m.rankings_cat_constructed_online(),
    limited_offline: () => m.rankings_cat_limited(),
    limited_online: () => m.rankings_cat_limited_online(),
  };

  const allCategories: RatingCategory[] = [
    "constructed_offline",
    "constructed_online",
    "limited_offline",
    "limited_online",
  ];

  let availableCategories = $derived(
    allCategories.filter(c => user?.[c] && (user[c] as CategoryRating).total > 0)
  );

  function sortedByDate(entries: TournamentRatingEntry[]): TournamentRatingEntry[] {
    return [...entries].sort((a, b) => b.date.localeCompare(a.date));
  }

  function top8Uids(entries: TournamentRatingEntry[]): Set<string> {
    return new Set(entries.slice(0, 8).map(e => e.tournament_uid));
  }

  function toggleCategory(cat: RatingCategory) {
    const next = new Set(expandedCategories);
    if (next.has(cat)) next.delete(cat);
    else next.add(cat);
    expandedCategories = next;
  }

  // Rating entries age out of the ranking 18 months after the event.
  function expiryMonth(date: string): string {
    const d = new Date(date);
    d.setMonth(d.getMonth() + 18);
    return d.toLocaleDateString(getLocale(), { year: "numeric", month: "short" });
  }
</script>

{#if availableCategories.length > 0}
  {#if showHeading}
    <h2 class="text-lg font-semibold text-ink-bright mb-3">{m.user_detail_ratings()}</h2>
  {/if}
  <div class="space-y-2">
    {#each availableCategories as cat}
      {@const catRating = user?.[cat] as CategoryRating}
      {@const isExpanded = expandedCategories.has(cat)}
      <FoldableSection
        title={categoryLabelFns[cat]()}
        open={isExpanded}
        ontoggle={() => toggleCategory(cat)}
      >
        {#snippet header()}
          <span class="ml-auto text-lg font-bold text-link">{catRating.total}</span>
        {/snippet}
        {@const sorted = sortedByDate(catRating.tournaments)}
        {@const topUids = top8Uids(catRating.tournaments)}
        <table class="w-full text-sm">
          <thead>
            <tr class="text-ink-faint text-xs">
              <th class="py-1 text-left">{m.user_detail_col_tournament()}</th>
              <th class="py-1 pl-3 text-right">{m.user_detail_col_vp()}</th>
              <th class="py-1 pl-3 text-right">{m.user_detail_col_gw()}</th>
              <th class="py-1 pl-3 text-right">{m.user_detail_col_pts()}</th>
            </tr>
          </thead>
          <tbody>
            {#each sorted as entry}
              {@const isTop8 = topUids.has(entry.tournament_uid)}
              <!-- Rows written before `position` existed fall back to finalist_position (the
                   placement for a winner/finalist); non-finalists stay bare until the nightly recompute backfills them. -->
              {@const place = entry.position || entry.finalist_position}
              <tr class="{isTop8 ? 'text-ink-bright' : 'text-ink-faint'}">
                <td class="py-1">
                  <a href="/tournaments/{entry.tournament_uid}" class="hover:text-link">
                    {#if isTop8}
                      <span class="font-medium">{entry.tournament_name}</span>
                    {:else}
                      {entry.tournament_name}
                    {/if}
                  </a>
                  {#if place > 0}
                    <span class="text-xs text-ink-muted font-medium ml-1">·
                      <RankCell rank={place} finalist={entry.finalist_position > 0} hash total={entry.player_count} />
                    </span>
                  {/if}
                  <span class="text-xs text-ink-faint ml-1">· {entry.date}</span>
                  <span class="text-xs text-ink-faint ml-1">· {m.user_detail_expires({ date: expiryMonth(entry.date) })}</span>
                </td>
                <td class="py-1 pl-3 text-right">{entry.vp}</td>
                <td class="py-1 pl-3 text-right">{entry.gw}</td>
                <td class="py-1 pl-3 text-right font-medium">{entry.points}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </FoldableSection>
    {/each}
  </div>
{:else if user === undefined}
  <!-- Still loading -->
{:else}
  <p class="text-ink-faint text-sm">{m.user_detail_no_rating()}</p>
{/if}
