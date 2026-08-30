<script lang="ts">
  import { toUserMessage } from '$lib/errors';
  import { untrack } from "svelte";
  import { goto } from "$app/navigation";
  import User from "./User.svelte";
  import DeceasedIcon from "./DeceasedIcon.svelte";
  import { getFilteredUsers, hasAnyUsers, userHasPastSanctions, isUserCurrentlySanctioned } from "$lib/db";
  import { getCountries, getSortedCountries, getCountryFlag } from "$lib/geonames";
  import { getRoleTone } from "$lib/roles";
  import Badge, { badgeToneClass } from "$lib/components/Badge.svelte";
  import { syncManager } from "$lib/sync";
  import { getAuthState } from "$lib/stores/auth.svelte";
  import { isOfficial as engineIsOfficial, canSponsorMember } from "$lib/engine";
  import { displayContext } from "$lib/displayContext";
  import type { User as UserType, Role } from "$lib/types";
  import type { UserListItem } from "$lib/db";
  import Button from '$lib/components/Button.svelte';
  import { RefreshCw, Users, Plus, X } from "@lucide/svelte";
  import { dialogPanel } from "$lib/actions/dialog";
  import { syncQueryParams, currentParams, readPageParam, pageParam } from "$lib/url-filters";
  import * as m from '$lib/paraglide/messages.js';

  let filteredUsers = $state<UserListItem[]>([]);
  let error = $state<string | null>(null);
  let isOnline = $state(navigator.onLine);
  let isSyncing = $state(true);
  let hasLoadedOnce = $state(false);
  let showSyncing = $state(false);
  // Delay showing syncing spinner to avoid flash on fast IDB reads
  $effect(() => {
    if (hasLoadedOnce || !isSyncing) { showSyncing = false; return; }
    const timer = setTimeout(() => { showSyncing = true; }, 200);
    return () => clearTimeout(timer);
  });

  let showCreateForm = $state(false);

  const availableRoles: Role[] = [
    "IC",
    "NC",
    "Prince",
    "Ethics",
    "PTC",
    "PT",
    "Judge",
    "DEV",
  ];

  // Filters every signed-in viewer can see live in the query string (url-filters) so leaving and returning restores the list;
  // the officials-only sponsor and no-VEKN toggles stay local — restoring one for a viewer who can't see its control would filter unaccountably.
  const urlParams = currentParams();
  let currentPage = $state(readPageParam() + 1);
  let pageSize = 250;
  let selectedCountry = $state<string>(urlParams.get("country") ?? "all");
  let selectedRoles = $state<Role[]>(
    (urlParams.get("roles")?.split(",").filter(r => availableRoles.includes(r as Role)) ?? []) as Role[],
  );
  let searchQuery = $state(urlParams.get("q") ?? "");
  // Mirrored to the URL only once the search debounce fires, not per keystroke.
  let debouncedSearch = $state(urlParams.get("q") ?? "");
  let filterHasPastSanctions = $state(urlParams.get("past_sanctions") === "true");
  let filterCurrentlySanctioned = $state(urlParams.get("sanctioned") === "true");
  // Official-only sponsor-management filters (coopted_by / vekn_id). 'mine' and
  // 'none' are mutually exclusive (a member either was coopted by me or by no one).
  let sponsorFilter = $state<"all" | "mine" | "none">("all");
  let filterNoVekn = $state(false);

  let displayRefreshTimer: ReturnType<typeof setTimeout> | undefined;
  let isLoadingUsers = false;

  // Officials receive members' contact info (full projection), so only they can search by email/Discord
  // — advertise it in the placeholder for them alone. Identity, not authority: the search is filtered by what synced.
  const isOfficial = $derived(engineIsOfficial(getAuthState().user));

  const canSponsor = $derived(canSponsorMember(getAuthState().user).allowed);

  const countries = getCountries();
  const sortedCountries = getSortedCountries();

  // A page restored from the URL can point past the end — clamp once loaded, or
  // the list renders empty with no controls to get back.
  $effect(() => {
    if (!hasLoadedOnce) return;
    const last = Math.max(1, totalPages);
    if (currentPage > last) untrack(() => { currentPage = last; });
  });

  const hasFilters = $derived(
    !!searchQuery.trim() || selectedCountry !== "all" || selectedRoles.length > 0
      || filterHasPastSanctions || filterCurrentlySanctioned || sponsorFilter !== "all" || filterNoVekn,
  );

  // One way out of a filtered-empty list, including one the nav menu restored.
  function clearFilters() {
    searchQuery = "";
    debouncedSearch = "";
    selectedCountry = "all";
    selectedRoles = [];
    filterHasPastSanctions = false;
    filterCurrentlySanctioned = false;
    sponsorFilter = "all";
    filterNoVekn = false;
    currentPage = 1;
    updateDisplayContext();
    loadUsers();
  }

  $effect(() => {
    syncQueryParams({
      q: debouncedSearch.trim() || null,
      country: selectedCountry === "all" ? null : selectedCountry,
      roles: selectedRoles.length ? selectedRoles.join(",") : null,
      past_sanctions: filterHasPastSanctions ? "true" : null,
      sanctioned: filterCurrentlySanctioned ? "true" : null,
      page: pageParam(currentPage - 1),
    });
  });

  // Paginate users (filtering happens in IndexedDB query)
  let paginatedUsers = $derived.by(() => {
    const start = (currentPage - 1) * pageSize;
    const end = start + pageSize;
    return filteredUsers.slice(start, end);
  });

  let totalPages = $derived(Math.ceil(filteredUsers.length / pageSize));

  async function loadUsers() {
    if (isLoadingUsers) {
      scheduleDisplayRefresh();
      return;
    }

    isLoadingUsers = true;
    try {
      error = null;

      const { country, roles, nameSearch, hasPastSanctions, currentlySanctioned, sponsor, noVekn } = displayContext.getFilters();
      let users = await getFilteredUsers(country, roles, nameSearch);

      if (hasPastSanctions || currentlySanctioned) {
        const sanctionChecks = await Promise.all(
          users.map(async (user) => {
            let passes = true;
            if (hasPastSanctions) {
              passes = passes && await userHasPastSanctions(user.uid);
            }
            if (currentlySanctioned) {
              passes = passes && await isUserCurrentlySanctioned(user.uid);
            }
            return { user, passes };
          })
        );
        users = sanctionChecks.filter(({ passes }) => passes).map(({ user }) => user);
      }

      // Sponsor / VEKN filters (officials only — coopted_by is full-projection).
      if (sponsor === "mine") {
        const myUid = getAuthState().user?.uid;
        users = users.filter((u) => !!myUid && u.coopted_by === myUid);
      } else if (sponsor === "none") {
        users = users.filter((u) => !u.coopted_by);
      }
      if (noVekn) {
        users = users.filter((u) => !u.vekn_id);
      }

      filteredUsers = users;

      if (!hasLoadedOnce) {
        const hasData = await hasAnyUsers();
        if (hasData) {
          hasLoadedOnce = true;
        }
      }

      updatePaginationContext();
    } catch (e) {
      error = toUserMessage(e, m.user_error_load_users());
      console.error("Error loading users:", e);
    } finally {
      isLoadingUsers = false;
    }
  }


  async function handleUserCreated(_created: UserType) {
    showCreateForm = false;
    await loadUsers();
  }

  function handleCreateCancel() {
    showCreateForm = false;
  }


  function handleSyncUserUpdate(user: UserType) {
    // matchesCurrentFilters sees the NEW data, so it only catches users moving INTO the filter — a
    // displayed user edited OUT of it (e.g. country FR→DE while filtering FR) would otherwise linger stale, so also refresh if currently displayed.
    const isDisplayed = filteredUsers.some((u) => u.uid === user.uid);
    if (!isDisplayed && !displayContext.matchesCurrentFilters(user)) {
      return;
    }

    scheduleDisplayRefresh();
  }

  function scheduleDisplayRefresh() {
    if (displayRefreshTimer) {
      return;
    }

    displayRefreshTimer = setTimeout(async () => {
      displayRefreshTimer = undefined;
      await loadUsers();
    }, 100);
  }

  function toggleRole(role: Role) {
    if (selectedRoles.includes(role)) {
      selectedRoles = selectedRoles.filter((r) => r !== role);
    } else {
      selectedRoles = [...selectedRoles, role];
    }
    currentPage = 1;

    updateDisplayContext();
    loadUsers();
  }

  function handleCountryChange(e: Event) {
    const target = e.target as HTMLSelectElement;
    selectedCountry = target.value;
    currentPage = 1;

    updateDisplayContext();
    loadUsers();
  }

  function updateDisplayContext() {
    const country = selectedCountry !== "all" ? selectedCountry : undefined;
    const roles = selectedRoles.length > 0 ? selectedRoles : undefined;
    const search = searchQuery.trim() || undefined;
    displayContext.setFilters(
      country,
      roles,
      search,
      filterHasPastSanctions,
      filterCurrentlySanctioned,
      sponsorFilter !== "all" ? sponsorFilter : undefined,
      filterNoVekn
    );
  }

  function setSponsorFilter(mode: "mine" | "none") {
    sponsorFilter = sponsorFilter === mode ? "all" : mode;
    currentPage = 1;
    updateDisplayContext();
    loadUsers();
  }

  function toggleNoVekn() {
    filterNoVekn = !filterNoVekn;
    currentPage = 1;
    updateDisplayContext();
    loadUsers();
  }

  function toggleSanctionFilter(type: "past" | "current") {
    if (type === "past") {
      filterHasPastSanctions = !filterHasPastSanctions;
    } else {
      filterCurrentlySanctioned = !filterCurrentlySanctioned;
    }
    currentPage = 1;
    updateDisplayContext();
    loadUsers();
  }

  let searchDebounceTimer: ReturnType<typeof setTimeout> | null = null;
  function handleSearchInput() {
    if (searchDebounceTimer) clearTimeout(searchDebounceTimer);
    searchDebounceTimer = setTimeout(() => {
      debouncedSearch = searchQuery;
      currentPage = 1;
      updateDisplayContext();
      loadUsers();
    }, 200);
  }

  function goToPage(page: number) {
    if (page >= 1 && page <= totalPages) {
      currentPage = page;
      updatePaginationContext();
    }
  }

  function updatePaginationContext() {
    const start = (currentPage - 1) * pageSize;
    const end = start + pageSize;
    const visibleUsers = filteredUsers.slice(start, end);
    displayContext.setPagination(currentPage, pageSize, visibleUsers);
  }

  // SSE connection is managed by +layout.svelte — this component only listens for events
  $effect(() => {
    untrack(() => {
      updateDisplayContext();
      loadUsers();
    });

    if (syncManager.isSynced) {
      isSyncing = false;
      untrack(() => scheduleDisplayRefresh());
    }

    const handleSyncEvent = (event: any) => {
      if (event.type === "user" && event.data) {
        handleSyncUserUpdate(event.data);
      } else if (event.type === "sync_complete") {
        isSyncing = false;
        scheduleDisplayRefresh();
      } else if (event.type === "error") {
        error = event.error || m.sync_error_generic();
        isSyncing = false;
      } else if (event.type === "disconnected") {
        isSyncing = false;
      }
    };

    syncManager.addEventListener(handleSyncEvent);

    const handleOnline = () => { isOnline = true; };
    const handleOffline = () => { isOnline = false; };

    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);

    return () => {
      syncManager.removeEventListener(handleSyncEvent);
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);

      if (displayRefreshTimer) {
        clearTimeout(displayRefreshTimer);
      }
      if (searchDebounceTimer) {
        clearTimeout(searchDebounceTimer);
      }
    };
  });
</script>

<div class="p-4 sm:p-8">
  <div class="max-w-6xl mx-auto">
    <div class="mb-8">
      <div class="flex items-center justify-between mb-4">
        <h1 class="text-3xl font-semibold text-accent">{m.nav_users()}</h1>

        {#if canSponsor}
          <Button
            variant="create"
            size="lg"
            onclick={() => showCreateForm = true}
            disabled={!isOnline}
          >
            <Plus class="w-4 h-4" aria-hidden="true" />
            {m.user_list_new_user()}
          </Button>
        {/if}
      </div>

      <div class="mb-4">
        <div
          class="bg-surface-card rounded-lg shadow p-4 mb-4 border border-line"
        >
          <div class="flex flex-wrap gap-4">
            <div class="flex-1 min-w-[200px]">
              <label
                for="name-search"
                class="block text-sm font-medium text-ink-muted mb-1"
              >
                {m.common_search()}
              </label>
              <input
                id="name-search"
                type="text"
                bind:value={searchQuery}
                oninput={handleSearchInput}
                placeholder={isOfficial ? m.user_list_search_placeholder_contacts() : m.user_list_search_placeholder()}
                class="w-full px-3 py-2 border border-line-strong rounded-lg bg-surface-card text-ink-bright placeholder:text-ink-faint"
              />
            </div>
            <div class="flex-1 min-w-[200px]">
              <label
                for="country-filter"
                class="block text-sm font-medium text-ink-muted mb-1"
              >
                {m.common_country()}
              </label>
              <select
                id="country-filter"
                onchange={handleCountryChange}
                value={selectedCountry}
                class="w-full pl-3 pr-9 py-2 border border-line-strong rounded-lg bg-surface-card text-ink-bright"
              >
                <option value="all">{m.user_list_all_countries()}</option>
                {#each sortedCountries as country}
                  <option value={country.iso_code}
                    >{country.name} {getCountryFlag(country.iso_code)}</option
                  >
                {/each}
              </select>
            </div>
          </div>

          <div class="mt-4">
            <div class="block text-sm font-medium text-ink-muted mb-2">{m.common_roles()}</div>
            <div class="flex flex-wrap gap-2">
              {#each availableRoles as role}
                <button
                  onclick={() => toggleRole(role)}
                  class="px-3 min-h-[44px] inline-flex items-center rounded text-sm font-medium transition-colors {selectedRoles.includes(
                    role,
                  )
                    ? badgeToneClass(getRoleTone(role))
                    : 'bg-surface-hover text-ink-muted hover:bg-surface-active'}"
                >
                  {role}
                </button>
              {/each}
            </div>
          </div>

          <div class="mt-4">
            <div class="block text-sm font-medium text-ink-muted mb-2">{m.sanction_mgr_title()}</div>
            <div class="flex flex-wrap gap-2">
              <button
                onclick={() => toggleSanctionFilter("past")}
                class="px-3 min-h-[44px] inline-flex items-center rounded text-sm font-medium transition-colors {filterHasPastSanctions
                  ? 'bg-accent-soft/60 text-link-soft'
                  : 'bg-surface-hover text-ink-muted hover:bg-surface-active'}"
              >
                {m.user_list_filter_sanctioned()}
              </button>
              <button
                onclick={() => toggleSanctionFilter("current")}
                class="px-3 min-h-[44px] inline-flex items-center rounded text-sm font-medium transition-colors {filterCurrentlySanctioned
                  ? 'bg-accent-soft/80 text-link-soft'
                  : 'bg-surface-hover text-ink-muted hover:bg-surface-active'}"
              >
                {m.user_list_filter_active_sanction()}
              </button>
            </div>
          </div>

          {#if isOfficial}
            <div class="mt-4">
              <div class="block text-sm font-medium text-ink-muted mb-2">{m.user_list_filter_sponsor_title()}</div>
              <div class="flex flex-wrap gap-2">
                <button
                  onclick={() => setSponsorFilter("mine")}
                  aria-pressed={sponsorFilter === "mine"}
                  disabled={filterNoVekn}
                  title={filterNoVekn ? m.user_list_filter_recruits_have_vekn() : undefined}
                  class="px-3 min-h-[44px] inline-flex items-center rounded text-sm font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed {sponsorFilter === 'mine'
                    ? 'bg-accent-soft/60 text-link-soft'
                    : 'bg-surface-hover text-ink-muted hover:bg-surface-active'}"
                >
                  {m.user_list_filter_my_recruits()}
                </button>
                <button
                  onclick={() => setSponsorFilter("none")}
                  aria-pressed={sponsorFilter === "none"}
                  class="px-3 min-h-[44px] inline-flex items-center rounded text-sm font-medium transition-colors {sponsorFilter === 'none'
                    ? 'bg-accent-soft/60 text-link-soft'
                    : 'bg-surface-hover text-ink-muted hover:bg-surface-active'}"
                >
                  {m.user_list_filter_no_sponsor()}
                </button>
                <button
                  onclick={toggleNoVekn}
                  aria-pressed={filterNoVekn}
                  disabled={sponsorFilter === "mine"}
                  title={sponsorFilter === "mine" ? m.user_list_filter_recruits_have_vekn() : undefined}
                  class="px-3 min-h-[44px] inline-flex items-center rounded text-sm font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed {filterNoVekn
                    ? 'bg-accent-soft/60 text-link-soft'
                    : 'bg-surface-hover text-ink-muted hover:bg-surface-active'}"
                >
                  {m.user_list_filter_no_vekn()}
                </button>
              </div>
            </div>
          {/if}
        </div>
      </div>
    </div>

    {#if error}
      <div
        class="bg-accent-soft/20 border border-accent-soft-border rounded-lg p-4 mb-6"
      >
        <p class="text-link-soft">{error}</p>
      </div>
    {/if}

    {#if filteredUsers.length > 0}
      <div
        id="users-list-container"
        class="bg-surface-card rounded-lg shadow overflow-hidden border border-line"
      >
        <div
          id="users-table-header"
          class="hidden sm:grid sm:grid-cols-12 gap-4 px-6 py-3 bg-surface-muted text-sm font-medium text-ink border-b border-line-strong"
        >
          <div id="header-name" class="col-span-3">{m.common_name()}</div>
          <div id="header-vekn-id" class="col-span-2">{m.add_player_vekn_id_label()}</div>
          <div id="header-country" class="col-span-2">{m.common_country()}</div>
          <div id="header-roles" class="col-span-5">{m.common_roles()}</div>
        </div>

        <div id="users-rows-container" class="divide-y divide-line">
          {#each paginatedUsers as user (user.uid)}
              <div
                class="user-row px-6 py-4 hover:bg-surface-muted/50 transition-colors cursor-pointer"
                onclick={() => goto(`/users/${user.uid}`)}
                onkeydown={(e) =>
                  e.key === "Enter" && goto(`/users/${user.uid}`)}
                role="button"
                tabindex="0"
              >
                <div class="sm:hidden space-y-2">
                  <div class="flex items-start justify-between">
                    <div>
                      <div class="user-name font-semibold text-ink-strong">
                        <DeceasedIcon deceased={user.deceased_at} />{user.name}
                        {#if user.nickname}
                          <span class="text-sm text-ink-faint"
                            >({user.nickname})</span
                          >
                        {/if}
                      </div>
                      {#if user.vekn_id}
                        <div class="text-sm text-ink-muted mt-1">
                          VEKN: {user.vekn_id}
                        </div>
                      {/if}
                      <div class="text-sm text-ink-muted">
                        {user.country
                          ? `${getCountryFlag(user.country)} ${countries[user.country]?.name || user.country}`
                          : m.common_na()}
                      </div>
                    </div>
                  </div>
                  {#if user.roles.length > 0}
                    <div class="flex flex-wrap gap-1">
                      {#each user.roles as role}
                        <Badge tone={getRoleTone(role)}>{role}</Badge>
                      {/each}
                    </div>
                  {/if}
                </div>

                <div class="hidden sm:grid sm:grid-cols-12 gap-4 items-center">
                  <div class="col-span-3">
                    <div class="user-name font-semibold text-ink-strong">
                      <DeceasedIcon deceased={user.deceased_at} />{user.name}
                    </div>
                    {#if user.nickname}
                      <div class="text-sm text-ink-faint">
                        {user.nickname}
                      </div>
                    {/if}
                  </div>
                  <div class="col-span-2 text-sm text-ink-muted">
                    {user.vekn_id || "—"}
                  </div>
                  <div class="col-span-2 text-sm text-ink-muted">
                    {user.country
                      ? `${getCountryFlag(user.country)} ${countries[user.country]?.name || user.country}`
                      : m.common_na()}
                  </div>
                  <div class="col-span-5">
                    {#if user.roles.length > 0}
                      <div class="flex flex-wrap gap-1">
                        {#each user.roles as role}
                          <Badge tone={getRoleTone(role)}>{role}</Badge>
                        {/each}
                      </div>
                    {:else}
                      <span class="text-sm text-ink-faint">—</span>
                    {/if}
                  </div>
                </div>
              </div>
          {/each}
        </div>
      </div>

      {#if totalPages > 1}
        <div class="mt-6 flex items-center justify-between">
          <div class="text-sm text-ink-muted">
            {m.user_list_showing_range({ from: ((currentPage - 1) * pageSize + 1).toString(), to: Math.min(currentPage * pageSize, filteredUsers.length).toString(), total: filteredUsers.length.toString() })}
          </div>
          <div class="flex items-center gap-2">
            <button
              onclick={() => goToPage(currentPage - 1)}
              disabled={currentPage === 1}
              class="px-3 py-1 text-sm font-medium text-ink bg-surface-card border border-line-strong rounded hover:bg-surface-hover disabled:opacity-50"
            >
              {m.common_previous()}
            </button>
            <span class="text-sm text-ink-muted">
              {m.user_list_page_info({ current: currentPage.toString(), total: totalPages.toString() })}
            </span>
            <button
              onclick={() => goToPage(currentPage + 1)}
              disabled={currentPage === totalPages}
              class="px-3 py-1 text-sm font-medium text-ink bg-surface-card border border-line-strong rounded hover:bg-surface-hover disabled:opacity-50"
            >
              {m.common_next()}
            </button>
          </div>
        </div>
      {:else}
        <div class="mt-6 text-center text-sm text-ink-muted">
          {m.user_list_showing_total({ count: filteredUsers.length.toString() })}
        </div>
      {/if}
    {/if}

    {#if !error && filteredUsers.length === 0 && (hasLoadedOnce || showSyncing)}
      <div class="text-center py-12">
        {#if showSyncing}
          <div class="text-ink-faint mb-4">
            <RefreshCw class="mx-auto h-12 w-12 animate-spin" />
          </div>
          <h3 class="text-lg font-medium text-ink-strong mb-2">{m.status_syncing()}...</h3>
          <p class="text-ink-muted">{m.user_list_loading_from_server()}</p>
        {:else}
          <div class="text-ink-faint mb-4">
            <Users class="mx-auto h-12 w-12" />
          </div>
          <h3 class="text-lg font-medium text-ink-strong mb-2">{m.user_list_no_users()}</h3>
          <p class="text-ink-muted">
            {#if hasFilters}
              {m.user_list_adjust_filters()}
            {:else}
              {m.user_list_no_users_yet()}
            {/if}
          </p>
          {#if hasFilters}
            <Button variant="secondary" size="md" class="mt-4" onclick={clearFilters}>
              {m.filters_clear()}
            </Button>
          {/if}
        {/if}
      </div>
    {/if}
  </div>
</div>

{#if showCreateForm && canSponsor}
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
  <div
    class="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm sm:flex sm:items-center sm:justify-center sm:p-4"
    role="presentation"
    onclick={handleCreateCancel}
  >
    <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
    <div
      use:dialogPanel={handleCreateCancel}
      role="dialog"
      aria-modal="true"
      aria-labelledby="create-user-title"
      tabindex="-1"
      class="bg-surface-card w-full h-full overflow-y-auto pt-safe-t pb-safe-b sm:pt-0 sm:h-auto sm:max-h-[85dvh] sm:max-w-lg sm:rounded-lg sm:border sm:border-line sm:shadow-xl"
      onclick={(e) => e.stopPropagation()}
      onkeydown={(e) => e.stopPropagation()}
    >
      <div class="p-6 border-b border-line flex items-center justify-between gap-4">
        <h2 id="create-user-title" class="text-xl font-medium text-ink-strong">
          {m.user_list_new_user()}
        </h2>
        <button onclick={handleCreateCancel} aria-label={m.common_close()} class="p-2 text-ink-faint hover:text-link transition-colors">
          <X class="w-5 h-5" />
        </button>
      </div>

      <div class="p-6">
        <User
          inline
          mode="create"
          oncreated={handleUserCreated}
          oncancel={handleCreateCancel}
        />
      </div>
    </div>
  </div>
{/if}
