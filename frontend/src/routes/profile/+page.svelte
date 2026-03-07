<script lang="ts">
  import { goto, replaceState } from "$app/navigation";
  import { onMount } from "svelte";
  import {
    getAuthState, setAuthState, getAccessToken, logout,
    initAuth, storeTokensFromCallback, hasAnyRole,
    requestMagicLink,
  } from "$lib/stores/auth.svelte";
  import { registerPasskey } from "$lib/stores/passkeys.svelte";
  import { claimVeknId, abandonVeknId, uploadAvatar } from "$lib/api";
  import { showToast } from "$lib/stores/toast.svelte";
  import { syncManager } from "$lib/sync";
  import { User } from "lucide-svelte";
  import AvatarCropper from "$lib/components/AvatarCropper.svelte";
  import * as m from '$lib/paraglide/messages.js';

  import ProfileView from "./ProfileView.svelte";
  import LinkedAccounts from "./LinkedAccounts.svelte";
  import AppSettings from "./AppSettings.svelte";
  import DeveloperSection from "./DeveloperSection.svelte";
  import DataSection from "./DataSection.svelte";

  const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

  const auth = $derived(getAuthState());
  const isDev = $derived(hasAnyRole('DEV', 'IC'));

  let discordMessage = $state("");
  let discordError = $state("");
  let passkeyMessage = $state("");

  // VEKN claim/abandon state
  let showClaimModal = $state(false);
  let claimVeknIdInput = $state("");
  let claimingVekn = $state(false);
  let showAbandonConfirm = $state(false);
  let abandoningVekn = $state(false);

  // Avatar state
  let showAvatarCropper = $state(false);
  let avatarCacheBust = $state(0);

  // Derived from auth
  const hasEmail = $derived(
    auth.isAuthenticated && auth.authMethods.some((am) => am.type === "email")
  );
  const emailIdentifier = $derived(
    auth.authMethods.find((am) => am.type === "email")?.identifier || null
  );
  const hasPasskey = $derived(
    auth.isAuthenticated && auth.authMethods.some((am) => am.type === "passkey")
  );
  const hasDiscord = $derived(
    auth.isAuthenticated && auth.authMethods.some((am) => am.type === "discord")
  );
  const discordUsername = $derived(
    auth.authMethods.find((am) => am.type === "discord")?.identifier || null
  );

  // Handle Discord link callback
  onMount(async () => {
    const params = new URLSearchParams(window.location.search);
    const discordLinked = params.get("discord_linked");
    const error = params.get("error");

    if (discordLinked === "success") {
      discordMessage = m.profile_discord_linked();
      await initAuth();
    } else if (discordLinked === "already") {
      discordMessage = m.profile_discord_already();
    } else if (error === "merge_failed") {
      discordError = m.profile_discord_merge_failed();
    } else if (error) {
      discordError = m.profile_discord_error({ error });
    }

    if (discordLinked || error) {
      replaceState("/profile", {});
    }
  });

  async function handleResync() {
    try {
      await syncManager.refresh();
      showToast({ type: "success", message: m.profile_resync_success() });
    } catch (e) {
      showToast({ type: "error", message: e instanceof Error ? e.message : m.profile_resync_failed() });
    }
  }

  async function handleLogout() {
    await logout();
    goto("/login");
  }

  async function handleRegisterPasskey() {
    passkeyMessage = "";
    const success = await registerPasskey();
    if (success) passkeyMessage = m.profile_passkey_registered();
  }

  async function handleLinkEmail(email: string): Promise<boolean> {
    return await requestMagicLink(email, "signup", true);
  }

  function handleLinkDiscord() {
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
      await storeTokensFromCallback(result.access_token, result.refresh_token);
      setAuthState({ user: result.user, isAuthenticated: true, isLoading: false, error: null });
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
      await storeTokensFromCallback(result.access_token, result.refresh_token);
      setAuthState({ user: result.user, isAuthenticated: true, isLoading: false, error: null });
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
    await initAuth();
    avatarCacheBust = Date.now();
  }
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
        <a href="/login"
          class="inline-block px-6 py-3 bg-crimson-700 hover:bg-crimson-600 text-white rounded-lg font-medium transition-colors">
          {m.login_sign_in()}
        </a>
      </div>
    {:else}
      {@const user = auth.user}

      <div class="bg-dusk-950 rounded-lg shadow border border-ash-800">
        <ProfileView
          {user}
          {avatarCacheBust}
          onAvatarClick={() => (showAvatarCropper = true)}
          onAbandonVekn={() => (showAbandonConfirm = true)}
          onClaimVekn={() => (showClaimModal = true)}
        />
        <LinkedAccounts
          {hasEmail}
          {emailIdentifier}
          {hasDiscord}
          {discordUsername}
          {hasPasskey}
          {discordMessage}
          {discordError}
          {passkeyMessage}
          error={auth.error}
          onLinkEmail={handleLinkEmail}
          onLinkDiscord={handleLinkDiscord}
          onRegisterPasskey={handleRegisterPasskey}
        />
        <AppSettings />
        {#if isDev}
          <DeveloperSection />
        {/if}
        <DataSection onResync={handleResync} onLogout={handleLogout} />
      </div>
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
      role="dialog" aria-modal="true" tabindex="-1"
    >
      <div class="p-6 border-b border-ash-800">
        <h2 class="text-xl font-medium text-bone-100">{m.profile_claim_vekn_title()}</h2>
        <p class="mt-2 text-sm text-ash-400">{m.profile_claim_vekn_description()}</p>
      </div>
      <form onsubmit={(e) => { e.preventDefault(); handleClaimVekn(); }} class="p-6 space-y-4">
        <div>
          <label for="claim-vekn-id" class="block text-sm font-medium text-ash-400 mb-1">{m.add_player_vekn_id_label()}</label>
          <input id="claim-vekn-id" type="text" bind:value={claimVeknIdInput} placeholder="1234567"
            class="w-full px-3 py-2 border border-ash-600 rounded bg-dusk-950 text-ash-200 focus:ring-2 focus:ring-crimson-500 focus:border-transparent" />
        </div>
        <div class="flex gap-2">
          <button type="submit" disabled={claimingVekn || !claimVeknIdInput.trim()}
            class="flex-1 px-4 py-2 bg-crimson-700 hover:bg-crimson-600 disabled:bg-ash-800 disabled:text-ash-500 text-white rounded font-medium transition-colors">
            {claimingVekn ? m.profile_claiming() : m.profile_claim_btn()}
          </button>
          <button type="button" onclick={() => { showClaimModal = false; claimVeknIdInput = ""; }} disabled={claimingVekn}
            class="px-4 py-2 bg-ash-700 hover:bg-ash-600 text-ash-200 rounded font-medium transition-colors">
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
      role="dialog" aria-modal="true" tabindex="-1"
    >
      <div class="p-6 border-b border-ash-800">
        <h2 class="text-xl font-medium text-crimson-400">{m.profile_abandon_vekn_title()}</h2>
      </div>
      <div class="p-6">
        <p class="text-ash-300 mb-4">{m.profile_abandon_vekn_description()}</p>
        <p class="text-sm text-ash-400 mb-6">{m.profile_abandon_vekn_hint()}</p>
        <div class="flex gap-2">
          <button onclick={handleAbandonVekn} disabled={abandoningVekn}
            class="flex-1 px-4 py-2 bg-crimson-700 hover:bg-crimson-600 disabled:bg-ash-800 disabled:text-ash-500 text-white rounded font-medium transition-colors">
            {abandoningVekn ? m.profile_abandoning() : m.profile_abandon_btn()}
          </button>
          <button onclick={() => (showAbandonConfirm = false)} disabled={abandoningVekn}
            class="px-4 py-2 bg-ash-700 hover:bg-ash-600 text-ash-200 rounded font-medium transition-colors">
            {m.common_cancel()}
          </button>
        </div>
      </div>
    </div>
  </div>
{/if}
