<script lang="ts">
  import type { User } from "$lib/types";
  import { getUser } from "$lib/db";
  import { getCountryFlag } from "$lib/geonames";
  import { showToast } from "$lib/stores/toast.svelte";
  import UserPicker from "$lib/components/UserPicker.svelte";
  import { X } from "@lucide/svelte";
  import * as m from '$lib/paraglide/messages.js';

  let {
    organizerUids,
    onadd,
    onremove,
  }: {
    organizerUids: string[];
    onadd: (userUid: string) => Promise<void>;
    onremove: (userUid: string) => Promise<void>;
  } = $props();

  let organizers = $state<Record<string, User | null>>({});
  let loading = $state(false);

  // Load organizer details
  async function loadOrganizers() {
    const result: Record<string, User | null> = {};
    for (const uid of organizerUids) {
      result[uid] = (await getUser(uid)) ?? null;
    }
    organizers = result;
  }

  $effect(() => {
    const _uids = organizerUids;
    loadOrganizers();
  });

  async function handleAdd(user: User) {
    loading = true;
    try {
      await onadd(user.uid);
      showToast({ type: "success", message: m.organizers_added() });
    } catch {
      // Error already shown by apiRequest
    } finally {
      loading = false;
    }
  }

  async function handleRemove(uid: string) {
    if (organizerUids.length <= 1) {
      showToast({ type: "error", message: m.organizers_last_warning() });
      return;
    }
    loading = true;
    try {
      await onremove(uid);
    } catch {
      // Error already shown by apiRequest
    } finally {
      loading = false;
    }
  }
</script>

<div class="space-y-3">
  <!-- Current organizers -->
  <div class="flex flex-wrap gap-2">
    {#each organizerUids as uid (uid)}
      {@const user = organizers[uid]}
      <span class="inline-flex items-center gap-1.5 px-3 py-1.5 bg-surface-hover rounded-lg text-sm text-ink-strong">
        {#if user?.country}
          <span>{getCountryFlag(user.country)}</span>
        {/if}
        {user?.name || uid.slice(0, 8)}
        {#if organizerUids.length > 1}
          <!-- 44px tap target padded out; negative margin keeps the chip compact -->
          <button
            onclick={() => handleRemove(uid)}
            disabled={loading}
            class="ml-0 -m-2.5 p-2.5 min-w-[44px] min-h-[44px] inline-flex items-center justify-center text-ink-faint hover:text-link transition-colors"
            title={m.common_delete()}
          >
            <X class="w-3.5 h-3.5" />
          </button>
        {/if}
      </span>
    {/each}
  </div>

  <!-- Search to add -->
  <UserPicker
    onselect={handleAdd}
    placeholder={m.organizers_search_placeholder()}
    excludeUids={organizerUids}
  />
</div>
