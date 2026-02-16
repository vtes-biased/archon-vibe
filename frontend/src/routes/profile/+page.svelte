<script lang="ts">
  import { goto, replaceState } from "$app/navigation";
  import { onMount } from "svelte";
  import {
    getAuthState,
    setAuthState,
    getAccessToken,
    logout,
    updateProfile,
    initAuth,
    storeTokensFromCallback,
    type ProfileUpdate,
  } from "$lib/stores/auth.svelte";
  import { registerPasskey, isPasskeySupported } from "$lib/stores/passkeys.svelte";
  import { claimVeknId, abandonVeknId, uploadAvatar } from "$lib/api";
  import { showToast } from "$lib/stores/toast.svelte";
  import { getCountries, getCountryFlag } from "$lib/geonames";
  import CityAutocomplete from "$lib/components/CityAutocomplete.svelte";
  import AvatarCropper from "$lib/components/AvatarCropper.svelte";
  import { syncManager } from "$lib/sync";
  import { User, Camera, SquarePen, Unlink, KeyRound, RefreshCw } from "lucide-svelte";
  import DiscordIcon from "$lib/components/DiscordIcon.svelte";
  import * as m from '$lib/paraglide/messages.js';

  const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

  const auth = $derived(getAuthState());
  const countries = getCountries();
  const sortedCountries = Object.values(countries).sort((a, b) => a.name.localeCompare(b.name));

  let isEditing = $state(false);
  let saving = $state(false);
  let registeringPasskey = $state(false);
  let passkeyMessage = $state("");
  let discordMessage = $state("");
  let discordError = $state("");

  // VEKN claim/abandon state
  let showClaimModal = $state(false);
  let claimVeknIdInput = $state("");
  let claimingVekn = $state(false);
  let showAbandonConfirm = $state(false);
  let abandoningVekn = $state(false);

  // Avatar state
  let showAvatarCropper = $state(false);
  let avatarCacheBust = $state(0);
  let isSyncing = $state(false);

  // Edit form state
  let editName = $state("");
  let editNickname = $state("");
  let editCountry = $state("");
  let editCity = $state("");
  let editContactEmail = $state("");
  let editContactPhone = $state("");

  // Handle Discord link callback
  onMount(async () => {
    const params = new URLSearchParams(window.location.search);
    const discordLinked = params.get("discord_linked");
    const error = params.get("error");

    if (discordLinked === "success") {
      discordMessage = m.profile_discord_linked();
      // Refresh auth state to get updated auth methods
      await initAuth();
    } else if (discordLinked === "already") {
      discordMessage = m.profile_discord_already();
    } else if (error === "merge_failed") {
      discordError = m.profile_discord_merge_failed();
    } else if (error) {
      discordError = m.profile_discord_error({ error });
    }

    // Clear URL params
    if (discordLinked || error) {
      replaceState("/profile", {});
    }
  });

  async function handleResync() {
    try {
      isSyncing = true;
      await syncManager.refresh();
      showToast({ type: "success", message: m.profile_resync_success() });
    } catch (e) {
      showToast({ type: "error", message: e instanceof Error ? e.message : m.profile_resync_failed() });
    } finally {
      isSyncing = false;
    }
  }

  function handleLogout() {
    logout();
    goto("/login");
  }

  function startEdit() {
    const user = auth.user;
    if (!user) return;
    editName = user.name || "";
    editNickname = user.nickname || "";
    editCountry = user.country || "";
    editCity = user.city || "";
    editContactEmail = user.contact_email || "";
    editContactPhone = user.contact_phone || "";
    isEditing = true;
  }

  function cancelEdit() {
    isEditing = false;
  }

  async function saveProfile() {
    saving = true;
    const data: ProfileUpdate = {
      name: editName || undefined,
      nickname: editNickname || undefined,
      country: editCountry || undefined,
      city: editCity || undefined,
      contact_email: editContactEmail || undefined,
      contact_phone: editContactPhone || undefined,
    };
    const success = await updateProfile(data);
    saving = false;
    if (success) {
      isEditing = false;
    }
  }

  async function handleRegisterPasskey() {
    registeringPasskey = true;
    passkeyMessage = "";
    const success = await registerPasskey();
    registeringPasskey = false;
    if (success) {
      passkeyMessage = m.profile_passkey_registered();
    }
  }

  function handleLinkDiscord() {
    // Redirect to Discord OAuth with link=true and token for auth
    const token = getAccessToken();
    if (!token) {
      discordError = m.profile_not_authenticated();
      return;
    }
    window.location.href = `${API_BASE}/auth/discord/authorize?link=true&token=${encodeURIComponent(token)}`;
  }

  async function handleClaimVekn() {
    if (!claimVeknIdInput.trim()) return;
    claimingVekn = true;
    try {
      const result = await claimVeknId(claimVeknIdInput.trim());
      showToast({ type: "success", message: result.message });
      showClaimModal = false;
      claimVeknIdInput = "";
      // Store new tokens for the VEKN user (uid changed)
      await storeTokensFromCallback(result.access_token, result.refresh_token);
      // Ensure auth state reflects claimed user even if /auth/me failed
      setAuthState({ user: result.user, isAuthenticated: true, isLoading: false, error: null });
      // Reconnect SSE with new token (uid changed after merge)
      await syncManager.refresh();
    } catch {
      // Error toast is shown by apiRequest
    } finally {
      claimingVekn = false;
    }
  }

  async function handleAbandonVekn() {
    abandoningVekn = true;
    try {
      const result = await abandonVeknId();
      showToast({ type: "success", message: result.message });
      showAbandonConfirm = false;
      // Store new tokens for the new user (split from VEKN record)
      await storeTokensFromCallback(result.access_token, result.refresh_token);
      // Ensure auth state reflects new user even if /auth/me failed
      setAuthState({ user: result.user, isAuthenticated: true, isLoading: false, error: null });
      // Reconnect SSE with new token (uid changed after split)
      await syncManager.refresh();
    } catch {
      // Error toast is shown by apiRequest
    } finally {
      abandoningVekn = false;
    }
  }

  async function handleSaveAvatar(blob: Blob) {
    if (!auth.user) return;
    await uploadAvatar(auth.user.uid, blob);
    showAvatarCropper = false;
    // Refresh auth state to get updated user with new avatar_path
    await initAuth();
    // Bust browser cache for avatar URL
    avatarCacheBust = Date.now();
  }

  function formatLocation(country: string | null, city?: string | null): string | null {
    if (!country) return null;
    const parts: string[] = [];
    if (city) parts.push(city);
    const countryName = countries[country]?.name || country;
    parts.push(`${getCountryFlag(country)} ${countryName}`);
    return parts.join(", ");
  }

  // Check if user has a passkey
  const hasPasskey = $derived(
    auth.isAuthenticated && auth.authMethods.some((am) => am.type === "passkey")
  );

  // Check if user has Discord linked
  const hasDiscord = $derived(
    auth.isAuthenticated && auth.authMethods.some((am) => am.type === "discord")
  );

  // Get Discord username if linked
  const discordUsername = $derived(
    auth.authMethods.find((am) => am.type === "discord")?.identifier || null
  );
</script>

<svelte:head>
  <title>{m.profile_page_title()} - Archon</title>
</svelte:head>

<div class="p-4 sm:p-8">
  <div class="max-w-2xl mx-auto">
    <h1 class="text-3xl font-light text-crimson-500 mb-6">{m.nav_profile()}</h1>

    {#if auth.isLoading}
      <div class="bg-dusk-950 rounded-lg shadow p-8 border border-ash-800 text-center">
        <div class="text-ash-400">{m.common_loading()}</div>
      </div>
    {:else if !auth.isAuthenticated || !auth.user}
      <div class="bg-dusk-950 rounded-lg shadow p-8 border border-ash-800 text-center">
        <div class="text-ash-500 mb-4">
          <User class="mx-auto h-16 w-16" />
        </div>
        <h2 class="text-xl font-medium text-bone-100 mb-2">{m.profile_sign_in_required()}</h2>
        <p class="text-ash-400 mb-6">{m.profile_sign_in_msg()}</p>
        <a
          href="/login"
          class="inline-block px-6 py-3 bg-crimson-700 hover:bg-crimson-600 text-white rounded-lg font-medium transition-colors"
        >
          {m.login_sign_in()}
        </a>
      </div>
    {:else}
      {@const user = auth.user}

      {#if isEditing}
        <!-- Edit Mode -->
        <div class="bg-dusk-950 rounded-lg shadow border border-ash-800">
          <div class="p-6 border-b border-ash-800">
            <h2 class="text-xl font-medium text-bone-100">{m.profile_edit_title()}</h2>
          </div>

          <form
            onsubmit={(e) => {
              e.preventDefault();
              saveProfile();
            }}
            class="p-6 space-y-4"
          >
            <div>
              <label for="edit-name" class="block text-sm font-medium text-ash-400 mb-1">
                {m.common_name()}
              </label>
              <input
                id="edit-name"
                type="text"
                bind:value={editName}
                class="w-full px-3 py-2 border border-ash-600 rounded bg-dusk-950 text-ash-200 focus:ring-2 focus:ring-crimson-500 focus:border-transparent"
              />
            </div>

            <div>
              <label for="edit-nickname" class="block text-sm font-medium text-ash-400 mb-1">
                {m.common_nickname()}
              </label>
              <input
                id="edit-nickname"
                type="text"
                bind:value={editNickname}
                class="w-full px-3 py-2 border border-ash-600 rounded bg-dusk-950 text-ash-200 focus:ring-2 focus:ring-crimson-500 focus:border-transparent"
              />
            </div>

            <div>
              <label for="edit-country" class="block text-sm font-medium text-ash-400 mb-1">
                {m.common_country()}
              </label>
              <select
                id="edit-country"
                bind:value={editCountry}
                onchange={() => {
                  editCity = "";
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
              <label for="edit-city" class="block text-sm font-medium text-ash-400 mb-1">
                {m.common_city()}
              </label>
              <CityAutocomplete
                bind:value={editCity}
                countryCode={editCountry}
                disabled={!editCountry}
              />
              {#if !editCountry}
                <p class="mt-1 text-xs text-mist-500">{m.city_select_country_first()}</p>
              {/if}
            </div>

            <div class="pt-4 border-t border-ash-800">
              <h3 class="text-sm font-medium text-ash-400 uppercase tracking-wide mb-4">
                {m.profile_contact_info()}
              </h3>

              <div class="space-y-4">
                <div>
                  <label
                    for="edit-contact-email"
                    class="block text-sm font-medium text-ash-400 mb-1"
                  >
                    {m.common_email()}
                  </label>
                  <input
                    id="edit-contact-email"
                    type="email"
                    bind:value={editContactEmail}
                    class="w-full px-3 py-2 border border-ash-600 rounded bg-dusk-950 text-ash-200 focus:ring-2 focus:ring-crimson-500 focus:border-transparent"
                  />
                </div>

                <div>
                  <label
                    for="edit-contact-phone"
                    class="block text-sm font-medium text-ash-400 mb-1"
                  >
                    {m.profile_phone()}
                  </label>
                  <input
                    id="edit-contact-phone"
                    type="tel"
                    bind:value={editContactPhone}
                    class="w-full px-3 py-2 border border-ash-600 rounded bg-dusk-950 text-ash-200 focus:ring-2 focus:ring-crimson-500 focus:border-transparent"
                  />
                </div>
              </div>
            </div>

            {#if auth.error}
              <div class="text-sm text-crimson-400">{auth.error}</div>
            {/if}

            <div class="flex gap-2 pt-4">
              <button
                type="submit"
                disabled={saving}
                class="flex-1 px-4 py-2 bg-crimson-700 hover:bg-crimson-600 disabled:bg-ash-700 text-white rounded font-medium transition-colors disabled:cursor-not-allowed"
              >
                {saving ? m.common_saving() : m.common_save()}
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
          </form>
        </div>
      {:else}
        <!-- View Mode -->
        <div class="bg-dusk-950 rounded-lg shadow border border-ash-800">
          <!-- Header -->
          <div class="p-6 border-b border-ash-800">
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-4">
                <div class="flex flex-col items-center gap-1">
                  <button
                    onclick={() => (showAvatarCropper = true)}
                    class="relative group"
                    title={m.user_change_avatar()}
                  >
                    {#if user.avatar_path}
                      <img
                        src={avatarCacheBust ? `${user.avatar_path}?v=${avatarCacheBust}` : user.avatar_path}
                        alt="Avatar"
                        class="w-16 h-16 rounded-full object-cover"
                      />
                    {:else}
                      <div
                        class="w-16 h-16 rounded-full bg-ash-800 flex items-center justify-center"
                      >
                        <User class="h-8 w-8 text-ash-500" />
                      </div>
                    {/if}
                    <div class="absolute inset-0 rounded-full bg-black/50 opacity-0 group-hover:opacity-100 flex items-center justify-center transition-opacity">
                      <Camera class="h-6 w-6 text-white" />
                    </div>
                  </button>
                  <button
                    onclick={() => (showAvatarCropper = true)}
                    class="text-xs text-ash-400 hover:text-crimson-400 sm:hidden"
                  >{m.user_change_photo()}</button>
                </div>
                <div>
                  <h2 class="text-xl font-medium text-bone-100">
                    {user.name || m.profile_anonymous()}
                  </h2>
                  {#if user.nickname}
                    <p class="text-ash-400">"{user.nickname}"</p>
                  {/if}
                </div>
              </div>
              <button
                onclick={startEdit}
                class="p-2 text-ash-500 hover:text-crimson-400 transition-colors"
                title={m.profile_edit_btn()}
              >
                <SquarePen class="w-5 h-5" />
              </button>
            </div>
          </div>

          <!-- Details -->
          <div class="p-6 space-y-4">
            {#if user.vekn_id}
              <div class="flex justify-between items-center">
                <span class="text-ash-400">{m.add_player_vekn_id_label()}</span>
                <div class="flex items-center gap-2">
                  <span class="text-bone-100 font-mono">{user.vekn_id}</span>
                  <button
                    onclick={() => (showAbandonConfirm = true)}
                    class="p-1 text-ash-500 hover:text-crimson-400 transition-colors"
                    title={m.profile_abandon_vekn_tooltip()}
                  >
                    <Unlink class="w-4 h-4" />
                  </button>
                </div>
              </div>
            {:else}
              <div class="flex justify-between items-center">
                <span class="text-ash-400">{m.add_player_vekn_id_label()}</span>
                <button
                  onclick={() => (showClaimModal = true)}
                  class="px-3 py-1 text-sm bg-crimson-700 hover:bg-crimson-600 text-white rounded transition-colors"
                >
                  {m.profile_claim_vekn_title()}
                </button>
              </div>
            {/if}

            {#if user.country}
              {@const location = formatLocation(user.country, user.city)}
              <div class="flex justify-between">
                <span class="text-ash-400">{m.profile_location()}</span>
                <span class="text-bone-100">{location}</span>
              </div>
            {/if}

            {#if user.roles.length > 0}
              <div class="flex justify-between items-start">
                <span class="text-ash-400">{m.common_roles()}</span>
                <div class="flex flex-wrap gap-2 justify-end">
                  {#each user.roles as role}
                    <span class="px-2 py-1 text-xs rounded bg-ash-800 text-bone-100"
                      >{role}</span
                    >
                  {/each}
                </div>
              </div>
            {/if}
          </div>

          <!-- Contact Info -->
          {#if user.contact_email || user.contact_phone}
            <div class="p-6 border-t border-ash-800 space-y-4">
              <h3 class="text-sm font-medium text-ash-400 uppercase tracking-wide">{m.profile_contact()}</h3>
              {#if user.contact_email}
                <div class="flex justify-between">
                  <span class="text-ash-400">{m.common_email()}</span>
                  <a
                    href="mailto:{user.contact_email}"
                    class="text-crimson-500 hover:text-crimson-400">{user.contact_email}</a
                  >
                </div>
              {/if}
              {#if user.contact_phone}
                <div class="flex justify-between">
                  <span class="text-ash-400">{m.profile_phone()}</span>
                  <span class="text-bone-100">{user.contact_phone}</span>
                </div>
              {/if}
            </div>
          {/if}

          <!-- Linked Accounts Section -->
          <div class="p-6 border-t border-ash-800 space-y-4">
            <h3 class="text-sm font-medium text-ash-400 uppercase tracking-wide">
              {m.profile_linked_accounts()}
            </h3>

            <!-- Discord -->
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-3">
                <DiscordIcon class="w-5 h-5 text-[#5865F2]" />
                <div>
                  <p class="text-bone-100">Discord</p>
                  {#if hasDiscord && discordUsername}
                    <p class="text-sm text-ash-400">{discordUsername}</p>
                  {:else}
                    <p class="text-sm text-ash-400">{m.profile_not_linked()}</p>
                  {/if}
                </div>
              </div>
              {#if !hasDiscord}
                <button
                  onclick={handleLinkDiscord}
                  class="px-4 py-2 bg-[#5865F2] hover:bg-[#4752C4] text-white rounded font-medium transition-colors"
                >
                  {m.profile_link()}
                </button>
              {:else}
                <span class="px-3 py-1 text-sm text-green-500 bg-green-500/10 rounded">{m.profile_linked()}</span
                >
              {/if}
            </div>
            {#if discordMessage}
              <p class="text-sm text-green-500">{discordMessage}</p>
            {/if}
            {#if discordError}
              <p class="text-sm text-crimson-400">{discordError}</p>
            {/if}

            <!-- Passkey -->
            {#if isPasskeySupported()}
              <div class="flex items-center justify-between">
                <div class="flex items-center gap-3">
                  <KeyRound class="w-5 h-5 text-ash-400" />
                  <div>
                    <p class="text-bone-100">Passkey</p>
                    <p class="text-sm text-ash-400">
                      {hasPasskey ? m.profile_passkey_configured() : m.profile_passkey_not_setup()}
                    </p>
                  </div>
                </div>
                {#if !hasPasskey}
                  <button
                    onclick={handleRegisterPasskey}
                    disabled={registeringPasskey}
                    class="px-4 py-2 bg-ash-800 hover:bg-ash-700 disabled:bg-ash-700 text-bone-100 rounded font-medium transition-colors disabled:cursor-not-allowed"
                  >
                    {registeringPasskey ? m.profile_passkey_adding() : m.common_add()}
                  </button>
                {:else}
                  <span class="px-3 py-1 text-sm text-green-500 bg-green-500/10 rounded"
                    >{m.profile_passkey_active()}</span
                  >
                {/if}
              </div>
              {#if passkeyMessage}
                <p class="text-sm text-green-500">{passkeyMessage}</p>
              {/if}
            {/if}

            {#if auth.error}
              <p class="text-sm text-crimson-400">{auth.error}</p>
            {/if}
          </div>

          <!-- Data -->
          <div class="p-6 border-t border-ash-800 space-y-4">
            <h3 class="text-sm font-medium text-ash-400 uppercase tracking-wide">{m.profile_data()}</h3>
            <div class="flex items-center justify-between">
              <div>
                <p class="text-bone-100">{m.profile_resync_title()}</p>
                <p class="text-sm text-ash-400">{m.profile_resync_description()}</p>
              </div>
              <button
                onclick={handleResync}
                disabled={isSyncing}
                class="px-4 py-2 bg-crimson-700 hover:bg-crimson-600 disabled:bg-ash-700 text-white rounded font-medium transition-colors disabled:cursor-not-allowed flex items-center gap-2"
              >
                <RefreshCw class="w-4 h-4 {isSyncing ? 'animate-spin' : ''}" />
                {isSyncing ? m.profile_resyncing() : m.profile_resync_btn()}
              </button>
            </div>
          </div>

          <!-- Logout -->
          <div class="p-6 border-t border-ash-800">
            <button
              onclick={handleLogout}
              class="w-full px-6 py-3 bg-ash-800 hover:bg-ash-700 text-bone-100 rounded-lg font-medium transition-colors"
            >
              {m.profile_sign_out()}
            </button>
          </div>
        </div>
      {/if}
    {/if}
  </div>
</div>

<!-- Claim VEKN ID Modal -->
{#if showClaimModal}
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
  <div
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
    role="presentation"
    onclick={() => (showClaimModal = false)}
    onkeydown={(e) => { if (e.key === 'Escape') showClaimModal = false; }}
  >
    <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
    <div
      class="bg-dusk-950 rounded-lg shadow-xl border border-ash-800 w-full max-w-md mx-4"
      onclick={(e) => e.stopPropagation()}
      onkeydown={(e) => e.stopPropagation()}
      role="dialog"
      aria-modal="true"
      tabindex="-1"
    >
      <div class="p-6 border-b border-ash-800">
        <h2 class="text-xl font-medium text-bone-100">{m.profile_claim_vekn_title()}</h2>
        <p class="mt-2 text-sm text-ash-400">
          {m.profile_claim_vekn_description()}
        </p>
      </div>
      <form
        onsubmit={(e) => {
          e.preventDefault();
          handleClaimVekn();
        }}
        class="p-6 space-y-4"
      >
        <div>
          <label for="claim-vekn-id" class="block text-sm font-medium text-ash-400 mb-1">
            {m.add_player_vekn_id_label()}
          </label>
          <input
            id="claim-vekn-id"
            type="text"
            bind:value={claimVeknIdInput}
            placeholder="1234567"
            class="w-full px-3 py-2 border border-ash-600 rounded bg-dusk-950 text-ash-200 focus:ring-2 focus:ring-crimson-500 focus:border-transparent"
          />
        </div>
        <div class="flex gap-2">
          <button
            type="submit"
            disabled={claimingVekn || !claimVeknIdInput.trim()}
            class="flex-1 px-4 py-2 bg-crimson-700 hover:bg-crimson-600 disabled:bg-ash-700 text-white rounded font-medium transition-colors disabled:cursor-not-allowed"
          >
            {claimingVekn ? m.profile_claiming() : m.profile_claim_btn()}
          </button>
          <button
            type="button"
            onclick={() => {
              showClaimModal = false;
              claimVeknIdInput = "";
            }}
            disabled={claimingVekn}
            class="px-4 py-2 bg-ash-700 hover:bg-ash-600 text-ash-200 rounded font-medium transition-colors disabled:cursor-not-allowed"
          >
            {m.common_cancel()}
          </button>
        </div>
      </form>
    </div>
  </div>
{/if}

<!-- Avatar Cropper Modal -->
{#if showAvatarCropper}
  <AvatarCropper onSave={handleSaveAvatar} onCancel={() => (showAvatarCropper = false)} />
{/if}

<!-- Abandon VEKN ID Confirmation Modal -->
{#if showAbandonConfirm}
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
  <div
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
    role="presentation"
    onclick={() => (showAbandonConfirm = false)}
    onkeydown={(e) => { if (e.key === 'Escape') showAbandonConfirm = false; }}
  >
    <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
    <div
      class="bg-dusk-950 rounded-lg shadow-xl border border-ash-800 w-full max-w-md mx-4"
      onclick={(e) => e.stopPropagation()}
      onkeydown={(e) => e.stopPropagation()}
      role="dialog"
      aria-modal="true"
      tabindex="-1"
    >
      <div class="p-6 border-b border-ash-800">
        <h2 class="text-xl font-medium text-crimson-400">{m.profile_abandon_vekn_title()}</h2>
      </div>
      <div class="p-6">
        <p class="text-ash-300 mb-4">
          {m.profile_abandon_vekn_description()}
        </p>
        <p class="text-sm text-ash-400 mb-6">
          {m.profile_abandon_vekn_hint()}
        </p>
        <div class="flex gap-2">
          <button
            onclick={handleAbandonVekn}
            disabled={abandoningVekn}
            class="flex-1 px-4 py-2 bg-crimson-700 hover:bg-crimson-600 disabled:bg-ash-700 text-white rounded font-medium transition-colors disabled:cursor-not-allowed"
          >
            {abandoningVekn ? m.profile_abandoning() : m.profile_abandon_btn()}
          </button>
          <button
            onclick={() => (showAbandonConfirm = false)}
            disabled={abandoningVekn}
            class="px-4 py-2 bg-ash-700 hover:bg-ash-600 text-ash-200 rounded font-medium transition-colors disabled:cursor-not-allowed"
          >
            {m.common_cancel()}
          </button>
        </div>
      </div>
    </div>
  </div>
{/if}
