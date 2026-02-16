<script lang="ts">
  import type { Rating, RatingCategory, CategoryRating, TournamentRatingEntry } from "$lib/types";
  import { ChevronDown, Crown, Medal } from "lucide-svelte";
  import * as m from '$lib/paraglide/messages.js';

  let { rating }: { rating: Rating | undefined } = $props();

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
    allCategories.filter(c => rating?.[c] && (rating[c] as CategoryRating).total > 0)
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
</script>

{#if availableCategories.length > 0}
  <h2 class="text-lg font-semibold text-ash-200 mb-3">{m.user_detail_ratings()}</h2>
  <div class="space-y-2">
    {#each availableCategories as cat}
      {@const catRating = rating?.[cat] as CategoryRating}
      {@const isExpanded = expandedCategories.has(cat)}
      <div class="bg-dusk-950 border border-ash-800 rounded-lg overflow-hidden">
        <button
          class="w-full flex items-center justify-between px-4 py-3 hover:bg-ash-800/30 transition-colors"
          onclick={() => toggleCategory(cat)}
        >
          <span class="font-medium text-ash-200">{categoryLabelFns[cat]()}</span>
          <div class="flex items-center gap-3">
            <span class="text-lg font-bold text-crimson-400">{catRating.total}</span>
            <ChevronDown
              class="w-4 h-4 text-ash-500 transition-transform {isExpanded ? 'rotate-180' : ''}"
            />
          </div>
        </button>

        {#if isExpanded}
          {@const sorted = sortedByDate(catRating.tournaments)}
          {@const topUids = top8Uids(catRating.tournaments)}
          <div class="border-t border-ash-800 px-4 py-2">
            <table class="w-full text-sm">
              <thead>
                <tr class="text-ash-500 text-xs">
                  <th class="py-1 text-left">{m.user_detail_col_tournament()}</th>
                  <th class="py-1 text-right">{m.user_detail_col_vp()}</th>
                  <th class="py-1 text-right">{m.user_detail_col_gw()}</th>
                  <th class="py-1 text-right">{m.user_detail_col_pts()}</th>
                </tr>
              </thead>
              <tbody>
                {#each sorted as entry}
                  {@const isTop8 = topUids.has(entry.tournament_uid)}
                  <tr class="{isTop8 ? 'text-ash-200' : 'text-ash-500'}">
                    <td class="py-1">
                      <a href="/tournaments/{entry.tournament_uid}" class="hover:text-crimson-400">
                        {#if isTop8}
                          <span class="font-medium">{entry.tournament_name}</span>
                        {:else}
                          {entry.tournament_name}
                        {/if}
                      </a>
                      <span class="text-xs text-ash-500 ml-1">{entry.date}</span>
                      {#if entry.finalist_position === 1}
                        <Crown class="w-3 h-3 inline text-amber-400 ml-1" />
                      {:else if entry.finalist_position === 2}
                        <Medal class="w-3 h-3 inline text-ash-400 ml-1" />
                      {/if}
                    </td>
                    <td class="py-1 text-right">{entry.vp}</td>
                    <td class="py-1 text-right">{entry.gw}</td>
                    <td class="py-1 text-right font-medium">{entry.points}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        {/if}
      </div>
    {/each}
  </div>
{:else if rating === undefined}
  <!-- Still loading or no rating data -->
{:else}
  <p class="text-ash-500 text-sm">{m.user_detail_no_rating()}</p>
{/if}
