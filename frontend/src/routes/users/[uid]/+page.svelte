<script lang="ts">
  import { page } from "$app/stores";
  import { getUser } from "$lib/db";
  import { syncManager } from "$lib/sync";
  import { getAuthState } from "$lib/stores/auth.svelte";
  import { canEditUser, canManageVekn } from "$lib/engine";
  import type { User } from "$lib/types";
  import UserComponent from "$lib/components/User.svelte";
  import VeknManagement from "$lib/components/VeknManagement.svelte";
  import SanctionsManager from "$lib/components/SanctionsManager.svelte";
  import PlayerRatings from "$lib/components/PlayerRatings.svelte";
  import { Loader2, Share2, Check } from "lucide-svelte";
  import * as m from '$lib/paraglide/messages.js';

  let copied = $state(false);

  async function shareProfile() {
    if (!user) return;
    const url = `${window.location.origin}/users/${user.uid}`;
    if (navigator.share) {
      try {
        await navigator.share({ title: user.name, url });
        return;
      } catch { /* user cancelled */ }
    }
    try {
      await navigator.clipboard.writeText(url);
      copied = true;
      setTimeout(() => { copied = false; }, 2000);
    } catch { /* noop */ }
  }

  let user = $state<User | undefined>();
  let isOnline = $state(navigator.onLine);

  const uid = $derived($page.params.uid);
  const auth = $derived(getAuthState());

  const canEdit = $derived(() => {
    if (!auth.user || !user) return false;
    try {
      return canEditUser(auth.user, auth.user.uid, user.uid, user).allowed;
    } catch {
      return false;
    }
  });

  const canManage = $derived(() => {
    if (!auth.user || !user || !isOnline) return false;
    try {
      return canManageVekn(auth.user, user).allowed;
    } catch {
      return false;
    }
  });

  const canIssueSanctions = $derived(() => {
    if (!auth.user || !user || !isOnline) return false;
    if (auth.user.uid === user.uid) return false;
    return auth.user.roles.includes("IC") || auth.user.roles.includes("Ethics");
  });

  let refreshTimer: ReturnType<typeof setTimeout> | undefined;

  async function loadData() {
    if (!uid) return;
    user = await getUser(uid);
  }

  function scheduleRefresh() {
    if (refreshTimer) return;
    refreshTimer = setTimeout(async () => {
      refreshTimer = undefined;
      await loadData();
    }, 100);
  }

  async function handleUserUpdated(_updated: User) {
    await loadData();
  }

  $effect(() => {
    uid; // reactive dependency
    loadData();

    const handleSync = (event: { type: string; data?: any }) => {
      if (event.type === "sync_complete") {
        scheduleRefresh();
      } else if (event.type === "user" && event.data?.uid === uid) {
        scheduleRefresh();
      } else if (event.type === "sanction" && event.data?.user_uid === uid) {
        scheduleRefresh();
      }
    };
    syncManager.addEventListener(handleSync);

    const handleOnline = () => { isOnline = true; };
    const handleOffline = () => { isOnline = false; };
    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);

    return () => {
      syncManager.removeEventListener(handleSync);
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
      if (refreshTimer) clearTimeout(refreshTimer);
    };
  });
</script>

<svelte:head>
  <title>{user?.name ?? m.user_detail_fallback_title()} - Archon</title>
</svelte:head>

<div class="max-w-3xl mx-auto px-4 py-6">
  {#if !user}
    <div class="text-center text-ash-400 py-8">
      <Loader2 class="w-6 h-6 animate-spin inline-block" />
      <span class="ml-2">{m.common_loading()}</span>
    </div>
  {:else}
    <div class="flex items-center justify-between mb-2">
      <div></div>
      <button
        onclick={shareProfile}
        class="p-2 text-ash-500 hover:text-crimson-400 transition-colors"
        title={m.profile_share()}
      >
        {#if copied}
          <Check class="w-5 h-5 text-emerald-400" />
        {:else}
          <Share2 class="w-5 h-5" />
        {/if}
      </button>
    </div>
    <UserComponent
      {user}
      mode="view"
      editable={canEdit() && isOnline}
      onupdated={handleUserUpdated}
    />

    {#if canManage()}
      <div class="mt-6">
        <VeknManagement {user} onaction={handleUserUpdated} />
      </div>
    {/if}

    <SanctionsManager {user} canIssueSanctions={canIssueSanctions()} />

    <div class="mt-6">
      <PlayerRatings {user} />
    </div>
  {/if}
</div>
