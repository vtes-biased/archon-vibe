<script lang="ts">
  import { onMount } from "svelte";
  import { getAuthState, initAuth } from "$lib/stores/auth.svelte";
  import { getNdaStatus, getNdaDocument, signNda, downloadNdaPdf, type NdaStatus } from "$lib/api";
  import { deobfuscateContact } from "$lib/contact";
  import { renderMarkdown } from "$lib/markdown";
  import Button from "$lib/components/Button.svelte";
  import InlineNotice from "$lib/components/InlineNotice.svelte";
  import ConfirmActionModal from "$lib/components/ConfirmActionModal.svelte";
  import { Loader2, FileSignature, CircleCheck } from "@lucide/svelte";
  import * as m from "$lib/paraglide/messages.js";

  const auth = $derived(getAuthState());

  let loading = $state(true);
  let status = $state<NdaStatus | null>(null);
  let documentHtml = $state("");
  let name = $state("");
  let email = $state("");
  let address = $state("");
  let phone = $state("");
  let showConfirm = $state(false);
  let signedRecordUid = $state<string | null>(null);

  const onRecord = $derived(status?.records.find((r) => r.status !== "pending") ?? null);

  function fmtDate(iso: string): string {
    return new Date(iso).toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  }

  onMount(async () => {
    // Root layout's auth hydration fires AFTER this page's onMount; settle it
    // first or a logged-in member reads as anonymous on a direct navigation.
    if (auth.isLoading) await initAuth();
    if (auth.user) {
      name = auth.user.name;
      email = deobfuscateContact(auth.user.contact_email);
      try {
        status = await getNdaStatus(auth.user.uid);
        if (status.pending) {
          const doc = await getNdaDocument(auth.user.uid);
          documentHtml = renderMarkdown(doc.text);
        }
      } catch {
        // Error toast is shown by apiRequest
      }
    }
    loading = false;
  });

  async function doSign() {
    if (!auth.user) return;
    const result = await signNda(auth.user.uid, {
      name: name.trim(),
      email: email.trim(),
      address: address.trim(),
      phone: phone.trim(),
    });
    signedRecordUid = result.record_uid;
    status = await getNdaStatus(auth.user.uid, { suppressErrorToast: true }).catch(() => status);
  }
</script>

<svelte:head>
  <title>{m.nda_sign_title()} - Archon</title>
</svelte:head>

<div class="p-4 sm:p-8">
  <div class="max-w-3xl mx-auto">
    <h1 class="text-3xl font-semibold text-accent mb-6">{m.nda_sign_title()}</h1>

    {#if loading}
      <div class="text-center text-ink-muted py-8">
        <Loader2 class="w-6 h-6 animate-spin inline-block" />
        <span class="ml-2">{m.common_loading()}</span>
      </div>
    {:else if !auth.isAuthenticated || !auth.user}
      <InlineNotice tone="warn">{m.nda_login_required()}</InlineNotice>
    {:else if signedRecordUid || (!status?.pending && onRecord)}
      <div class="bg-surface-card border border-line rounded-lg p-6 space-y-4">
        <div class="flex items-center gap-2 text-ink-bright">
          <CircleCheck class="w-5 h-5 text-info" aria-hidden="true" />
          <span class="text-lg font-medium">
            {signedRecordUid ? m.nda_signed_success() : m.nda_on_record()}
          </span>
        </div>
        {#if signedRecordUid && email.trim()}
          <p class="text-sm text-ink-muted">{m.nda_signed_email_note({ email: email.trim() })}</p>
        {/if}
        {#if onRecord}
          <p class="text-sm text-ink-muted">
            {#if onRecord.status === "signed"}
              {m.nda_signed_row({
                name: onRecord.signer_name ?? "—",
                date: onRecord.signed_at ? fmtDate(onRecord.signed_at) : "—",
              })}
            {:else}
              {m.nda_uploaded_row({ date: onRecord.signed_at ? fmtDate(onRecord.signed_at) : "—" })}
            {/if}
          </p>
        {/if}
        <Button
          variant="primary"
          size="md"
          onclick={() => downloadNdaPdf(auth.user!.uid, signedRecordUid ?? onRecord!.uid)}
          title={m.nda_download_copy_btn()}
        >
          {m.nda_download_copy_btn()}
        </Button>
      </div>
    {:else if !status?.pending}
      <InlineNotice>{m.nda_no_pending()}</InlineNotice>
    {:else}
      <p class="text-sm text-ink-muted mb-4">{m.nda_sign_intro()}</p>
      <article class="doc-prose prose max-w-none bg-surface-card border border-line rounded-lg p-6">
        {@html documentHtml}
      </article>

      <form
        class="mt-6 bg-surface-card border border-line rounded-lg p-6 space-y-4"
        onsubmit={(e) => {
          e.preventDefault();
          showConfirm = true;
        }}
      >
        <div>
          <label for="nda-name" class="block text-sm font-medium text-ink-muted mb-1">{m.nda_field_name()}</label>
          <input id="nda-name" type="text" bind:value={name} required
            class="w-full px-3 py-2 border border-line-strong rounded bg-surface-card text-ink-bright focus:ring-2 focus:ring-accent focus:border-transparent" />
        </div>
        <div>
          <label for="nda-email" class="block text-sm font-medium text-ink-muted mb-1">{m.nda_field_email()}</label>
          <input id="nda-email" type="email" bind:value={email}
            class="w-full px-3 py-2 border border-line-strong rounded bg-surface-card text-ink-bright focus:ring-2 focus:ring-accent focus:border-transparent" />
        </div>
        <div>
          <label for="nda-address" class="block text-sm font-medium text-ink-muted mb-1">{m.nda_field_address()}</label>
          <input id="nda-address" type="text" bind:value={address}
            class="w-full px-3 py-2 border border-line-strong rounded bg-surface-card text-ink-bright focus:ring-2 focus:ring-accent focus:border-transparent" />
        </div>
        <div>
          <label for="nda-phone" class="block text-sm font-medium text-ink-muted mb-1">{m.nda_field_phone()}</label>
          <input id="nda-phone" type="tel" bind:value={phone}
            class="w-full px-3 py-2 border border-line-strong rounded bg-surface-card text-ink-bright focus:ring-2 focus:ring-accent focus:border-transparent" />
        </div>
        <Button type="submit" variant="primary" size="lg" disabled={!name.trim()}>
          <FileSignature class="inline w-4 h-4 mr-1" aria-hidden="true" />
          {m.nda_sign_btn()}
        </Button>
      </form>
    {/if}
  </div>
</div>

{#if showConfirm}
  <ConfirmActionModal
    title={m.nda_sign_confirm_title()}
    body={m.nda_sign_confirm_body({ name: name.trim() })}
    confirmLabel={m.nda_sign_btn()}
    action={doSign}
    onClose={() => (showConfirm = false)}
    reportResult={false}
  />
{/if}
