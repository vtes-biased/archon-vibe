<script lang="ts">
  import { untrack, onDestroy } from 'svelte';
  import { Upload, Trash2 } from '@lucide/svelte';
  import * as m from '$lib/paraglide/messages.js';
  import { uploadTournamentBanner, deleteTournamentBanner } from '$lib/api';
  import BannerCropper from '$lib/components/BannerCropper.svelte';
  import ConfirmActionModal from '$lib/components/ConfirmActionModal.svelte';

  interface Props {
    tournamentUid: string;
    bannerPath?: string | null;
    /** Organizer view: show add/change/remove affordances. */
    canManage: boolean;
  }
  let { tournamentUid, bannerPath, canManage }: Props = $props();

  let showCropper = $state(false);
  let showRemoveConfirm = $state(false);
  let broken = $state(false);

  // Optimistic override so the hero updates the instant an upload/remove
  // succeeds, before the authoritative banner_path arrives over SSE:
  //   undefined → follow the prop   |   {url} → show this   |   null → hidden
  let override = $state<{ url: string } | null | undefined>(undefined);
  let overrideUrl: string | null = null;

  function clearOverride() {
    if (overrideUrl) {
      URL.revokeObjectURL(overrideUrl);
      overrideUrl = null;
    }
    override = undefined;
  }

  // When the server-sent banner_path changes, it has caught up with (or
  // superseded) our optimistic state — drop the override. Tracks the prop only;
  // override is mutated under untrack so this never re-fires itself.
  $effect(() => {
    bannerPath; // track
    untrack(() => {
      broken = false;
      clearOverride();
    });
  });

  const src = $derived(override === undefined ? (bannerPath ?? null) : (override?.url ?? null));
  const heroVisible = $derived(!!src && !broken);
  const showEmpty = $derived(canManage && !heroVisible);

  async function handleCropSave(blob: Blob) {
    // Throws on failure; the api layer has already surfaced the error toast, so
    // the cropper just keeps its modal open for a retry.
    await uploadTournamentBanner(tournamentUid, blob);
    if (overrideUrl) URL.revokeObjectURL(overrideUrl);
    overrideUrl = URL.createObjectURL(blob);
    override = { url: overrideUrl };
    broken = false;
    showCropper = false;
  }

  // Don't leak the optimistic object URL if the page unmounts mid-preview.
  onDestroy(() => {
    if (overrideUrl) URL.revokeObjectURL(overrideUrl);
  });

  async function removeBanner() {
    await deleteTournamentBanner(tournamentUid);
    if (overrideUrl) URL.revokeObjectURL(overrideUrl);
    overrideUrl = null;
    override = null; // optimistic hide; SSE will null the prop shortly after
  }
</script>

{#if heroVisible}
  <div class="-mx-4 sm:mx-0 mb-6 sm:rounded-lg overflow-hidden bg-surface-muted relative">
    <img
      {src}
      alt=""
      width="1200"
      height="630"
      class="block w-full aspect-[1200/630] object-cover"
      loading="eager"
      onerror={() => (broken = true)}
    />
    {#if canManage}
      <div class="absolute top-2 right-2 flex gap-2">
        <button
          type="button"
          onclick={() => (showCropper = true)}
          class="min-w-11 min-h-11 px-3 inline-flex items-center justify-center gap-1.5 rounded-lg
                 bg-surface-card/90 backdrop-blur-sm border border-line shadow
                 text-ink-bright hover:bg-surface-card text-sm font-medium cursor-pointer transition-colors"
        >
          <Upload class="w-4 h-4" aria-hidden="true" />
          {m.tournament_banner_change()}
        </button>
        <button
          type="button"
          onclick={() => (showRemoveConfirm = true)}
          aria-label={m.tournament_banner_remove()}
          class="w-11 h-11 inline-flex items-center justify-center rounded-lg
                 bg-surface-card/90 backdrop-blur-sm border border-line shadow
                 text-ink-muted hover:text-link cursor-pointer transition-colors"
        >
          <Trash2 class="w-4 h-4" aria-hidden="true" />
        </button>
      </div>
    {/if}
  </div>
{:else if showEmpty}
  <button
    type="button"
    onclick={() => (showCropper = true)}
    class="-mx-4 sm:mx-0 mb-6 sm:rounded-lg aspect-[1200/630] max-h-40 sm:max-h-44
           flex flex-col items-center justify-center gap-2 text-center px-4
           border-2 border-dashed border-line text-ink-muted
           hover:border-line-strong hover:text-ink-bright hover:bg-surface-hover/30
           transition-colors cursor-pointer"
  >
    <Upload class="w-6 h-6" aria-hidden="true" />
    <span class="text-sm font-medium">{m.tournament_banner_add()}</span>
    <span class="text-xs text-ink-faint">{m.tournament_banner_add_hint()}</span>
  </button>
{/if}

{#if showCropper}
  <BannerCropper onSave={handleCropSave} onCancel={() => (showCropper = false)} />
{/if}

{#if showRemoveConfirm}
  <ConfirmActionModal
    title={m.tournament_banner_remove_confirm_title()}
    body={m.tournament_banner_remove_confirm_body()}
    confirmLabel={m.tournament_banner_remove()}
    action={removeBanner}
    onClose={() => (showRemoveConfirm = false)}
  />
{/if}
