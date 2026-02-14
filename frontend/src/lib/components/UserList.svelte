<script lang="ts">
  import { untrack } from "svelte";
  import User from "./User.svelte";
  import { getFilteredUsers, hasAnyUsers, userHasPastSanctions, isUserCurrentlySanctioned } from "$lib/db";
  import { getCountries, getCountryFlag } from "$lib/geonames";
  import { getRoleClasses } from "$lib/roles";
  import { syncManager } from "$lib/sync";
  import { displayContext } from "$lib/displayContext";
  import type { User as UserType, Role } from "$lib/types";
  import Icon from "@iconify/svelte";
  import * as m from '$lib/paraglide/messages.js';

  let filteredUsers = $state<UserType[]>([]);
  let error = $state<string | null>(null);
  let isOnline = $state(navigator.onLine);
  let isSyncing = $state(true); // True until sync_complete received from backend
  let hasLoadedOnce = $state(false); // True after first successful IndexedDB load

  // Create user form
  let showCreateForm = $state(false);
  let editingUserId = $state<string | null>(null);
  let expandedUserId = $state<string | null>(null);
  let isUserEditing = $state(false); // Track when expanded User component is in edit mode

  // Pagination and filtering
  let currentPage = $state(1);
  let pageSize = 250;
  let selectedCountry = $state<string>("all");
  let selectedRoles = $state<Role[]>([]);
  let searchQuery = $state("");
  let filterHasPastSanctions = $state(false);
  let filterCurrentlySanctioned = $state(false);

  // Display refresh scheduling - simple debounce
  let displayRefreshTimer: ReturnType<typeof setTimeout> | undefined;
  let isLoadingUsers = false; // Prevent concurrent loadUsers() calls

  const countries = getCountries();
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

  // Paginate users (filtering happens in IndexedDB query)
  let paginatedUsers = $derived(() => {
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
      const { country, roles, nameSearch, hasPastSanctions, currentlySanctioned } = displayContext.getFilters();
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
      error = e instanceof Error ? e.message : "Failed to load users";
      console.error("Error loading users:", e);
    } finally {
      isLoadingUsers = false;
    }
  }


  function toggleCreateForm() {
    showCreateForm = !showCreateForm;
    if (showCreateForm) {
      editingUserId = null;
    }
  }

  async function handleUserCreated(_created: UserType) {
    // Reload from DB to get sorted data
    showCreateForm = false;
    await loadUsers();
  }

  function handleCreateCancel() {
    showCreateForm = false;
  }

  async function handleUserUpdated(_updatedUser: UserType) {
    editingUserId = null;
    // Reload from DB to get sorted data
    await loadUsers();
  }
  function cancelEditUser() {
    editingUserId = null;
  }

  function toggleExpandUser(uid: string) {
    expandedUserId = expandedUserId === uid ? null : uid;
    // Reset edit tracking when changing expanded user
    if (expandedUserId === null) {
      isUserEditing = false;
    }
  }

  function handleUserEditingChange(editing: boolean) {
    const wasEditing = isUserEditing;
    isUserEditing = editing;
    // If we just exited edit mode, refresh to catch any skipped sync updates
    if (wasEditing && !editing) {
      scheduleDisplayRefresh();
    }
  }

  /**
   * Handle incoming sync user update with filter awareness.
   * Uses debounced refresh to avoid flooding during initial sync.
   */
  function handleSyncUserUpdate(user: UserType) {
    // Check if this user is relevant to current display filters
    if (!displayContext.matchesCurrentFilters(user)) {
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
    // Skip refresh if user is being edited - they might have a modal open
    // The list will refresh when they exit edit mode
    if (isUserEditing) {
      return;
    }

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
      filterCurrentlySanctioned
    );
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

  // Initial load, SSE connection, and online/offline listeners
  // This effect should only run on mount - use untrack to avoid re-running on filter changes
  $effect(() => {
    // Use untrack to prevent filter state from becoming dependencies
    // These calls are for initialization only, not reactive updates
    untrack(() => {
      updateDisplayContext();
      loadUsers();
    });

    // Connect to SSE stream
    syncManager.connect();

    // Listen for sync events
    const handleSyncEvent = (event: any) => {
      if (event.type === "connected") {
        // SSE connected
      } else if (event.type === "user" && event.data) {
        handleSyncUserUpdate(event.data);
      } else if (event.type === "sync_complete") {
        // Historical sync complete - stop showing syncing spinner
        isSyncing = false;
        // Refresh display to show any final data
        scheduleDisplayRefresh();
      } else if (event.type === "error") {
        error = event.error || "Sync error occurred";
        isSyncing = false; // Stop showing syncing on error
      } else if (event.type === "disconnected") {
        // Connection lost - stop syncing state to avoid stuck spinner
        isSyncing = false;
      }
    };

    syncManager.addEventListener(handleSyncEvent);

    const handleOnline = () => {
      isOnline = true;
      untrack(() => syncManager.connect());
    };
    const handleOffline = () => {
      isOnline = false;
    };

    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);

    return () => {
      syncManager.removeEventListener(handleSyncEvent);
      syncManager.disconnect();
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);

      // Clear any pending timers
      if (displayRefreshTimer) {
        clearTimeout(displayRefreshTimer);
      }
    };
  });
</script>

<div class="p-4 sm:p-8">
  <div class="max-w-6xl mx-auto">
    <!-- Header -->
    <div class="mb-8">
      <div class="flex items-center justify-between mb-4">
        <h1 class="text-3xl font-light text-crimson-500">{m.nav_users()}</h1>

        <div class="flex items-center gap-3">
          <button
            id="new-user-button"
            onclick={toggleCreateForm}
            disabled={!isOnline}
            class="px-4 py-2 text-sm font-medium text-bone-100 bg-emerald-700 hover:bg-emerald-600 disabled:bg-ash-700 rounded-lg transition-colors duration-200 shadow-md hover:shadow-lg disabled:cursor-not-allowed"
          >
            {showCreateForm ? m.common_cancel() : m.user_list_new_user()}
          </button>

        </div>
      </div>

      <div class="mb-4">
        <!-- Filters -->
        <div
          class="bg-dusk-950 rounded-lg shadow p-4 mb-4 border border-ash-800"
        >
          <div class="flex flex-wrap gap-4">
            <!-- Name Search -->
            <div class="flex-1 min-w-[200px]">
              <label
                for="name-search"
                class="block text-sm font-medium text-ash-400 mb-1"
              >
                {m.common_search()}
              </label>
              <input
                id="name-search"
                type="text"
                bind:value={searchQuery}
                oninput={handleSearchInput}
                placeholder={m.user_list_search_placeholder()}
                class="w-full px-3 py-2 border border-ash-600 rounded-lg bg-dusk-950 text-ash-200 placeholder:text-ash-600"
              />
            </div>
            <!-- Country Filter -->
            <div class="flex-1 min-w-[200px]">
              <label
                for="country-filter"
                class="block text-sm font-medium text-ash-400 mb-1"
              >
                {m.common_country()}
              </label>
              <select
                id="country-filter"
                onchange={handleCountryChange}
                value={selectedCountry}
                class="w-full px-3 py-2 border border-ash-600 rounded-lg bg-dusk-950 text-ash-200"
              >
                <option value="all">{m.user_list_all_countries()}</option>
                {#each Object.entries(countries) as [code, country]}
                  <option value={code}
                    >{country.name} {getCountryFlag(code)}</option
                  >
                {/each}
              </select>
            </div>
          </div>

          <!-- Role Filters -->
          <div class="mt-4">
            <div class="block text-sm font-medium text-ash-400 mb-2">{m.common_roles()}</div>
            <div class="flex flex-wrap gap-2">
              {#each availableRoles as role}
                <button
                  onclick={() => toggleRole(role)}
                  class="px-3 py-1 rounded text-sm font-medium transition-colors {selectedRoles.includes(
                    role,
                  )
                    ? getRoleClasses(role)
                    : 'bg-ash-800 text-ash-400 hover:bg-ash-700'}"
                >
                  {role}
                </button>
              {/each}
            </div>
          </div>

          <!-- Sanction Filters -->
          <div class="mt-4">
            <div class="block text-sm font-medium text-ash-400 mb-2">{m.sanction_mgr_title()}</div>
            <div class="flex flex-wrap gap-2">
              <button
                onclick={() => toggleSanctionFilter("past")}
                class="px-3 py-1 rounded text-sm font-medium transition-colors {filterHasPastSanctions
                  ? 'bg-crimson-800/60 text-crimson-200'
                  : 'bg-ash-800 text-ash-400 hover:bg-ash-700'}"
              >
                {m.user_list_filter_sanctioned()}
              </button>
              <button
                onclick={() => toggleSanctionFilter("current")}
                class="px-3 py-1 rounded text-sm font-medium transition-colors {filterCurrentlySanctioned
                  ? 'bg-crimson-900/80 text-crimson-200'
                  : 'bg-ash-800 text-ash-400 hover:bg-ash-700'}"
              >
                {m.user_list_filter_active_sanction()}
              </button>
            </div>
          </div>
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
        class="bg-crimson-900/20 border border-crimson-800 rounded-lg p-4 mb-6"
      >
        <p class="text-crimson-300">{error}</p>
      </div>
    {/if}

    <!-- User List -->
    {#if filteredUsers.length > 0}
      <div
        id="users-list-container"
        class="bg-dusk-950 rounded-lg shadow overflow-hidden border border-ash-800"
      >
        <!-- Table Header (hidden on mobile) -->
        <div
          id="users-table-header"
          class="hidden sm:grid sm:grid-cols-12 gap-4 px-6 py-3 bg-ash-900 text-sm font-medium text-ash-300 border-b border-ash-700"
        >
          <div id="header-name" class="col-span-3">{m.common_name()}</div>
          <div id="header-vekn-id" class="col-span-2">{m.add_player_vekn_id_label()}</div>
          <div id="header-country" class="col-span-2">{m.common_country()}</div>
          <div id="header-roles" class="col-span-5">{m.common_roles()}</div>
        </div>

        <!-- User Rows -->
        <div id="users-rows-container" class="divide-y divide-ash-800">
          {#each paginatedUsers() as user (user.uid)}
            {#if editingUserId === user.uid}
              <div class="px-6 py-4">
                <User
                  {user}
                  mode="edit"
                  inline
                  showManagement={isOnline}
                  onupdated={handleUserUpdated}
                  oncancel={cancelEditUser}
                />
              </div>
            {:else if expandedUserId === user.uid}
              <div
                class="px-6 py-4 cursor-pointer"
                onclick={() => toggleExpandUser(user.uid)}
                onkeydown={(e) =>
                  e.key === "Enter" && toggleExpandUser(user.uid)}
                role="button"
                tabindex="0"
              >
                <User
                  {user}
                  mode="view"
                  inline
                  editable={isOnline}
                  showManagement={isOnline}
                  onupdated={handleUserUpdated}
                  oneditingchange={handleUserEditingChange}
                />
              </div>
            {:else}
              <div
                class="user-row px-6 py-4 hover:bg-ash-900/50 transition-colors cursor-pointer"
                onclick={() => toggleExpandUser(user.uid)}
                onkeydown={(e) =>
                  e.key === "Enter" && toggleExpandUser(user.uid)}
                role="button"
                tabindex="0"
              >
                <!-- Mobile Layout -->
                <div class="sm:hidden space-y-2">
                  <div class="flex items-start justify-between">
                    <div>
                      <div class="user-name font-semibold text-bone-100">
                        {user.name}
                        {#if user.nickname}
                          <span class="text-sm text-ash-500"
                            >({user.nickname})</span
                          >
                        {/if}
                      </div>
                      {#if user.vekn_id}
                        <div class="text-sm text-ash-400 mt-1">
                          VEKN: {user.vekn_id}
                        </div>
                      {/if}
                      <div class="text-sm text-ash-400">
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
                          {role}
                        </span>
                      {/each}
                    </div>
                  {/if}
                </div>

                <!-- Desktop Table Layout -->
                <div class="hidden sm:grid sm:grid-cols-12 gap-4 items-center">
                  <div class="col-span-3">
                    <div class="user-name font-semibold text-bone-100">
                      {user.name}
                    </div>
                    {#if user.nickname}
                      <div class="text-sm text-ash-500">
                        {user.nickname}
                      </div>
                    {/if}
                  </div>
                  <div class="col-span-2 text-sm text-ash-400">
                    {user.vekn_id || "—"}
                  </div>
                  <div class="col-span-2 text-sm text-ash-400">
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
                            {role}
                          </span>
                        {/each}
                      </div>
                    {:else}
                      <span class="text-sm text-ash-600">—</span>
                    {/if}
                  </div>
                </div>
              </div>
            {/if}
          {/each}
        </div>
      </div>

      <!-- Pagination Controls -->
      {#if totalPages > 1}
        <div class="mt-6 flex items-center justify-between">
          <div class="text-sm text-ash-400">
            {m.user_list_showing_range({ from: ((currentPage - 1) * pageSize + 1).toString(), to: Math.min(currentPage * pageSize, filteredUsers.length).toString(), total: filteredUsers.length.toString() })}
          </div>
          <div class="flex items-center gap-2">
            <button
              onclick={() => goToPage(currentPage - 1)}
              disabled={currentPage === 1}
              class="px-3 py-1 text-sm font-medium text-ash-300 bg-dusk-950 border border-ash-600 rounded hover:bg-ash-800 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {m.common_previous()}
            </button>
            <span class="text-sm text-ash-400">
              {m.user_list_page_info({ current: currentPage.toString(), total: totalPages.toString() })}
            </span>
            <button
              onclick={() => goToPage(currentPage + 1)}
              disabled={currentPage === totalPages}
              class="px-3 py-1 text-sm font-medium text-ash-300 bg-dusk-950 border border-ash-600 rounded hover:bg-ash-800 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {m.common_next()}
            </button>
          </div>
        </div>
      {:else}
        <div class="mt-6 text-center text-sm text-ash-400">
          {m.user_list_showing_total({ count: filteredUsers.length.toString() })}
        </div>
      {/if}
    {/if}

    <!-- Empty State -->
    {#if !error && filteredUsers.length === 0}
      <div class="text-center py-12">
        {#if isSyncing}
          <!-- Syncing state -->
          <div class="text-ash-500 mb-4">
            <Icon icon="lucide:refresh-cw" class="mx-auto h-12 w-12 animate-spin" />
          </div>
          <h3 class="text-lg font-medium text-bone-100 mb-2">{m.status_syncing()}...</h3>
          <p class="text-ash-400">{m.user_list_loading_from_server()}</p>
        {:else}
          <!-- Truly empty state -->
          <div class="text-ash-600 mb-4">
            <Icon icon="lucide:users" class="mx-auto h-12 w-12" />
          </div>
          <h3 class="text-lg font-medium text-bone-100 mb-2">{m.user_list_no_users()}</h3>
          <p class="text-ash-400">
            {#if searchQuery.trim() || selectedCountry !== "all" || selectedRoles.length > 0 || filterHasPastSanctions || filterCurrentlySanctioned}
              {m.user_list_adjust_filters()}
            {:else}
              {m.user_list_no_users_yet()}
            {/if}
          </p>
        {/if}
      </div>
    {/if}
  </div>
</div>
