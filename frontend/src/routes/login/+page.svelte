<script lang="ts">
  import { goto, replaceState } from "$app/navigation";
  import { onMount, onDestroy } from "svelte";
  import {
    getAuthState,
    storeTokensFromCallback,
    requestMagicLink,
    login,
  } from "$lib/stores/auth.svelte";
  import {
    isPasskeySupported,
    createAccountWithPasskey,
    loginWithPasskey,
    startConditionalUI,
    stopConditionalUI,
  } from "$lib/stores/passkeys.svelte";
  import { Mail, KeyRound } from '@lucide/svelte';
  import DiscordIcon from "$lib/components/DiscordIcon.svelte";
  import Button from '$lib/components/Button.svelte';
  import * as m from '$lib/paraglide/messages.js';

  const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

  const auth = $derived(getAuthState());
  const passkeySupported = $derived(isPasskeySupported());

  // Mode: 'login' or 'signup'
  let mode = $state<"login" | "signup">("login");
  let oauthError = $state<string | null>(null);

  // Form state
  let email = $state("");
  let password = $state("");

  // Magic link sent state (for signup)
  let magicLinkSent = $state(false);
  let magicLinkEmail = $state("");

  // Forgot password mode
  let forgotPassword = $state(false);
  let resetEmailSent = $state(false);

  // Signup consent: ToS + Privacy + age/parental self-attestation. Gates all signup methods.
  let consentChecked = $state(false);
  const linkClass = "text-link hover:text-link-soft focus-visible:text-link-soft underline";
  // First-party only: our Paraglide message + anchors built from our own titles. No untrusted
  // input flows in, so {@html} below is safe (no sanitizer needed).
  const consentHtml = $derived(
    m.login_consent_html({
      terms: `<a href="/legal/terms" target="_blank" rel="noopener noreferrer" class="${linkClass}">${m.legal_terms_title()}</a>`,
      privacy: `<a href="/legal/privacy" target="_blank" rel="noopener noreferrer" class="${linkClass}">${m.legal_privacy_title()}</a>`,
    }),
  );

  // Post-login destination (?redirect= from e.g. a tournament page sign-in CTA).
  // Same-origin paths only — never a full URL (open-redirect guard).
  function successTarget(): string {
    const r = new URLSearchParams(window.location.search).get("redirect");
    return r && r.startsWith("/") && !r.startsWith("//") ? r : "/";
  }

  async function handleCreateAccount() {
    if (!consentChecked) return;
    stopConditionalUI(); // a pending conditional get() blocks the modal create()
    const success = await createAccountWithPasskey();
    if (success) {
      goto(successTarget());
    }
  }

  async function handlePasskeyLogin() {
    stopConditionalUI(); // a pending conditional get() blocks the modal get()
    const success = await loginWithPasskey();
    if (success) {
      goto(successTarget());
    }
  }

  async function handleEmailLogin() {
    if (!email.trim() || !password) return;
    const success = await login(email.trim(), password);
    if (success) {
      goto(successTarget());
    }
  }

  function handleDiscordLogin() {
    window.location.href = `${API_BASE}/auth/discord/authorize`;
  }

  async function handleSignupMagicLink() {
    if (!email.trim() || !consentChecked) return;
    const success = await requestMagicLink(email.trim(), "signup");
    if (success) {
      magicLinkSent = true;
      magicLinkEmail = email.trim();
      email = "";
    }
  }

  async function handleForgotPassword() {
    if (!email.trim()) return;
    const success = await requestMagicLink(email.trim(), "reset");
    if (success) {
      resetEmailSent = true;
      magicLinkEmail = email.trim();
    }
  }

  // Handle OAuth callback tokens from URL
  onMount(async () => {
    const params = new URLSearchParams(window.location.search);

    // Auto-redirect to Discord OAuth when login_hint=discord (used by Discord bot)
    if (params.get("login_hint") === "discord") {
      const redirect = params.get("redirect");
      const discordUrl = redirect
        ? `${API_BASE}/auth/discord/authorize?redirect=${encodeURIComponent(redirect)}`
        : `${API_BASE}/auth/discord/authorize`;
      window.location.href = discordUrl;
      return;
    }

    const token = params.get("token");
    const refresh = params.get("refresh");
    const error = params.get("error");

    if (error) {
      const errorMessages: Record<string, string> = {
        invalid_state: m.login_error_invalid_state(),
        state_expired: m.login_error_state_expired(),
        discord_token_failed: m.login_error_discord_token(),
        discord_user_failed: m.login_error_discord_user(),
        discord_error: m.login_error_discord(),
      };
      oauthError = errorMessages[error] || m.login_error_auth({ error });
      replaceState("/login", {});
      return;
    }

    if (token && refresh) {
      await storeTokensFromCallback(token, refresh);
      const target = successTarget();
      replaceState("/login", {});
      goto(target);
      return;
    }

    // Passkey autofill (conditional UI): surface stored passkeys in the
    // identifier input's autofill dropdown. Internally gated on
    // isConditionalUISupported; resolves when the user picks one (then
    // authenticates) and aborts silently on unmount or explicit-flow start.
    startConditionalUI(() => goto(successTarget()));
  });

  onDestroy(stopConditionalUI);

  // Redirect if already authenticated
  $effect(() => {
    if (auth.isAuthenticated && !auth.isLoading) {
      goto(successTarget());
    }
  });
</script>

<svelte:head>
  <title>{m.login_page_title()} - Archon</title>
</svelte:head>

<div class="min-h-shell flex items-center justify-center p-4">
  <div class="w-full max-w-md">
    <div class="text-center mb-8">
      <h1 class="text-4xl font-light text-accent mb-2">Archon</h1>
      <p class="text-ink-muted">{m.common_tagline()}</p>
    </div>

    <div class="bg-surface-card rounded-lg shadow-lg p-8 border border-line">
      <!-- Mode toggle (hidden when showing success states) -->
      {#if !magicLinkSent && !resetEmailSent && !forgotPassword}
        <div class="flex mb-6 bg-surface-muted rounded-lg p-1">
          <button
            onclick={() => { mode = "login"; consentChecked = false; }}
            class="flex-1 py-2 px-4 rounded-md text-sm font-medium transition-colors {mode === 'login'
              ? 'bg-accent-strong text-white'
              : 'text-ink-muted hover:text-ink-bright'}"
          >
            {m.login_tab_login()}
          </button>
          <button
            onclick={() => { mode = "signup"; consentChecked = false; }}
            class="flex-1 py-2 px-4 rounded-md text-sm font-medium transition-colors {mode === 'signup'
              ? 'bg-accent-strong text-white'
              : 'text-ink-muted hover:text-ink-bright'}"
          >
            {m.login_tab_signup()}
          </button>
        </div>
      {/if}

      {#if auth.error || oauthError}
        <div class="mb-4 p-3 banner-error border rounded-lg text-sm">
          {auth.error || oauthError}
        </div>
      {/if}

      {#if magicLinkSent}
        <!-- SIGNUP: MAGIC LINK SENT -->
        <div class="space-y-4 text-center">
          <div class="w-16 h-16 mx-auto badge-info rounded-full flex items-center justify-center">
            <Mail class="w-8 h-8" />
          </div>
          <h2 class="text-lg font-medium text-ink-strong">{m.login_check_email()}</h2>
          <p class="text-ink-muted text-sm">
            {m.login_sent_link_to()}<br />
            <span class="text-ink-strong font-medium">{magicLinkEmail}</span>
          </p>
          <p class="text-ink-faint text-xs">
            {m.login_click_link_signup()}<br />
            {m.login_link_expires()}
          </p>
          <button
            onclick={() => { magicLinkSent = false; magicLinkEmail = ""; }}
            class="text-sm text-link hover:text-link-soft"
          >
            {m.login_use_different_email()}
          </button>
        </div>

      {:else if resetEmailSent}
        <!-- PASSWORD RESET: EMAIL SENT -->
        <div class="space-y-4 text-center">
          <div class="w-16 h-16 mx-auto badge-info rounded-full flex items-center justify-center">
            <Mail class="w-8 h-8" />
          </div>
          <h2 class="text-lg font-medium text-ink-strong">{m.login_check_email()}</h2>
          <p class="text-ink-muted text-sm">
            {m.login_sent_reset_link()}<br />
            <span class="text-ink-strong font-medium">{magicLinkEmail}</span>
          </p>
          <p class="text-ink-faint text-xs">
            {m.login_click_link_reset()}<br />
            {m.login_link_expires()}
          </p>
          <button
            onclick={() => { resetEmailSent = false; forgotPassword = false; email = ""; }}
            class="text-sm text-link hover:text-link-soft"
          >
            {m.login_back_to_login()}
          </button>
        </div>

      {:else if forgotPassword}
        <!-- FORGOT PASSWORD FORM -->
        <div class="space-y-4">
          <h2 class="text-lg font-medium text-ink-strong text-center">{m.login_reset_title()}</h2>
          <p class="text-ink-muted text-sm text-center">
            {m.login_reset_instructions()}
          </p>

          <form onsubmit={(e) => { e.preventDefault(); handleForgotPassword(); }} class="space-y-4">
            <div>
              <label for="reset-email" class="block text-sm text-ink-muted mb-1">{m.common_email()}</label>
              <input
                type="email"
                id="reset-email"
                name="email"
                autocomplete="username"
                bind:value={email}
                placeholder={m.login_placeholder_email()}
                disabled={auth.isLoading}
                class="w-full px-4 py-3 bg-surface-muted border border-line-strong rounded-lg text-ink-strong placeholder-ink-faint focus:outline-none focus:border-accent-strong-hover disabled:opacity-50"
              />
            </div>
            <Button
              type="submit"
              variant="primary"
              size="lg"
              block
              loading={auth.isLoading}
              disabled={!email.trim()}
            >
              {m.login_send_reset_link()}
            </Button>
          </form>

          <button
            onclick={() => { forgotPassword = false; email = ""; }}
            class="w-full text-sm text-ink-muted hover:text-ink-bright"
          >
            {m.login_back_to_login()}
          </button>
        </div>

      {:else if mode === "login"}
        <!-- LOGIN MODE -->
        <div class="space-y-4">
          <p class="text-ink-muted text-sm text-center mb-4">
            {m.login_welcome_back()}
          </p>

          <!-- Email + Password Form -->
          <form onsubmit={(e) => { e.preventDefault(); handleEmailLogin(); }} class="space-y-4">
            <div>
              <label for="login-email" class="block text-sm text-ink-muted mb-1">{m.common_email()}</label>
              <input
                type="email"
                id="login-email"
                name="email"
                autocomplete="username webauthn"
                bind:value={email}
                placeholder={m.login_placeholder_email()}
                disabled={auth.isLoading}
                class="w-full px-4 py-3 bg-surface-muted border border-line-strong rounded-lg text-ink-strong placeholder-ink-faint focus:outline-none focus:border-accent-strong-hover disabled:opacity-50"
              />
            </div>
            <div>
              <label for="login-password" class="block text-sm text-ink-muted mb-1">{m.common_password()}</label>
              <input
                type="password"
                id="login-password"
                name="password"
                autocomplete="current-password"
                bind:value={password}
                placeholder={m.login_placeholder_password()}
                disabled={auth.isLoading}
                class="w-full px-4 py-3 bg-surface-muted border border-line-strong rounded-lg text-ink-strong placeholder-ink-faint focus:outline-none focus:border-accent-strong-hover disabled:opacity-50"
              />
            </div>
            <Button
              type="submit"
              variant="primary"
              size="lg"
              block
              loading={auth.isLoading}
              disabled={!email.trim() || !password}
            >
              {m.login_sign_in()}
            </Button>
          </form>

          <button
            onclick={() => { forgotPassword = true; password = ""; }}
            class="w-full text-sm text-ink-muted hover:text-ink-bright"
          >
            {m.login_forgot_password()}
          </button>

          <!-- Divider -->
          <div class="relative my-4">
            <div class="absolute inset-0 flex items-center">
              <div class="w-full border-t border-line-strong"></div>
            </div>
            <div class="relative flex justify-center text-sm">
              <span class="px-2 bg-surface-card text-ink-faint">{m.common_or()}</span>
            </div>
          </div>

          {#if passkeySupported}
            <Button
              variant="secondary"
              size="lg"
              block
              disabled={auth.isLoading}
              onclick={handlePasskeyLogin}
            >
              <KeyRound class="w-5 h-5" />
              {m.login_passkey_login()}
            </Button>
          {/if}

          <!-- Discord OAuth -->
          <button
            onclick={handleDiscordLogin}
            disabled={auth.isLoading}
            class="w-full py-3 bg-[#5865F2] hover:bg-[#4752C4] disabled:bg-surface-hover disabled:text-ink-faint text-white rounded-lg font-medium transition-colors flex items-center justify-center gap-2"
          >
            <DiscordIcon class="w-5 h-5" />
            {m.login_discord_login()}
          </button>

          {#if !passkeySupported}
            <p class="text-center text-sm text-ink-faint">
              {m.login_passkey_not_supported()}
            </p>
          {/if}
        </div>
      {:else}
        <!-- SIGNUP MODE -->
        <div class="space-y-4">
          <p class="text-ink-muted text-sm text-center mb-4">
            {m.login_create_account_msg()}
          </p>

          <!-- Consent gate: ToS + Privacy + age/parental self-attestation -->
          <div class="flex items-start gap-2 text-xs text-ink leading-snug">
            <input
              id="signup-consent"
              type="checkbox"
              bind:checked={consentChecked}
              disabled={auth.isLoading}
              class="mt-0.5 shrink-0 w-5 h-5 accent-accent-strong-hover"
            />
            <label for="signup-consent">{@html consentHtml}</label>
          </div>

          {#if passkeySupported}
            <Button
              variant="primary"
              size="lg"
              block
              loading={auth.isLoading}
              disabled={!consentChecked}
              onclick={handleCreateAccount}
            >
              {#if !auth.isLoading}<KeyRound class="w-5 h-5" />{/if}
              {m.login_passkey_signup()}
            </Button>
          {/if}

          <!-- Discord OAuth -->
          <button
            onclick={handleDiscordLogin}
            disabled={auth.isLoading || !consentChecked}
            class="w-full py-3 bg-[#5865F2] hover:bg-[#4752C4] disabled:bg-surface-hover disabled:text-ink-faint text-white rounded-lg font-medium transition-colors flex items-center justify-center gap-2"
          >
            <DiscordIcon class="w-5 h-5" />
            {m.login_discord_signup()}
          </button>

          <!-- Divider -->
          <div class="relative my-4">
            <div class="absolute inset-0 flex items-center">
              <div class="w-full border-t border-line-strong"></div>
            </div>
            <div class="relative flex justify-center text-sm">
              <span class="px-2 bg-surface-card text-ink-faint">{m.login_or_signup_email()}</span>
            </div>
          </div>

          <!-- Email signup form -->
          <form onsubmit={(e) => { e.preventDefault(); handleSignupMagicLink(); }} class="space-y-3">
            <label for="signup-email" class="sr-only">{m.common_email()}</label>
            <input
              type="email"
              id="signup-email"
              name="email"
              autocomplete="username"
              bind:value={email}
              placeholder={m.login_placeholder_signup_email()}
              disabled={auth.isLoading}
              class="w-full px-4 py-3 bg-surface-muted border border-line-strong rounded-lg text-ink-strong placeholder-ink-faint focus:outline-none focus:border-accent-strong-hover disabled:opacity-50"
            />
            <Button
              type="submit"
              variant="secondary"
              size="lg"
              block
              loading={auth.isLoading}
              disabled={!email.trim() || !consentChecked}
            >
              {#if !auth.isLoading}<Mail class="w-5 h-5" />{/if}
              {m.login_email_signup()}
            </Button>
          </form>

          {#if !passkeySupported}
            <p class="text-center text-sm text-ink-faint">
              {m.login_passkey_not_supported()}
            </p>
          {/if}
        </div>
      {/if}
    </div>
  </div>
</div>
