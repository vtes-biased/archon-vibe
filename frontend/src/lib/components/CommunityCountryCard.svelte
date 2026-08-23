<script lang="ts">
  import Badge from "$lib/components/Badge.svelte";
  import CommunityLinkPills from "./CommunityLinkPills.svelte";
  import DiscordContact from "./DiscordContact.svelte";
  import { deobfuscateContact } from "$lib/contact";
  import { getCountryFlag } from "$lib/geonames";
  import { getRoleTone } from "$lib/roles";
  import type { CommunityLink } from "$lib/types";
  import type { UserListItem } from "$lib/db";
  import { ChevronDown, ChevronRight, Pencil } from "@lucide/svelte";
  import * as m from '$lib/paraglide/messages.js';

  interface LinkEntry { user: UserListItem; link: CommunityLink }

  interface Props {
    code: string;
    name: string;
    pinned: LinkEntry[];
    groups: LinkEntry[];
    officials: UserListItem[];
    isOwnCountry: boolean;
    expanded: boolean;
    showLinks: boolean;
    showOfficials: boolean;
    canPromoteNational: boolean;
    canEdit: (entry: LinkEntry) => boolean;
    onToggle: () => void;
    onEdit: (entry: LinkEntry) => void;
  }
  let {
    code, name, pinned, groups, officials, isOwnCountry, expanded, showLinks,
    showOfficials, canPromoteNational, canEdit,
    onToggle, onEdit,
  }: Props = $props();

  const count = $derived(
    (showLinks ? pinned.length + groups.length : 0) + (showOfficials ? officials.length : 0)
  );
  const curatorPrompt = $derived(showLinks && canPromoteNational && pinned.length === 0 && groups.length === 0);

  const coordinators = $derived(officials.filter(o => o.roles?.includes("NC")));
  const princes = $derived(officials.filter(o => !o.roles?.includes("NC")));
  let princesOpen = $state(false);
</script>

{#snippet officialRow(official: UserListItem)}
  {@const email = deobfuscateContact(official.contact_email)}
  {@const phone = deobfuscateContact(official.contact_phone)}
  <div class="py-3 first:pt-0 last:pb-0">
    <div class="flex items-center gap-2 flex-wrap">
      <a href="/users/{official.uid}" class="font-medium text-ink-strong hover:text-link transition-colors">{official.name}</a>
      {#each official.roles.filter(r => r === "NC" || r === "Prince") as role}
        <Badge tone={getRoleTone(role)}>{role}</Badge>
      {/each}
      {#if official.city}
        <span class="text-sm text-ink-muted">{official.city}</span>
      {/if}
    </div>
    <div class="flex flex-wrap gap-3 mt-2 text-xs text-ink-muted">
      {#if email}
        <a href="mailto:{email}" class="text-link hover:text-link-soft">{email}</a>
      {/if}
      {#if official.discord_id}
        <DiscordContact discordId={official.discord_id} username={official.contact_discord} />
      {/if}
      {#if phone}
        {#if official.phone_is_whatsapp}
          <a href="https://wa.me/{phone.replace(/[^0-9]/g, '')}" target="_blank" rel="noopener noreferrer" class="text-link hover:text-link-soft">WhatsApp: {phone}</a>
        {:else}
          <span>{phone}</span>
        {/if}
      {/if}
    </div>
  </div>
{/snippet}

{#snippet entries(list: LinkEntry[])}
  <div class="flex flex-wrap gap-2">
    {#each list as entry (entry.user.uid + entry.link.url)}
      <div class="flex items-center gap-1">
        <CommunityLinkPills links={[entry.link]} />
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
{/snippet}

<div class="bg-surface-card rounded-lg shadow border border-line overflow-hidden">
  <button
    onclick={onToggle}
    class="w-full flex items-center justify-between p-4 hover:bg-surface-muted/50 transition-colors text-left"
  >
    <div class="flex items-center gap-2">
      <span class="text-lg">{getCountryFlag(code)}</span>
      <span class="font-medium text-ink-strong">{name}</span>
      {#if isOwnCountry}
        <span class="px-2 py-0.5 text-xs rounded bg-accent-soft/40 text-link">{m.community_your_country()}</span>
      {/if}
      <span class="text-xs text-ink-faint">({count})</span>
    </div>
    {#if expanded}
      <ChevronDown class="w-5 h-5 text-ink-faint" />
    {:else}
      <ChevronRight class="w-5 h-5 text-ink-faint" />
    {/if}
  </button>

  {#if expanded}
    <div class="border-t border-line divide-y divide-line/50">
      {#if showLinks && pinned.length > 0}
        <div class="p-4 space-y-2">
          <h3 class="text-sm font-medium text-ink-strong">{m.community_card_pinned()}</h3>
          {@render entries(pinned)}
        </div>
      {/if}

      {#if showLinks && groups.length > 0}
        <div class="p-4 space-y-2">
          <h3 class="text-sm font-medium text-ink-strong">{m.community_card_groups()}</h3>
          {@render entries(groups)}
        </div>
      {/if}

      {#if curatorPrompt}
        <div class="p-4">
          <p class="p-3 rounded border text-sm banner-info">{m.community_curator_empty_prompt({ country: name })}</p>
        </div>
      {/if}

      {#if showOfficials && officials.length > 0}
        <div class="p-4 space-y-2">
          <h3 class="text-sm font-medium text-ink-strong">{m.community_card_officials()}</h3>
          {#if coordinators.length > 0}
            <div class="divide-y divide-line/50">
              {#each coordinators as official}
                {@render officialRow(official)}
              {/each}
            </div>
          {/if}
          {#if princes.length > 0}
            <button
              onclick={() => { princesOpen = !princesOpen; }}
              class="w-full flex items-center gap-2 min-h-11 text-left"
            >
              {#if princesOpen}
                <ChevronDown class="w-4 h-4 text-ink-faint" />
              {:else}
                <ChevronRight class="w-4 h-4 text-ink-faint" />
              {/if}
              <Badge tone={getRoleTone("Prince")}>Prince</Badge>
              <span class="text-xs text-ink-faint">({princes.length})</span>
            </button>
            {#if princesOpen}
              <div class="divide-y divide-line/50">
                {#each princes as official}
                  {@render officialRow(official)}
                {/each}
              </div>
            {/if}
          {/if}
        </div>
      {/if}
    </div>
  {/if}
</div>
