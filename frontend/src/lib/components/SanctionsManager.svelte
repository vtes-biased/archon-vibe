<script lang="ts">
  import type { User, Sanction, SanctionLevel, SanctionCategory } from "$lib/types";
  import { createSanction, updateSanction, deleteSanctionApi } from "$lib/api";
  import { getActiveSanctionsForUser } from "$lib/db";
  import { visibleSanctions } from "$lib/utils";
  import { showToast } from "$lib/stores/toast.svelte";
  import SanctionBadge from "./SanctionBadge.svelte";
  import { Pencil, TriangleAlert, CircleCheck, Trash2 } from "@lucide/svelte";
  import Button from '$lib/components/Button.svelte';
  import * as m from '$lib/paraglide/messages.js';

  let {
    user,
    canIssueSanctions,
    inline = false,
  }: {
    user: User;
    canIssueSanctions: boolean;
    inline?: boolean;
  } = $props();

  // Sanctions state
  let userSanctions = $state<Sanction[]>([]);
  let showSanctionModal = $state(false);
  let sanctionTargetUser = $state<User | null>(null);
  let sanctionLevel = $state<SanctionLevel>("probation");
  let sanctionCategory = $state<SanctionCategory>("unsportsmanlike_conduct");
  let sanctionDescription = $state("");
  let sanctionExpiresAt = $state("");
  let creatingSanction = $state(false);

  // Edit sanction modal
  let showEditSanctionModal = $state(false);
  let editingSanction = $state<Sanction | null>(null);
  let editSanctionLevel = $state<SanctionLevel>("warning");
  let editSanctionCategory = $state<SanctionCategory>("unsportsmanlike_conduct");
  let editSanctionDescription = $state("");
  let editSanctionExpiresAt = $state("");
  let processingSanctionAction = $state(false);

  // Load sanctions when user changes
  $effect(() => {
    getActiveSanctionsForUser(user.uid).then((sanctions) => {
      userSanctions = sanctions;
    });
  });

  // Cautions are private to their tournament; the member directory only
  // surfaces them to managers (IC/Ethics).
  const shownSanctions = $derived(visibleSanctions(userSanctions, canIssueSanctions));

  const formatDate = (iso: string) =>
    new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });

  const expiryRequired = $derived(sanctionLevel === "probation");
  const expiryAllowed = $derived(sanctionLevel === "suspension" || sanctionLevel === "probation");

  const editExpiryRequired = $derived(editSanctionLevel === "probation");
  const editExpiryAllowed = $derived(editSanctionLevel === "suspension" || editSanctionLevel === "probation");

  const editSanctionHasChanges = $derived(() => {
    if (!editingSanction) return false;
    const origExpiry = editingSanction.expires_at
      ? new Date(editingSanction.expires_at).toISOString().split("T")[0]
      : "";
    return (
      editSanctionLevel !== editingSanction.level ||
      editSanctionCategory !== editingSanction.category ||
      editSanctionDescription !== editingSanction.description ||
      editSanctionExpiresAt !== origExpiry
    );
  });

  function focusOnMount(node: HTMLElement) {
    const input = node.querySelector<HTMLElement>("input:not(.hidden):not([type=hidden]), textarea, select");
    (input ?? node).focus();
  }

  function openSanctionModal() {
    sanctionTargetUser = user;
    sanctionLevel = "probation";
    sanctionCategory = "unsportsmanlike_conduct";
    sanctionDescription = "";
    sanctionExpiresAt = "";
    showSanctionModal = true;
  }

  function openEditSanctionModal(sanction: Sanction) {
    editingSanction = sanction;
    editSanctionLevel = sanction.level;
    editSanctionCategory = sanction.category;
    editSanctionDescription = String(sanction.description || "");
    editSanctionExpiresAt = sanction.expires_at
      ? new Date(sanction.expires_at).toISOString().split("T")[0] ?? ""
      : "";
    showEditSanctionModal = true;
  }

  function closeEditSanctionModal() {
    showEditSanctionModal = false;
    editingSanction = null;
  }

  async function handleCreateSanction() {
    if (!sanctionTargetUser || !sanctionDescription.trim()) return;
    creatingSanction = true;
    const targetUid = sanctionTargetUser.uid;
    try {
      const sanction = await createSanction({
        user_uid: targetUid,
        level: sanctionLevel,
        category: sanctionCategory,
        description: sanctionDescription.trim(),
        expires_at: sanctionExpiresAt || null,
      });
      userSanctions = [...userSanctions, sanction];
      showToast({ type: "success", message: m.sanction_mgr_issued_success() });
      showSanctionModal = false;
      sanctionTargetUser = null;
      sanctionLevel = "probation";
      sanctionCategory = "unsportsmanlike_conduct";
      sanctionDescription = "";
      sanctionExpiresAt = "";
    } catch {
      // Error toast shown by apiRequest
    } finally {
      creatingSanction = false;
    }
  }

  async function handleSaveSanction() {
    if (!editingSanction) return;
    const sanctionUid = editingSanction.uid;
    processingSanctionAction = true;
    try {
      const updated = await updateSanction(sanctionUid, {
        level: editSanctionLevel,
        category: editSanctionCategory,
        description: editSanctionDescription.trim(),
        expires_at: editExpiryAllowed && editSanctionExpiresAt ? editSanctionExpiresAt : undefined,
      });
      userSanctions = userSanctions.map((s) => (s.uid === sanctionUid ? updated : s));
      showToast({ type: "success", message: m.sanction_mgr_updated() });
      closeEditSanctionModal();
    } catch {
      // Error toast shown by apiRequest
    } finally {
      processingSanctionAction = false;
    }
  }

  async function handleLiftSanction() {
    if (!editingSanction) return;
    const sanctionUid = editingSanction.uid;
    processingSanctionAction = true;
    try {
      const updated = await updateSanction(sanctionUid, { lifted: true });
      userSanctions = userSanctions.map((s) => (s.uid === sanctionUid ? updated : s));
      showToast({ type: "success", message: m.sanction_mgr_lifted_success() });
      closeEditSanctionModal();
    } catch {
      // Error toast shown by apiRequest
    } finally {
      processingSanctionAction = false;
    }
  }

  async function handleDeleteSanction() {
    if (!editingSanction) return;
    const sanctionUid = editingSanction.uid;
    processingSanctionAction = true;
    try {
      userSanctions = userSanctions.filter((s) => s.uid !== sanctionUid);
      await deleteSanctionApi(sanctionUid);
      showToast({ type: "success", message: m.sanction_mgr_deleted() });
      closeEditSanctionModal();
    } catch {
      if (user) {
        userSanctions = await getActiveSanctionsForUser(user.uid);
      }
    } finally {
      processingSanctionAction = false;
    }
  }
</script>

{#if inline}
  <!-- Inline mode: just badges in a row (for User.svelte view mode) -->
  {#if shownSanctions.length > 0}
    <div class="flex items-start gap-2">
      <span class="font-medium">{m.sanction_mgr_title()}:</span>
      <div class="flex flex-wrap gap-1">
        {#each shownSanctions as sanction (sanction.uid)}
          <SanctionBadge {sanction} />
        {/each}
      </div>
    </div>
  {/if}
{:else}
  <!-- Standalone section card -->
  {#if canIssueSanctions || shownSanctions.length > 0}
    <div class="mt-6">
      <h2 class="text-lg font-semibold text-ash-200 mb-3">{m.sanction_mgr_title()}</h2>
      <div class="bg-dusk-950 border border-ash-800 rounded-lg p-4">
        {#if shownSanctions.length > 0}
          <div class="space-y-2 {canIssueSanctions ? 'mb-4' : ''}">
            {#each shownSanctions as sanction (sanction.uid)}
              {#if canIssueSanctions}
                <button
                  type="button"
                  onclick={() => openEditSanctionModal(sanction)}
                  class="w-full flex items-center justify-between gap-2 p-3 bg-dusk-900 rounded border border-ash-700 hover:border-ash-600 transition-colors text-left"
                >
                  <div class="flex-1 min-w-0">
                    <div class="flex items-center gap-2">
                      <SanctionBadge {sanction} />
                      <span class="text-sm text-ash-300 truncate">{sanction.description}</span>
                    </div>
                    <div class="text-xs text-ash-500 mt-1">
                      {formatDate(sanction.issued_at)}
                      {#if sanction.expires_at}
                        → {formatDate(sanction.expires_at)}
                      {/if}
                    </div>
                  </div>
                  <Pencil class="w-4 h-4 text-ash-500 flex-shrink-0" />
                </button>
              {:else}
                <div class="p-3 bg-dusk-900 rounded border border-ash-700">
                  <div class="flex items-center gap-2">
                    <SanctionBadge {sanction} />
                    <span class="text-sm text-ash-300">{sanction.description}</span>
                  </div>
                  <div class="text-xs text-ash-500 mt-1">
                    {formatDate(sanction.issued_at)}
                    {#if sanction.expires_at}
                      → {formatDate(sanction.expires_at)}
                    {/if}
                  </div>
                </div>
              {/if}
            {/each}
          </div>
        {/if}

        {#if canIssueSanctions}
          <div class="flex flex-wrap gap-2">
            <Button variant="primary" size="md" onclick={() => openSanctionModal()} title={m.sanction_mgr_issue_btn()}>
              <TriangleAlert class="inline w-3.5 h-3.5 mr-1" />
              {m.sanction_mgr_issue_btn()}
            </Button>
          </div>
        {/if}
      </div>
    </div>
  {/if}
{/if}

<!-- Issue Sanction Modal -->
{#if showSanctionModal && sanctionTargetUser}
  <div
    role="presentation"
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
    onclick={(e) => { e.stopPropagation(); if (e.target === e.currentTarget) showSanctionModal = false; }}
  >
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="sanction-modal-title"
      tabindex="-1"
      use:focusOnMount
      onkeydown={(e) => e.key === 'Escape' && (showSanctionModal = false)}
      class="bg-dusk-950 rounded-lg shadow-xl border border-crimson-800/50 w-full max-w-md mx-4"
    >
      <div class="p-6 border-b border-ash-800">
        <h2 id="sanction-modal-title" class="text-xl font-medium text-crimson-400">{m.sanction_mgr_issue_btn()}</h2>
        <p class="mt-2 text-sm text-ash-400">
          {m.sanction_mgr_issue_to({ name: sanctionTargetUser.name })}
        </p>
      </div>
      <form
        onsubmit={(e) => {
          e.preventDefault();
          handleCreateSanction();
        }}
        class="p-6 space-y-4"
      >
        <div>
          <label for="sanction-level" class="block text-sm font-medium text-ash-400 mb-1">
            {m.common_level()} *
          </label>
          <select
            id="sanction-level"
            bind:value={sanctionLevel}
            class="w-full px-3 py-2 border border-ash-600 rounded bg-dusk-950 text-ash-200 focus:ring-2 focus:ring-crimson-500 focus:border-transparent"
          >
            <option value="probation">{m.sanction_level_probation()}</option>
            <option value="suspension">{m.sanction_level_suspension()}</option>
          </select>
          {#if sanctionLevel === "suspension"}
            <p class="mt-1 text-xs text-ash-500">
              {m.sanction_mgr_permanent_hint()}
            </p>
          {/if}
        </div>

        <div>
          <label for="sanction-category" class="block text-sm font-medium text-ash-400 mb-1">
            {m.common_category()} *
          </label>
          <select
            id="sanction-category"
            bind:value={sanctionCategory}
            class="w-full px-3 py-2 border border-ash-600 rounded bg-dusk-950 text-ash-200 focus:ring-2 focus:ring-crimson-500 focus:border-transparent"
          >
            <option value="procedural_error">{m.sanction_cat_procedural_error()}</option>
            <option value="tournament_error">{m.sanction_cat_tournament_error()}</option>
            <option value="unsportsmanlike_conduct">{m.sanction_cat_unsportsmanlike_conduct()}</option>
          </select>
        </div>

        <div>
          <label for="sanction-description" class="block text-sm font-medium text-ash-400 mb-1">
            {m.common_description()} *
          </label>
          <textarea
            id="sanction-description"
            bind:value={sanctionDescription}
            rows="3"
            placeholder={m.sanction_mgr_description_placeholder()}
            required
            class="w-full px-3 py-2 border border-ash-600 rounded bg-dusk-950 text-ash-200 focus:ring-2 focus:ring-crimson-500 focus:border-transparent resize-none"
          ></textarea>
        </div>

        {#if expiryAllowed}
          <div>
            <label for="sanction-expires" class="block text-sm font-medium text-ash-400 mb-1">
              {m.sanction_mgr_expires_at()} {expiryRequired ? "*" : ""}
            </label>
            <input
              id="sanction-expires"
              type="date"
              bind:value={sanctionExpiresAt}
              required={expiryRequired}
              min={new Date().toISOString().split("T")[0]}
              class="w-full px-3 py-2 border border-ash-600 rounded bg-dusk-950 text-ash-200 focus:ring-2 focus:ring-crimson-500 focus:border-transparent"
            />
            <p class="mt-1 text-xs text-ash-500">
              {m.sanction_mgr_max_expiry()}
            </p>
          </div>
        {/if}

        <div class="flex gap-2 pt-2">
          <Button
            type="submit"
            variant="primary"
            size="lg"
            class="flex-1"
            loading={creatingSanction}
            disabled={!sanctionDescription.trim() || (expiryRequired && !sanctionExpiresAt)}
          >
            {creatingSanction ? m.sanction_mgr_issuing() : m.sanction_mgr_issue_btn()}
          </Button>
          <Button
            variant="secondary"
            size="lg"
            disabled={creatingSanction}
            onclick={() => { showSanctionModal = false; sanctionTargetUser = null; }}
          >
            {m.common_cancel()}
          </Button>
        </div>
      </form>
    </div>
  </div>
{/if}

<!-- Edit Sanction Modal -->
{#if showEditSanctionModal && editingSanction}
  <div
    role="presentation"
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
    onclick={(e) => { e.stopPropagation(); if (e.target === e.currentTarget) closeEditSanctionModal(); }}
  >
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="edit-sanction-modal-title"
      tabindex="-1"
      use:focusOnMount
      onkeydown={(e) => e.key === 'Escape' && closeEditSanctionModal()}
      class="bg-dusk-950 rounded-lg shadow-xl border border-ash-800 w-full max-w-md mx-4"
    >
      <div class="p-6 border-b border-ash-800">
        <div class="flex items-center justify-between">
          <h2 id="edit-sanction-modal-title" class="text-xl font-medium text-bone-100">{m.sanction_mgr_edit_title()}</h2>
          {#if editingSanction.lifted_at}
            <span class="text-xs badge-success px-2 py-1 rounded">{m.sanction_lifted()}</span>
          {/if}
        </div>
        <p class="mt-1 text-xs text-ash-500">
          {m.sanction_issued({ date: new Date(editingSanction.issued_at).toLocaleDateString() })}
        </p>
      </div>
      <div class="p-6 space-y-4">
        <div>
          <label for="edit-sanction-level" class="block text-sm font-medium text-ash-400 mb-1">
            {m.common_level()}
          </label>
          <select
            id="edit-sanction-level"
            bind:value={editSanctionLevel}
            disabled={!!editingSanction.lifted_at}
            class="w-full px-3 py-2 border border-ash-600 rounded bg-dusk-950 text-ash-200 focus:ring-2 focus:ring-crimson-500 focus:border-transparent disabled:opacity-50"
          >
            <option value="caution">{m.sanction_level_caution()}</option>
            <option value="warning">{m.sanction_level_warning()}</option>
            <option value="standings_adjustment">{m.sanction_level_sa()}</option>
            <option value="disqualification">{m.sanction_level_disqualification()}</option>
            <option value="probation">{m.sanction_level_probation()}</option>
            <option value="suspension">{m.sanction_level_suspension()}</option>
          </select>
        </div>

        <div>
          <label for="edit-sanction-category" class="block text-sm font-medium text-ash-400 mb-1">
            {m.common_category()}
          </label>
          <select
            id="edit-sanction-category"
            bind:value={editSanctionCategory}
            disabled={!!editingSanction.lifted_at}
            class="w-full px-3 py-2 border border-ash-600 rounded bg-dusk-950 text-ash-200 focus:ring-2 focus:ring-crimson-500 focus:border-transparent disabled:opacity-50"
          >
            <option value="procedural_error">{m.sanction_cat_procedural_error()}</option>
            <option value="tournament_error">{m.sanction_cat_tournament_error()}</option>
            <option value="unsportsmanlike_conduct">{m.sanction_cat_unsportsmanlike_conduct()}</option>
          </select>
        </div>

        <div>
          <label for="edit-sanction-description" class="block text-sm font-medium text-ash-400 mb-1">
            {m.common_description()}
          </label>
          <textarea
            id="edit-sanction-description"
            bind:value={editSanctionDescription}
            disabled={!!editingSanction.lifted_at}
            rows="3"
            class="w-full px-3 py-2 border border-ash-600 rounded bg-dusk-950 text-ash-200 focus:ring-2 focus:ring-crimson-500 focus:border-transparent resize-none disabled:opacity-50"
          ></textarea>
        </div>

        {#if editExpiryAllowed}
          <div>
            <label for="edit-sanction-expires" class="block text-sm font-medium text-ash-400 mb-1">
              {m.sanction_mgr_expires_at()} {editExpiryRequired ? "*" : ""}
            </label>
            <input
              id="edit-sanction-expires"
              type="date"
              bind:value={editSanctionExpiresAt}
              disabled={!!editingSanction.lifted_at}
              required={editExpiryRequired}
              min={new Date().toISOString().split("T")[0]}
              class="w-full px-3 py-2 border border-ash-600 rounded bg-dusk-950 text-ash-200 focus:ring-2 focus:ring-crimson-500 focus:border-transparent disabled:opacity-50"
            />
            {#if editSanctionLevel === "suspension"}
              <p class="mt-1 text-xs text-ash-500">{m.sanction_mgr_permanent_hint()}</p>
            {/if}
          </div>
        {/if}

        <div class="flex flex-col gap-2 pt-4 border-t border-ash-800">
          {#if !editingSanction.lifted_at && editSanctionHasChanges()}
            <Button
              variant="primary"
              size="lg"
              block
              loading={processingSanctionAction}
              disabled={!editSanctionDescription.trim() || (editExpiryRequired && !editSanctionExpiresAt)}
              onclick={handleSaveSanction}
            >
              {processingSanctionAction ? m.common_saving() : m.sanction_mgr_save_changes()}
            </Button>
          {/if}

          <div class="flex gap-2">
            {#if (editingSanction.level === "probation" || editingSanction.level === "suspension") && !editingSanction.lifted_at}
              <Button variant="primary" size="lg" class="flex-1" loading={processingSanctionAction} onclick={handleLiftSanction}>
                <CircleCheck class="inline w-4 h-4 mr-1" />
                {processingSanctionAction ? m.sanction_mgr_lifting() : m.sanction_mgr_lift()}
              </Button>
            {/if}

            <Button variant="danger" size="lg" class="flex-1" loading={processingSanctionAction} onclick={handleDeleteSanction}>
              <Trash2 class="inline w-4 h-4 mr-1" />
              {processingSanctionAction ? m.common_deleting() : m.common_delete()}
            </Button>

            <Button variant="secondary" size="lg" disabled={processingSanctionAction} onclick={closeEditSanctionModal}>
              {m.common_cancel()}
            </Button>
          </div>
        </div>
      </div>
    </div>
  </div>
{/if}
