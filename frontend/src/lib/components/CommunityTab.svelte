<script lang="ts">
  import { getAllUsers } from "$lib/db";
  import { syncManager } from "$lib/sync";
  import { getAuthState } from "$lib/stores/auth.svelte";
  import { getCountries, getCountryFlag } from "$lib/geonames";
  import { getRoleClasses } from "$lib/roles";
  import { apiRequest } from "$lib/api";
  import { showToast } from "$lib/stores/toast.svelte";
  import type { User, CommunityLink } from "$lib/types";
  import CommunityLinkPills from "./CommunityLinkPills.svelte";
  import CommunitySocialSection from "./CommunitySocialSection.svelte";
  import CommunityContentSection from "./CommunityContentSection.svelte";
  import { ChevronDown, ChevronRight, Globe, Hash, Pencil, Search, Users, Video } from "lucide-svelte";
  import * as m from '$lib/paraglide/messages.js';

  const auth = $derived(getAuthState());
  const countries = getCountries();

  const SOCIAL_TYPES = new Set(["discord", "telegram", "whatsapp", "forum", "facebook", "reddit"]);
  const CONTENT_TYPES = new Set(["youtube", "twitch", "blog", "website", "instagram", "other"]);

  // Country → primary language mapping
  const COUNTRY_LANGUAGE: Record<string, string> = {
    US: "en", GB: "en", AU: "en", CA: "en", NZ: "en", IE: "en", ZA: "en",
    FR: "fr", BE: "fr", CH: "fr", MC: "fr",
    ES: "es", MX: "es", AR: "es", CO: "es", CL: "es", PE: "es", VE: "es", EC: "es", UY: "es", PY: "es", BO: "es", CR: "es", PA: "es", GT: "es", HN: "es", SV: "es", NI: "es", CU: "es", DO: "es", PR: "es",
    PT: "pt", BR: "pt",
    IT: "it",
    DE: "de", AT: "de", LI: "de",
    PL: "pl", FI: "fi", SE: "sv", NL: "nl", NO: "no", DK: "da",
    JP: "ja", CN: "zh", TW: "zh", KR: "ko", RU: "ru",
    CZ: "cs", HU: "hu", RO: "ro", BG: "bg", HR: "hr", GR: "el", TR: "tr",
    TH: "th", VN: "vi",
  };

  let allUsersWithLinks = $state<User[]>([]);
  let icUsers = $state<User[]>([]);
  let expandedCountries = $state<Set<string>>(new Set());
  let loaded = $state(false);
  let searchQuery = $state("");
  let selectedLanguage = $state("");

  const isOfficial = $derived(
    auth.user?.roles?.some((r: string) => r === "IC" || r === "NC" || r === "Prince") ?? false
  );
  const isModerator = $derived(isOfficial);

  // IC links (global resources)
  const icLinks = $derived.by(() => {
    const links: CommunityLink[] = [];
    for (const u of icUsers) {
      if (u.community_links) {
        for (const l of u.community_links) {
          if (l.moderation?.status !== "hidden" || isModerator) links.push(l);
        }
      }
    }
    return links;
  });

  // Social links grouped by country
  const socialGroups = $derived.by(() => {
    const grouped = new Map<string, { user: User; links: CommunityLink[] }[]>();
    for (const u of allUsersWithLinks) {
      if (u.roles?.includes("IC")) continue; // IC links shown in global section
      const country = u.country || "??";
      const socialLinks = (u.community_links || []).filter(l =>
        SOCIAL_TYPES.has(l.type) && (l.moderation?.status !== "hidden" || isModerator)
      );
      if (socialLinks.length === 0) continue;
      if (!grouped.has(country)) grouped.set(country, []);
      // Sort: promoted first, then officials first
      const isOfficialUser = u.roles?.some(r => r === "NC" || r === "Prince") ?? false;
      grouped.get(country)!.push({ user: u, links: socialLinks });
    }
    // Sort users within each country: officials first, promoted first
    for (const users of grouped.values()) {
      users.sort((a, b) => {
        const aOff = a.user.roles?.some(r => r === "NC" || r === "Prince") ? 0 : 1;
        const bOff = b.user.roles?.some(r => r === "NC" || r === "Prince") ? 0 : 1;
        if (aOff !== bOff) return aOff - bOff;
        const aProm = a.links.some(l => l.moderation?.status === "promoted") ? 0 : 1;
        const bProm = b.links.some(l => l.moderation?.status === "promoted") ? 0 : 1;
        return aProm - bProm;
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
        if (selectedLanguage && l.language && l.language !== selectedLanguage) continue;
        items.push({ user: u, link: l });
      }
    }
    // Sort: promoted first, officials first, then by user name
    items.sort((a, b) => {
      const aProm = a.link.moderation?.status === "promoted" ? 0 : 1;
      const bProm = b.link.moderation?.status === "promoted" ? 0 : 1;
      if (aProm !== bProm) return aProm - bProm;
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
        if (CONTENT_TYPES.has(l.type) && l.language) langs.add(l.language);
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
    for (const u of allUsersWithLinks) {
      if (!u.roles?.some(r => r === "NC" || r === "Prince")) continue;
      if (!u.contact_email && !u.contact_discord && !u.contact_phone) continue;
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
    // IC users (for global resources)
    icUsers = allUsers.filter(u =>
      !u.deleted_at && u.roles?.includes("IC") && u.community_links?.length
    );
    // All users with community links
    allUsersWithLinks = allUsers.filter(u =>
      !u.deleted_at && u.community_links?.length
    );
    // Auto-expand user's country
    if (auth.user?.country) {
      expandedCountries = new Set([auth.user.country]);
      expandedOfficialCountries = new Set([auth.user.country]);
      // Default language filter from user's country
      if (!selectedLanguage) {
        selectedLanguage = COUNTRY_LANGUAGE[auth.user.country] || "";
      }
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
      showToast({ type: "error", message: e.detail || "Moderation failed" });
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
  <div class="text-center py-8 text-ash-400">{m.common_loading()}</div>
{:else}
  <!-- Global Resources (IC links) -->
  {#if icLinks.length > 0}
    <div class="bg-dusk-950 rounded-lg shadow border border-ash-800 p-5 mb-6">
      <div class="flex items-center gap-2 mb-3">
        <Globe class="w-5 h-5 text-crimson-500" />
        <h2 class="text-lg font-medium text-bone-100">{m.community_global_resources()}</h2>
      </div>
      <CommunityLinkPills links={icLinks} />
    </div>
  {/if}

  <!-- Add links prompt -->
  {#if auth.isAuthenticated && auth.user?.vekn_id}
    <a href="/profile" class="flex items-center gap-2 rounded-lg bg-dusk-900 border border-ash-700 px-4 py-3 mb-6 text-sm text-bone-300 hover:bg-dusk-800 transition-colors">
      <Pencil class="w-4 h-4 text-crimson-400 shrink-0" />
      <span>{m.community_add_links_prompt()} <span class="text-crimson-400 font-medium">{m.community_go_to_profile()}</span></span>
    </a>
  {/if}

  <!-- Country-not-set prompt -->
  {#if auth.isAuthenticated && !auth.user?.country}
    <div class="p-4 mb-6 rounded-lg border text-sm banner-amber">
      {m.community_set_country_prompt()}
      <a href="/profile" class="underline hover:text-amber-200 ml-1">{m.community_go_to_profile()}</a>
    </div>
  {/if}

  <!-- Not logged in prompt -->
  {#if !auth.isAuthenticated}
    <div class="p-4 mb-6 rounded-lg bg-ash-900 border border-ash-700 text-sm text-ash-300">
      {m.community_login_prompt()}
      <a href="/login" class="underline text-crimson-500 hover:text-crimson-400 ml-1">{m.community_sign_in()}</a>
    </div>
  {/if}

  <!-- Communities Section (Social links by country) -->
  {#if socialGroups.length > 0}
    <div class="mb-8">
      <div class="flex items-center gap-2 mb-3">
        <Hash class="w-5 h-5 text-crimson-500" />
        <h2 class="text-lg font-medium text-bone-100">{m.community_section_communities()}</h2>
      </div>

      <!-- Country search -->
      <div class="relative mb-3">
        <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-ash-500" />
        <input
          type="text"
          bind:value={searchQuery}
          placeholder={m.community_search_countries()}
          class="w-full pl-9 pr-3 py-2 border border-ash-600 rounded-lg bg-dusk-950 text-ash-200 text-sm focus:ring-2 focus:ring-crimson-500 focus:border-transparent"
        />
      </div>

      <CommunitySocialSection
        groups={socialGroups}
        {expandedCountries}
        userCountry={auth.user?.country ?? null}
        {isModerator}
        onToggleCountry={toggleCountry}
        onModerate={handleModerate}
      />
    </div>
  {/if}

  <!-- Content Section (language-filtered) -->
  {#if contentItems.length > 0 || contentLanguages.length > 0}
    <div class="mb-8">
      <div class="flex items-center gap-2 mb-3">
        <Video class="w-5 h-5 text-crimson-500" />
        <h2 class="text-lg font-medium text-bone-100">{m.community_section_content()}</h2>
      </div>

      <CommunityContentSection
        items={contentItems}
        languages={contentLanguages}
        {selectedLanguage}
        {isModerator}
        onSelectLanguage={(lang) => { selectedLanguage = lang; }}
        onModerate={handleModerate}
      />
    </div>
  {/if}

  <!-- Officials Directory -->
  {#if officialGroups.length > 0}
    <div>
      <div class="flex items-center gap-2 mb-3">
        <Users class="w-5 h-5 text-crimson-500" />
        <h2 class="text-lg font-medium text-bone-100">{m.community_section_officials()}</h2>
      </div>

      <div class="space-y-2">
        {#each officialGroups as group}
          {@const isExpanded = expandedOfficialCountries.has(group.code)}
          <div class="bg-dusk-950 rounded-lg shadow border border-ash-800 overflow-hidden">
            <button
              onclick={() => toggleOfficialCountry(group.code)}
              class="w-full flex items-center justify-between p-4 hover:bg-ash-900/50 transition-colors text-left"
            >
              <div class="flex items-center gap-2">
                <span class="text-lg">{getCountryFlag(group.code)}</span>
                <span class="font-medium text-bone-100">{group.name}</span>
                {#if auth.user?.country === group.code}
                  <span class="px-2 py-0.5 text-xs rounded bg-crimson-900/40 text-crimson-400">{m.community_your_country()}</span>
                {/if}
                <span class="text-xs text-ash-500">({group.officials.length})</span>
              </div>
              {#if isExpanded}
                <ChevronDown class="w-5 h-5 text-ash-500" />
              {:else}
                <ChevronRight class="w-5 h-5 text-ash-500" />
              {/if}
            </button>

            {#if isExpanded}
              <div class="border-t border-ash-800 divide-y divide-ash-800/50">
                {#each group.officials as official}
                  <div class="p-4">
                    <div class="flex items-start justify-between gap-4">
                      <div class="min-w-0 flex-1">
                        <div class="flex items-center gap-2 flex-wrap">
                          <a href="/users/{official.uid}" class="font-medium text-bone-100 hover:text-crimson-400 transition-colors">{official.name}</a>
                          {#each official.roles.filter(r => r === "NC" || r === "Prince") as role}
                            <span class="px-2 py-0.5 rounded text-xs font-medium {getRoleClasses(role)}">{role}</span>
                          {/each}
                        </div>
                        {#if official.city}
                          <div class="text-sm text-ash-400 mt-0.5">{official.city}</div>
                        {/if}
                        {#if official.contact_email || official.contact_discord || official.contact_phone}
                          <div class="flex flex-wrap gap-3 mt-2 text-xs text-ash-400">
                            {#if official.contact_email}
                              <a href="mailto:{official.contact_email}" class="text-crimson-500 hover:text-crimson-400">{official.contact_email}</a>
                            {/if}
                            {#if official.contact_discord}
                              <span>Discord: {official.contact_discord}</span>
                            {/if}
                            {#if official.contact_phone}
                              {#if official.phone_is_whatsapp}
                                <a href="https://wa.me/{official.contact_phone.replace(/[^0-9]/g, '')}" target="_blank" rel="noopener noreferrer" class="text-crimson-500 hover:text-crimson-400">WhatsApp: {official.contact_phone}</a>
                              {:else}
                                <span>{official.contact_phone}</span>
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
  {#if socialGroups.length === 0 && contentItems.length === 0 && officialGroups.length === 0 && icLinks.length === 0}
    <div class="text-center py-12">
      <Users class="mx-auto h-12 w-12 text-ash-600 mb-4" />
      <h3 class="text-lg font-medium text-bone-100 mb-2">{m.community_no_officials()}</h3>
      <p class="text-ash-400">{m.community_no_officials_hint()}</p>
    </div>
  {/if}
{/if}
