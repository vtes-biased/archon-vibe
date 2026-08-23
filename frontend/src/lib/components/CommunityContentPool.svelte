<script lang="ts">
  import CommunityLinkPills from "./CommunityLinkPills.svelte";
  import { LANGUAGE_NAMES } from "$lib/data/languages";
  import type { CommunityLink, LinkMedia } from "$lib/types";
  import type { UserListItem } from "$lib/db";
  import { Pencil, X } from "@lucide/svelte";
  import * as m from '$lib/paraglide/messages.js';

  interface LinkEntry { user: UserListItem; link: CommunityLink }

  interface Props {
    items: LinkEntry[];
    languages: string[];
    mediaKinds: LinkMedia[];
    selectedLanguages: string[];
    selectedMedia: LinkMedia | null;
    canEdit: (entry: LinkEntry) => boolean;
    onToggleLanguage: (lang: string) => void;
    onSelectMedia: (kind: LinkMedia | null) => void;
    onClearFilters: () => void;
    onEdit: (entry: LinkEntry) => void;
  }
  let {
    items, languages, mediaKinds, selectedLanguages, selectedMedia, canEdit,
    onToggleLanguage, onSelectMedia, onClearFilters, onEdit,
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
        {LANGUAGE_NAMES[code] ?? code}
        <button type="button" aria-label={m.profile_remove_language({ lang: LANGUAGE_NAMES[code] ?? code })}
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
          <option value={lang}>{LANGUAGE_NAMES[lang] || lang}</option>
        {/each}
      </select>
    {/if}
  </div>
</div>

{#if items.length > 0}
  <div class="space-y-2">
    {#each items as entry (entry.user.uid + entry.link.url)}
      <div class="bg-surface-card rounded-lg border border-line p-2 flex items-center gap-2">
        <div class="flex-1 min-w-0">
          <CommunityLinkPills links={[entry.link]} />
        </div>
        {#if canEdit(entry)}
          <button type="button" onclick={() => onEdit(entry)}
            aria-label={m.community_edit_link()}
            class="grid place-items-center w-11 h-11 shrink-0 text-ink-faint hover:text-link transition-colors">
            <Pencil class="w-4 h-4" />
          </button>
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
