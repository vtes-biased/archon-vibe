<script lang="ts">
  import { toUserMessage } from '$lib/errors';
  import { untrack } from "svelte";
  import { goto } from "$app/navigation";
  import User from "./User.svelte";
  import DeceasedIcon from "./DeceasedIcon.svelte";
  import { getFilteredUsers, hasAnyUsers, userHasPastSanctions, isUserCurrentlySanctioned } from "$lib/db";
  import { getCountries, getSortedCountries, getCountryFlag } from "$lib/geonames";
  import { getRoleClasses, getRoleLabel } from "$lib/roles";
  import { syncManager } from "$lib/sync";
  import { getAuthState } from "$lib/stores/auth.svelte";
  import { isOfficial as engineIsOfficial } from "$lib/engine";
  import { displayContext } from "$lib/displayContext";
  import type { User as UserType, Role } from "$lib/types";
  import Button from '$lib/components/Button.svelte';
  import { RefreshCw, Users } from "@lucide/svelte";
  import { syncQueryParams, currentParams, readPageParam, pageParam } from "$lib/url-filters";
  import * as m from '$lib/paraglide/messages.js';

  let filteredUsers = $state<UserType[]>([]);
  let error = $state<string | null>(null);
  let isOnline = $state(navigator.onLine);
  let isSyncing = $state(true); // True until sync_complete received from backend
  let hasLoadedOnce = $state(false); // True after first successful IndexedDB load
  let showSyncing = $state(false);
  // Delay showing syncing spinner to avoid flash on fast IDB reads
  $effect(() => {
    if (hasLoadedOnce || !isSyncing) { showSyncing = false; return; }
    const timer = setTimeout(() => { showSyncing = true; }, 200);
    return () => clearTimeout(timer);
  });

  // Create user form
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

  // Pagination and filtering. The public filters live in the query string (see
  // $lib/url-filters) so leaving for a member page and coming back restores the
  // list; the officials-only triage toggles below stay local — restoring one for
  // a viewer who cannot see its control would filter the list unaccountably.
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
  let filterHasPastSanctions = $state(false);
  let filterCurrentlySanctioned = $state(false);
  // Official-only sponsor-management filters (coopted_by / vekn_id). 'mine' and
  // 'none' are mutually exclusive (a member either was coopted by me or by no one).
  let sponsorFilter = $state<"all" | "mine" | "none">("all");
  let filterNoVekn = $state(false);

  // Display refresh scheduling - simple debounce
  let displayRefreshTimer: ReturnType<typeof setTimeout> | undefined;
  let isLoadingUsers = false; // Prevent concurrent loadUsers() calls

  // Officials receive members' contact info (full projection), so only they can
  // search by email/Discord — advertise it in the placeholder for them alone.
  // Identity, not authority: the search itself is filtered by what synced.
  const isOfficial = $derived(engineIsOfficial(getAuthState().user));

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

  // Mirror the public filters + page into the address bar.
  $effect(() => {
    syncQueryParams({
      q: debouncedSearch.trim() || null,
      country: selectedCountry === "all" ? null : selectedCountry,
      roles: selectedRoles.length ? selectedRoles.join(",") : null,
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
    // Prevent concurrent calls - just schedule a refresh if already loading
    if (isLoadingUsers) {
      scheduleDisplayRefresh();
      return;
    }

    isLoadingUsers = true;
    try {
      error = null;

      // Get filters from display context (single source of truth)
      const { country, roles, nameSearch, hasPastSanctions, currentlySanctioned, sponsor, noVekn } = displayContext.getFilters();
      let users = await getFilteredUsers(country, roles, nameSearch);

      // Apply sanction filters (async per-user checks)
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

      // Track if we have any cached data (used to decide whether to show syncing UI)
      if (!hasLoadedOnce) {
        const hasData = await hasAnyUsers();
        if (hasData) {
          hasLoadedOnce = true;
        }
      }

      // Update pagination context with currently visible users
      updatePaginationContext();
    } catch (e) {
      error = toUserMessage(e, m.user_error_load_users());
      console.error("Error loading users:", e);
    } finally {
      isLoadingUsers = false;
    }
  }


  function toggleCreateForm() {
    showCreateForm = !showCreateForm;
  }

  async function handleUserCreated(_created: UserType) {
    // Reload from DB to get sorted data
    showCreateForm = false;
    await loadUsers();
  }

  function handleCreateCancel() {
    showCreateForm = false;
  }


  /**
   * Handle incoming sync user update with filter awareness.
   * Uses debounced refresh to avoid flooding during initial sync.
   */
  function handleSyncUserUpdate(user: UserType) {
    // Refresh when the update is relevant to the current view. matchesCurrentFilters
    // sees the NEW data, so it only catches users moving INTO the filter — a displayed
    // user edited OUT of it (e.g. country FR→DE while filtering FR) would otherwise
    // linger stale. So also refresh if the user is currently displayed.
    const isDisplayed = filteredUsers.some((u) => u.uid === user.uid);
    if (!isDisplayed && !displayContext.matchesCurrentFilters(user)) {
      return;
    }

    // Always use debounced refresh - this coalesces multiple rapid events
    // The debounce timer is short (100ms) so display updates quickly
    scheduleDisplayRefresh();
  }

  /**
   * Schedule a display refresh. If already scheduled, do nothing.
   * Uses a short debounce to coalesce rapid SSE events.
   * Skips refresh if a user is being edited (might have modal open).
   */
  function scheduleDisplayRefresh() {
    // If refresh already scheduled, do nothing - the pending refresh will pick up new data
    if (displayRefreshTimer) {
      return;
    }

    // Schedule refresh after 100ms - this coalesces multiple rapid events
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
    currentPage = 1; // Reset to first page

    // Update display context immediately before async loadUsers()
    updateDisplayContext();
    loadUsers();
  }

  function handleCountryChange(e: Event) {
    const target = e.target as HTMLSelectElement;
    selectedCountry = target.value;
    currentPage = 1; // Reset to first page

    // Update display context immediately before async loadUsers()
    updateDisplayContext();
    loadUsers();
  }

  /**
   * Update display context with current filter state.
   */
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
    sponsorFilter = sponsorFilter === mode ? "all" : mode; // toggle off if re-clicked
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

  // Debounced search handler
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
      // Update pagination context when page changes
      updatePaginationContext();
    }
  }

  /**
   * Update pagination context based on current state.
   */
  function updatePaginationContext() {
    const start = (currentPage - 1) * pageSize;
    const end = start + pageSize;
    const visibleUsers = filteredUsers.slice(start, end);
    displayContext.setPagination(currentPage, pageSize, visibleUsers);
  }

  // Initial load and SSE event listeners
  // SSE connection is managed by +layout.svelte — this component only listens for events
  $effect(() => {
    // Use untrack to prevent filter state from becoming dependencies
    untrack(() => {
      updateDisplayContext();
      loadUsers();
    });

    // If sync already completed before mount, refresh immediately
    if (syncManager.isSynced) {
      isSyncing = false;
      untrack(() => scheduleDisplayRefresh());
    }

    // Listen for sync events
    const handleSyncEvent = (event: any) => {
      if (event.type === "user" && event.data) {
        handleSyncUserUpdate(event.data);
      } else if (event.type === "sync_complete") {
        // Historical sync complete - stop showing syncing spinner
        isSyncing = false;
        // Refresh display to show any final data
        scheduleDisplayRefresh();
      } else if (event.type === "error") {
        error = event.error || m.sync_error_generic();
        isSyncing = false; // Stop showing syncing on error
      } else if (event.type === "disconnected") {
        // Connection lost - stop syncing state to avoid stuck spinner
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

      // Clear any pending timers
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
    <!-- Header -->
    <div class="mb-8">
      <div class="flex items-center justify-between mb-4">
        <h1 class="text-3xl font-semibold text-accent">{m.nav_users()}</h1>

        <div class="flex items-center gap-3">
          <Button
            id="new-user-button"
            variant="primary"
            size="lg"
            class="shadow-md hover:shadow-lg"
            onclick={toggleCreateForm}
            disabled={!isOnline}
          >
            {showCreateForm ? m.common_cancel() : m.user_list_new_user()}
          </Button>

        </div>
      </div>

      <div class="mb-4">
        <!-- Filters -->
        <div
          class="bg-surface-card rounded-lg shadow p-4 mb-4 border border-line"
        >
          <div class="flex flex-wrap gap-4">
            <!-- Name Search -->
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
            <!-- Country Filter -->
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

          <!-- Role Filters -->
          <div class="mt-4">
            <div class="block text-sm font-medium text-ink-muted mb-2">{m.common_roles()}</div>
            <div class="flex flex-wrap gap-2">
              {#each availableRoles as role}
                <button
                  onclick={() => toggleRole(role)}
                  class="px-3 min-h-[44px] inline-flex items-center rounded text-sm font-medium transition-colors {selectedRoles.includes(
                    role,
                  )
                    ? getRoleClasses(role)
                    : 'bg-surface-hover text-ink-muted hover:bg-surface-active'}"
                >
                  {getRoleLabel(role)}
                </button>
              {/each}
            </div>
          </div>

          <!-- Sanction Filters -->
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

          <!-- Sponsor / VEKN filters (organizer & NC sponsor-management workflow) -->
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

    <!-- Create User Form -->
    {#if showCreateForm}
      <div class="mb-6">
        <User
          mode="create"
          oncreated={handleUserCreated}
          oncancel={handleCreateCancel}
        />
      </div>
    {/if}

    <!-- Error State -->
    {#if error}
      <div
        class="bg-accent-soft/20 border border-accent-soft-border rounded-lg p-4 mb-6"
      >
        <p class="text-link-soft">{error}</p>
      </div>
    {/if}

    <!-- User List -->
    {#if filteredUsers.length > 0}
      <div
        id="users-list-container"
        class="bg-surface-card rounded-lg shadow overflow-hidden border border-line"
      >
        <!-- Table Header (hidden on mobile) -->
        <div
          id="users-table-header"
          class="hidden sm:grid sm:grid-cols-12 gap-4 px-6 py-3 bg-surface-muted text-sm font-medium text-ink border-b border-line-strong"
        >
          <div id="header-name" class="col-span-3">{m.common_name()}</div>
          <div id="header-vekn-id" class="col-span-2">{m.add_player_vekn_id_label()}</div>
          <div id="header-country" class="col-span-2">{m.common_country()}</div>
          <div id="header-roles" class="col-span-5">{m.common_roles()}</div>
        </div>

        <!-- User Rows -->
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
                <!-- Mobile Layout -->
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
                        <span
                          class="px-2 py-1 rounded text-xs font-medium {getRoleClasses(
                            role,
                          )}"
                        >
                          {getRoleLabel(role)}
                        </span>
                      {/each}
                    </div>
                  {/if}
                </div>

                <!-- Desktop Table Layout -->
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
                          <span
                            class="px-2 py-1 rounded text-xs font-medium {getRoleClasses(
                              role,
                            )}"
                          >
                            {getRoleLabel(role)}
                          </span>
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

      <!-- Pagination Controls -->
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

    <!-- Empty State -->
    {#if !error && filteredUsers.length === 0 && (hasLoadedOnce || showSyncing)}
      <div class="text-center py-12">
        {#if showSyncing}
          <!-- Syncing state -->
          <div class="text-ink-faint mb-4">
            <RefreshCw class="mx-auto h-12 w-12 animate-spin" />
          </div>
          <h3 class="text-lg font-medium text-ink-strong mb-2">{m.status_syncing()}...</h3>
          <p class="text-ink-muted">{m.user_list_loading_from_server()}</p>
        {:else}
          <!-- Truly empty state -->
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
