<script lang="ts">
  import type { User, RatingCategory, CategoryRating, TournamentRatingEntry } from "$lib/types";
  import { ChevronDown, Crown, Medal } from "@lucide/svelte";
  import * as m from '$lib/paraglide/messages.js';

  let { user }: { user: User | undefined } = $props();

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
</script>

{#if availableCategories.length > 0}
  <h2 class="text-lg font-semibold text-ink-bright mb-3">{m.user_detail_ratings()}</h2>
  <div class="space-y-2">
    {#each availableCategories as cat}
      {@const catRating = user?.[cat] as CategoryRating}
      {@const isExpanded = expandedCategories.has(cat)}
      <div class="bg-surface-card border border-line rounded-lg overflow-hidden">
        <button
          class="w-full flex items-center justify-between px-4 py-3 hover:bg-surface-hover/30 transition-colors"
          onclick={() => toggleCategory(cat)}
        >
          <span class="font-medium text-ink-bright">{categoryLabelFns[cat]()}</span>
          <div class="flex items-center gap-3">
            <span class="text-lg font-bold text-link">{catRating.total}</span>
            <ChevronDown
              class="w-4 h-4 text-ink-faint transition-transform {isExpanded ? 'rotate-180' : ''}"
            />
          </div>
        </button>

        {#if isExpanded}
          {@const sorted = sortedByDate(catRating.tournaments)}
          {@const topUids = top8Uids(catRating.tournaments)}
          <div class="border-t border-line px-4 py-2">
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
                  <tr class="{isTop8 ? 'text-ink-bright' : 'text-ink-faint'}">
                    <td class="py-1">
                      <a href="/tournaments/{entry.tournament_uid}" class="hover:text-link">
                        {#if isTop8}
                          <span class="font-medium">{entry.tournament_name}</span>
                        {:else}
                          {entry.tournament_name}
                        {/if}
                      </a>
                      <span class="text-xs text-ink-faint ml-1">{entry.date}</span>
                      {#if entry.finalist_position === 1}
                        <Crown class="w-3 h-3 inline text-highlight ml-1" />
                      {:else if entry.finalist_position === 2}
                        <Medal class="w-3 h-3 inline text-ink-muted ml-1" />
                      {/if}
                    </td>
                    <td class="py-1 pl-3 text-right">{entry.vp}</td>
                    <td class="py-1 pl-3 text-right">{entry.gw}</td>
                    <td class="py-1 pl-3 text-right font-medium">{entry.points}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        {/if}
      </div>
    {/each}
  </div>
{:else if user === undefined}
  <!-- Still loading -->
{:else}
  <p class="text-ink-faint text-sm">{m.user_detail_no_rating()}</p>
{/if}
