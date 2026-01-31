<script lang="ts">
  import type { User } from "$lib/types";
  import { sponsorVeknMember, linkVeknId, forceAbandonVeknId, mergeUsers } from "$lib/api";
  import { showToast } from "$lib/stores/toast.svelte";
  import Icon from "@iconify/svelte";

  let {
    user,
    onaction,
  }: {
    user: User;
    onaction: (user: User) => void;
  } = $props();

  let showLinkModal = $state(false);
  let showSponsorConfirm = $state(false);
  let showForceAbandonConfirm = $state(false);
  let showMergeModal = $state(false);
  let linkVeknIdInput = $state("");
  let mergeTargetUid = $state("");
  let processingAction = $state(false);

  function focusOnMount(node: HTMLElement) {
    node.focus();
  }

  async function handleSponsor() {
    processingAction = true;
    try {
      const result = await sponsorVeknMember(user.uid);
      showToast({ type: "success", message: result.message });
      showSponsorConfirm = false;
      onaction(result.user);
    } catch {
      // Error toast shown by apiRequest
    } finally {
      processingAction = false;
    }
  }

  async function handleLink() {
    if (!linkVeknIdInput.trim()) return;
    processingAction = true;
    try {
      const result = await linkVeknId(linkVeknIdInput.trim(), user.uid);
      showToast({ type: "success", message: result.message });
      showLinkModal = false;
      linkVeknIdInput = "";
      onaction(result.user);
    } catch {
      // Error toast shown by apiRequest
    } finally {
      processingAction = false;
    }
  }

  async function handleForceAbandon() {
    processingAction = true;
    try {
      const result = await forceAbandonVeknId(user.uid);
      showToast({ type: "success", message: result.message });
      showForceAbandonConfirm = false;
    } catch {
      // Error toast shown by apiRequest
    } finally {
      processingAction = false;
    }
  }

  async function handleMerge() {
    if (!mergeTargetUid.trim()) return;
    processingAction = true;
    try {
      const result = await mergeUsers(user.uid, mergeTargetUid.trim());
      showToast({ type: "success", message: result.message });
      showMergeModal = false;
      mergeTargetUid = "";
      onaction(result.user);
    } catch {
      // Error toast shown by apiRequest
    } finally {
      processingAction = false;
    }
  }
</script>

<!-- Inline VEKN section -->
<fieldset class="border border-ash-700 rounded p-4">
  <legend class="text-sm font-medium text-ash-400 px-2">VEKN</legend>
  <p class="text-sm text-ash-300 mb-2">
    {#if user.vekn_id}
      ID: {user.vekn_id}
    {:else}
      No VEKN ID
    {/if}
  </p>
  <div class="flex flex-wrap gap-2">
    {#if !user.vekn_id}
      <button
        type="button"
        onclick={(e) => { e.stopPropagation(); showSponsorConfirm = true; }}
        class="px-3 py-1 text-xs bg-emerald-800 hover:bg-emerald-700 text-bone-100 rounded transition-colors"
        title="Allocate new VEKN ID"
      >
        <Icon icon="lucide:user-plus" class="inline w-3 h-3 mr-1" />
        Sponsor
      </button>
      <button
        type="button"
        onclick={(e) => { e.stopPropagation(); showLinkModal = true; }}
        class="px-3 py-1 text-xs bg-ash-700 hover:bg-ash-600 text-bone-100 rounded transition-colors"
        title="Link existing VEKN ID"
      >
        <Icon icon="lucide:link" class="inline w-3 h-3 mr-1" />
        Link VEKN
      </button>
    {:else}
      <button
        type="button"
        onclick={(e) => { e.stopPropagation(); showForceAbandonConfirm = true; }}
        class="px-3 py-1 text-xs bg-crimson-800 hover:bg-crimson-700 text-bone-100 rounded transition-colors"
        title="Remove VEKN ID from user"
      >
        <Icon icon="lucide:unlink" class="inline w-3 h-3 mr-1" />
        Force Abandon
      </button>
    {/if}
    <button
      type="button"
      onclick={(e) => { e.stopPropagation(); showMergeModal = true; }}
      class="px-3 py-1 text-xs bg-ash-700 hover:bg-ash-600 text-bone-100 rounded transition-colors"
      title="Merge with another user"
    >
      <Icon icon="lucide:git-merge" class="inline w-3 h-3 mr-1" />
      Merge
    </button>
  </div>
</fieldset>

<!-- Sponsor Confirmation Modal -->
{#if showSponsorConfirm}
  <div
    role="presentation"
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
    onclick={(e) => { e.stopPropagation(); if (e.target === e.currentTarget) showSponsorConfirm = false; }}
  >
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="sponsor-modal-title"
      tabindex="-1"
      use:focusOnMount
      onkeydown={(e) => e.key === 'Escape' && (showSponsorConfirm = false)}
      class="bg-dusk-950 rounded-lg shadow-xl border border-ash-800 w-full max-w-md mx-4"
    >
      <div class="p-6 border-b border-ash-800">
        <h2 id="sponsor-modal-title" class="text-xl font-medium text-bone-100">Sponsor New Member</h2>
      </div>
      <div class="p-6">
        <p class="text-ash-300 mb-4">
          This will allocate a new VEKN ID to <strong class="text-bone-100">{user.name}</strong> and record you as their sponsor.
        </p>
        <div class="flex gap-2">
          <button
            onclick={handleSponsor}
            disabled={processingAction}
            class="flex-1 px-4 py-2 bg-emerald-700 hover:bg-emerald-600 disabled:bg-ash-700 text-bone-100 rounded font-medium transition-colors disabled:cursor-not-allowed"
          >
            {processingAction ? "Sponsoring..." : "Sponsor"}
          </button>
          <button
            onclick={() => (showSponsorConfirm = false)}
            disabled={processingAction}
            class="px-4 py-2 bg-ash-700 hover:bg-ash-600 text-ash-200 rounded font-medium transition-colors disabled:cursor-not-allowed"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  </div>
{/if}

<!-- Link VEKN ID Modal -->
{#if showLinkModal}
  <div
    role="presentation"
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
    onclick={(e) => { e.stopPropagation(); if (e.target === e.currentTarget) showLinkModal = false; }}
  >
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="link-modal-title"
      tabindex="-1"
      use:focusOnMount
      onkeydown={(e) => e.key === 'Escape' && (showLinkModal = false)}
      class="bg-dusk-950 rounded-lg shadow-xl border border-ash-800 w-full max-w-md mx-4"
    >
      <div class="p-6 border-b border-ash-800">
        <h2 id="link-modal-title" class="text-xl font-medium text-bone-100">Link VEKN ID</h2>
        <p class="mt-2 text-sm text-ash-400">
          Link an existing VEKN ID to {user.name}. If the ID is held by another user, they will be displaced.
        </p>
      </div>
      <form
        onsubmit={(e) => {
          e.preventDefault();
          handleLink();
        }}
        class="p-6 space-y-4"
      >
        <div>
          <label for="link-vekn-id" class="block text-sm font-medium text-ash-400 mb-1">
            VEKN ID
          </label>
          <input
            id="link-vekn-id"
            type="text"
            bind:value={linkVeknIdInput}
            placeholder="1234567"
            class="w-full px-3 py-2 border border-ash-600 rounded bg-dusk-950 text-ash-200 focus:ring-2 focus:ring-crimson-500 focus:border-transparent"
          />
        </div>
        <div class="flex gap-2">
          <button
            type="submit"
            disabled={processingAction || !linkVeknIdInput.trim()}
            class="flex-1 px-4 py-2 bg-crimson-700 hover:bg-crimson-600 disabled:bg-ash-700 text-bone-100 rounded font-medium transition-colors disabled:cursor-not-allowed"
          >
            {processingAction ? "Linking..." : "Link"}
          </button>
          <button
            type="button"
            onclick={() => {
              showLinkModal = false;
              linkVeknIdInput = "";
            }}
            disabled={processingAction}
            class="px-4 py-2 bg-ash-700 hover:bg-ash-600 text-ash-200 rounded font-medium transition-colors disabled:cursor-not-allowed"
          >
            Cancel
          </button>
        </div>
      </form>
    </div>
  </div>
{/if}

<!-- Force Abandon Confirmation Modal -->
{#if showForceAbandonConfirm}
  <div
    role="presentation"
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
    onclick={(e) => { e.stopPropagation(); if (e.target === e.currentTarget) showForceAbandonConfirm = false; }}
  >
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="force-abandon-modal-title"
      tabindex="-1"
      use:focusOnMount
      onkeydown={(e) => e.key === 'Escape' && (showForceAbandonConfirm = false)}
      class="bg-dusk-950 rounded-lg shadow-xl border border-ash-800 w-full max-w-md mx-4"
    >
      <div class="p-6 border-b border-ash-800">
        <h2 id="force-abandon-modal-title" class="text-xl font-medium text-crimson-400">Force Abandon VEKN ID?</h2>
      </div>
      <div class="p-6">
        <p class="text-ash-300 mb-4">
          This will remove the VEKN ID <strong class="text-bone-100">{user.vekn_id}</strong> from <strong class="text-bone-100">{user.name}</strong>'s account, along with all their login methods.
        </p>
        <p class="text-sm text-crimson-400 mb-6">
          They will need to claim the VEKN ID again or be re-linked by a coordinator.
        </p>
        <div class="flex gap-2">
          <button
            onclick={handleForceAbandon}
            disabled={processingAction}
            class="flex-1 px-4 py-2 bg-crimson-700 hover:bg-crimson-600 disabled:bg-ash-700 text-bone-100 rounded font-medium transition-colors disabled:cursor-not-allowed"
          >
            {processingAction ? "Abandoning..." : "Force Abandon"}
          </button>
          <button
            onclick={() => (showForceAbandonConfirm = false)}
            disabled={processingAction}
            class="px-4 py-2 bg-ash-700 hover:bg-ash-600 text-ash-200 rounded font-medium transition-colors disabled:cursor-not-allowed"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  </div>
{/if}

<!-- Merge Users Modal -->
{#if showMergeModal}
  <div
    role="presentation"
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
    onclick={(e) => { e.stopPropagation(); if (e.target === e.currentTarget) showMergeModal = false; }}
  >
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="merge-modal-title"
      tabindex="-1"
      use:focusOnMount
      onkeydown={(e) => e.key === 'Escape' && (showMergeModal = false)}
      class="bg-dusk-950 rounded-lg shadow-xl border border-ash-800 w-full max-w-md mx-4"
    >
      <div class="p-6 border-b border-ash-800">
        <h2 id="merge-modal-title" class="text-xl font-medium text-bone-100">Merge Users</h2>
        <p class="mt-2 text-sm text-ash-400">
          Merge another user into {user.name}. The other user's auth methods, sanctions, and data will be transferred here.
        </p>
      </div>
      <form
        onsubmit={(e) => {
          e.preventDefault();
          handleMerge();
        }}
        class="p-6 space-y-4"
      >
        <div>
          <label for="merge-target-uid" class="block text-sm font-medium text-ash-400 mb-1">
            User UID to merge (will be deleted)
          </label>
          <input
            id="merge-target-uid"
            type="text"
            bind:value={mergeTargetUid}
            placeholder="User UID"
            class="w-full px-3 py-2 border border-ash-600 rounded bg-dusk-950 text-ash-200 focus:ring-2 focus:ring-crimson-500 focus:border-transparent font-mono text-sm"
          />
        </div>
        <div class="flex gap-2">
          <button
            type="submit"
            disabled={processingAction || !mergeTargetUid.trim()}
            class="flex-1 px-4 py-2 bg-crimson-700 hover:bg-crimson-600 disabled:bg-ash-700 text-bone-100 rounded font-medium transition-colors disabled:cursor-not-allowed"
          >
            {processingAction ? "Merging..." : "Merge"}
          </button>
          <button
            type="button"
            onclick={() => {
              showMergeModal = false;
              mergeTargetUid = "";
            }}
            disabled={processingAction}
            class="px-4 py-2 bg-ash-700 hover:bg-ash-600 text-ash-200 rounded font-medium transition-colors disabled:cursor-not-allowed"
          >
            Cancel
          </button>
        </div>
      </form>
    </div>
  </div>
{/if}
