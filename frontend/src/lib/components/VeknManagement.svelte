<script lang="ts">
  import type { User } from "$lib/types";
  import { sponsorVeknMember, linkVeknId, forceAbandonVeknId, mergeUsers, setMemberDeceased, deleteMember } from "$lib/api";
  import { showToast } from "$lib/stores/toast.svelte";
  import { UserPlus, Link, Unlink, GitMerge, CloudOff, Flower2, Trash2, TriangleAlert, ArrowLeftRight } from "@lucide/svelte";
  import Button from '$lib/components/Button.svelte';
  import UserPicker from '$lib/components/UserPicker.svelte';
  import Badge from '$lib/components/Badge.svelte';
  import { getCountryFlag } from "$lib/geonames";
  import * as m from '$lib/paraglide/messages.js';

  let {
    user,
    onaction,
    ondelete,
    canMarkDeceased = false,
    canDelete = false,
    canMerge = false,
    // Cross-country official: sponsoring is allowed anywhere, but link/
    // delete/abandon stay country-scoped — render only the Sponsor action.
    sponsorOnly = false,
  }: {
    user: User;
    onaction: (user: User) => void;
    ondelete?: () => void;
    canMarkDeceased?: boolean;
    canDelete?: boolean;
    canMerge?: boolean;
    sponsorOnly?: boolean;
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
  let mergeTarget = $state<User | null>(null);
  let processingAction = $state(false);

  // A uid carrying a VEKN ID is immovable — the backend refuses to soft-delete
  // one, so the survivor must be whichever side holds it. When only the picked
  // account does, the merge still works, just the other way round.
  const mergeSwap = $derived(!!mergeTarget?.vekn_id && !user.vekn_id);
  const mergeBlocked = $derived(!!mergeTarget?.vekn_id && !!user.vekn_id);
  const mergeKeep = $derived(mergeSwap ? mergeTarget : user);
  const mergeDrop = $derived(mergeSwap ? user : mergeTarget);

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
    if (!mergeKeep || !mergeDrop || mergeBlocked) return;
    // Read before the reset below clears what these derive from.
    const swapped = mergeSwap;
    processingAction = true;
    try {
      const result = await mergeUsers(mergeKeep.uid, mergeDrop.uid);
      showToast({ type: "success", message: result.message });
      showMergeModal = false;
      mergeTarget = null;
      // A swapped merge soft-deletes the profile we are standing on.
      if (swapped) ondelete?.();
      else onaction(result.user);
    } catch {
      // Error toast shown by apiRequest
    } finally {
      processingAction = false;
    }
  }
</script>

<div>
  <h2 class="text-lg font-semibold text-ink-bright mb-3">{m.vekn_title()}</h2>
  <div class="bg-surface-card border border-line rounded-lg p-4">
    <p class="text-sm text-ink mb-3">
      {#if user.vekn_id}
        {m.vekn_id_display({ id: user.vekn_id })}
        {#if veknSyncPending}
          <span class="ml-2"><Badge kind="status" tone="pending">
            <CloudOff class="w-3 h-3" aria-hidden="true" />
            {m.vekn_sync_pending_member()}
          </Badge></span>
        {/if}
      {:else}
        {m.vekn_no_id()}
      {/if}
    </p>
    {#if veknSyncPending}
      <p class="text-xs text-ink-faint -mt-2 mb-3">{m.vekn_sync_pending_hint()}</p>
    {/if}
    <div class="flex flex-wrap gap-2">
      {#if !user.vekn_id}
        <Button variant="primary" size="md" onclick={() => showSponsorConfirm = true} title={m.vekn_sponsor_title()}>
          <UserPlus class="inline w-3.5 h-3.5 mr-1" />
          {m.vekn_sponsor()}
        </Button>
        {#if !sponsorOnly}
          <Button variant="secondary" size="md" onclick={() => showLinkModal = true} title={m.vekn_link_modal_title()}>
            <Link class="inline w-3.5 h-3.5 mr-1" />
            {m.vekn_link_btn()}
          </Button>
        {/if}
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
      {#if canMerge}
        <Button variant="secondary" size="md" onclick={() => { mergeTarget = null; showMergeModal = true; }} title={m.vekn_merge_modal_title()}>
          <GitMerge class="inline w-3.5 h-3.5 mr-1" />
          {m.vekn_merge()}
        </Button>
      {/if}
    </div>

    <!-- Deceased status: VEKN members only (symmetric with delete for VEKN-less);
         still shown if already set on a VEKN-less member so it can be cleared. -->
    {#if isDeceased || (user.vekn_id && canMarkDeceased)}
      <div class="mt-3 pt-3 border-t border-line flex items-center justify-between gap-2">
        {#if isDeceased}
          <span class="text-sm text-ink inline-flex items-center gap-1.5">
            <Flower2 class="w-4 h-4 text-ink-muted" aria-hidden="true" />
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
      class="bg-surface-card rounded-lg shadow-xl border border-line w-full max-w-md mx-4 max-h-[85dvh] overflow-y-auto"
    >
      <div class="p-6 border-b border-line">
        <h2 id="sponsor-modal-title" class="text-xl font-medium text-ink-strong">{m.vekn_sponsor_title()}</h2>
      </div>
      <div class="p-6">
        <p class="text-ink mb-4">
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
      class="bg-surface-card rounded-lg shadow-xl border border-line w-full max-w-md mx-4 max-h-[85dvh] overflow-y-auto"
    >
      <div class="p-6 border-b border-line">
        <h2 id="link-modal-title" class="text-xl font-medium text-ink-strong">{m.vekn_link_modal_title()}</h2>
        <p class="mt-2 text-sm text-ink-muted">
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
          <label for="link-vekn-id" class="block text-sm font-medium text-ink-muted mb-1">
            {m.add_player_vekn_id_label()}
          </label>
          <input
            id="link-vekn-id"
            type="text"
            bind:value={linkVeknIdInput}
            placeholder="1234567"
            class="w-full px-3 py-2 border border-line-strong rounded bg-surface-card text-ink-bright focus:ring-2 focus:ring-accent focus:border-transparent"
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
      class="bg-surface-card rounded-lg shadow-xl border border-line w-full max-w-md mx-4 max-h-[85dvh] overflow-y-auto"
    >
      <div class="p-6 border-b border-line">
        <h2 id="force-abandon-modal-title" class="text-xl font-medium text-link">{m.vekn_abandon_title()}</h2>
      </div>
      <div class="p-6">
        <p class="text-ink mb-4">
          {m.vekn_abandon_confirm({ id: user.vekn_id!, name: user.name })}
        </p>
        <p class="text-sm text-link mb-6">
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
      class="bg-surface-card rounded-lg shadow-xl border border-line w-full max-w-md mx-4 max-h-[85dvh] overflow-y-auto"
    >
      <div class="p-6 border-b border-line">
        <h2 id="merge-modal-title" class="text-xl font-medium text-ink-strong">{m.vekn_merge_modal_title()}</h2>
        <p class="mt-2 text-sm text-ink-muted">
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
        {#if !mergeTarget}
          <div>
            <label for="merge-target-search" class="block text-sm font-medium text-ink-muted mb-1">
              {m.vekn_merge_search_label()}
            </label>
            <!-- The only picker that must see non-members: the duplicate being
                 merged away is typically the account that never got a VEKN id. -->
            <UserPicker
              inputId="merge-target-search"
              excludeUids={[user.uid]}
              placeholder={m.vekn_merge_search_placeholder()}
              onselect={(u) => (mergeTarget = u)}
              membersOnly={false}
            />
          </div>
        {:else}
          <div class="flex items-center gap-2 px-3 py-2 rounded border border-line-strong bg-surface-muted">
            <span class="flex-1 text-sm text-ink-bright">
              {#if mergeTarget.country}
                <span class="mr-1">{getCountryFlag(mergeTarget.country)}</span>
              {/if}
              {mergeTarget.name}
              {#if mergeTarget.vekn_id}
                <span class="text-ink-faint ml-2">#{mergeTarget.vekn_id}</span>
              {/if}
            </span>
            <Button variant="secondary" size="sm" disabled={processingAction} onclick={() => (mergeTarget = null)}>
              {m.vekn_merge_change_target()}
            </Button>
          </div>

          {#if mergeBlocked}
            <p class="banner-error border rounded-lg p-3 text-sm flex items-start gap-2">
              <TriangleAlert class="w-4 h-4 shrink-0 mt-0.5" aria-hidden="true" />
              <span>{m.vekn_merge_blocked_notice()}</span>
            </p>
          {:else}
            {#if mergeSwap}
              <p class="banner-warn border rounded-lg p-3 text-sm flex items-start gap-2">
                <ArrowLeftRight class="w-4 h-4 shrink-0 mt-0.5" aria-hidden="true" />
                <span>{m.vekn_merge_swap_notice({ name: mergeTarget.name })}</span>
              </p>
            {/if}
            <p class="text-sm text-ink-muted">
              {m.vekn_merge_summary({ drop: mergeDrop?.name ?? "", keep: mergeKeep?.name ?? "" })}
            </p>
          {/if}
        {/if}

        <div class="flex gap-2">
          {#if mergeTarget && !mergeBlocked}
            <Button type="submit" variant="primary" size="lg" class="flex-1" loading={processingAction}>
              {processingAction ? m.vekn_merging() : m.vekn_merge()}
            </Button>
          {/if}
          <Button
            variant="secondary"
            size="lg"
            class={mergeTarget && !mergeBlocked ? "" : "flex-1"}
            disabled={processingAction}
            onclick={() => {
              showMergeModal = false;
              mergeTarget = null;
            }}
          >
            {m.common_cancel()}
          </Button>
        </div>
      </form>
    </div>
  </div>
{/if}

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
      class="bg-surface-card rounded-lg shadow-xl border border-line w-full max-w-md mx-4 max-h-[85dvh] overflow-y-auto"
    >
      <div class="p-6 border-b border-line">
        <h2 id="delete-modal-title" class="text-xl font-medium text-link">{m.member_delete_modal_title()}</h2>
      </div>
      <div class="p-6">
        <p class="text-ink mb-4">
          {m.member_delete_confirm({ name: user.name })}
        </p>
        <p class="text-sm text-link mb-6">
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
