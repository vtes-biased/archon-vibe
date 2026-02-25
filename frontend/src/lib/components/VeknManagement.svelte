<script lang="ts">
  import type { User } from "$lib/types";
  import { sponsorVeknMember, linkVeknId, forceAbandonVeknId, mergeUsers } from "$lib/api";
  import { showToast } from "$lib/stores/toast.svelte";
  import { UserPlus, Link, Unlink, GitMerge } from "lucide-svelte";
  import * as m from '$lib/paraglide/messages.js';

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

<!-- VEKN Management Section -->
<div>
  <h2 class="text-lg font-semibold text-ash-200 mb-3">{m.vekn_title()}</h2>
  <div class="bg-dusk-950 border border-ash-800 rounded-lg p-4">
    <p class="text-sm text-ash-300 mb-3">
      {#if user.vekn_id}
        {m.vekn_id_display({ id: user.vekn_id })}
      {:else}
        {m.vekn_no_id()}
      {/if}
    </p>
    <div class="flex flex-wrap gap-2">
      {#if !user.vekn_id}
        <button
          type="button"
          onclick={() => showSponsorConfirm = true}
          class="px-3 py-1.5 text-sm btn-emerald rounded transition-colors"
          title={m.vekn_sponsor_title()}
        >
          <UserPlus class="inline w-3.5 h-3.5 mr-1" />
          {m.vekn_sponsor()}
        </button>
        <button
          type="button"
          onclick={() => showLinkModal = true}
          class="px-3 py-1.5 text-sm bg-ash-700 hover:bg-ash-600 text-bone-100 rounded transition-colors"
          title={m.vekn_link_modal_title()}
        >
          <Link class="inline w-3.5 h-3.5 mr-1" />
          {m.vekn_link_btn()}
        </button>
      {:else}
        <button
          type="button"
          onclick={() => showForceAbandonConfirm = true}
          class="px-3 py-1.5 text-sm bg-crimson-700 hover:bg-crimson-600 text-white rounded transition-colors"
          title={m.vekn_abandon_title()}
        >
          <Unlink class="inline w-3.5 h-3.5 mr-1" />
          {m.vekn_force_abandon()}
        </button>
      {/if}
      <button
        type="button"
        onclick={() => showMergeModal = true}
        class="px-3 py-1.5 text-sm bg-ash-700 hover:bg-ash-600 text-bone-100 rounded transition-colors"
        title={m.vekn_merge_modal_title()}
      >
        <GitMerge class="inline w-3.5 h-3.5 mr-1" />
        {m.vekn_merge()}
      </button>
    </div>
  </div>
</div>

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
        <h2 id="sponsor-modal-title" class="text-xl font-medium text-bone-100">{m.vekn_sponsor_title()}</h2>
      </div>
      <div class="p-6">
        <p class="text-ash-300 mb-4">
          {m.vekn_sponsor_confirm({ name: user.name })}
        </p>
        <div class="flex gap-2">
          <button
            onclick={handleSponsor}
            disabled={processingAction}
            class="flex-1 px-4 py-2 btn-emerald rounded font-medium transition-colors"
          >
            {processingAction ? m.vekn_sponsoring() : m.vekn_sponsor()}
          </button>
          <button
            onclick={() => (showSponsorConfirm = false)}
            disabled={processingAction}
            class="px-4 py-2 bg-ash-700 hover:bg-ash-600 text-ash-200 rounded font-medium transition-colors"
          >
            {m.common_cancel()}
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
        <h2 id="link-modal-title" class="text-xl font-medium text-bone-100">{m.vekn_link_modal_title()}</h2>
        <p class="mt-2 text-sm text-ash-400">
          {m.vekn_link_description({ name: user.name })}
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
            {m.add_player_vekn_id_label()}
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
            class="flex-1 px-4 py-2 bg-crimson-700 hover:bg-crimson-600 disabled:bg-ash-800 disabled:text-ash-500 text-white rounded font-medium transition-colors"
          >
            {processingAction ? m.vekn_linking() : m.vekn_link_submit()}
          </button>
          <button
            type="button"
            onclick={() => {
              showLinkModal = false;
              linkVeknIdInput = "";
            }}
            disabled={processingAction}
            class="px-4 py-2 bg-ash-700 hover:bg-ash-600 text-ash-200 rounded font-medium transition-colors"
          >
            {m.common_cancel()}
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
        <h2 id="force-abandon-modal-title" class="text-xl font-medium text-crimson-400">{m.vekn_abandon_title()}</h2>
      </div>
      <div class="p-6">
        <p class="text-ash-300 mb-4">
          {m.vekn_abandon_confirm({ id: user.vekn_id!, name: user.name })}
        </p>
        <p class="text-sm text-crimson-400 mb-6">
          {m.vekn_abandon_warning()}
        </p>
        <div class="flex gap-2">
          <button
            onclick={handleForceAbandon}
            disabled={processingAction}
            class="flex-1 px-4 py-2 bg-crimson-700 hover:bg-crimson-600 disabled:bg-ash-800 disabled:text-ash-500 text-white rounded font-medium transition-colors"
          >
            {processingAction ? m.vekn_abandoning() : m.vekn_force_abandon()}
          </button>
          <button
            onclick={() => (showForceAbandonConfirm = false)}
            disabled={processingAction}
            class="px-4 py-2 bg-ash-700 hover:bg-ash-600 text-ash-200 rounded font-medium transition-colors"
          >
            {m.common_cancel()}
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
        <h2 id="merge-modal-title" class="text-xl font-medium text-bone-100">{m.vekn_merge_modal_title()}</h2>
        <p class="mt-2 text-sm text-ash-400">
          {m.vekn_merge_description({ name: user.name })}
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
            {m.vekn_merge_uid_label()}
          </label>
          <input
            id="merge-target-uid"
            type="text"
            bind:value={mergeTargetUid}
            placeholder={m.vekn_merge_uid_placeholder()}
            class="w-full px-3 py-2 border border-ash-600 rounded bg-dusk-950 text-ash-200 focus:ring-2 focus:ring-crimson-500 focus:border-transparent font-mono text-sm"
          />
        </div>
        <div class="flex gap-2">
          <button
            type="submit"
            disabled={processingAction || !mergeTargetUid.trim()}
            class="flex-1 px-4 py-2 bg-crimson-700 hover:bg-crimson-600 disabled:bg-ash-800 disabled:text-ash-500 text-white rounded font-medium transition-colors"
          >
            {processingAction ? m.vekn_merging() : m.vekn_merge()}
          </button>
          <button
            type="button"
            onclick={() => {
              showMergeModal = false;
              mergeTargetUid = "";
            }}
            disabled={processingAction}
            class="px-4 py-2 bg-ash-700 hover:bg-ash-600 text-ash-200 rounded font-medium transition-colors"
          >
            {m.common_cancel()}
          </button>
        </div>
      </form>
    </div>
  </div>
{/if}
