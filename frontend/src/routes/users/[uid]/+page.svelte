<script lang="ts">
  import { page } from "$app/stores";
  import { getUser, getRatingByUserUid } from "$lib/db";
  import { syncManager } from "$lib/sync";
  import { getAuthState } from "$lib/stores/auth.svelte";
  import { canEditUser } from "$lib/engine";
  import type { User, Rating } from "$lib/types";
  import UserComponent from "$lib/components/User.svelte";
  import PlayerRatings from "$lib/components/PlayerRatings.svelte";
  import Icon from "@iconify/svelte";
  import * as m from '$lib/paraglide/messages.js';

  let user = $state<User | undefined>();
  let rating = $state<Rating | undefined>();
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

  let refreshTimer: ReturnType<typeof setTimeout> | undefined;

  async function loadData() {
    if (!uid) return;
    user = await getUser(uid);
    rating = await getRatingByUserUid(uid);
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
      } else if ((event.type === "rating" || event.type === "sanction") && event.data?.user_uid === uid) {
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
      <Icon icon="lucide:loader-2" class="w-6 h-6 animate-spin inline-block" />
      <span class="ml-2">{m.common_loading()}</span>
    </div>
  {:else}
    <UserComponent
      {user}
      mode="view"
      editable={canEdit() && isOnline}
      showManagement={canEdit() && isOnline}
      onupdated={handleUserUpdated}
    />

    <div class="mt-6">
      <PlayerRatings {rating} />
    </div>
  {/if}
</div>
