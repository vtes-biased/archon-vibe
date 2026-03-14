<script lang="ts">
  import { getCountryFlag } from "$lib/geonames";
  import { getRoleClasses } from "$lib/roles";
  import type { User, CommunityLink } from "$lib/types";
  import CommunityLinkPills from "./CommunityLinkPills.svelte";
  import CommunityModerationActions from "./CommunityModerationActions.svelte";
  import { ChevronDown, ChevronRight } from "lucide-svelte";
  import * as m from '$lib/paraglide/messages.js';

  interface CountryGroup {
    code: string;
    name: string;
    users: { user: User; links: CommunityLink[] }[];
  }

  interface Props {
    groups: CountryGroup[];
    expandedCountries: Set<string>;
    userCountry: string | null;
    isModerator: boolean;
    onToggleCountry: (code: string) => void;
    onModerate: (userUid: string, url: string, action: string) => void;
  }
  let { groups, expandedCountries, userCountry, isModerator, onToggleCountry, onModerate }: Props = $props();
</script>

{#if groups.length > 0}
  <div class="space-y-2">
    {#each groups as group}
      {@const isExpanded = expandedCountries.has(group.code)}
      {@const isMyCountry = userCountry === group.code}
      <div class="bg-dusk-950 rounded-lg shadow border border-ash-800 overflow-hidden">
        <button
          onclick={() => onToggleCountry(group.code)}
          class="w-full flex items-center justify-between p-4 hover:bg-ash-900/50 transition-colors text-left"
        >
          <div class="flex items-center gap-2">
            <span class="text-lg">{getCountryFlag(group.code)}</span>
            <span class="font-medium text-bone-100">{group.name}</span>
            {#if isMyCountry}
              <span class="px-2 py-0.5 text-xs rounded bg-crimson-900/40 text-crimson-400">{m.community_your_country()}</span>
            {/if}
            <span class="text-xs text-ash-500">({group.users.reduce((n, u) => n + u.links.length, 0)})</span>
          </div>
          {#if isExpanded}
            <ChevronDown class="w-5 h-5 text-ash-500" />
          {:else}
            <ChevronRight class="w-5 h-5 text-ash-500" />
          {/if}
        </button>

        {#if isExpanded}
          <div class="border-t border-ash-800 divide-y divide-ash-800/50">
            {#each group.users as { user, links }}
              <div class="p-4">
                {#if user.name}
                  <div class="flex items-center gap-2 mb-2 flex-wrap">
                    <a href="/users/{user.uid}" class="font-medium text-bone-100 hover:text-crimson-400 transition-colors">{user.name}</a>
                    {#each user.roles.filter(r => r === "NC" || r === "Prince" || r === "IC") as role}
                      <span class="px-2 py-0.5 rounded text-xs font-medium {getRoleClasses(role)}">{role}</span>
                    {/each}
                    {#if user.city}
                      <span class="text-sm text-ash-400">{user.city}</span>
                    {/if}
                  </div>
                {/if}
                <CommunityLinkPills {links} />
                {#if isModerator}
                  <CommunityModerationActions userUid={user.uid} {links} {onModerate} />
                {/if}
              </div>
            {/each}
          </div>
        {/if}
      </div>
    {/each}
  </div>
{/if}
