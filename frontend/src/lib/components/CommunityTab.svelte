<script lang="ts">
  import { getAllUsers } from "$lib/db";
  import { syncManager } from "$lib/sync";
  import { getAuthState } from "$lib/stores/auth.svelte";
  import { getCountries, getCountryFlag } from "$lib/geonames";
  import { getRoleClasses } from "$lib/roles";
  import type { User, CommunityLink } from "$lib/types";
  import CommunityLinkPills from "./CommunityLinkPills.svelte";
  import { ChevronDown, ChevronRight, Globe, Pencil, Users } from "lucide-svelte";
  import * as m from '$lib/paraglide/messages.js';

  const auth = $derived(getAuthState());
  const countries = getCountries();

  // Officials grouped by country
  interface CountryGroup {
    code: string;
    name: string;
    officials: User[];
  }

  let icUsers = $state<User[]>([]);
  let countryGroups = $state<CountryGroup[]>([]);
  let expandedCountries = $state<Set<string>>(new Set());
  let loaded = $state(false);

  async function loadOfficials() {
    const allUsers = await getAllUsers();
    const officials = allUsers.filter(u =>
      !u.deleted_at && u.roles?.some(r => r === "IC" || r === "NC" || r === "Prince")
    );

    // Separate IC users (global)
    icUsers = officials.filter(u => u.roles?.includes("IC"));

    // Group NC/Prince by country
    const grouped = new Map<string, User[]>();
    for (const u of officials) {
      if (!u.roles?.includes("NC") && !u.roles?.includes("Prince")) continue;
      const c = u.country || "??";
      if (!grouped.has(c)) grouped.set(c, []);
      grouped.get(c)!.push(u);
    }

    // Sort: NC before Prince, then by city
    for (const users of grouped.values()) {
      users.sort((a, b) => {
        const aNC = a.roles?.includes("NC") ? 0 : 1;
        const bNC = b.roles?.includes("NC") ? 0 : 1;
        if (aNC !== bNC) return aNC - bNC;
        return (a.city || "").localeCompare(b.city || "");
      });
    }

    const userCountry = auth.user?.country;
    countryGroups = [...grouped.entries()]
      .map(([code, officials]) => ({
        code,
        name: countries[code]?.name || code,
        officials,
      }))
      .sort((a, b) => {
        // User's country always first
        if (userCountry) {
          if (a.code === userCountry) return -1;
          if (b.code === userCountry) return 1;
        }
        return a.name.localeCompare(b.name);
      });

    // Auto-expand user's country
    if (auth.user?.country) {
      expandedCountries = new Set([auth.user.country]);
    }

    loaded = true;
  }

  function toggleCountry(code: string) {
    const next = new Set(expandedCountries);
    if (next.has(code)) next.delete(code);
    else next.add(code);
    expandedCountries = next;
  }

  // Load on mount and refresh on sync
  $effect(() => {
    loadOfficials();
    const handler = (event: { type: string }) => {
      if (event.type === "user" || event.type === "sync_complete") loadOfficials();
    };
    syncManager.addEventListener(handler);
    return () => syncManager.removeEventListener(handler);
  });

  const isOfficial = $derived(
    auth.user?.roles?.some((r: string) => r === "IC" || r === "NC" || r === "Prince") ?? false
  );

  // Collect all IC community links grouped by type
  const icLinks = $derived.by(() => {
    const links: CommunityLink[] = [];
    for (const u of icUsers) {
      if (u.community_links) links.push(...u.community_links);
    }
    return links;
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

  <!-- Official edit prompt -->
  {#if isOfficial}
    <a href="/profile" class="flex items-center gap-2 rounded-lg bg-dusk-900 border border-ash-700 px-4 py-3 mb-6 text-sm text-bone-300 hover:bg-dusk-800 transition-colors">
      <Pencil class="w-4 h-4 text-crimson-400 shrink-0" />
      <span>{m.community_add_contact_prompt()} <span class="text-crimson-400 font-medium">{m.community_go_to_profile()}</span></span>
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

  <!-- Country groups -->
  {#if countryGroups.length > 0}
    <div class="space-y-2">
      {#each countryGroups as group}
        {@const isExpanded = expandedCountries.has(group.code)}
        {@const isMyCountry = auth.user?.country === group.code}
        <div class="bg-dusk-950 rounded-lg shadow border border-ash-800 overflow-hidden">
          <button
            onclick={() => toggleCountry(group.code)}
            class="w-full flex items-center justify-between p-4 hover:bg-ash-900/50 transition-colors text-left"
          >
            <div class="flex items-center gap-2">
              <span class="text-lg">{getCountryFlag(group.code)}</span>
              <span class="font-medium text-bone-100">{group.name}</span>
              {#if isMyCountry}
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
                <a href="/users/{official.uid}" class="block p-4 hover:bg-ash-900/30 transition-colors">
                  <div class="flex items-start justify-between gap-4">
                    <div class="min-w-0 flex-1">
                      <div class="flex items-center gap-2 flex-wrap">
                        <span class="font-medium text-bone-100">{official.name}</span>
                        {#each official.roles.filter(r => r === "NC" || r === "Prince" || r === "IC") as role}
                          <span class="px-2 py-0.5 rounded text-xs font-medium {getRoleClasses(role)}">{role}</span>
                        {/each}
                      </div>
                      {#if official.city}
                        <div class="text-sm text-ash-400 mt-0.5">{official.city}</div>
                      {/if}
                      {#if official.contact_email || official.contact_discord || official.contact_phone}
                        <div class="flex flex-wrap gap-3 mt-2 text-xs text-ash-400">
                          {#if official.contact_email}
                            <a href="mailto:{official.contact_email}" class="text-crimson-500 hover:text-crimson-400" onclick={(e) => e.stopPropagation()}>{official.contact_email}</a>
                          {/if}
                          {#if official.contact_discord}
                            <span>Discord: {official.contact_discord}</span>
                          {/if}
                          {#if official.contact_phone}
                            {#if official.phone_is_whatsapp}
                              <a href="https://wa.me/{official.contact_phone.replace(/[^0-9]/g, '')}" target="_blank" rel="noopener noreferrer" class="text-crimson-500 hover:text-crimson-400" onclick={(e) => e.stopPropagation()}>WhatsApp: {official.contact_phone}</a>
                            {:else}
                              <span>{official.contact_phone}</span>
                            {/if}
                          {/if}
                        </div>
                      {/if}
                    </div>
                  </div>
                  {#if official.community_links?.length}
                    <div class="mt-2" onclick={(e) => e.stopPropagation()}>
                      <CommunityLinkPills links={official.community_links} />
                    </div>
                  {/if}
                </a>
              {/each}
            </div>
          {/if}
        </div>
      {/each}
    </div>
  {:else}
    <div class="text-center py-12">
      <Users class="mx-auto h-12 w-12 text-ash-600 mb-4" />
      <h3 class="text-lg font-medium text-bone-100 mb-2">{m.community_no_officials()}</h3>
      <p class="text-ash-400">{m.community_no_officials_hint()}</p>
    </div>
  {/if}
{/if}
