<script lang="ts">
  import { toUserMessage } from '$lib/errors';
  import { importArchonFile, type ArchonImportResult } from "$lib/api";
  import { showToast } from "$lib/stores/toast.svelte";
  import { Upload, Download, X } from "@lucide/svelte";
  import Button from "$lib/components/Button.svelte";
  import * as m from '$lib/paraglide/messages.js';

  const API_BASE = import.meta.env.VITE_API_URL ?? "";

  let {
    show = $bindable(false),
    tournamentUid,
    hasRounds = false,
  }: {
    show: boolean;
    tournamentUid: string;
    hasRounds?: boolean;
  } = $props();

  let archonFile = $state<File | null>(null);
  let archonUploading = $state(false);
  let archonResult = $state<ArchonImportResult | null>(null);
  let archonConfirmOverwrite = $state(false);

  // Reset transient state whenever the modal closes.
  $effect(() => {
    if (!show) {
      archonFile = null;
      archonResult = null;
      archonConfirmOverwrite = false;
    }
  });

  async function handleArchonImport() {
    if (!archonFile) return;
    // Confirm overwrite if tournament already has rounds
    if (hasRounds && !archonConfirmOverwrite) {
      archonConfirmOverwrite = true;
      return;
    }
    archonUploading = true;
    archonResult = null;
    archonConfirmOverwrite = false;
    try {
      const result = await importArchonFile(tournamentUid, archonFile);
      archonResult = result;
      if (result.success) {
        showToast({ type: "success", message: m.archon_import_success() });
        archonFile = null;
        const input = document.getElementById("archon-file-input") as HTMLInputElement;
        if (input) input.value = "";
      }
    } catch (e) {
      archonResult = {
        success: false,
        errors: [toUserMessage(e, m.common_error_unknown())],
        warnings: [],
        players_matched: 0,
        rounds_imported: 0,
        has_finals: false,
      };
    } finally {
      archonUploading = false;
    }
  }
</script>

{#if show}
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
  <div
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
    role="presentation"
    onclick={() => (show = false)}
    onkeydown={(e) => { if (e.key === 'Escape') show = false; }}
  >
    <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
    <div
      class="bg-surface-card rounded-lg shadow-xl border border-line w-full max-w-md mx-4"
      onclick={(e) => e.stopPropagation()}
      onkeydown={(e) => e.stopPropagation()}
      role="dialog"
      aria-modal="true"
      tabindex="-1"
    >
      <div class="p-6 border-b border-line flex items-center justify-between gap-2">
        <h2 class="text-xl font-medium text-link">{m.archon_import_title()}</h2>
        <button onclick={() => (show = false)} class="text-ink-faint hover:text-ink-strong transition-colors" aria-label={m.common_cancel()}>
          <X class="w-5 h-5" />
        </button>
      </div>
      <div class="p-6 space-y-3">
        <p class="text-xs text-ink-muted">{m.archon_import_description()}</p>
        <a href="{API_BASE}/api/tournaments/archon-template" download
          class="inline-flex items-center gap-2 text-sm text-link hover:text-link-soft">
          <Download class="w-4 h-4" />
          {m.archon_download_template()}
        </a>
        <div class="flex items-center gap-2">
          <input id="archon-file-input" type="file" accept=".xlsx"
            onchange={(e) => { archonFile = (e.target as HTMLInputElement).files?.[0] ?? null; archonResult = null; archonConfirmOverwrite = false; }}
            class="text-sm text-ink file:mr-2 file:py-1 file:px-3 file:rounded file:border-0 file:text-sm file:bg-surface-active file:text-ink-bright hover:file:bg-surface-active" />
          <Button variant="primary" size="md" disabled={!archonFile} loading={archonUploading} onclick={handleArchonImport}>
            {#if !archonUploading}<Upload class="w-4 h-4" />{/if}
            {archonUploading ? m.archon_uploading() : m.archon_upload_file()}
          </Button>
        </div>
        {#if archonConfirmOverwrite}
          <div class="banner-warn border rounded p-3 text-sm">
            <p>{m.archon_import_confirm_overwrite()}</p>
            <div class="flex gap-2 mt-2">
              <Button variant="primary" size="md" onclick={handleArchonImport}>
                {m.common_confirm()}
              </Button>
              <Button variant="secondary" size="md" onclick={() => archonConfirmOverwrite = false}>
                {m.common_cancel()}
              </Button>
            </div>
          </div>
        {/if}
        {#if archonResult}
          {#if archonResult.success}
            <div class="banner-info border rounded p-3 text-sm">
              <p>{m.archon_import_success()}</p>
              <p class="text-xs mt-1">{m.archon_players_matched({ count: archonResult.players_matched })} · {m.archon_rounds_imported({ count: archonResult.rounds_imported })}{archonResult.has_finals ? ` · ${m.archon_finals_label()}` : ""}</p>
            </div>
          {:else}
            <div class="banner-error border rounded p-3 text-sm">
              <p class="font-medium">{m.archon_import_error()}</p>
              <ul class="mt-1 text-xs space-y-0.5">
                {#each archonResult.errors as error}
                  <li>· {error}</li>
                {/each}
              </ul>
            </div>
          {/if}
        {/if}
      </div>
    </div>
  </div>
{/if}
