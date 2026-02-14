<script lang="ts">
  import { page } from "$app/stores";
  import { getUser, getRatingByUserUid } from "$lib/db";
  import { syncManager } from "$lib/sync";
  import { getCountryFlag, getCountry } from "$lib/geonames";
  import type { User, Rating, RatingCategory, CategoryRating } from "$lib/types";
  import Icon from "@iconify/svelte";
  import * as m from '$lib/paraglide/messages.js';

  let user = $state<User | undefined>();
  let rating = $state<Rating | undefined>();
  let expandedCategories = $state<Set<RatingCategory>>(new Set());

  const uid = $derived($page.params.uid);

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

  function toggleCategory(cat: RatingCategory) {
    const next = new Set(expandedCategories);
    if (next.has(cat)) next.delete(cat);
    else next.add(cat);
    expandedCategories = next;
  }

  async function loadData() {
    if (!uid) return;
    user = await getUser(uid);
    rating = await getRatingByUserUid(uid);
  }

  $effect(() => {
    uid; // reactive dependency
    loadData();

    const handleSync = (event: { type: string }) => {
      if (event.type === "user" || event.type === "rating" || event.type === "sync_complete") {
        loadData();
      }
    };
    syncManager.addEventListener(handleSync);
    return () => syncManager.removeEventListener(handleSync);
  });
</script>

<svelte:head>
  <title>{user?.name ?? m.user_detail_fallback_title()} - Archon</title>
</svelte:head>

<div class="max-w-3xl mx-auto px-4 py-6">
  {#if !user}
    <div class="text-center text-ash-400 py-8">
      <Icon icon="lucide:loader-2" class="w-6 h-6 animate-spin inline-block" />
      <span class="ml-2">{m.common_loading()}</span>
    </div>
  {:else}
    <!-- User header -->
    <div class="bg-dusk-950 rounded-lg p-4 mb-6 border border-ash-800">
      <h1 class="text-xl font-bold text-ash-100">{user.name}</h1>
      <div class="flex flex-wrap gap-x-4 gap-y-1 mt-2 text-sm text-ash-400">
        {#if user.nickname}
          <span>"{user.nickname}"</span>
        {/if}
        {#if user.vekn_id}
          <span>{m.user_detail_vekn({ id: user.vekn_id })}</span>
        {/if}
        {#if user.country}
          <span>{getCountryFlag(user.country)} {getCountry(user.country)?.name ?? user.country}</span>
        {/if}
      </div>
      {#if user.roles.length > 0}
        <div class="flex flex-wrap gap-1 mt-2">
          {#each user.roles as role}
            <span class="px-2 py-0.5 rounded text-xs font-medium bg-ash-800 text-ash-300">{role}</span>
          {/each}
        </div>
      {/if}
    </div>

    <!-- Ratings -->
    {#if availableCategories.length > 0}
      <h2 class="text-lg font-semibold text-ash-200 mb-3">{m.user_detail_ratings()}</h2>
      <div class="space-y-2">
        {#each availableCategories as cat}
          {@const catRating = rating?.[cat] as CategoryRating}
          {@const isExpanded = expandedCategories.has(cat)}
          <div class="bg-dusk-950 border border-ash-800 rounded-lg overflow-hidden">
            <!-- Category header (clickable) -->
            <button
              class="w-full flex items-center justify-between px-4 py-3 hover:bg-ash-800/30 transition-colors"
              onclick={() => toggleCategory(cat)}
            >
              <span class="font-medium text-ash-200">{categoryLabelFns[cat]()}</span>
              <div class="flex items-center gap-3">
                <span class="text-lg font-bold text-crimson-400">{catRating.total}</span>
                <Icon
                  icon="lucide:chevron-down"
                  class="w-4 h-4 text-ash-500 transition-transform {isExpanded ? 'rotate-180' : ''}"
                />
              </div>
            </button>

            <!-- Tournament list (foldable) -->
            {#if isExpanded}
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
                    {#each catRating.tournaments as entry, i}
                      {@const isTop8 = i < 8}
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
                            <Icon icon="lucide:crown" class="w-3 h-3 inline text-amber-400 ml-1" />
                          {:else if entry.finalist_position === 2}
                            <Icon icon="lucide:medal" class="w-3 h-3 inline text-ash-400 ml-1" />
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
  {/if}
</div>
