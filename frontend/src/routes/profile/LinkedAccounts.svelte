<script lang="ts">
  import { KeyRound, Mail } from "@lucide/svelte";
  import { isPasskeySupported } from "$lib/stores/passkeys.svelte";
  import DiscordIcon from "$lib/components/DiscordIcon.svelte";
  import GithubIcon from "$lib/components/GithubIcon.svelte";
  import Button from "$lib/components/Button.svelte";
  import * as m from '$lib/paraglide/messages.js';

  interface Props {
    hasEmail: boolean;
    emailIdentifier: string | null;
    hasDiscord: boolean;
    discordUsername: string | null;
    hasGithub: boolean;
    githubUsername: string | null;
    hasPasskey: boolean;
    discordMessage: string;
    discordError: string;
    githubMessage: string;
    githubError: string;
    passkeyMessage: string;
    error: string | null;
    onLinkEmail: (email: string) => Promise<boolean>;
    onChangePassword: (password: string) => Promise<string | null>;
    onLinkDiscord: () => void;
    onLinkGithub: () => void;
    onUnlinkGithub: () => void;
    onRegisterPasskey: () => void;
  }
  let {
    hasEmail, emailIdentifier,
    hasDiscord, discordUsername,
    hasGithub, githubUsername, hasPasskey,
    discordMessage, discordError, githubMessage, githubError, passkeyMessage, error,
    onLinkEmail, onChangePassword, onLinkDiscord, onLinkGithub, onUnlinkGithub, onRegisterPasskey,
  }: Props = $props();

  let registeringPasskey = $state(false);
  let showEmailSetup = $state(false);
  let emailInput = $state("");
  let emailLinkSent = $state(false);
  let emailLinkAddress = $state("");
  let sendingEmailLink = $state(false);
  let emailError = $state("");
  let showPasswordChange = $state(false);
  let newPassword = $state("");
  let changingPassword = $state(false);
  let passwordChanged = $state(false);
  let passwordError = $state("");

  async function handleRegisterPasskey() {
    registeringPasskey = true;
    await onRegisterPasskey();
    registeringPasskey = false;
  }

  async function handleChangePassword() {
    passwordError = "";
    if (newPassword.length < 8) {
      passwordError = m.auth_verify_error_password_length();
      return;
    }
    changingPassword = true;
    passwordError = (await onChangePassword(newPassword)) ?? "";
    changingPassword = false;
    if (!passwordError) {
      newPassword = "";
      showPasswordChange = false;
      passwordChanged = true;
    }
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

<div class="p-3 sm:p-6 space-y-4">
  <h3 class="text-sm font-medium text-ink-muted uppercase tracking-wide">{m.profile_linked_accounts()}</h3>

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
      <div class="flex items-center gap-2">
        <span class="px-3 py-1 text-sm rounded badge-success">{m.profile_passkey_active()}</span>
        {#if !showPasswordChange}
          <Button variant="secondary" size="lg" onclick={() => { showPasswordChange = true; passwordChanged = false; }}>
            {m.profile_password_change()}
          </Button>
        {/if}
      </div>
    {:else if !showEmailSetup}
      <Button variant="secondary" size="lg" onclick={() => (showEmailSetup = true)}>
        {m.profile_email_setup()}
      </Button>
    {/if}
  </div>
  {#if hasEmail && showPasswordChange}
    <form onsubmit={(e) => { e.preventDefault(); handleChangePassword(); }}
      class="ml-8 flex gap-2">
      <input type="password" bind:value={newPassword} autocomplete="new-password" minlength="8" required
        placeholder={m.auth_verify_password_placeholder()}
        class="flex-1 px-3 py-2 bg-surface-muted border border-line-strong rounded text-ink-strong placeholder-ink-faint focus:outline-none focus:border-accent-strong-hover text-sm" />
      <Button type="submit" variant="primary" size="lg" class="whitespace-nowrap" loading={changingPassword} disabled={!newPassword}>
        {m.common_save()}
      </Button>
      <Button variant="secondary" size="lg" onclick={() => { showPasswordChange = false; newPassword = ""; passwordError = ""; }}>
        {m.common_cancel()}
      </Button>
    </form>
  {/if}
  {#if passwordError}
    <p class="ml-8 text-sm text-link">{passwordError}</p>
  {/if}
  {#if passwordChanged}
    <p class="ml-8 text-sm text-info">{m.profile_password_changed()}</p>
  {/if}
  {#if showEmailSetup && !hasEmail}
    {#if emailLinkSent}
      <div class="ml-8 p-3 rounded-lg bg-surface-muted border border-line-strong space-y-1">
        <p class="text-sm text-info">{m.profile_email_check_inbox()}</p>
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
      <span class="px-3 py-1 text-sm rounded badge-success">{m.profile_linked()}</span>
    {/if}
  </div>
  {#if discordMessage}
    <p class="text-sm text-info">{discordMessage}</p>
  {/if}
  {#if discordError}
    <p class="text-sm text-link">{discordError}</p>
  {/if}

  <div class="flex items-center justify-between">
    <div class="flex items-center gap-3">
      <GithubIcon class="w-5 h-5 text-ink-strong" />
      <div>
        <p class="text-ink-strong">GitHub</p>
        {#if hasGithub && githubUsername}
          <p class="text-sm text-ink-muted">@{githubUsername}</p>
        {:else}
          <p class="text-sm text-ink-muted">{m.profile_github_hint()}</p>
        {/if}
      </div>
    </div>
    {#if !hasGithub}
      <button onclick={onLinkGithub}
        class="px-4 py-2 bg-[#24292e] hover:bg-[#1b1f23] text-white rounded font-medium transition-colors">
        {m.profile_link()}
      </button>
    {:else}
      <Button variant="secondary" size="lg" onclick={onUnlinkGithub}>
        {m.profile_unlink()}
      </Button>
    {/if}
  </div>
  {#if githubMessage}
    <p class="text-sm text-info">{githubMessage}</p>
  {/if}
  {#if githubError}
    <p class="text-sm text-link">{githubError}</p>
  {/if}

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
        <span class="px-3 py-1 text-sm rounded badge-success">{m.profile_passkey_active()}</span>
      {/if}
    </div>
    {#if passkeyMessage}
      <p class="text-sm text-info">{passkeyMessage}</p>
    {/if}
  {/if}

  {#if error}
    <p class="text-sm text-link">{error}</p>
  {/if}
</div>
