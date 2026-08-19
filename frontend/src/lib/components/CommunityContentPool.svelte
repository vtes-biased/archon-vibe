<script lang="ts">
  import Badge from "$lib/components/Badge.svelte";
  import CommunityLinkPills from "./CommunityLinkPills.svelte";
  import CommunityModerationActions from "./CommunityModerationActions.svelte";
  import { languageName } from "$lib/data/languages";
  import { getCountryFlag } from "$lib/geonames";
  import { getRoleTone, getRoleLabel } from "$lib/roles";
  import type { CommunityLink, LinkMedia, User } from "$lib/types";
  import { Plus, X } from "@lucide/svelte";
  import * as m from '$lib/paraglide/messages.js';

  interface LinkEntry { user: User; link: CommunityLink }

  interface Props {
    items: LinkEntry[];
    languages: string[];
    mediaKinds: LinkMedia[];
    selectedLanguages: string[];
    selectedMedia: LinkMedia | null;
    canModerate: (country: string | null) => boolean;
    canPromoteNational: (country: string | null) => boolean;
    canPromoteGlobal: boolean;
    linkCountry: (entry: LinkEntry) => string | null;
    onToggleLanguage: (lang: string) => void;
    onSelectMedia: (kind: LinkMedia | null) => void;
    onClearFilters: () => void;
    onModerate: (userUid: string, url: string, action: string) => void;
    onAddLink: (() => void) | null;
  }
  let {
    items, languages, mediaKinds, selectedLanguages, selectedMedia, canModerate,
    canPromoteNational, canPromoteGlobal, linkCountry, onToggleLanguage,
    onSelectMedia, onClearFilters, onModerate, onAddLink,
  }: Props = $props();

  const filtered = $derived(selectedLanguages.length > 0 || selectedMedia !== null);
  const unselectedLanguages = $derived(languages.filter(l => !selectedLanguages.includes(l)));

  const MEDIA_LABEL: Record<LinkMedia, () => string> = {
    video: m.community_media_video,
    podcast: m.community_media_podcast,
    text: m.community_media_text,
    social: m.community_media_social,
  };

  const chip = (active: boolean) =>
    `px-3 min-h-11 rounded-full text-sm font-medium transition-colors whitespace-nowrap ${
      active ? "bg-accent-strong text-white" : "bg-surface-hover text-ink hover:bg-surface-active"
    }`;
</script>

<div class="space-y-2 mb-4">
  <div class="flex flex-wrap gap-2">
    <button onclick={() => onSelectMedia(null)} class={chip(selectedMedia === null)}>{m.community_filter_all()}</button>
    {#each mediaKinds as kind}
      <button onclick={() => onSelectMedia(kind)} class={chip(selectedMedia === kind)}>{MEDIA_LABEL[kind]()}</button>
    {/each}
  </div>
  <div class="flex flex-wrap items-center gap-1.5">
    {#each selectedLanguages as code (code)}
      <span class="inline-flex items-center gap-1 pl-2 pr-1 py-1 rounded-full bg-surface-hover text-ink-bright text-xs">
        {languageName(code)}
        <button type="button" aria-label={m.profile_remove_language({ lang: languageName(code) })}
          onclick={() => onToggleLanguage(code)}
          class="grid place-items-center w-6 h-6 -m-1 rounded-full text-ink-faint hover:text-link cursor-pointer">
          <X class="w-3.5 h-3.5" />
        </button>
      </span>
    {/each}
    {#if selectedLanguages.length === 0}
      <span class="text-xs text-ink-faint">{m.community_all_languages()}</span>
    {/if}
    {#if unselectedLanguages.length > 0}
      <select value="" aria-label={m.profile_add_language()}
        onchange={(e) => { const c = e.currentTarget.value; e.currentTarget.value = ""; if (c) onToggleLanguage(c); }}
        class="px-2 py-1.5 border border-line-strong rounded bg-surface-card text-ink-muted text-xs">
        <option value="" disabled selected>+ {m.profile_add_language()}</option>
        {#each unselectedLanguages as lang}
          <option value={lang}>{languageName(lang)}</option>
        {/each}
      </select>
    {/if}
  </div>
</div>

{#if items.length > 0}
  <div class="space-y-2">
    {#each items as entry (entry.user.uid + entry.link.url)}
      {@const { user, link } = entry}
      <div class="bg-surface-card rounded-lg border border-line p-3 flex items-center gap-3">
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2 flex-wrap mb-1">
            <CommunityLinkPills links={[link]} />
          </div>
          <div class="flex items-center gap-2 text-xs text-ink-muted flex-wrap">
            {#if user.name}
              <a href="/users/{user.uid}" class="hover:text-link transition-colors">{user.name}</a>
            {/if}
            {#if linkCountry(entry)}
              <span>{getCountryFlag(linkCountry(entry)!)}</span>
            {/if}
            {#each user.roles.filter(r => r === "NC" || r === "Prince" || r === "IC") as role}
              <Badge tone={getRoleTone(role)}>{getRoleLabel(role)}</Badge>
            {/each}
            {#if (link.languages?.length ?? 0) > 1}
              <span class="text-ink-faint tracking-wide">{link.languages!.map(c => c.toUpperCase()).join(" · ")}</span>
            {/if}
          </div>
        </div>
        {#if canModerate(linkCountry(entry))}
          <CommunityModerationActions
            userUid={user.uid}
            {link}
            {onModerate}
            canPromoteNational={canPromoteNational(linkCountry(entry))}
            {canPromoteGlobal}
          />
        {/if}
      </div>
    {/each}
  </div>
{:else if filtered}
  <div class="text-center py-6 text-ink-muted text-sm space-y-2">
    <p>{m.community_no_content_filtered()}</p>
    <button type="button" onclick={onClearFilters} class="min-h-11 text-link hover:text-link-soft transition-colors">
      {m.filters_clear()}
    </button>
  </div>
{:else}
  <div class="text-center py-6 text-ink-muted text-sm">{m.community_no_content()}</div>
{/if}

{#if onAddLink}
  <button type="button" onclick={onAddLink}
    class="mt-3 flex items-center gap-1 min-h-11 text-sm text-link hover:text-link-soft transition-colors">
    <Plus class="w-4 h-4" />
    {m.community_add_link()}
  </button>
{/if}
