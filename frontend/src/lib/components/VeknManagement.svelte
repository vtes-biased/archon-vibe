<script lang="ts">
  import type { User } from "$lib/types";
  import { sponsorVeknMember, linkVeknId, forceAbandonVeknId, mergeUsers, setMemberDeceased, deleteMember } from "$lib/api";
  import { showToast } from "$lib/stores/toast.svelte";
  import { UserPlus, Link, Unlink, GitMerge, CloudOff, Flower2, Trash2, TriangleAlert } from "@lucide/svelte";
  import Button from '$lib/components/Button.svelte';
  import * as m from '$lib/paraglide/messages.js';

  let {
    user,
    onaction,
    ondelete,
    canMarkDeceased = false,
    canDelete = false,
  }: {
    user: User;
    onaction: (user: User) => void;
    ondelete?: () => void;
    canMarkDeceased?: boolean;
    canDelete?: boolean;
  } = $props();

  const isDeceased = $derived(!!user.deceased_at);

  const veknPush = import.meta.env.VITE_VEKN_PUSH === "true";
  // Strict false: undefined means the viewer's projection omits the field
  const veknSyncPending = $derived(
    veknPush && !!user.vekn_id && user.vekn_synced === false
  );

  let showLinkModal = $state(false);
  let showSponsorConfirm = $state(false);
  let showForceAbandonConfirm = $state(false);
  let showMergeModal = $state(false);
  let showDeleteConfirm = $state(false);
  let linkVeknIdInput = $state("");
  let mergeTargetUid = $state("");
  let processingAction = $state(false);

  function focusOnMount(node: HTMLElement) {
    const input = node.querySelector<HTMLElement>("input:not(.hidden):not([type=hidden]), textarea, select");
    (input ?? node).focus();
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

  async function handleDeceased() {
    // No confirmation: marking/clearing is trivially reversible.
    processingAction = true;
    try {
      const updated = await setMemberDeceased(user.uid, !isDeceased);
      showToast({
        type: "success",
        message: isDeceased ? m.deceased_cleared_toast() : m.deceased_marked_toast(),
      });
      onaction(updated);
    } catch {
      // Error toast shown by apiRequest
    } finally {
      processingAction = false;
    }
  }

  async function handleDelete() {
    processingAction = true;
    try {
      await deleteMember(user.uid);
      showToast({ type: "success", message: m.member_deleted_toast() });
      showDeleteConfirm = false;
      ondelete?.();
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
        {#if veknSyncPending}
          <span class="ml-2 px-2 py-0.5 rounded text-xs font-medium banner-warn border inline-flex items-center gap-1">
            <CloudOff class="w-3 h-3" aria-hidden="true" />
            {m.vekn_sync_pending_member()}
          </span>
        {/if}
      {:else}
        {m.vekn_no_id()}
      {/if}
    </p>
    {#if veknSyncPending}
      <p class="text-xs text-ash-500 -mt-2 mb-3">{m.vekn_sync_pending_hint()}</p>
    {/if}
    <div class="flex flex-wrap gap-2">
      {#if !user.vekn_id}
        <Button variant="primary" size="md" onclick={() => showSponsorConfirm = true} title={m.vekn_sponsor_title()}>
          <UserPlus class="inline w-3.5 h-3.5 mr-1" />
          {m.vekn_sponsor()}
        </Button>
        <Button variant="secondary" size="md" onclick={() => showLinkModal = true} title={m.vekn_link_modal_title()}>
          <Link class="inline w-3.5 h-3.5 mr-1" />
          {m.vekn_link_btn()}
        </Button>
        {#if canDelete}
          <Button variant="danger" size="md" onclick={() => showDeleteConfirm = true} title={m.member_delete_title()}>
            <Trash2 class="inline w-3.5 h-3.5 mr-1" />
            {m.member_delete()}
          </Button>
        {/if}
      {:else}
        <Button variant="danger" size="md" onclick={() => showForceAbandonConfirm = true} title={m.vekn_abandon_title()}>
          <Unlink class="inline w-3.5 h-3.5 mr-1" />
          {m.vekn_force_abandon()}
        </Button>
      {/if}
      <Button variant="secondary" size="md" onclick={() => showMergeModal = true} title={m.vekn_merge_modal_title()}>
        <GitMerge class="inline w-3.5 h-3.5 mr-1" />
        {m.vekn_merge()}
      </Button>
    </div>

    <!-- Deceased status: VEKN members only (symmetric with delete for VEKN-less);
         still shown if already set on a VEKN-less member so it can be cleared. -->
    {#if isDeceased || (user.vekn_id && canMarkDeceased)}
      <div class="mt-3 pt-3 border-t border-ash-800 flex items-center justify-between gap-2">
        {#if isDeceased}
          <span class="text-sm text-ash-300 inline-flex items-center gap-1.5">
            <Flower2 class="w-4 h-4 text-ash-400" aria-hidden="true" />
            {m.deceased_status_set()}
          </span>
        {:else}
          <span></span>
        {/if}
        {#if canMarkDeceased}
          <Button variant="secondary" size="md" class="shrink-0" disabled={processingAction} onclick={handleDeceased}>
            {#if !isDeceased}<Flower2 class="w-3.5 h-3.5" aria-hidden="true" />{/if}
            {isDeceased ? m.deceased_clear() : m.deceased_mark()}
          </Button>
        {/if}
      </div>
    {/if}
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
          <Button variant="primary" size="lg" class="flex-1" loading={processingAction} onclick={handleSponsor}>
            {processingAction ? m.vekn_sponsoring() : m.vekn_sponsor()}
          </Button>
          <Button variant="secondary" size="lg" disabled={processingAction} onclick={() => (showSponsorConfirm = false)}>
            {m.common_cancel()}
          </Button>
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
          <Button type="submit" variant="primary" size="lg" class="flex-1" loading={processingAction} disabled={!linkVeknIdInput.trim()}>
            {processingAction ? m.vekn_linking() : m.vekn_link_submit()}
          </Button>
          <Button
            variant="secondary"
            size="lg"
            disabled={processingAction}
            onclick={() => {
              showLinkModal = false;
              linkVeknIdInput = "";
            }}
          >
            {m.common_cancel()}
          </Button>
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
          <Button variant="danger" size="lg" class="flex-1" loading={processingAction} onclick={handleForceAbandon}>
            <TriangleAlert class="w-4 h-4" aria-hidden="true" />
            {processingAction ? m.vekn_abandoning() : m.vekn_force_abandon()}
          </Button>
          <Button variant="secondary" size="lg" disabled={processingAction} onclick={() => (showForceAbandonConfirm = false)}>
            {m.common_cancel()}
          </Button>
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
          <Button type="submit" variant="primary" size="lg" class="flex-1" loading={processingAction} disabled={!mergeTargetUid.trim()}>
            {processingAction ? m.vekn_merging() : m.vekn_merge()}
          </Button>
          <Button
            variant="secondary"
            size="lg"
            disabled={processingAction}
            onclick={() => {
              showMergeModal = false;
              mergeTargetUid = "";
            }}
          >
            {m.common_cancel()}
          </Button>
        </div>
      </form>
    </div>
  </div>
{/if}

<!-- Delete Member Confirmation Modal -->
{#if showDeleteConfirm}
  <div
    role="presentation"
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
    onclick={(e) => { e.stopPropagation(); if (e.target === e.currentTarget) showDeleteConfirm = false; }}
  >
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="delete-modal-title"
      tabindex="-1"
      use:focusOnMount
      onkeydown={(e) => e.key === 'Escape' && (showDeleteConfirm = false)}
      class="bg-dusk-950 rounded-lg shadow-xl border border-ash-800 w-full max-w-md mx-4"
    >
      <div class="p-6 border-b border-ash-800">
        <h2 id="delete-modal-title" class="text-xl font-medium text-crimson-400">{m.member_delete_modal_title()}</h2>
      </div>
      <div class="p-6">
        <p class="text-ash-300 mb-4">
          {m.member_delete_confirm({ name: user.name })}
        </p>
        <p class="text-sm text-crimson-400 mb-6">
          {m.member_delete_warning()}
        </p>
        <div class="flex gap-2">
          <Button variant="danger" size="lg" class="flex-1" loading={processingAction} onclick={handleDelete}>
            <Trash2 class="w-4 h-4" aria-hidden="true" />
            {processingAction ? m.member_deleting() : m.member_delete()}
          </Button>
          <Button variant="secondary" size="lg" disabled={processingAction} onclick={() => (showDeleteConfirm = false)}>
            {m.common_cancel()}
          </Button>
        </div>
      </div>
    </div>
  </div>
{/if}
