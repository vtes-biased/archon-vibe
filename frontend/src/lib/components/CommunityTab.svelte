<script lang="ts">
  import { getAllUsers } from "$lib/db";
  import { syncManager } from "$lib/sync";
  import { getAuthState, updateProfile } from "$lib/stores/auth.svelte";
  import { getCountries, getCountryFlag } from "$lib/geonames";
  import { COUNTRY_LANGUAGE } from "$lib/data/country-language";
  import { apiRequest } from "$lib/api";
  import { showToast } from "$lib/stores/toast.svelte";
  import { canModerateLink, canPromoteLinkNational, canPromoteLinkGlobal, getCommunityLinkReference, isOfficial } from "$lib/engine";
  import { getLocale } from "$lib/paraglide/runtime.js";
  import type { CommunityLink, LinkMedia, User } from "$lib/types";
  import CommunityLinkPills from "./CommunityLinkPills.svelte";
  import CommunityModerationActions from "./CommunityModerationActions.svelte";
  import CommunityCountryCard from "./CommunityCountryCard.svelte";
  import CommunityContentPool from "./CommunityContentPool.svelte";
  import CommunityLinkEditor from "./CommunityLinkEditor.svelte";
  import { Globe, Search, Users, Video } from "@lucide/svelte";
  import * as m from '$lib/paraglide/messages.js';

  // Sponsor mode (?sponsor=1): the visitor came to find an official to sponsor them for a VEKN ID —
  // show only the officials, pre-filtered to their country, with an explicit contact CTA.
  let { sponsorMode = false }: { sponsorMode?: boolean } = $props();

  interface LinkEntry { user: User; link: CommunityLink }

  const auth = $derived(getAuthState());
  const countries = getCountries();

  let allUsersWithLinks = $state<User[]>([]);
  let officials = $state<User[]>([]);
  let loaded = $state(false);
  let searchQuery = $state("");
  let pickedCountry = $state<string | null>(null);
  // Codes whose expansion differs from the default (own and picked open).
  let toggledCards = $state<Set<string>>(new Set());
  let selectedLanguages = $state<string[]>([]);
  let selectedMedia = $state<LinkMedia | null>(null);
  let adding = $state(false);

  const reference = $derived(getCommunityLinkReference());
  // Reading the reactive engine accessors keeps these recomputing once WASM lands.
  const canModerate = (country: string | null) => canModerateLink(auth.user, country).allowed;
  const canPromoteNational = (country: string | null) => canPromoteLinkNational(auth.user, country).allowed;
  const canPromoteGlobal = $derived(canPromoteLinkGlobal(auth.user).allowed);

  const pinScope = (l: CommunityLink) =>
    l.moderation?.status === "promoted" ? l.moderation.scope : null;
  const linkCountry = (e: LinkEntry) => e.link.country || e.user.country || null;

  const entries = $derived.by(() => {
    const all: LinkEntry[] = [];
    for (const user of allUsersWithLinks) {
      for (const link of user.community_links || []) {
        const entry = { user, link };
        if (link.moderation?.status === "hidden" && !canModerate(linkCountry(entry))) continue;
        all.push(entry);
      }
    }
    return all;
  });

  const globalLinks = $derived(entries.filter(e => pinScope(e.link) === "global"));
  const nationalLinks = $derived(entries.filter(e => pinScope(e.link) === "national"));
  const unpinned = $derived(entries.filter(e => !pinScope(e.link)));
  const channelLinks = $derived(unpinned.filter(e => reference?.placement[e.link.type] === "channel"));
  const contentLinks = $derived(unpinned.filter(e => reference?.placement[e.link.type] === "content"));

  const officialsByCountry = $derived.by(() => {
    const grouped = new Map<string, User[]>();
    for (const official of officials) {
      const code = official.country || "??";
      if (!grouped.has(code)) grouped.set(code, []);
      grouped.get(code)!.push(official);
    }
    for (const list of grouped.values()) {
      list.sort((a, b) => {
        const aNC = a.roles?.includes("NC") ? 0 : 1;
        const bNC = b.roles?.includes("NC") ? 0 : 1;
        if (aNC !== bNC) return aNC - bNC;
        return (a.city || "").localeCompare(b.city || "");
      });
    }
    return grouped;
  });

  // Officials carry contact info — gate it behind sign-in so it isn't shown directly to
  // logged-out visitors; the public projection still ships the data, this is a display-only gate.
  const showOfficials = $derived(auth.isAuthenticated);
  const showLinks = $derived(!sponsorMode);

  function cardFor(code: string) {
    const inCountry = (e: LinkEntry) => (linkCountry(e) || "??") === code;
    return {
      code,
      name: countries[code]?.name || code,
      pinned: nationalLinks.filter(inCountry),
      groups: channelLinks.filter(inCountry),
      officials: officialsByCountry.get(code) || [],
    };
  }

  const knownCountries = $derived.by(() => {
    const codes = new Set<string>(officialsByCountry.keys());
    for (const e of [...nationalLinks, ...channelLinks]) codes.add(linkCountry(e) || "??");
    return [...codes]
      .map(code => ({ code, name: countries[code]?.name || code }))
      .sort((a, b) => a.name.localeCompare(b.name));
  });

  const searchMatches = $derived.by(() => {
    const query = searchQuery.trim().toLowerCase();
    if (!query) return [];
    return knownCountries
      .filter(c => c.name.toLowerCase().includes(query) || c.code.toLowerCase().includes(query))
      .slice(0, 8);
  });

  const ownCountry = $derived(auth.user?.country ?? null);
  const displayedCards = $derived.by(() => {
    if (sponsorMode) {
      const own = ownCountry && officialsByCountry.has(ownCountry) ? [ownCountry] : null;
      return (own ?? [...officialsByCountry.keys()].sort((a, b) =>
        (countries[a]?.name || a).localeCompare(countries[b]?.name || b)
      )).map(cardFor);
    }
    const codes = [ownCountry, pickedCountry].filter((c): c is string => !!c);
    return [...new Set(codes)].map(cardFor);
  });

  const poolLanguages = $derived.by(() => {
    const langs = new Set<string>();
    for (const e of contentLinks) for (const lang of e.link.languages || []) langs.add(lang);
    return [...langs].sort();
  });

  const poolItems = $derived.by(() => {
    const items = contentLinks.filter(e => {
      if (selectedMedia && reference?.media[e.link.type] !== selectedMedia) return false;
      const languages = e.link.languages || [];
      // A language-less link predates the requirement: it shows under every filter.
      if (selectedLanguages.length && languages.length) {
        return languages.some(l => selectedLanguages.includes(l));
      }
      return true;
    });
    return items.sort((a, b) => {
      const aOff = a.user.roles?.some(r => r === "IC" || r === "NC" || r === "Prince") ? 0 : 1;
      const bOff = b.user.roles?.some(r => r === "IC" || r === "NC" || r === "Prince") ? 0 : 1;
      if (aOff !== bOff) return aOff - bOff;
      return a.user.name.localeCompare(b.user.name);
    });
  });

  const ownLinks = $derived(auth.user?.community_links ?? []);
  const canAddLinks = $derived(
    auth.isAuthenticated &&
    !!auth.user?.vekn_id &&
    ownLinks.length < (isOfficial(auth.user) ? 10 : 5)
  );

  async function loadData() {
    const allUsers = await getAllUsers();
    allUsersWithLinks = allUsers.filter(u => !u.deleted_at && u.community_links?.length);
    // Officials directory: NC/Prince reachable by contact info — independent of
    // community_links (an official with an email but no link must still show).
    officials = allUsers.filter(u =>
      !u.deleted_at &&
      u.roles?.some(r => r === "NC" || r === "Prince") &&
      (u.contact_email || u.discord_id || u.contact_phone)
    );
    loaded = true;
  }

  const isExpanded = (code: string) =>
    (code === ownCountry || code === pickedCountry) !== toggledCards.has(code);

  function toggleCard(code: string) {
    const next = new Set(toggledCards);
    if (next.has(code)) next.delete(code);
    else next.add(code);
    toggledCards = next;
  }

  function toggleLanguage(lang: string) {
    selectedLanguages = selectedLanguages.includes(lang)
      ? selectedLanguages.filter(l => l !== lang)
      : [...selectedLanguages, lang];
  }

  async function handleModerate(userUid: string, url: string, action: string) {
    try {
      await apiRequest(`/api/users/${userUid}/community-link-moderation`, {
        method: "PATCH",
        body: JSON.stringify({ url, action }),
      });
      await loadData();
    } catch (e: any) {
      showToast({ type: "error", message: e.detail || m.community_moderation_failed() });
    }
  }

  async function saveLink(link: CommunityLink) {
    adding = false;
    if (!(await updateProfile({ community_links: [...ownLinks, link] }))) {
      showToast({ type: "error", message: m.profile_save_error() });
    }
  }

  let languageSeeded = false;
  $effect(() => {
    if (languageSeeded || poolLanguages.length === 0) return;
    languageSeeded = true;
    if (poolLanguages.includes(getLocale())) selectedLanguages = [getLocale()];
  });

  $effect(() => {
    loadData();
    const handler = (event: { type: string }) => {
      if (event.type === "user" || event.type === "sync_complete") loadData();
    };
    syncManager.addEventListener(handler);
    return () => syncManager.removeEventListener(handler);
  });
</script>

{#if !loaded}
  <div class="text-center py-8 text-ink-muted">{m.common_loading()}</div>
{:else}
  {#if sponsorMode && auth.isAuthenticated}
    <div class="p-4 mb-6 rounded-lg border text-sm banner-info">
      {m.community_sponsor_cta()}
    </div>
  {/if}

  {#if !auth.isAuthenticated}
    <div class="p-4 mb-6 rounded-lg bg-surface-muted border border-line-strong text-sm text-ink">
      {m.community_login_prompt()}
      <a href="/login" class="underline text-link hover:text-link-soft ml-1">{m.community_sign_in()}</a>
    </div>
  {/if}

  {#if auth.isAuthenticated && !ownCountry}
    <div class="p-4 mb-6 rounded-lg border text-sm banner-warn">
      {m.community_set_country_prompt()}
      <a href="/profile" class="underline hover:text-warn ml-1">{m.community_go_to_profile()}</a>
    </div>
  {/if}

  {#if showLinks && globalLinks.length > 0}
    <div class="bg-surface-card rounded-lg shadow border border-line p-5 mb-6">
      <div class="flex items-center gap-2 mb-3">
        <Globe class="w-5 h-5 text-accent" />
        <h2 class="text-lg font-medium text-ink-strong">{m.community_global_resources()}</h2>
      </div>
      <div class="flex flex-wrap items-center gap-x-3 gap-y-2">
        {#each globalLinks as entry (entry.user.uid + entry.link.url)}
          <div class="flex items-center gap-1">
            <CommunityLinkPills links={[entry.link]} />
            {#if canModerate(linkCountry(entry))}
              <CommunityModerationActions
                userUid={entry.user.uid}
                link={entry.link}
                onModerate={handleModerate}
                canPromoteNational={canPromoteNational(linkCountry(entry))}
                {canPromoteGlobal}
              />
            {/if}
          </div>
        {/each}
      </div>
    </div>
  {/if}

  <div class="mb-8 space-y-2">
    {#each displayedCards as card (card.code)}
      <CommunityCountryCard
        code={card.code}
        name={card.name}
        pinned={card.pinned}
        groups={card.groups}
        officials={card.officials}
        isOwnCountry={card.code === ownCountry}
        expanded={isExpanded(card.code)}
        {showLinks}
        {showOfficials}
        canModerate={canModerate(card.code)}
        canPromoteNational={canPromoteNational(card.code)}
        {canPromoteGlobal}
        onToggle={() => toggleCard(card.code)}
        onModerate={handleModerate}
        onAddLink={canAddLinks && showLinks && card.code === ownCountry ? () => { adding = true; } : null}
      />
    {/each}

    <div class="relative">
      <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-ink-faint" />
      <input
        type="text"
        bind:value={searchQuery}
        placeholder={m.community_search_countries()}
        class="w-full pl-9 pr-3 py-2 border border-line-strong rounded-lg bg-surface-card text-ink-bright text-sm focus:ring-2 focus:ring-accent focus:border-transparent"
      />
      {#if searchMatches.length > 0}
        <div class="absolute z-10 w-full mt-1 bg-surface-card border border-line-strong rounded-lg shadow-lg max-h-60 overflow-auto">
          {#each searchMatches as match}
            <button
              onclick={() => { pickedCountry = match.code; searchQuery = ""; }}
              class="w-full flex items-center gap-2 px-3 min-h-11 text-left text-sm text-ink-bright hover:bg-surface-muted transition-colors"
            >
              <span>{getCountryFlag(match.code)}</span>
              <span>{match.name}</span>
            </button>
          {/each}
        </div>
      {/if}
    </div>
  </div>

  {#if showLinks}
    <div class="mb-8">
      <div class="flex items-center gap-2 mb-3">
        <Video class="w-5 h-5 text-accent" />
        <h2 class="text-lg font-medium text-ink-strong">{m.community_section_content()}</h2>
      </div>

      <CommunityContentPool
        items={poolItems}
        languages={poolLanguages}
        mediaKinds={reference?.mediaKinds ?? []}
        {selectedLanguages}
        {selectedMedia}
        {canModerate}
        {canPromoteNational}
        {canPromoteGlobal}
        {linkCountry}
        onToggleLanguage={toggleLanguage}
        onSelectMedia={(kind) => { selectedMedia = kind; }}
        onClearFilters={() => { selectedLanguages = []; selectedMedia = null; }}
        onModerate={handleModerate}
        onAddLink={canAddLinks ? () => { adding = true; } : null}
      />
    </div>
  {/if}

  {#if displayedCards.length === 0 && globalLinks.length === 0 && poolItems.length === 0}
    <div class="text-center py-12">
      <Users class="mx-auto h-12 w-12 text-ink-faint mb-4" />
      <h3 class="text-lg font-medium text-ink-strong mb-2">{m.community_no_officials()}</h3>
      <p class="text-ink-muted">{m.community_no_officials_hint()}</p>
    </div>
  {/if}

  {#if adding}
    <CommunityLinkEditor
      link={null}
      ownerCountry={ownCountry}
      defaultLanguage={COUNTRY_LANGUAGE[ownCountry ?? ""] || getLocale()}
      onclose={() => { adding = false; }}
      onsave={saveLink}
    />
  {/if}
{/if}
