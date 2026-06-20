<script lang="ts">
  import { KeyRound, Mail } from "@lucide/svelte";
  import { isPasskeySupported } from "$lib/stores/passkeys.svelte";
  import DiscordIcon from "$lib/components/DiscordIcon.svelte";
  import Button from "$lib/components/Button.svelte";
  import * as m from '$lib/paraglide/messages.js';

  interface Props {
    hasEmail: boolean;
    emailIdentifier: string | null;
    hasDiscord: boolean;
    discordUsername: string | null;
    hasPasskey: boolean;
    discordMessage: string;
    discordError: string;
    passkeyMessage: string;
    error: string | null;
    onLinkEmail: (email: string) => Promise<boolean>;
    onLinkDiscord: () => void;
    onRegisterPasskey: () => void;
  }
  let {
    hasEmail, emailIdentifier,
    hasDiscord, discordUsername, hasPasskey,
    discordMessage, discordError, passkeyMessage, error,
    onLinkEmail, onLinkDiscord, onRegisterPasskey,
  }: Props = $props();

  let registeringPasskey = $state(false);
  let showEmailSetup = $state(false);
  let emailInput = $state("");
  let emailLinkSent = $state(false);
  let emailLinkAddress = $state("");
  let sendingEmailLink = $state(false);
  let emailError = $state("");

  async function handleRegisterPasskey() {
    registeringPasskey = true;
    await onRegisterPasskey();
    registeringPasskey = false;
  }

  async function handleSendEmailLink() {
    if (!emailInput.trim()) return;
    sendingEmailLink = true;
    emailError = "";
    const success = await onLinkEmail(emailInput.trim());
    sendingEmailLink = false;
    if (success) {
      emailLinkAddress = emailInput.trim();
      emailLinkSent = true;
    } else {
      // Use backend error detail if available (passed via error prop)
      emailError = error || m.profile_email_send_failed();
    }
  }
</script>

<div class="p-6 border-t border-line space-y-4">
  <h3 class="text-sm font-medium text-ink-muted uppercase tracking-wide">{m.profile_linked_accounts()}</h3>

  <!-- Email & Password -->
  <div class="flex items-center justify-between">
    <div class="flex items-center gap-3">
      <Mail class="w-5 h-5 text-ink-muted" />
      <div>
        <p class="text-ink-strong">{m.profile_email_password()}</p>
        {#if hasEmail && emailIdentifier}
          <p class="text-sm text-ink-muted">{emailIdentifier}</p>
        {:else}
          <p class="text-sm text-ink-muted">{m.profile_passkey_not_setup()}</p>
        {/if}
      </div>
    </div>
    {#if hasEmail}
      <span class="px-3 py-1 text-sm text-blue-500 bg-blue-500/10 rounded">{m.profile_passkey_active()}</span>
    {:else if !showEmailSetup}
      <Button variant="secondary" size="lg" onclick={() => (showEmailSetup = true)}>
        {m.profile_email_setup()}
      </Button>
    {/if}
  </div>
  {#if showEmailSetup && !hasEmail}
    {#if emailLinkSent}
      <div class="ml-8 p-3 rounded-lg bg-surface-muted border border-line-strong space-y-1">
        <p class="text-sm text-blue-400">{m.profile_email_check_inbox()}</p>
        <p class="text-sm text-ink-muted">{m.profile_email_sent_to({ email: emailLinkAddress })}</p>
        <p class="text-xs text-ink-faint">{m.profile_email_verify_hint()}</p>
      </div>
    {:else}
      <form onsubmit={(e) => { e.preventDefault(); handleSendEmailLink(); }}
        class="ml-8 flex gap-2">
        <input type="email" bind:value={emailInput} required
          placeholder={m.login_placeholder_email()}
          class="flex-1 px-3 py-2 bg-surface-muted border border-line-strong rounded text-ink-strong placeholder-ink-faint focus:outline-none focus:border-accent-strong-hover text-sm" />
        <Button type="submit" variant="primary" size="lg" class="whitespace-nowrap" loading={sendingEmailLink} disabled={!emailInput.trim()}>
          {sendingEmailLink ? m.profile_email_sending() : m.profile_email_send_link()}
        </Button>
      </form>
    {/if}
    {#if emailError}
      <p class="ml-8 text-sm text-link">{emailError}</p>
    {/if}
  {/if}

  <!-- Discord -->
  <div class="flex items-center justify-between">
    <div class="flex items-center gap-3">
      <DiscordIcon class="w-5 h-5 text-[#5865F2]" />
      <div>
        <p class="text-ink-strong">Discord</p>
        {#if hasDiscord && discordUsername}
          <p class="text-sm text-ink-muted">{discordUsername}</p>
        {:else}
          <p class="text-sm text-ink-muted">{m.profile_not_linked()}</p>
        {/if}
      </div>
    </div>
    {#if !hasDiscord}
      <button onclick={onLinkDiscord}
        class="px-4 py-2 bg-[#5865F2] hover:bg-[#4752C4] text-white rounded font-medium transition-colors">
        {m.profile_link()}
      </button>
    {:else}
      <span class="px-3 py-1 text-sm text-blue-500 bg-blue-500/10 rounded">{m.profile_linked()}</span>
    {/if}
  </div>
  {#if discordMessage}
    <p class="text-sm text-blue-500">{discordMessage}</p>
  {/if}
  {#if discordError}
    <p class="text-sm text-link">{discordError}</p>
  {/if}

  <!-- Passkey -->
  {#if isPasskeySupported()}
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-3">
        <KeyRound class="w-5 h-5 text-ink-muted" />
        <div>
          <p class="text-ink-strong">Passkey</p>
          <p class="text-sm text-ink-muted">
            {hasPasskey ? m.profile_passkey_configured() : m.profile_passkey_not_setup()}
          </p>
        </div>
      </div>
      {#if !hasPasskey}
        <Button variant="secondary" size="lg" loading={registeringPasskey} onclick={handleRegisterPasskey}>
          {registeringPasskey ? m.profile_passkey_adding() : m.common_add()}
        </Button>
      {:else}
        <span class="px-3 py-1 text-sm text-blue-500 bg-blue-500/10 rounded">{m.profile_passkey_active()}</span>
      {/if}
    </div>
    {#if passkeyMessage}
      <p class="text-sm text-blue-500">{passkeyMessage}</p>
    {/if}
  {/if}

  {#if error}
    <p class="text-sm text-link">{error}</p>
  {/if}
</div>
