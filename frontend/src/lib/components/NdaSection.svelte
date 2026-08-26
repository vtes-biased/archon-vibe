<script lang="ts">
  import type { User } from "$lib/types";
  import type { NdaStatus } from "$lib/api";
  import { requestNdaSignature, uploadNdaScan, downloadNdaPdf } from "$lib/api";
  import { showToast } from "$lib/stores/toast.svelte";
  import Button from "$lib/components/Button.svelte";
  import Badge from "$lib/components/Badge.svelte";
  import InlineNotice from "$lib/components/InlineNotice.svelte";
  import { Download, FileSignature, TriangleAlert, Upload } from "@lucide/svelte";
  import * as m from "$lib/paraglide/messages.js";

  let {
    user,
    status,
    onchanged,
  }: {
    user: User;
    status: NdaStatus | null;
    onchanged: () => void;
  } = $props();

  let requesting = $state(false);
  let uploading = $state(false);
  let fileInput: HTMLInputElement | null = $state(null);

  function fmtDate(iso: string): string {
    return new Date(iso).toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  }

  async function handleRequest() {
    requesting = true;
    try {
      await requestNdaSignature(user.uid);
      showToast({ type: "success", message: m.nda_requested_toast() });
      onchanged();
    } catch {
      // Error toast is shown by apiRequest
    }
    requesting = false;
  }

  async function handleFileSelect(event: Event) {
    const file = (event.target as HTMLInputElement).files?.[0];
    if (!file) return;
    uploading = true;
    try {
      await uploadNdaScan(user.uid, file);
      showToast({ type: "success", message: m.nda_uploaded_toast() });
      onchanged();
    } catch {
      // Error toast is shown by apiRequest
    }
    uploading = false;
    if (fileInput) fileInput.value = "";
  }
</script>

{#if status}
  <div class="mt-6">
    <h2 class="text-lg font-semibold text-ink-bright mb-3">{m.nda_section_title()}</h2>
    <div class="bg-surface-card border border-line rounded-lg p-4 space-y-3">
      {#if !status.has_nda}
        <InlineNotice tone="warn" icon={TriangleAlert}>
          {m.nda_none_on_record()}
        </InlineNotice>
      {/if}
      {#if status.pending}
        <InlineNotice>
          {m.nda_pending_since({ date: fmtDate(status.pending.created_at) })}
        </InlineNotice>
      {/if}
      {#each status.records.filter((r) => r.status !== "pending") as record (record.uid)}
        <div class="flex items-center justify-between gap-3 flex-wrap">
          <div class="flex items-center gap-2 min-w-0">
            <Badge kind="status" tone="info">
              <FileSignature class="w-3 h-3" aria-hidden="true" />
              {m.nda_on_record()}
            </Badge>
            <span class="text-sm text-ink-muted truncate">
              {#if record.status === "signed"}
                {m.nda_signed_row({
                  name: record.signer_name ?? "—",
                  date: record.signed_at ? fmtDate(record.signed_at) : "—",
                })}
              {:else}
                {m.nda_uploaded_row({
                  date: record.signed_at ? fmtDate(record.signed_at) : "—",
                })}
              {/if}
            </span>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onclick={() => downloadNdaPdf(user.uid, record.uid)}
            title={m.nda_download_btn()}
          >
            <Download class="inline w-3.5 h-3.5 mr-1" aria-hidden="true" />
            {m.nda_download_btn()}
          </Button>
        </div>
      {/each}
      <div class="flex flex-wrap gap-2">
        <Button
          variant="primary"
          size="md"
          loading={requesting}
          disabled={!!status.pending}
          onclick={handleRequest}
          title={m.nda_request_btn()}
        >
          <FileSignature class="inline w-3.5 h-3.5 mr-1" aria-hidden="true" />
          {m.nda_request_btn()}
        </Button>
        <Button
          variant="secondary"
          size="md"
          loading={uploading}
          onclick={() => fileInput?.click()}
          title={m.nda_upload_btn()}
        >
          <Upload class="inline w-3.5 h-3.5 mr-1" aria-hidden="true" />
          {m.nda_upload_btn()}
        </Button>
        <input
          bind:this={fileInput}
          type="file"
          accept="application/pdf,image/jpeg,image/png,image/webp"
          class="hidden"
          onchange={handleFileSelect}
        />
      </div>
    </div>
  </div>
{/if}
