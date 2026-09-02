<script lang="ts">
  import { toUserMessage } from '$lib/errors';
  import { goto, replaceState } from "$app/navigation";
  import { onMount } from "svelte";
  import {
    authorizedFetch, getAuthState, getAccessToken, logout,
    initAuth, storeTokensFromCallback,
    requestMagicLink,
  } from "$lib/stores/auth.svelte";
  import { canManageOauthClients, canRunAdminSync } from "$lib/engine";
  import { HOF_MIN_WINS } from "$lib/tournament-utils";
  import { registerPasskey } from "$lib/stores/passkeys.svelte";
  import { syncManager } from "$lib/sync";
  import { claimVeknId, abandonVeknId, uploadAvatar, getNdaStatus, type NdaStatus } from "$lib/api";
  import { showToast } from "$lib/stores/toast.svelte";

  import { CircleUser, TriangleAlert, Trophy, FileSignature, IdCard, Swords, Settings } from "@lucide/svelte";
  import InlineNotice from "$lib/components/InlineNotice.svelte";
  import AvatarCropper from "$lib/components/AvatarCropper.svelte";
  import PlayerRatings from "$lib/components/PlayerRatings.svelte";
  import PlayerRecord from "$lib/components/PlayerRecord.svelte";
  import Button from "$lib/components/Button.svelte";
  import * as m from '$lib/paraglide/messages.js';

  import TabStrip from "$lib/components/TabStrip.svelte";
  import ProfileIdentity from "./ProfileIdentity.svelte";
  import ProfileContact from "./ProfileContact.svelte";
  import LinkedAccounts from "./LinkedAccounts.svelte";
  import AuthorizedApps from "./AuthorizedApps.svelte";
  import NdaRecords from "./NdaRecords.svelte";
  import AppSettings from "./AppSettings.svelte";
  import DeveloperSection from "./DeveloperSection.svelte";
  import AdminSection from "./AdminSection.svelte";
  import DataSection from "./DataSection.svelte";
  import Badge from "$lib/components/Badge.svelte";
  import { dialogPanel } from "$lib/actions/dialog";

  const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

  const auth = $derived(getAuthState());
  const isDev = $derived(canManageOauthClients(auth.user).allowed);
  const canAdminister = $derived(canRunAdminSync(auth.user).allowed);

  let discordMessage = $state("");
  let discordError = $state("");
  let githubMessage = $state("");
  let githubError = $state("");
  let passkeyMessage = $state("");

  let showClaimModal = $state(false);
  let claimVeknIdInput = $state("");
  let claimingVekn = $state(false);
  let showAbandonConfirm = $state(false);
  let abandoningVekn = $state(false);

  let showAvatarCropper = $state(false);

  type TabId = 'profile' | 'record' | 'account';
  let activeTab = $state<TabId>('profile');
  const tabs: { id: TabId; label: string; icon: typeof IdCard }[] = [
    { id: 'profile', label: m.profile_tab_profile(), icon: IdCard },
    { id: 'record', label: m.profile_tab_record(), icon: Swords },
    { id: 'account', label: m.profile_tab_account(), icon: Settings },
  ];

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
  // GitHub is a link-only field on the user (not a login method), so its state
  // comes from the user object rather than authMethods.
  const hasGithub = $derived(!!auth.user?.github_login);
  const githubUsername = $derived(auth.user?.github_login || null);

  let ndaStatus = $state<NdaStatus | null>(null);
  let ndaChecked = $state(false);
  const ndaPending = $derived(!!ndaStatus?.pending);
  const ndaRecords = $derived(ndaStatus?.records.filter((r) => r.status !== "pending") ?? []);

  // One silent online check per visit.
  $effect(() => {
    const u = auth.user;
    if (!u || ndaChecked || !navigator.onLine) return;
    ndaChecked = true;
    getNdaStatus(u.uid, { suppressErrorToast: true })
      .then((s) => (ndaStatus = s))
      .catch(() => {});
  });

  onMount(async () => {
    const params = new URLSearchParams(window.location.search);
    const discordLinked = params.get("discord_linked");
    const error = params.get("error");
    const githubLinked = params.get("github_linked");
    const githubErr = params.get("github_error");

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

    if (githubLinked === "success") {
      githubMessage = m.profile_github_linked();
      await initAuth();
    } else if (githubErr) {
      githubError = m.profile_github_error({ error: githubErr });
    }

    // Deep link from VEKN-ID guidance (e.g. tournament registration block)
    const claim = params.get("claim");
    if (claim !== null) {
      showClaimModal = true;
    }

    if (discordLinked || error || githubLinked || githubErr) activeTab = 'account';

    if (discordLinked || error || githubLinked || githubErr || claim !== null) {
      replaceState("/profile", {});
    }
  });

  async function handleResync() {
    try {
      await syncManager.refresh();
      showToast({ type: "success", message: m.profile_resync_success() });
    } catch (e) {
      showToast({ type: "error", message: toUserMessage(e, m.profile_resync_failed()) });
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

  function handleLinkGithub() {
    const token = getAccessToken();
    if (!token) {
      githubError = m.profile_not_authenticated();
      return;
    }
    window.location.href = `${API_BASE}/auth/github/authorize?token=${encodeURIComponent(token)}`;
  }

  async function handleUnlinkGithub() {
    githubMessage = "";
    githubError = "";
    const res = await authorizedFetch(`${API_BASE}/auth/github/unlink`, {
      method: "POST",
    });
    if (res.ok) {
      githubMessage = m.profile_github_unlinked();
      await initAuth();
    } else {
      githubError = m.profile_github_error({ error: String(res.status) });
    }
  }

  async function handleClaimVekn() {
    if (!claimVeknIdInput.trim()) return;
    claimingVekn = true;
    try {
      const result = await claimVeknId(claimVeknIdInput.trim());
      showToast({ type: "success", message: result.message });
      showClaimModal = false;
      claimVeknIdInput = "";
      // storeTokensFromCallback handles: store tokens, fetch /auth/me, set auth state, sync refresh
      await storeTokensFromCallback(result.access_token, result.refresh_token);
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
    // avatar_path is now a versioned URL — initAuth refetches it and the <img>
    // refreshes on its own; no manual cache-bust needed.
    await initAuth();
  }
</script>

<svelte:head>
  <title>{m.profile_page_title()} - Archon</title>
</svelte:head>

<div class="p-4 sm:p-8">
  <div class="max-w-2xl mx-auto">
    <h1 class="text-3xl font-semibold text-accent mb-6">{m.nav_profile()}</h1>

    {#if auth.isLoading}
      <div class="bg-surface-card rounded-lg shadow p-8 border border-line text-center">
        <div class="text-ink-muted">{m.common_loading()}</div>
      </div>
    {:else if !auth.isAuthenticated || !auth.user}
      <div class="bg-surface-card rounded-lg shadow p-8 border border-line text-center">
        <div class="text-ink-faint mb-4">
          <CircleUser class="mx-auto h-16 w-16" />
        </div>
        <h2 class="text-xl font-medium text-ink-strong mb-2">{m.profile_sign_in_required()}</h2>
        <p class="text-ink-muted mb-6">{m.profile_sign_in_msg()}</p>
        <a href="/login"
          class="inline-block px-6 py-3 bg-accent-strong hover:bg-accent-strong-hover text-white rounded-lg font-medium transition-colors">
          {m.login_sign_in()}
        </a>
      </div>
    {:else}
      {@const user = auth.user}

      {#if ndaPending}
        <div class="mb-4">
          <InlineNotice tone="warn" icon={FileSignature}>
            {m.profile_nda_pending_notice()}
            <a href="/nda" class="text-link underline ml-1">{m.profile_nda_pending_link()}</a>
          </InlineNotice>
        </div>
      {/if}

      <div class="bg-surface-card rounded-lg shadow border border-line">
        {#key user.uid}
        <ProfileIdentity
          {user}
          onAvatarClick={() => (showAvatarCropper = true)}
          onAbandonVekn={() => (showAbandonConfirm = true)}
          onClaimVekn={() => (showClaimModal = true)}
        />

        <TabStrip {tabs} bind:active={activeTab} />

        {#if activeTab === 'profile'}
          <div class="p-3 sm:p-6">
            <ProfileContact {user} />
          </div>
        {:else if activeTab === 'record'}
          <div class="p-3 sm:p-6 space-y-4">
            <div class="flex items-center justify-between gap-3 flex-wrap">
              <h3 class="text-sm font-medium text-ink-muted uppercase tracking-wide">{m.user_detail_ratings()}</h3>
              {#if (user.wins?.length ?? 0) >= HOF_MIN_WINS}
                <Badge kind="link" tone="highlight" href="/rankings?tab=halloffame">
                  <Trophy class="w-3 h-3" aria-hidden="true" />
                  {m.profile_hof_member({ wins: String(user.wins?.length ?? 0) })}
                </Badge>
              {/if}
            </div>
            <PlayerRatings {user} showHeading={false} />
            <PlayerRecord {user} self />
          </div>
        {:else}
          <div class="divide-y divide-line">
            <LinkedAccounts
              {hasEmail}
              {emailIdentifier}
              {hasDiscord}
              {discordUsername}
              {hasGithub}
              {githubUsername}
              {hasPasskey}
              {discordMessage}
              {discordError}
              {githubMessage}
              {githubError}
              {passkeyMessage}
              error={auth.error}
              onLinkEmail={handleLinkEmail}
              onLinkDiscord={handleLinkDiscord}
              onLinkGithub={handleLinkGithub}
              onUnlinkGithub={handleUnlinkGithub}
              onRegisterPasskey={handleRegisterPasskey}
            />
            <AuthorizedApps />
            {#if ndaRecords.length}
              <NdaRecords userUid={user.uid} records={ndaRecords} />
            {/if}
            <AppSettings />
            {#if isDev}
              <DeveloperSection />
            {/if}
            {#if canAdminister}
              <AdminSection />
            {/if}
            <DataSection onResync={handleResync} onLogout={handleLogout} />
          </div>
        {/if}
        {/key}
      </div>
    {/if}

    <p class="mt-6 text-center text-xs text-ink-faint">Archon v{__APP_VERSION__}</p>
  </div>
</div>

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
      class="bg-surface-card rounded-lg shadow-xl border border-line w-full max-w-md mx-4 max-h-[85dvh] overflow-y-auto"
      onclick={(e) => e.stopPropagation()}
      onkeydown={(e) => e.stopPropagation()}
      use:dialogPanel={() => showClaimModal = false}
      role="dialog" aria-modal="true" tabindex="-1"
    >
      <div class="p-6 border-b border-line">
        <h2 class="text-xl font-medium text-ink-strong">{m.profile_claim_vekn_title()}</h2>
        <p class="mt-2 text-sm text-ink-muted">{m.profile_claim_vekn_description()}</p>
      </div>
      <form onsubmit={(e) => { e.preventDefault(); handleClaimVekn(); }} class="p-6 space-y-4">
        <div>
          <label for="claim-vekn-id" class="block text-sm font-medium text-ink-muted mb-1">{m.add_player_vekn_id_label()}</label>
          <input id="claim-vekn-id" type="text" bind:value={claimVeknIdInput} placeholder="1234567"
            class="w-full px-3 py-2 border border-line-strong rounded bg-surface-card text-ink-bright focus:ring-2 focus:ring-accent focus:border-transparent" />
        </div>
        <div class="flex gap-2">
          <Button type="submit" variant="primary" size="lg" class="flex-1" loading={claimingVekn} disabled={!claimVeknIdInput.trim()}>
            {claimingVekn ? m.profile_claiming() : m.profile_claim_btn()}
          </Button>
          <Button variant="secondary" size="lg" disabled={claimingVekn} onclick={() => { showClaimModal = false; claimVeknIdInput = ""; }}>
            {m.common_cancel()}
          </Button>
        </div>
      </form>
    </div>
  </div>
{/if}

{#if showAvatarCropper}
  <AvatarCropper onSave={handleSaveAvatar} onCancel={() => (showAvatarCropper = false)} />
{/if}

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
      class="bg-surface-card rounded-lg shadow-xl border border-line w-full max-w-md mx-4 max-h-[85dvh] overflow-y-auto"
      onclick={(e) => e.stopPropagation()}
      onkeydown={(e) => e.stopPropagation()}
      use:dialogPanel={() => showAbandonConfirm = false}
      role="dialog" aria-modal="true" tabindex="-1"
    >
      <div class="p-6 border-b border-line">
        <h2 class="text-xl font-medium text-link">{m.profile_abandon_vekn_title()}</h2>
      </div>
      <div class="p-6">
        <p class="text-ink mb-4">{m.profile_abandon_vekn_description()}</p>
        <p class="text-sm text-ink-muted mb-6">{m.profile_abandon_vekn_hint()}</p>
        <div class="flex gap-2">
          <Button variant="danger" size="lg" class="flex-1" loading={abandoningVekn} onclick={handleAbandonVekn}>
            <TriangleAlert class="w-4 h-4" aria-hidden="true" />
            {abandoningVekn ? m.profile_abandoning() : m.profile_abandon_btn()}
          </Button>
          <Button variant="secondary" size="lg" disabled={abandoningVekn} onclick={() => (showAbandonConfirm = false)}>
            {m.common_cancel()}
          </Button>
        </div>
      </div>
    </div>
  </div>
{/if}
