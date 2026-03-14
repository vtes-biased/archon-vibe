<script lang="ts">
  import { getCountryFlag } from "$lib/geonames";
  import { getRoleClasses } from "$lib/roles";
  import type { User, CommunityLink } from "$lib/types";
  import CommunityLinkPills from "./CommunityLinkPills.svelte";
  import CommunityModerationActions from "./CommunityModerationActions.svelte";
  import * as m from '$lib/paraglide/messages.js';

  interface ContentItem {
    user: User;
    link: CommunityLink;
  }

  interface Props {
    items: ContentItem[];
    languages: string[];
    selectedLanguage: string;
    isModerator: boolean;
    onSelectLanguage: (lang: string) => void;
    onModerate: (userUid: string, url: string, action: string) => void;
  }
  let { items, languages, selectedLanguage, isModerator, onSelectLanguage, onModerate }: Props = $props();

  const LANGUAGE_NAMES: Record<string, string> = {
    en: "English", es: "Español", fr: "Français", pt: "Português", it: "Italiano",
    de: "Deutsch", pl: "Polski", fi: "Suomi", sv: "Svenska", nl: "Nederlands",
    ja: "日本語", zh: "中文", ko: "한국어", ru: "Русский", cs: "Čeština",
    hu: "Magyar", ro: "Română", bg: "Български", hr: "Hrvatski", el: "Ελληνικά",
    tr: "Türkçe", ar: "العربية", th: "ไทย", vi: "Tiếng Việt",
  };
</script>

<!-- Language filter chips -->
<div class="flex flex-wrap gap-2 mb-4 overflow-x-auto">
  <button
    onclick={() => onSelectLanguage("")}
    class="px-3 py-1.5 rounded-full text-sm font-medium transition-colors whitespace-nowrap
      {selectedLanguage === '' ? 'bg-crimson-700 text-white' : 'bg-ash-800 text-ash-300 hover:bg-ash-700'}"
  >{m.community_filter_all()}</button>
  {#each languages as lang}
    <button
      onclick={() => onSelectLanguage(lang)}
      class="px-3 py-1.5 rounded-full text-sm font-medium transition-colors whitespace-nowrap
        {selectedLanguage === lang ? 'bg-crimson-700 text-white' : 'bg-ash-800 text-ash-300 hover:bg-ash-700'}"
    >{LANGUAGE_NAMES[lang] || lang}</button>
  {/each}
</div>

<!-- Content list -->
{#if items.length > 0}
  <div class="space-y-2">
    {#each items as { user, link }}
      <div class="bg-dusk-950 rounded-lg border border-ash-800 p-3 flex items-center gap-3">
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2 flex-wrap mb-1">
            <CommunityLinkPills links={[link]} />
          </div>
          <div class="flex items-center gap-2 text-xs text-ash-400 flex-wrap">
            {#if user.name}
              <a href="/users/{user.uid}" class="hover:text-crimson-400 transition-colors">{user.name}</a>
            {/if}
            {#if user.country}
              <span>{getCountryFlag(user.country)}</span>
            {/if}
            {#each user.roles.filter(r => r === "NC" || r === "Prince" || r === "IC") as role}
              <span class="px-1.5 py-0.5 rounded text-xs font-medium {getRoleClasses(role)}">{role}</span>
            {/each}
            {#if link.moderation?.status === "promoted"}
              <span class="text-amber-400 text-xs">★</span>
            {/if}
          </div>
        </div>
        {#if isModerator}
          <CommunityModerationActions userUid={user.uid} links={[link]} {onModerate} />
        {/if}
      </div>
    {/each}
  </div>
{:else}
  <div class="text-center py-6 text-ash-400 text-sm">{m.community_no_content()}</div>
{/if}
