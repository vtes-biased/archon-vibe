<script lang="ts">
  import type { User, Sanction, SanctionLevel, SanctionCategory } from "$lib/types";
  import { createSanction, updateSanction, deleteSanctionApi } from "$lib/api";
  import { getActiveSanctionsForUser } from "$lib/db";
  import { showToast } from "$lib/stores/toast.svelte";
  import SanctionBadge from "./SanctionBadge.svelte";
  import Icon from "@iconify/svelte";

  let {
    user,
    canIssueSanctions,
  }: {
    user: User;
    canIssueSanctions: boolean;
  } = $props();

  // Sanctions state
  let userSanctions = $state<Sanction[]>([]);
  let showSanctionModal = $state(false);
  let sanctionTargetUser = $state<User | null>(null);
  let sanctionLevel = $state<SanctionLevel>("probation");
  let sanctionCategory = $state<SanctionCategory>("other");
  let sanctionDescription = $state("");
  let sanctionExpiresAt = $state("");
  let creatingSanction = $state(false);

  // Edit sanction modal
  let showEditSanctionModal = $state(false);
  let editingSanction = $state<Sanction | null>(null);
  let editSanctionLevel = $state<SanctionLevel>("warning");
  let editSanctionCategory = $state<SanctionCategory>("other");
  let editSanctionDescription = $state("");
  let editSanctionExpiresAt = $state("");
  let processingSanctionAction = $state(false);

  // Load sanctions when user changes
  $effect(() => {
    getActiveSanctionsForUser(user.uid).then((sanctions) => {
      userSanctions = sanctions;
    });
  });

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
    node.focus();
  }

  function openSanctionModal() {
    sanctionTargetUser = user;
    sanctionLevel = "probation";
    sanctionCategory = "other";
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
      showToast({ type: "success", message: `${sanctionLevel.toUpperCase()} issued successfully` });
      showSanctionModal = false;
      sanctionTargetUser = null;
      sanctionLevel = "probation";
      sanctionCategory = "other";
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
      showToast({ type: "success", message: "Sanction updated" });
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
      showToast({ type: "success", message: "Sanction lifted" });
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
      showToast({ type: "success", message: "Sanction deleted" });
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

<!-- Inline sanctions section -->
{#if canIssueSanctions}
  <fieldset class="border border-crimson-800/50 rounded p-4">
    <legend class="text-sm font-medium text-crimson-400 px-2">Sanctions</legend>

    {#if userSanctions.length > 0}
      <div class="mb-4 space-y-2">
        {#each userSanctions as sanction (sanction.uid)}
          <button
            type="button"
            onclick={(e) => { e.stopPropagation(); openEditSanctionModal(sanction); }}
            class="w-full flex items-center justify-between gap-2 p-2 bg-dusk-900 rounded border border-ash-700 hover:border-ash-600 transition-colors text-left"
          >
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2">
                <SanctionBadge {sanction} />
                <span class="text-xs text-ash-400 truncate">{sanction.description}</span>
              </div>
              <div class="text-xs text-ash-500 mt-1">
                {new Date(sanction.issued_at).toLocaleDateString()}
                {#if sanction.expires_at}
                  → {new Date(sanction.expires_at).toLocaleDateString()}
                {/if}
              </div>
            </div>
            <Icon icon="lucide:pencil" class="w-4 h-4 text-ash-500" />
          </button>
        {/each}
      </div>
    {/if}

    <div class="flex flex-wrap gap-2">
      <button
        type="button"
        onclick={(e) => { e.stopPropagation(); openSanctionModal(); }}
        class="px-3 py-1 text-xs bg-crimson-800 hover:bg-crimson-700 text-bone-100 rounded transition-colors"
        title="Issue a sanction"
      >
        <Icon icon="lucide:alert-triangle" class="inline w-3 h-3 mr-1" />
        Issue Sanction
      </button>
    </div>
  </fieldset>
{/if}

<!-- View mode: sanctions badges -->
{#if !canIssueSanctions && userSanctions.length > 0}
  <div class="flex items-start gap-2">
    <span class="font-medium">Sanctions:</span>
    <div class="flex flex-wrap gap-1">
      {#each userSanctions as sanction (sanction.uid)}
        <SanctionBadge {sanction} />
      {/each}
    </div>
  </div>
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
        <h2 id="sanction-modal-title" class="text-xl font-medium text-crimson-400">Issue Sanction</h2>
        <p class="mt-2 text-sm text-ash-400">
          Issue a sanction to <strong class="text-bone-100">{sanctionTargetUser.name}</strong>
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
            Level *
          </label>
          <select
            id="sanction-level"
            bind:value={sanctionLevel}
            class="w-full px-3 py-2 border border-ash-600 rounded bg-dusk-950 text-ash-200 focus:ring-2 focus:ring-crimson-500 focus:border-transparent"
          >
            <option value="probation">Probation</option>
            <option value="suspension">Suspension</option>
          </select>
          {#if sanctionLevel === "suspension"}
            <p class="mt-1 text-xs text-ash-500">
              Leave expiry empty for permanent ban
            </p>
          {/if}
        </div>

        <div>
          <label for="sanction-category" class="block text-sm font-medium text-ash-400 mb-1">
            Category *
          </label>
          <select
            id="sanction-category"
            bind:value={sanctionCategory}
            class="w-full px-3 py-2 border border-ash-600 rounded bg-dusk-950 text-ash-200 focus:ring-2 focus:ring-crimson-500 focus:border-transparent"
          >
            <option value="deck_problem">Deck Problem</option>
            <option value="procedural">Procedural</option>
            <option value="cheating">Cheating</option>
            <option value="unsporting">Unsporting Conduct</option>
            <option value="other">Other</option>
          </select>
        </div>

        <div>
          <label for="sanction-description" class="block text-sm font-medium text-ash-400 mb-1">
            Description *
          </label>
          <textarea
            id="sanction-description"
            bind:value={sanctionDescription}
            rows="3"
            placeholder="Describe the reason for this sanction..."
            required
            class="w-full px-3 py-2 border border-ash-600 rounded bg-dusk-950 text-ash-200 focus:ring-2 focus:ring-crimson-500 focus:border-transparent resize-none"
          ></textarea>
        </div>

        {#if expiryAllowed}
          <div>
            <label for="sanction-expires" class="block text-sm font-medium text-ash-400 mb-1">
              Expires At {expiryRequired ? "*" : "(optional)"}
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
              Maximum 18 months from today
            </p>
          </div>
        {/if}

        <div class="flex gap-2 pt-2">
          <button
            type="submit"
            disabled={creatingSanction || !sanctionDescription.trim() || (expiryRequired && !sanctionExpiresAt)}
            class="flex-1 px-4 py-2 bg-crimson-700 hover:bg-crimson-600 disabled:bg-ash-700 text-bone-100 rounded font-medium transition-colors disabled:cursor-not-allowed"
          >
            {creatingSanction ? "Issuing..." : "Issue Sanction"}
          </button>
          <button
            type="button"
            onclick={() => { showSanctionModal = false; sanctionTargetUser = null; }}
            disabled={creatingSanction}
            class="px-4 py-2 bg-ash-700 hover:bg-ash-600 text-ash-200 rounded font-medium transition-colors disabled:cursor-not-allowed"
          >
            Cancel
          </button>
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
          <h2 id="edit-sanction-modal-title" class="text-xl font-medium text-bone-100">Edit Sanction</h2>
          {#if editingSanction.lifted_at}
            <span class="text-xs text-emerald-400 bg-emerald-900/30 px-2 py-1 rounded">Lifted</span>
          {/if}
        </div>
        <p class="mt-1 text-xs text-ash-500">
          Issued: {new Date(editingSanction.issued_at).toLocaleDateString()}
        </p>
      </div>
      <div class="p-6 space-y-4">
        <div>
          <label for="edit-sanction-level" class="block text-sm font-medium text-ash-400 mb-1">
            Level
          </label>
          <select
            id="edit-sanction-level"
            bind:value={editSanctionLevel}
            disabled={!!editingSanction.lifted_at}
            class="w-full px-3 py-2 border border-ash-600 rounded bg-dusk-950 text-ash-200 focus:ring-2 focus:ring-crimson-500 focus:border-transparent disabled:opacity-50"
          >
            <option value="caution">Caution</option>
            <option value="warning">Warning</option>
            <option value="disqualification">Disqualification</option>
            <option value="probation">Probation</option>
            <option value="suspension">Suspension</option>
          </select>
        </div>

        <div>
          <label for="edit-sanction-category" class="block text-sm font-medium text-ash-400 mb-1">
            Category
          </label>
          <select
            id="edit-sanction-category"
            bind:value={editSanctionCategory}
            disabled={!!editingSanction.lifted_at}
            class="w-full px-3 py-2 border border-ash-600 rounded bg-dusk-950 text-ash-200 focus:ring-2 focus:ring-crimson-500 focus:border-transparent disabled:opacity-50"
          >
            <option value="deck_problem">Deck Problem</option>
            <option value="procedural">Procedural</option>
            <option value="cheating">Cheating</option>
            <option value="unsporting">Unsporting Conduct</option>
            <option value="other">Other</option>
          </select>
        </div>

        <div>
          <label for="edit-sanction-description" class="block text-sm font-medium text-ash-400 mb-1">
            Description
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
              Expires At {editExpiryRequired ? "*" : "(optional)"}
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
              <p class="mt-1 text-xs text-ash-500">Leave empty for permanent ban</p>
            {/if}
          </div>
        {/if}

        <div class="flex flex-col gap-2 pt-4 border-t border-ash-800">
          {#if !editingSanction.lifted_at && editSanctionHasChanges()}
            <button
              type="button"
              onclick={handleSaveSanction}
              disabled={processingSanctionAction || !editSanctionDescription.trim() || (editExpiryRequired && !editSanctionExpiresAt)}
              class="w-full px-4 py-2 bg-crimson-700 hover:bg-crimson-600 disabled:bg-ash-700 text-bone-100 rounded font-medium transition-colors disabled:cursor-not-allowed"
            >
              {processingSanctionAction ? "Saving..." : "Save Changes"}
            </button>
          {/if}

          <div class="flex gap-2">
            {#if (editingSanction.level === "probation" || editingSanction.level === "suspension") && !editingSanction.lifted_at}
              <button
                type="button"
                onclick={handleLiftSanction}
                disabled={processingSanctionAction}
                class="flex-1 px-4 py-2 bg-emerald-700 hover:bg-emerald-600 disabled:bg-ash-700 text-bone-100 rounded font-medium transition-colors disabled:cursor-not-allowed"
              >
                <Icon icon="lucide:check-circle" class="inline w-4 h-4 mr-1" />
                {processingSanctionAction ? "Lifting..." : "Lift"}
              </button>
            {/if}

            <button
              type="button"
              onclick={handleDeleteSanction}
              disabled={processingSanctionAction}
              class="flex-1 px-4 py-2 bg-crimson-800 hover:bg-crimson-700 disabled:bg-ash-700 text-bone-100 rounded font-medium transition-colors disabled:cursor-not-allowed"
            >
              <Icon icon="lucide:trash-2" class="inline w-4 h-4 mr-1" />
              {processingSanctionAction ? "Deleting..." : "Delete"}
            </button>

            <button
              type="button"
              onclick={closeEditSanctionModal}
              disabled={processingSanctionAction}
              class="px-4 py-2 bg-ash-700 hover:bg-ash-600 text-ash-200 rounded font-medium transition-colors disabled:cursor-not-allowed"
            >
              Cancel
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
{/if}
