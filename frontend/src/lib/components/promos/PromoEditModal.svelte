<script lang="ts">
  import { onDestroy } from 'svelte';
  import type { League, Promo, PromoKind, TournamentRank } from "$lib/types";
  import { getAllLeagues } from "$lib/db";
  import { ApiError, createPromo, updatePromo, deletePromoCatalogEntry, uploadPromoImage, deletePromoImage, type PromoPayload } from "$lib/api";
  import { promoImageUrl } from "$lib/promo-utils";
  import { showToast } from "$lib/stores/toast.svelte";
  import { toUserMessage } from "$lib/errors";
  import Button from "$lib/components/Button.svelte";
  import { Trash2, TriangleAlert, X } from "@lucide/svelte";
  import * as m from '$lib/paraglide/messages.js';

  let {
    promo = null,
    onclose,
    onsaved,
  }: {
    promo?: Promo | null; // null = create
    onclose: () => void;
    onsaved: () => void;
  } = $props();

  // Captured state: snapshot at open so SSE updates never mutate the form mid-edit.
  // svelte-ignore state_referenced_locally
  let name = $state(promo?.name ?? "");
  // svelte-ignore state_referenced_locally
  let kind = $state<PromoKind>(promo?.kind ?? "card");
  // svelte-ignore state_referenced_locally
  let description = $state(promo?.description ?? "");
  // svelte-ignore state_referenced_locally
  let releaseDate = $state(promo?.release_date?.slice(0, 10) ?? "");
  // svelte-ignore state_referenced_locally
  let allowedRanks = $state<TournamentRank[]>([...(promo?.allowed_ranks ?? [])]);
  // svelte-ignore state_referenced_locally
  let leagueUids = $state<string[]>([...(promo?.league_uids ?? [])]);
  // svelte-ignore state_referenced_locally
  let active = $state(promo?.active ?? true);

  // Rank gating only distinguishes championships ("" = regular events, not a gate).
  const RANKS: TournamentRank[] = ["National Championship", "Continental Championship"];

  let leagues = $state<League[]>([]);
  $effect(() => {
    getAllLeagues().then((ls) => {
      leagues = ls.filter((l) => !l.deleted_at).sort((a, b) => a.name.localeCompare(b.name));
    });
  });

  function toggleIn<T>(list: T[], value: T): T[] {
    return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
  }

  // Image: plain file input (NO cropper — promo art is variable-aspect pre-made
  // scans). webp/png/jpeg, 1MB max — mirrors the server-side check.
  const ALLOWED_TYPES = ["image/webp", "image/png", "image/jpeg"];
  const MAX_IMAGE_SIZE = 1024 * 1024;
  let imageFile = $state<File | null>(null);
  let previewUrl = $state<string | null>(null);
  let removeImage = $state(false);
  let imageError = $state("");
  let fileInput: HTMLInputElement | undefined;

  const shownImageUrl = $derived(
    previewUrl ?? (promo && !removeImage ? promoImageUrl(promo) : null)
  );

  function handleFileSelect(e: Event) {
    const file = (e.target as HTMLInputElement).files?.[0];
    if (!file) return;
    imageError = "";
    if (!ALLOWED_TYPES.includes(file.type)) {
      imageError = m.promo_image_invalid_type();
      return;
    }
    if (file.size > MAX_IMAGE_SIZE) {
      imageError = m.promo_image_too_large();
      return;
    }
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    imageFile = file;
    previewUrl = URL.createObjectURL(file);
    removeImage = false;
  }

  function handleRemoveImage() {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = null;
    imageFile = null;
    imageError = "";
    removeImage = true;
    if (fileInput) fileInput.value = "";
  }

  onDestroy(() => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
  });

  let saving = $state(false);
  // Delete (edit mode): 409 = referenced by reports/raffles/ledger → offer retire.
  let deleting = $state(false);
  let deleteConflict = $state(false);
  let deleteError = $state("");
  const canSave = $derived(name.trim().length > 0 && !saving && !deleting);

  async function save() {
    if (!canSave) return;
    saving = true;
    const payload: PromoPayload = {
      name: name.trim(),
      kind,
      description: description.trim(),
      release_date: releaseDate || null,
      active,
      allowed_ranks: [...allowedRanks],
      league_uids: [...leagueUids],
    };
    let uid: string;
    try {
      if (promo) {
        await updatePromo(promo.uid, payload);
        uid = promo.uid;
      } else {
        uid = (await createPromo(payload)).uid;
      }
    } catch {
      // Error toast shown by apiRequest; keep the form open for a retry.
      saving = false;
      return;
    }
    try {
      if (removeImage && promo?.image_path && !imageFile) await deletePromoImage(uid);
      if (imageFile) await uploadPromoImage(uid, imageFile);
    } catch {
      // Toast shown by apiRequest — the promo itself saved; image can be re-edited.
    }
    saving = false;
    showToast({ type: "success", message: promo ? m.promo_updated_toast() : m.promo_created_toast() });
    onsaved();
    onclose();
  }

  async function handleDelete() {
    if (!promo || deleting) return;
    deleting = true;
    deleteConflict = false;
    deleteError = "";
    try {
      await deletePromoCatalogEntry(promo.uid);
      showToast({ type: "success", message: m.promo_deleted_toast() });
      onsaved();
      onclose();
    } catch (e) {
      // The helper suppresses the toast — render inline.
      if (e instanceof ApiError && e.status === 409) deleteConflict = true;
      else deleteError = toUserMessage(e, m.promo_delete_failed());
    } finally {
      deleting = false;
    }
  }

  async function retireInstead() {
    if (!promo || deleting) return;
    deleting = true;
    try {
      await updatePromo(promo.uid, { active: false });
      showToast({ type: "success", message: m.promo_retired_toast() });
      onsaved();
      onclose();
    } catch {
      // Error toast shown by apiRequest
    } finally {
      deleting = false;
    }
  }

  function requestClose() {
    if (!saving && !deleting) onclose();
  }

  function focusOnMount(node: HTMLElement) {
    const input = node.querySelector<HTMLElement>("input:not([type=hidden]):not([type=file]), textarea, select");
    (input ?? node).focus();
  }

  const inputClass =
    'w-full px-3 py-2 text-sm border border-line-strong rounded-lg bg-surface-card text-ink-bright focus:ring-2 focus:ring-accent focus:border-transparent';
</script>

<!-- Full-screen sheet on mobile, centered card at sm:+ -->
<div
  role="presentation"
  class="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm sm:flex sm:items-center sm:justify-center sm:p-4"
  onclick={(e) => { e.stopPropagation(); if (e.target === e.currentTarget) requestClose(); }}
>
  <div
    role="dialog"
    aria-modal="true"
    aria-labelledby="promo-edit-title"
    tabindex="-1"
    use:focusOnMount
    onkeydown={(e) => { e.stopPropagation(); if (e.key === 'Escape') requestClose(); }}
    class="bg-surface-card w-full h-full overflow-y-auto pt-safe-t pb-safe-b sm:pt-0 sm:pb-safe-b sm:h-auto sm:max-h-[90dvh] sm:max-w-lg sm:rounded-lg sm:border sm:border-line sm:shadow-xl"
  >
    <div class="p-6 border-b border-line">
      <h2 id="promo-edit-title" class="text-xl font-medium text-ink-strong">
        {promo ? m.promo_edit_title() : m.promo_create_title()}
      </h2>
    </div>

    <form onsubmit={(e) => { e.preventDefault(); save(); }} class="p-6 space-y-4">
      <div>
        <label for="promo-name" class="block text-sm text-ink-muted mb-1">{m.common_name()} *</label>
        <input id="promo-name" type="text" bind:value={name} maxlength="200" required class={inputClass} />
      </div>

      <div>
        <label for="promo-kind" class="block text-sm text-ink-muted mb-1">{m.promo_kind_label()}</label>
        <select id="promo-kind" bind:value={kind} class={inputClass}>
          <option value="card">{m.promo_kind_card()}</option>
          <option value="pack">{m.promo_kind_pack()}</option>
          <option value="other">{m.promo_kind_other()}</option>
        </select>
      </div>

      <div>
        <label for="promo-description" class="block text-sm text-ink-muted mb-1">{m.common_description()}</label>
        <textarea id="promo-description" bind:value={description} rows="3" class="{inputClass} resize-y"></textarea>
      </div>

      <div>
        <label for="promo-release-date" class="block text-sm text-ink-muted mb-1">{m.promo_release_date_label()}</label>
        <input id="promo-release-date" type="date" bind:value={releaseDate} class={inputClass} />
      </div>

      <div>
        <span class="block text-sm text-ink-muted mb-1">{m.promo_image_label()}</span>
        {#if shownImageUrl}
          <div class="flex items-start gap-3 mb-2">
            <img src={shownImageUrl} alt={name} class="w-24 aspect-[5/7] object-contain rounded bg-surface-muted" />
            <button
              type="button"
              onclick={handleRemoveImage}
              class="min-h-[44px] inline-flex items-center gap-1.5 text-sm text-ink-muted hover:text-link transition-colors"
            >
              <X class="w-4 h-4" aria-hidden="true" />
              {m.promo_image_remove()}
            </button>
          </div>
        {/if}
        <input
          bind:this={fileInput}
          type="file"
          accept="image/webp,image/png,image/jpeg"
          onchange={handleFileSelect}
          aria-label={m.promo_image_label()}
          class="block w-full text-sm text-ink-muted file:mr-3 file:px-3 file:py-1.5 file:rounded-lg file:border-0 file:bg-surface-hover file:text-ink-bright file:text-sm file:cursor-pointer"
        />
        <p class="mt-1 text-xs text-ink-faint">{m.promo_image_hint()}</p>
        {#if imageError}
          <p class="mt-1 text-xs text-link">{imageError}</p>
        {/if}
      </div>

      <div>
        <span class="block text-sm text-ink-muted mb-1">{m.promo_allowed_ranks_label()}</span>
        <div class="space-y-1">
          {#each RANKS as rank (rank)}
            <label class="flex items-center gap-3 min-h-[44px] cursor-pointer">
              <input
                type="checkbox"
                checked={allowedRanks.includes(rank)}
                onchange={() => (allowedRanks = toggleIn(allowedRanks, rank))}
                class="w-5 h-5 rounded border-line-strong bg-surface-card text-accent focus:ring-accent"
              />
              <span class="text-sm text-ink-bright">{rank}</span>
            </label>
          {/each}
        </div>
        <p class="text-xs text-ink-faint">{m.promo_allowed_ranks_hint()}</p>
      </div>

      <div>
        <span class="block text-sm text-ink-muted mb-1">{m.promo_leagues_label()}</span>
        {#if leagues.length > 0}
          <div class="max-h-40 overflow-y-auto border border-line rounded-lg px-3 py-1">
            {#each leagues as league (league.uid)}
              <label class="flex items-center gap-3 min-h-[44px] cursor-pointer">
                <input
                  type="checkbox"
                  checked={leagueUids.includes(league.uid)}
                  onchange={() => (leagueUids = toggleIn(leagueUids, league.uid))}
                  class="w-5 h-5 shrink-0 rounded border-line-strong bg-surface-card text-accent focus:ring-accent"
                />
                <span class="text-sm text-ink-bright truncate">{league.name}</span>
              </label>
            {/each}
          </div>
          <p class="mt-1 text-xs text-ink-faint">{m.promo_leagues_hint()}</p>
        {:else}
          <p class="text-xs text-ink-faint">{m.promo_no_leagues()}</p>
        {/if}
      </div>

      <label class="flex items-center gap-3 min-h-[44px] cursor-pointer">
        <input
          type="checkbox"
          bind:checked={active}
          class="w-5 h-5 rounded border-line-strong bg-surface-card text-accent focus:ring-accent"
        />
        <span class="text-sm text-ink-bright">{m.promo_active_label()}</span>
      </label>

      <div class="flex gap-2 pt-2">
        <Button type="submit" variant="primary" size="lg" class="flex-1" loading={saving} disabled={!canSave}>
          {m.common_save()}
        </Button>
        <Button variant="secondary" size="lg" disabled={saving || deleting} onclick={requestClose}>
          {m.common_cancel()}
        </Button>
      </div>

      {#if promo}
        <div class="border-t border-line pt-4">
          {#if deleteConflict}
            <div class="p-3 rounded-lg banner-warn border text-sm mb-3">
              <div class="flex items-start gap-2">
                <TriangleAlert class="w-4 h-4 shrink-0 mt-0.5" aria-hidden="true" />
                <span class="flex-1">{m.promo_delete_referenced()}</span>
              </div>
              {#if promo.active}
                <div class="mt-2">
                  <Button variant="secondary" size="sm" loading={deleting} onclick={retireInstead}>
                    {m.promo_retire()}
                  </Button>
                </div>
              {/if}
            </div>
          {:else if deleteError}
            <p class="text-sm text-link mb-3">{deleteError}</p>
          {/if}
          <Button variant="danger" loading={deleting} disabled={saving} onclick={handleDelete}>
            <Trash2 class="w-4 h-4" aria-hidden="true" />
            {m.promo_delete()}
          </Button>
        </div>
      {/if}
    </form>
  </div>
</div>
