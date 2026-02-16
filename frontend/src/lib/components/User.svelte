<script lang="ts">
  import type { User, Role } from "$lib/types";
  import { createUser, updateUser, uploadAvatar } from "$lib/api";
  import { getCountries, getCountryFlag } from "$lib/geonames";
  import { getRoleClasses } from "$lib/roles";
  import { getAuthState } from "$lib/stores/auth.svelte";
  import { canChangeRole as engineCanChangeRole, canEditUser } from "$lib/engine";
  import CityAutocomplete from "./CityAutocomplete.svelte";
  import AvatarCropper from "./AvatarCropper.svelte";
  import SanctionsManager from "./SanctionsManager.svelte";
  import { Loader2, X, User as UserIcon, Camera, SquarePen } from "lucide-svelte";
  import * as m from '$lib/paraglide/messages.js';

  let {
    user,
    mode = "view",
    editable = true,
    inline = false,
    onupdated,
    oncreated,
    oncancel,
    oneditingchange,
  }: {
    user?: User;
    mode?: "view" | "edit" | "create";
    editable?: boolean;
    inline?: boolean;
    onupdated?: (user: User) => void;
    oncreated?: (user: User) => void;
    oncancel?: () => void;
    oneditingchange?: (editing: boolean) => void;
  } = $props();

  const auth = $derived(getAuthState());

  // Check if current user can change a specific role (using engine)
  function canChangeRole(role: Role): boolean {
    if (!auth.user) return false;
    if (mode === "create") {
      // For create mode, assume user will have VEKN ID (auto-allocated by backend)
      // Create a minimal user context for permission check
      const targetContext = {
        roles: [] as Role[],
        country: editCountry || null,
        vekn_id: "pending",  // Will be auto-allocated
      };
      try {
        return engineCanChangeRole(auth.user, targetContext as User, role).allowed;
      } catch {
        return false;
      }
    }
    // For edit mode, use actual user data
    if (!user) return false;
    try {
      return engineCanChangeRole(auth.user, user, role).allowed;
    } catch {
      // Engine not initialized yet
      return false;
    }
  }

  // Avatar state
  let showAvatarCropper = $state(false);

  // Check if current user can edit this user's avatar (only own avatar)
  const canEditAvatar = $derived(() => {
    if (!auth.user || !user) return false;
    return auth.user.uid === user.uid;
  });

  async function handleAvatarSave(blob: Blob) {
    if (!user) return;
    try {
      await uploadAvatar(user.uid, blob);
      showAvatarCropper = false;
      // The SSE event will update the user with the new avatar_path
    } catch {
      // Error toast shown by uploadAvatar
    }
  }

  let _isEditingLocal = $state<boolean | null>(null);
  const isEditing = $derived(_isEditingLocal ?? (mode === "edit" || mode === "create"));

  let editName = $state("");
  let editCountry = $state("");
  let editCity = $state("");
  let editNickname = $state("");
  let editEmail = $state("");  // For create mode: optional email to send invite
  let editRoles = $state<Role[]>([]);
  let saving = $state(false);
  let error = $state("");
  // Track if we've initialized edit fields for current edit session
  let editInitialized = $state(false);

  // Debounce timer for text fields
  let debounceTimer: ReturnType<typeof setTimeout> | null = null;
  const DEBOUNCE_MS = 500;

  // Initialize edit fields only once when first entering edit mode
  // Don't react to user prop changes while editing (we're the source of truth)
  $effect(() => {
    if (isEditing && !editInitialized && user) {
      editName = user.name || "";
      editCountry = user.country || "";
      editCity = user.city || "";
      editNickname = user.nickname || "";
      editRoles = [...user.roles];
      editInitialized = true;
    } else if (!isEditing) {
      // Reset flag when exiting edit mode
      editInitialized = false;
    }
  });

  // Auto-save function (for edit mode only, not create)
  async function autoSave() {
    if (mode === "create" || !user) return;
    if (!editName.trim() || !editCountry.trim()) {
      error = m.user_error_name_country_required();
      return;
    }

    try {
      saving = true;
      error = "";
      const updated = await updateUser(
        user.uid,
        editName.trim(),
        editCountry.trim().toUpperCase(),
        undefined,  // VEKN ID managed via Sponsor/Link/Abandon only
        editCity.trim() || null,
        editNickname.trim() || null,
        editRoles,
      );
      onupdated?.(updated);
    } catch (e) {
      error = e instanceof Error ? e.message : "Failed to save";
    } finally {
      saving = false;
    }
  }

  // Debounced auto-save for text fields
  function debouncedAutoSave() {
    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      autoSave();
    }, DEBOUNCE_MS);
  }

  // Immediate auto-save for select/role changes
  function immediateAutoSave() {
    if (debounceTimer) clearTimeout(debounceTimer);
    autoSave();
  }

  // Load countries for select box
  const countries = getCountries();
  const sortedCountries = Object.values(countries).sort((a, b) =>
    a.name.localeCompare(b.name),
  );

  const availableRoles: Role[] = [
    "IC",
    "NC",
    "Prince",
    "Ethics",
    "PTC",
    "PT",
    "Rulemonger",
    "Judge",
    "Judgekin",
    "DEV",
  ];

  function startEdit() {
    if (!user) return;
    _isEditingLocal = true;
    editName = user.name;
    editCountry = user.country || "";
    editCity = user.city || "";
    editNickname = user.nickname || "";
    editRoles = [...user.roles];
    editInitialized = true;
    error = "";
    oneditingchange?.(true);
  }

  function cancelEdit() {
    if (mode === "create") {
      oncancel?.();
    } else {
      _isEditingLocal = false;
      editInitialized = false;
      error = "";
      oneditingchange?.(false);
    }
  }

  function toggleRole(role: Role) {
    if (editRoles.includes(role)) {
      editRoles = editRoles.filter((r) => r !== role);
    } else {
      editRoles = [...editRoles, role];
    }
    // Immediate save for role changes
    immediateAutoSave();
  }

  async function saveEdit() {
    if (!editName.trim() || !editCountry.trim()) {
      error = m.user_error_name_country_required();
      return;
    }

    try {
      saving = true;
      error = "";

      if (mode === "create") {
        const created = await createUser(
          editName.trim(),
          editCountry.trim().toUpperCase(),
          editCity.trim() || null,
          editNickname.trim() || null,
          editEmail.trim() || null,
          editRoles,
        );
        oncreated?.(created);
      } else if (user) {
        const updated = await updateUser(
          user.uid,
          editName.trim(),
          editCountry.trim().toUpperCase(),
          undefined,  // VEKN ID managed via Sponsor/Link/Abandon only
          editCity.trim() || null,
          editNickname.trim() || null,
          editRoles,
        );
        _isEditingLocal = false;
        onupdated?.(updated);
      }
    } catch (e) {
      error = e instanceof Error ? e.message : "Failed to save user";
    } finally {
      saving = false;
    }
  }
</script>

<div class={inline ? "p-4" : "bg-dusk-950 rounded-lg shadow p-4 hover:shadow-md transition-shadow border border-ash-800"}>
  {#if isEditing}
    <!-- Edit/Create Mode -->
    <div role="presentation" onclick={(e) => e.stopPropagation()} onkeydown={(e) => e.stopPropagation()}>
      <form
        onsubmit={(e) => {
          e.preventDefault();
          if (mode === "create") saveEdit();
        }}
        class="space-y-4"
      >
      {#if mode !== "create"}
        <!-- Close button + saving indicator for edit mode -->
        <div class="flex justify-end items-center gap-2 -mt-1 -mr-1">
          {#if saving}
            <span class="text-xs text-ash-400 flex items-center gap-1">
              <Loader2 class="w-3 h-3 animate-spin" />
              {m.user_saving()}
            </span>
          {/if}
          <button
            type="button"
            onclick={cancelEdit}
            class="p-2 text-ash-500 hover:text-crimson-400 transition-colors"
            title={m.common_close()}
          >
            <X class="w-5 h-5" />
          </button>
        </div>
      {/if}
      <div>
        <label
          for="edit-name"
          class="block text-sm font-medium text-ash-400 mb-1"
        >
          {m.common_name()} *
        </label>
        <input
          id="edit-name"
          type="text"
          bind:value={editName}
          oninput={() => mode !== "create" && debouncedAutoSave()}
          required
          class="w-full px-3 py-2 border border-ash-600 rounded bg-dusk-950 text-ash-200 focus:ring-2 focus:ring-crimson-500 focus:border-transparent"
        />
      </div>

      {#if mode === "create"}
        <!-- Email field for create mode (optional, sends invite) -->
        <div>
          <label
            for="edit-email"
            class="block text-sm font-medium text-ash-400 mb-1"
          >
            {m.user_email_label()}
          </label>
          <input
            id="edit-email"
            type="email"
            bind:value={editEmail}
            placeholder={m.user_email_placeholder()}
            class="w-full px-3 py-2 border border-ash-600 rounded bg-dusk-950 text-ash-200 focus:ring-2 focus:ring-crimson-500 focus:border-transparent"
          />
          <p class="mt-1 text-xs text-ash-500">
            {m.user_email_hint()}
          </p>
        </div>
      {:else}
        <!-- VEKN ID (read-only, managed via standalone VEKN Management section) -->
        <div>
          <span class="block text-sm font-medium text-ash-400 mb-1">{m.add_player_vekn_id_label()}</span>
          <span class="block px-3 py-2 text-ash-300">{user?.vekn_id || '—'}</span>
        </div>
      {/if}

      <div>
        <label
          for="edit-country"
          class="block text-sm font-medium text-ash-400 mb-1"
        >
          {m.common_country()} *
        </label>
        <select
          id="edit-country"
          bind:value={editCountry}
          required
          onchange={() => {
            // Clear city when country changes
            if (editCity) {
              editCity = "";
            }
            // Immediate save for country changes
            if (mode !== "create") immediateAutoSave();
          }}
          class="w-full px-3 py-2 border border-ash-600 rounded bg-dusk-950 text-ash-200 focus:ring-2 focus:ring-crimson-500 focus:border-transparent"
        >
          <option value="">{m.user_country_placeholder()}</option>
          {#each sortedCountries as country}
            <option value={country.iso_code}>
              {country.name} {getCountryFlag(country.iso_code)}
            </option>
          {/each}
        </select>
      </div>

      <div>
        <label
          for="edit-city"
          class="block text-sm font-medium text-ash-400 mb-1"
        >
          {m.common_city()}
        </label>
        <CityAutocomplete
          bind:value={editCity}
          countryCode={editCountry}
          disabled={!editCountry}
          onselect={() => mode !== "create" && immediateAutoSave()}
        />
        {#if !editCountry}
          <p class="mt-1 text-xs text-mist-dark">
            {m.user_city_hint()}
          </p>
        {/if}
      </div>

      <div>
        <label
          for="edit-nickname"
          class="block text-sm font-medium text-ash-400 mb-1"
        >
          {m.common_nickname()}
        </label>
        <input
          id="edit-nickname"
          type="text"
          bind:value={editNickname}
          oninput={() => mode !== "create" && debouncedAutoSave()}
          class="w-full px-3 py-2 border border-ash-600 rounded bg-dusk-950 text-ash-200 focus:ring-2 focus:ring-crimson-500 focus:border-transparent"
        />
      </div>

      <fieldset>
        <legend class="block text-sm font-medium text-ash-400 mb-2">
          {m.common_roles()}
        </legend>
        <div class="flex flex-wrap gap-2">
          {#each availableRoles as role}
            {@const allowed = canChangeRole(role)}
            <button
              type="button"
              onclick={(e) => { e.stopPropagation(); if (allowed) toggleRole(role); }}
              disabled={!allowed}
              title={allowed ? m.user_toggle_role({ role }) : m.user_cannot_change_role({ role })}
              class="px-3 py-1 rounded text-sm font-medium transition-colors {editRoles.includes(role)
                ? getRoleClasses(role)
                : 'bg-ash-800 text-ash-400'} {allowed ? 'hover:opacity-80 cursor-pointer' : 'opacity-50 cursor-not-allowed'}"
            >
              {role}
            </button>
          {/each}
        </div>
        {#if mode !== "create" && user && !user.vekn_id}
          <p class="mt-2 text-xs text-crimson-400">
            {m.user_vekn_required_for_roles()}
          </p>
        {/if}
      </fieldset>

      {#if error}
        <div class="text-sm text-crimson-400">
          {error}
        </div>
      {/if}

      {#if mode === "create"}
        <!-- Create mode: show save/cancel buttons -->
        <div class="flex gap-2 pt-2">
          <button
            type="submit"
            disabled={saving}
            class="flex-1 px-4 py-2 bg-crimson-700 hover:bg-crimson-600 disabled:bg-ash-700 text-white rounded font-medium transition-colors disabled:cursor-not-allowed"
          >
            {saving ? m.user_creating() : m.user_create_btn()}
          </button>
          <button
            type="button"
            onclick={cancelEdit}
            disabled={saving}
            class="px-4 py-2 bg-ash-700 hover:bg-ash-600 text-ash-200 rounded font-medium transition-colors disabled:cursor-not-allowed"
          >
            {m.common_cancel()}
          </button>
        </div>
      {/if}
    </form>
    </div>
  {:else if user}
    <!-- View Mode -->
    <div class="flex items-start justify-between">
      <!-- Avatar -->
      <div class="mr-4 flex-shrink-0">
        {#if canEditAvatar()}
          <div class="flex flex-col items-center gap-1">
            <button
              onclick={(e) => { e.stopPropagation(); showAvatarCropper = true; }}
              class="relative group"
              title={m.user_change_avatar()}
            >
              {#if user.avatar_path}
                <img
                  src={user.avatar_path}
                  alt="{user.name}'s avatar"
                  class="w-16 h-16 rounded-full object-cover ring-2 ring-ash-700 group-hover:ring-crimson-500 transition-all"
                />
              {:else}
                <div class="w-16 h-16 rounded-full bg-ash-800 flex items-center justify-center ring-2 ring-ash-700 group-hover:ring-crimson-500 transition-all">
                  <UserIcon class="w-8 h-8 text-ash-500" />
                </div>
              {/if}
              <div class="absolute inset-0 rounded-full bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                <Camera class="w-5 h-5 text-white" />
              </div>
            </button>
            <button
              onclick={(e) => { e.stopPropagation(); showAvatarCropper = true; }}
              class="text-xs text-ash-400 hover:text-crimson-400 sm:hidden"
            >{m.user_change_photo()}</button>
          </div>
        {:else if user.avatar_path}
          <img
            src={user.avatar_path}
            alt="{user.name}'s avatar"
            class="w-16 h-16 rounded-full object-cover ring-2 ring-ash-700"
          />
        {:else}
          <div class="w-16 h-16 rounded-full bg-ash-800 flex items-center justify-center ring-2 ring-ash-700">
            <UserIcon class="w-8 h-8 text-ash-500" />
          </div>
        {/if}
      </div>

      <div class="flex-1">
        <h3 class="text-lg font-semibold text-bone-100">
          {user.name}
        </h3>

        <div class="mt-2 space-y-1 text-sm text-ash-400">
          {#if user.vekn_id}
            <div class="flex items-center gap-2">
              <span class="font-medium">{m.add_player_vekn_id_label()}:</span>
              <span>{user.vekn_id}</span>
            </div>
          {/if}

          {#if user.nickname}
            <div class="flex items-center gap-2">
              <span class="font-medium">{m.common_nickname()}:</span>
              <span>{user.nickname}</span>
            </div>
          {/if}

          <div class="flex items-center gap-2">
            <span class="font-medium">{m.common_country()}:</span>
            <span
              >{user.country
                ? `${getCountryFlag(user.country)} ${countries[user.country]?.name || user.country}`
                : m.common_na()}</span
            >
          </div>

          {#if user.city}
            <div class="flex items-center gap-2">
              <span class="font-medium">{m.common_city()}:</span>
              <span>{user.city}</span>
            </div>
          {/if}

          {#if user.roles.length > 0}
            <div class="flex items-start gap-2">
              <span class="font-medium">{m.common_roles()}:</span>
              <div class="flex flex-wrap gap-1">
                {#each user.roles as role}
                  <span
                    class="px-2 py-0.5 rounded text-xs font-medium {getRoleClasses(role)}"
                  >
                    {role}
                  </span>
                {/each}
              </div>
            </div>
          {/if}

          <SanctionsManager {user} canIssueSanctions={false} inline={true} />
        </div>
      </div>

      {#if editable}
        <button
          onclick={(e) => { e.stopPropagation(); startEdit(); }}
          class="ml-2 p-2 text-ash-500 hover:text-crimson-400 transition-colors"
          title={m.user_edit()}
        >
          <SquarePen class="w-5 h-5" />
        </button>
      {/if}
    </div>

    <div class="mt-3 pt-3 border-t border-ash-700">
      <p class="text-xs text-mist-dark">
        {m.user_last_modified({ date: new Date(user.modified).toLocaleString() })}
      </p>
    </div>

  {:else}
    <!-- Invalid state -->
    <div class="text-crimson-400">
      {m.user_invalid_state()}
    </div>
  {/if}
</div>

<!-- Avatar Cropper Modal -->
{#if showAvatarCropper && user}
  <AvatarCropper
    onSave={handleAvatarSave}
    onCancel={() => (showAvatarCropper = false)}
  />
{/if}
