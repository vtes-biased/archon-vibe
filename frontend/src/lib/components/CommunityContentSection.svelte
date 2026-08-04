<script lang="ts">
  import { getCountryFlag } from "$lib/geonames";
  import { getRoleClasses } from "$lib/roles";
  import { LANGUAGE_NAMES } from "$lib/data/languages";
  import type { User, CommunityLink } from "$lib/types";
  import CommunityLinkPills from "./CommunityLinkPills.svelte";
  import CommunityModerationActions from "./CommunityModerationActions.svelte";
  import { Pin } from "@lucide/svelte";
  import * as m from '$lib/paraglide/messages.js';

  interface ContentItem {
    user: User;
    link: CommunityLink;
  }

  interface Props {
    items: ContentItem[];
    languages: string[];
    selectedLanguage: string;
    canModerate: (user: User) => boolean;
    canPromoteNational: (user: User) => boolean;
    canPromoteGlobal: boolean;
    onSelectLanguage: (lang: string) => void;
    onModerate: (userUid: string, url: string, action: string) => void;
  }
  let { items, languages, selectedLanguage, canModerate, canPromoteNational, canPromoteGlobal, onSelectLanguage, onModerate }: Props = $props();

  const scope = (link: CommunityLink) =>
    link.moderation?.status === "promoted" ? link.moderation.scope : null;
</script>

<!-- Language filter chips -->
<div class="flex flex-wrap gap-2 mb-4 overflow-x-auto">
  <button
    onclick={() => onSelectLanguage("")}
    class="px-3 py-1.5 rounded-full text-sm font-medium transition-colors whitespace-nowrap
      {selectedLanguage === '' ? 'bg-accent-strong text-white' : 'bg-surface-hover text-ink hover:bg-surface-active'}"
  >{m.community_filter_all()}</button>
  {#each languages as lang}
    <button
      onclick={() => onSelectLanguage(lang)}
      class="px-3 py-1.5 rounded-full text-sm font-medium transition-colors whitespace-nowrap
        {selectedLanguage === lang ? 'bg-accent-strong text-white' : 'bg-surface-hover text-ink hover:bg-surface-active'}"
    >{LANGUAGE_NAMES[lang] || lang}</button>
  {/each}
</div>

<!-- Content list -->
{#if items.length > 0}
  <div class="space-y-2">
    {#each items as { user, link }}
      <div class="bg-surface-card rounded-lg border border-line p-3 flex items-center gap-3">
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2 flex-wrap mb-1">
            <CommunityLinkPills links={[link]} />
          </div>
          <div class="flex items-center gap-2 text-xs text-ink-muted flex-wrap">
            {#if scope(link)}
              <span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs font-medium
                {scope(link) === 'global' ? 'badge-blue' : 'badge-amethyst'}">
                <Pin class="w-3 h-3" />
                {scope(link) === 'global' ? m.community_scope_global() : m.community_scope_national()}
              </span>
            {/if}
            {#if user.name}
              <a href="/users/{user.uid}" class="hover:text-link transition-colors">{user.name}</a>
            {/if}
            {#if user.country}
              <span>{getCountryFlag(user.country)}</span>
            {/if}
            {#each user.roles.filter(r => r === "NC" || r === "Prince" || r === "IC") as role}
              <span class="px-1.5 py-0.5 rounded text-xs font-medium {getRoleClasses(role)}">{role}</span>
            {/each}
            {#if (link.languages?.length ?? 0) > 1}
              <span class="text-ink-faint tracking-wide">{link.languages!.map(c => c.toUpperCase()).join(" · ")}</span>
            {/if}
          </div>
        </div>
        {#if canModerate(user)}
          <CommunityModerationActions
            userUid={user.uid}
            {link}
            {onModerate}
            canPromoteNational={canPromoteNational(user)}
            {canPromoteGlobal}
          />
        {/if}
      </div>
    {/each}
  </div>
{:else}
  <div class="text-center py-6 text-ink-muted text-sm">{m.community_no_content()}</div>
{/if}
