<script lang="ts">
  import { getAllUsers } from "$lib/db";
  import { syncManager } from "$lib/sync";
  import { getAuthState } from "$lib/stores/auth.svelte";
  import { getCountries, getCountryFlag } from "$lib/geonames";
  import { getRoleClasses } from "$lib/roles";
  import { deobfuscateContact } from "$lib/contact";
  import { apiRequest } from "$lib/api";
  import { showToast } from "$lib/stores/toast.svelte";
  import type { User, CommunityLink } from "$lib/types";
  import CommunityLinkPills from "./CommunityLinkPills.svelte";
  import CommunitySocialSection from "./CommunitySocialSection.svelte";
  import CommunityContentSection from "./CommunityContentSection.svelte";
  import DiscordIcon from "./DiscordIcon.svelte";
  import { ChevronDown, ChevronRight, Globe, Hash, Pencil, Search, Users, Video } from "@lucide/svelte";
  import * as m from '$lib/paraglide/messages.js';

  const auth = $derived(getAuthState());
  const countries = getCountries();

  const SOCIAL_TYPES = new Set(["discord", "telegram", "whatsapp", "forum", "facebook", "reddit"]);
  const CONTENT_TYPES = new Set(["youtube", "twitch", "blog", "website", "instagram", "other"]);

  let allUsersWithLinks = $state<User[]>([]);
  let officials = $state<User[]>([]);
  let expandedCountries = $state<Set<string>>(new Set());
  let loaded = $state(false);
  let searchQuery = $state("");
  let selectedLanguage = $state("");

  const isOfficial = $derived(
    auth.user?.roles?.some((r: string) => r === "IC" || r === "NC" || r === "Prince") ?? false
  );
  const isModerator = $derived(isOfficial);
  const isIC = $derived(auth.user?.roles?.includes("IC") ?? false);
  const isNC = $derived(auth.user?.roles?.includes("NC") ?? false);

  const pinScope = (l: CommunityLink) =>
    l.moderation?.status === "promoted" ? l.moderation.scope : null;

  // Global resources: links a moderator (IC) has pinned globally, from any owner.
  const globalLinks = $derived.by(() => {
    const links: CommunityLink[] = [];
    for (const u of allUsersWithLinks) {
      for (const l of u.community_links || []) {
        if (pinScope(l) === "global") links.push(l);
      }
    }
    return links;
  });

  // Social links grouped by country
  const socialGroups = $derived.by(() => {
    const grouped = new Map<string, { user: User; links: CommunityLink[] }[]>();
    for (const u of allUsersWithLinks) {
      const country = u.country || "??";
      const socialLinks = (u.community_links || []).filter(l =>
        SOCIAL_TYPES.has(l.type) && (l.moderation?.status !== "hidden" || isModerator)
      );
      if (socialLinks.length === 0) continue;
      if (!grouped.has(country)) grouped.set(country, []);
      grouped.get(country)!.push({ user: u, links: socialLinks });
    }
    // Sort users within each country: pinned (scoped promotion) first, then officials
    for (const users of grouped.values()) {
      users.sort((a, b) => {
        const aPin = a.links.some(l => pinScope(l)) ? 0 : 1;
        const bPin = b.links.some(l => pinScope(l)) ? 0 : 1;
        if (aPin !== bPin) return aPin - bPin;
        const aOff = a.user.roles?.some(r => r === "NC" || r === "Prince") ? 0 : 1;
        const bOff = b.user.roles?.some(r => r === "NC" || r === "Prince") ? 0 : 1;
        return aOff - bOff;
      });
    }
    const userCountry = auth.user?.country;
    const query = searchQuery.toLowerCase();
    return [...grouped.entries()]
      .map(([code, users]) => ({
        code,
        name: countries[code]?.name || code,
        users,
      }))
      .filter(g => !query || g.name.toLowerCase().includes(query) || g.code.toLowerCase().includes(query))
      .sort((a, b) => {
        if (userCountry) {
          if (a.code === userCountry) return -1;
          if (b.code === userCountry) return 1;
        }
        return a.name.localeCompare(b.name);
      });
  });

  // Content links with language filtering
  const contentItems = $derived.by(() => {
    const items: { user: User; link: CommunityLink }[] = [];
    for (const u of allUsersWithLinks) {
      for (const l of u.community_links || []) {
        if (!CONTENT_TYPES.has(l.type)) continue;
        if (l.moderation?.status === "hidden" && !isModerator) continue;
        if (selectedLanguage && l.languages?.length && !l.languages.includes(selectedLanguage)) continue;
        items.push({ user: u, link: l });
      }
    }
    // Sort: global pin, national pin, promoted, officials, then by user name
    const rank = (l: CommunityLink) => {
      if (l.moderation?.status !== "promoted") return 3;
      if (l.moderation.scope === "global") return 0;
      if (l.moderation.scope === "national") return 1;
      return 2;
    };
    items.sort((a, b) => {
      const aRank = rank(a.link);
      const bRank = rank(b.link);
      if (aRank !== bRank) return aRank - bRank;
      const aOff = a.user.roles?.some(r => r === "IC" || r === "NC" || r === "Prince") ? 0 : 1;
      const bOff = b.user.roles?.some(r => r === "IC" || r === "NC" || r === "Prince") ? 0 : 1;
      if (aOff !== bOff) return aOff - bOff;
      return a.user.name.localeCompare(b.user.name);
    });
    return items;
  });

  // Available content languages
  const contentLanguages = $derived.by(() => {
    const langs = new Set<string>();
    for (const u of allUsersWithLinks) {
      for (const l of u.community_links || []) {
        if (!CONTENT_TYPES.has(l.type)) continue;
        for (const lang of l.languages || []) langs.add(lang);
      }
    }
    return [...langs].sort();
  });

  // Officials directory (NC/Prince with contact info)
  interface OfficialGroup {
    code: string;
    name: string;
    officials: User[];
  }
  const officialGroups = $derived.by(() => {
    const grouped = new Map<string, User[]>();
    for (const u of officials) {
      const c = u.country || "??";
      if (!grouped.has(c)) grouped.set(c, []);
      grouped.get(c)!.push(u);
    }
    for (const users of grouped.values()) {
      users.sort((a, b) => {
        const aNC = a.roles?.includes("NC") ? 0 : 1;
        const bNC = b.roles?.includes("NC") ? 0 : 1;
        if (aNC !== bNC) return aNC - bNC;
        return (a.city || "").localeCompare(b.city || "");
      });
    }
    const userCountry = auth.user?.country;
    return [...grouped.entries()]
      .map(([code, officials]) => ({ code, name: countries[code]?.name || code, officials }))
      .sort((a, b) => {
        if (userCountry) {
          if (a.code === userCountry) return -1;
          if (b.code === userCountry) return 1;
        }
        return a.name.localeCompare(b.name);
      });
  });

  let expandedOfficialCountries = $state<Set<string>>(new Set());

  async function loadData() {
    const allUsers = await getAllUsers();
    // All users with community links
    allUsersWithLinks = allUsers.filter(u =>
      !u.deleted_at && u.community_links?.length
    );
    // Officials directory: NC/Prince reachable by contact info — independent of
    // community_links (an official with an email but no link must still show).
    officials = allUsers.filter(u =>
      !u.deleted_at &&
      u.roles?.some(r => r === "NC" || r === "Prince") &&
      (u.contact_email || u.discord_id || u.contact_phone)
    );
    // Auto-expand user's country (the language filter defaults to "All")
    if (auth.user?.country) {
      expandedCountries = new Set([auth.user.country]);
      expandedOfficialCountries = new Set([auth.user.country]);
    }
    loaded = true;
  }

  function toggleCountry(code: string) {
    const next = new Set(expandedCountries);
    if (next.has(code)) next.delete(code);
    else next.add(code);
    expandedCountries = next;
  }

  function toggleOfficialCountry(code: string) {
    const next = new Set(expandedOfficialCountries);
    if (next.has(code)) next.delete(code);
    else next.add(code);
    expandedOfficialCountries = next;
  }

  async function handleModerate(userUid: string, url: string, action: string) {
    try {
      await apiRequest(`/api/users/${userUid}/community-link-moderation`, {
        method: "PATCH",
        body: JSON.stringify({ url, action }),
      });
      await loadData(); // Refresh after moderation
    } catch (e: any) {
      showToast({ type: "error", message: e.detail || m.community_moderation_failed() });
    }
  }

  // Load on mount and refresh on sync
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
  <!-- Global Resources: links pinned globally by a moderator -->
  {#if globalLinks.length > 0}
    <div class="bg-surface-card rounded-lg shadow border border-line p-5 mb-6">
      <div class="flex items-center gap-2 mb-3">
        <Globe class="w-5 h-5 text-accent" />
        <h2 class="text-lg font-medium text-ink-strong">{m.community_global_resources()}</h2>
      </div>
      <CommunityLinkPills links={globalLinks} />
    </div>
  {/if}

  <!-- Add links prompt -->
  {#if auth.isAuthenticated && auth.user?.vekn_id}
    <a href="/profile" class="flex items-center gap-2 rounded-lg bg-surface-muted border border-line-strong px-4 py-3 mb-6 text-sm text-ink-strong hover:bg-surface-muted transition-colors">
      <Pencil class="w-4 h-4 text-link shrink-0" />
      <span>{m.community_add_links_prompt()} <span class="text-link font-medium">{m.community_go_to_profile()}</span></span>
    </a>
  {/if}

  <!-- Country-not-set prompt -->
  {#if auth.isAuthenticated && !auth.user?.country}
    <div class="p-4 mb-6 rounded-lg border text-sm banner-warn">
      {m.community_set_country_prompt()}
      <a href="/profile" class="underline hover:text-purple-200 ml-1">{m.community_go_to_profile()}</a>
    </div>
  {/if}

  <!-- Not logged in prompt -->
  {#if !auth.isAuthenticated}
    <div class="p-4 mb-6 rounded-lg bg-surface-muted border border-line-strong text-sm text-ink">
      {m.community_login_prompt()}
      <a href="/login" class="underline text-link hover:text-link-soft ml-1">{m.community_sign_in()}</a>
    </div>
  {/if}

  <!-- Communities Section (Social links by country) -->
  {#if socialGroups.length > 0}
    <div class="mb-8">
      <div class="flex items-center gap-2 mb-3">
        <Hash class="w-5 h-5 text-accent" />
        <h2 class="text-lg font-medium text-ink-strong">{m.community_section_communities()}</h2>
      </div>

      <!-- Country search -->
      <div class="relative mb-3">
        <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-ink-faint" />
        <input
          type="text"
          bind:value={searchQuery}
          placeholder={m.community_search_countries()}
          class="w-full pl-9 pr-3 py-2 border border-line-strong rounded-lg bg-surface-card text-ink-bright text-sm focus:ring-2 focus:ring-accent focus:border-transparent"
        />
      </div>

      <CommunitySocialSection
        groups={socialGroups}
        {expandedCountries}
        userCountry={auth.user?.country ?? null}
        {isModerator}
        {isIC}
        {isNC}
        onToggleCountry={toggleCountry}
        onModerate={handleModerate}
      />
    </div>
  {/if}

  <!-- Content Section (language-filtered) -->
  {#if contentItems.length > 0 || contentLanguages.length > 0}
    <div class="mb-8">
      <div class="flex items-center gap-2 mb-3">
        <Video class="w-5 h-5 text-accent" />
        <h2 class="text-lg font-medium text-ink-strong">{m.community_section_content()}</h2>
      </div>

      <CommunityContentSection
        items={contentItems}
        languages={contentLanguages}
        {selectedLanguage}
        {isModerator}
        {isIC}
        {isNC}
        viewerCountry={auth.user?.country ?? null}
        onSelectLanguage={(lang) => { selectedLanguage = lang; }}
        onModerate={handleModerate}
      />
    </div>
  {/if}

  <!-- Officials Directory -->
  {#if officialGroups.length > 0}
    <div>
      <div class="flex items-center gap-2 mb-3">
        <Users class="w-5 h-5 text-accent" />
        <h2 class="text-lg font-medium text-ink-strong">{m.community_section_officials()}</h2>
      </div>

      <div class="space-y-2">
        {#each officialGroups as group}
          {@const isExpanded = expandedOfficialCountries.has(group.code)}
          <div class="bg-surface-card rounded-lg shadow border border-line overflow-hidden">
            <button
              onclick={() => toggleOfficialCountry(group.code)}
              class="w-full flex items-center justify-between p-4 hover:bg-surface-muted/50 transition-colors text-left"
            >
              <div class="flex items-center gap-2">
                <span class="text-lg">{getCountryFlag(group.code)}</span>
                <span class="font-medium text-ink-strong">{group.name}</span>
                {#if auth.user?.country === group.code}
                  <span class="px-2 py-0.5 text-xs rounded bg-accent-soft/40 text-link">{m.community_your_country()}</span>
                {/if}
                <span class="text-xs text-ink-faint">({group.officials.length})</span>
              </div>
              {#if isExpanded}
                <ChevronDown class="w-5 h-5 text-ink-faint" />
              {:else}
                <ChevronRight class="w-5 h-5 text-ink-faint" />
              {/if}
            </button>

            {#if isExpanded}
              <div class="border-t border-line divide-y divide-line/50">
                {#each group.officials as official}
                  <div class="p-4">
                    <div class="flex items-start justify-between gap-4">
                      <div class="min-w-0 flex-1">
                        <div class="flex items-center gap-2 flex-wrap">
                          <a href="/users/{official.uid}" class="font-medium text-ink-strong hover:text-link transition-colors">{official.name}</a>
                          {#each official.roles.filter(r => r === "NC" || r === "Prince") as role}
                            <span class="px-2 py-0.5 rounded text-xs font-medium {getRoleClasses(role)}">{role}</span>
                          {/each}
                        </div>
                        {#if official.city}
                          <div class="text-sm text-ink-muted mt-0.5">{official.city}</div>
                        {/if}
                        {#if official.contact_email || official.discord_id || official.contact_phone}
                          {@const email = deobfuscateContact(official.contact_email)}
                          {@const phone = deobfuscateContact(official.contact_phone)}
                          <div class="flex flex-wrap gap-3 mt-2 text-xs text-ink-muted">
                            {#if email}
                              <a href="mailto:{email}" class="text-link hover:text-link-soft">{email}</a>
                            {/if}
                            {#if official.discord_id}
                              <a
                                href="https://discord.com/users/{official.discord_id}"
                                target="_blank"
                                rel="noopener noreferrer"
                                class="inline-flex items-center gap-1 text-link hover:text-link-soft"
                              >
                                <DiscordIcon class="w-3.5 h-3.5" />
                                <span>{official.contact_discord || "Discord"}</span>
                              </a>
                            {/if}
                            {#if phone}
                              {#if official.phone_is_whatsapp}
                                <a href="https://wa.me/{phone.replace(/[^0-9]/g, '')}" target="_blank" rel="noopener noreferrer" class="text-link hover:text-link-soft">WhatsApp: {phone}</a>
                              {:else}
                                <span>{phone}</span>
                              {/if}
                            {/if}
                          </div>
                        {/if}
                      </div>
                    </div>
                  </div>
                {/each}
              </div>
            {/if}
          </div>
        {/each}
      </div>
    </div>
  {/if}

  <!-- Empty state -->
  {#if socialGroups.length === 0 && contentItems.length === 0 && officialGroups.length === 0 && globalLinks.length === 0}
    <div class="text-center py-12">
      <Users class="mx-auto h-12 w-12 text-ink-faint mb-4" />
      <h3 class="text-lg font-medium text-ink-strong mb-2">{m.community_no_officials()}</h3>
      <p class="text-ink-muted">{m.community_no_officials_hint()}</p>
    </div>
  {/if}
{/if}
