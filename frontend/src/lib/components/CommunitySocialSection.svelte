<script lang="ts">
  import { getCountryFlag } from "$lib/geonames";
  import { getRoleTone, getRoleLabel } from "$lib/roles";
  import Badge from "$lib/components/Badge.svelte";
  import type { User, CommunityLink } from "$lib/types";
  import CommunityLinkPills from "./CommunityLinkPills.svelte";
  import CommunityModerationActions from "./CommunityModerationActions.svelte";
  import { ChevronDown, ChevronRight } from "@lucide/svelte";
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
    canModerate: (user: User) => boolean;
    canPromoteNational: (user: User) => boolean;
    canPromoteGlobal: boolean;
    onToggleCountry: (code: string) => void;
    onModerate: (userUid: string, url: string, action: string) => void;
  }
  let { groups, expandedCountries, userCountry, canModerate, canPromoteNational, canPromoteGlobal, onToggleCountry, onModerate }: Props = $props();
</script>

{#if groups.length > 0}
  <div class="space-y-2">
    {#each groups as group}
      {@const isExpanded = expandedCountries.has(group.code)}
      {@const isMyCountry = userCountry === group.code}
      <div class="bg-surface-card rounded-lg shadow border border-line overflow-hidden">
        <button
          onclick={() => onToggleCountry(group.code)}
          class="w-full flex items-center justify-between p-4 hover:bg-surface-muted/50 transition-colors text-left"
        >
          <div class="flex items-center gap-2">
            <span class="text-lg">{getCountryFlag(group.code)}</span>
            <span class="font-medium text-ink-strong">{group.name}</span>
            {#if isMyCountry}
              <span class="px-2 py-0.5 text-xs rounded bg-accent-soft/40 text-link">{m.community_your_country()}</span>
            {/if}
            <span class="text-xs text-ink-faint">({group.users.reduce((n, u) => n + u.links.length, 0)})</span>
          </div>
          {#if isExpanded}
            <ChevronDown class="w-5 h-5 text-ink-faint" />
          {:else}
            <ChevronRight class="w-5 h-5 text-ink-faint" />
          {/if}
        </button>

        {#if isExpanded}
          <div class="border-t border-line divide-y divide-line/50">
            {#each group.users as { user, links }}
              <div class="p-4">
                {#if user.name}
                  <div class="flex items-center gap-2 mb-2 flex-wrap">
                    <a href="/users/{user.uid}" class="font-medium text-ink-strong hover:text-link transition-colors">{user.name}</a>
                    {#each user.roles.filter(r => r === "NC" || r === "Prince" || r === "IC") as role}
                      <Badge tone={getRoleTone(role)}>{getRoleLabel(role)}</Badge>
                    {/each}
                    {#if user.city}
                      <span class="text-sm text-ink-muted">{user.city}</span>
                    {/if}
                  </div>
                {/if}
                {#if canModerate(user)}
                  <div class="flex flex-wrap gap-3">
                    {#each links as link}
                      <div class="flex flex-col items-center gap-1">
                        <CommunityLinkPills links={[link]} />
                        <CommunityModerationActions
                          userUid={user.uid}
                          {link}
                          {onModerate}
                          canPromoteNational={canPromoteNational(user)}
                          {canPromoteGlobal}
                        />
                      </div>
                    {/each}
                  </div>
                {:else}
                  <CommunityLinkPills {links} />
                {/if}
              </div>
            {/each}
          </div>
        {/if}
      </div>
    {/each}
  </div>
{/if}
