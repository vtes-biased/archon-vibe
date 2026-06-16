<script lang="ts">
  import { page } from "$app/stores";
  import { goto } from "$app/navigation";
  import { getUser } from "$lib/db";
  import { syncManager } from "$lib/sync";
  import { getAuthState } from "$lib/stores/auth.svelte";
  import { canEditUser, canManageVekn, canMarkDeceased, canDeleteMember } from "$lib/engine";
  import { engineReady } from "$lib/stores/engine-ready.svelte";
  import type { User } from "$lib/types";
  import UserComponent from "$lib/components/User.svelte";
  import VeknManagement from "$lib/components/VeknManagement.svelte";
  import SanctionsManager from "$lib/components/SanctionsManager.svelte";
  import PlayerRatings from "$lib/components/PlayerRatings.svelte";
  import { Loader2, Share2, Check } from "@lucide/svelte";
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
  let sponsorName = $state<string | undefined>();
  let isOnline = $state(navigator.onLine);

  const uid = $derived($page.params.uid);
  const auth = $derived(getAuthState());

  // initEngine() runs once in +layout.svelte; the permission wrappers below read
  // engineReady() internally, so canEdit/canManage recompute when WASM lands.
  const canEdit = $derived(() => {
    if (!auth.user || !user || !engineReady()) return false;
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

  const canManageDeceased = $derived(() => {
    if (!auth.user || !user || !isOnline || !engineReady()) return false;
    if (auth.user.uid === user.uid) return false;
    try {
      return canMarkDeceased(auth.user, user.country ?? null).allowed;
    } catch {
      return false;
    }
  });

  // Soft-delete is IC-only; the button itself only shows for VEKN-less members
  // (handled in VeknManagement) — VEKN members are removed via deceased status.
  const canDelete = $derived(() => {
    if (!auth.user || !user || !isOnline || !engineReady()) return false;
    if (auth.user.uid === user.uid) return false;
    try {
      return canDeleteMember(auth.user).allowed;
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
    // coopted_by is full-projection only, so its presence is the permission gate.
    // Resolve the sponsor's name from local IndexedDB; absence falls back gracefully.
    sponsorName = user?.coopted_by ? (await getUser(user.coopted_by))?.name : undefined;
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

  // After a soft-delete the profile no longer belongs in any listing; leave the
  // now-orphaned detail page for the members list.
  async function handleMemberDeleted() {
    await goto("/users?tab=members");
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

    {#if user.coopted_by}
      {@const date = user.coopted_at ? new Date(user.coopted_at).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" }) : "—"}
      <p class="mt-2 px-4 text-xs text-mist-dark">
        {#if sponsorName}
          {m.user_sponsored_by({ name: sponsorName, date })}
        {:else}
          {m.user_sponsored_unknown({ date })}
        {/if}
      </p>
    {/if}

    {#if canManage()}
      <div class="mt-6">
        <VeknManagement {user} onaction={handleUserUpdated} ondelete={handleMemberDeleted} canMarkDeceased={canManageDeceased()} canDelete={canDelete()} />
      </div>
    {/if}

    <SanctionsManager {user} canIssueSanctions={canIssueSanctions()} />

    <div class="mt-6">
      <PlayerRatings {user} />
    </div>
  {/if}
</div>
