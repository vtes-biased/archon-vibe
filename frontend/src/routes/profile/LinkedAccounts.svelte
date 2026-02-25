<script lang="ts">
  import { KeyRound, Mail } from "lucide-svelte";
  import { isPasskeySupported } from "$lib/stores/passkeys.svelte";
  import DiscordIcon from "$lib/components/DiscordIcon.svelte";
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

<div class="p-6 border-t border-ash-800 space-y-4">
  <h3 class="text-sm font-medium text-ash-400 uppercase tracking-wide">{m.profile_linked_accounts()}</h3>

  <!-- Email & Password -->
  <div class="flex items-center justify-between">
    <div class="flex items-center gap-3">
      <Mail class="w-5 h-5 text-ash-400" />
      <div>
        <p class="text-bone-100">{m.profile_email_password()}</p>
        {#if hasEmail && emailIdentifier}
          <p class="text-sm text-ash-400">{emailIdentifier}</p>
        {:else}
          <p class="text-sm text-ash-400">{m.profile_passkey_not_setup()}</p>
        {/if}
      </div>
    </div>
    {#if hasEmail}
      <span class="px-3 py-1 text-sm text-green-500 bg-green-500/10 rounded">{m.profile_passkey_active()}</span>
    {:else if !showEmailSetup}
      <button onclick={() => (showEmailSetup = true)}
        class="px-4 py-2 bg-ash-800 hover:bg-ash-700 text-bone-100 rounded font-medium transition-colors">
        {m.profile_email_setup()}
      </button>
    {/if}
  </div>
  {#if showEmailSetup && !hasEmail}
    {#if emailLinkSent}
      <div class="ml-8 p-3 rounded-lg bg-dusk-900 border border-ash-700 space-y-1">
        <p class="text-sm text-green-400">{m.profile_email_check_inbox()}</p>
        <p class="text-sm text-ash-400">{m.profile_email_sent_to({ email: emailLinkAddress })}</p>
        <p class="text-xs text-ash-500">{m.profile_email_verify_hint()}</p>
      </div>
    {:else}
      <form onsubmit={(e) => { e.preventDefault(); handleSendEmailLink(); }}
        class="ml-8 flex gap-2">
        <input type="email" bind:value={emailInput} required
          placeholder={m.login_placeholder_email()}
          class="flex-1 px-3 py-2 bg-dusk-900 border border-ash-700 rounded text-bone-100 placeholder-ash-500 focus:outline-none focus:border-crimson-600 text-sm" />
        <button type="submit" disabled={sendingEmailLink || !emailInput.trim()}
          class="px-4 py-2 bg-crimson-700 hover:bg-crimson-600 disabled:bg-ash-800 disabled:text-ash-500 text-white rounded font-medium text-sm transition-colors whitespace-nowrap">
          {sendingEmailLink ? m.profile_email_sending() : m.profile_email_send_link()}
        </button>
      </form>
    {/if}
    {#if emailError}
      <p class="ml-8 text-sm text-crimson-400">{emailError}</p>
    {/if}
  {/if}

  <!-- Discord -->
  <div class="flex items-center justify-between">
    <div class="flex items-center gap-3">
      <DiscordIcon class="w-5 h-5 text-[#5865F2]" />
      <div>
        <p class="text-bone-100">Discord</p>
        {#if hasDiscord && discordUsername}
          <p class="text-sm text-ash-400">{discordUsername}</p>
        {:else}
          <p class="text-sm text-ash-400">{m.profile_not_linked()}</p>
        {/if}
      </div>
    </div>
    {#if !hasDiscord}
      <button onclick={onLinkDiscord}
        class="px-4 py-2 bg-[#5865F2] hover:bg-[#4752C4] text-white rounded font-medium transition-colors">
        {m.profile_link()}
      </button>
    {:else}
      <span class="px-3 py-1 text-sm text-green-500 bg-green-500/10 rounded">{m.profile_linked()}</span>
    {/if}
  </div>
  {#if discordMessage}
    <p class="text-sm text-green-500">{discordMessage}</p>
  {/if}
  {#if discordError}
    <p class="text-sm text-crimson-400">{discordError}</p>
  {/if}

  <!-- Passkey -->
  {#if isPasskeySupported()}
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-3">
        <KeyRound class="w-5 h-5 text-ash-400" />
        <div>
          <p class="text-bone-100">Passkey</p>
          <p class="text-sm text-ash-400">
            {hasPasskey ? m.profile_passkey_configured() : m.profile_passkey_not_setup()}
          </p>
        </div>
      </div>
      {#if !hasPasskey}
        <button onclick={handleRegisterPasskey} disabled={registeringPasskey}
          class="px-4 py-2 bg-ash-800 hover:bg-ash-700 disabled:bg-ash-800 disabled:text-ash-500 text-bone-100 rounded font-medium transition-colors">
          {registeringPasskey ? m.profile_passkey_adding() : m.common_add()}
        </button>
      {:else}
        <span class="px-3 py-1 text-sm text-green-500 bg-green-500/10 rounded">{m.profile_passkey_active()}</span>
      {/if}
    </div>
    {#if passkeyMessage}
      <p class="text-sm text-green-500">{passkeyMessage}</p>
    {/if}
  {/if}

  {#if error}
    <p class="text-sm text-crimson-400">{error}</p>
  {/if}
</div>
