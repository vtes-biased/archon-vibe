<script lang="ts">
  import { downloadNdaPdf, type NdaRecord } from "$lib/api";
  import Button from "$lib/components/Button.svelte";
  import { Download } from "@lucide/svelte";
  import * as m from "$lib/paraglide/messages.js";

  let { userUid, records }: { userUid: string; records: NdaRecord[] } = $props();

  function fmtDate(iso: string): string {
    return new Date(iso).toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  }
</script>

<div class="p-3 sm:p-6 space-y-4">
  <h3 class="text-sm font-medium text-ink-muted uppercase tracking-wide">{m.nda_section_title()}</h3>
  {#each records as record (record.uid)}
    <div class="flex items-center justify-between gap-3">
      <div class="min-w-0">
        <p class="text-ink-strong">{m.nda_on_record()}</p>
        <p class="text-sm text-ink-muted">
          {#if record.status === "signed"}
            {m.nda_signed_row({
              name: record.signer_name ?? "—",
              date: record.signed_at ? fmtDate(record.signed_at) : "—",
            })}
          {:else}
            {m.nda_uploaded_row({ date: record.signed_at ? fmtDate(record.signed_at) : "—" })}
          {/if}
        </p>
      </div>
      <Button
        variant="secondary"
        size="lg"
        class="shrink-0"
        onclick={() => downloadNdaPdf(userUid, record.uid)}
        title={m.nda_download_copy_btn()}
      >
        <Download class="w-4 h-4" aria-hidden="true" />
        {m.nda_download_btn()}
      </Button>
    </div>
  {/each}
</div>
