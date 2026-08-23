<script lang="ts">
  import { goto, replaceState } from "$app/navigation";
  import { onMount } from "svelte";
  import { getAuthState, verifyMagicLink, setPassword, type VerifyMagicLinkResult } from "$lib/stores/auth.svelte";
  import { Loader2, X } from '@lucide/svelte';
  import Button from '$lib/components/Button.svelte';
  import * as m from '$lib/paraglide/messages.js';

  const auth = $derived(getAuthState());

  // States: verifying -> password_form -> submitting -> success/error
  let verifying = $state(true);
  let verifyResult = $state<VerifyMagicLinkResult | null>(null);
  let error = $state<string | null>(null);

  let password = $state("");
  let passwordError = $state<string | null>(null);
  let linkDead = $state(false);

  onMount(async () => {
    const params = new URLSearchParams(window.location.search);
    const token = params.get("token");

    if (!token) {
      error = m.auth_verify_error_missing_token();
      verifying = false;
      return;
    }

    const result = await verifyMagicLink(token);
    verifying = false;

    if (result) {
      verifyResult = result;
      // Clear URL params for security
      replaceState("/verify-email", {});
    } else {
      error = auth.error || m.auth_verify_error_failed();
    }
  });

  async function handleSetPassword() {
    passwordError = null;
    linkDead = false;

    if (password.length < 8) {
      passwordError = m.auth_verify_error_password_length();
      return;
    }

    if (!verifyResult) {
      passwordError = m.auth_verify_error_session_expired();
      linkDead = true;
      return;
    }

    const success = await setPassword(verifyResult.setPasswordToken, password);

    if (success) {
      goto("/");
    } else {
      passwordError = auth.error || m.auth_verify_error_set_password();
      linkDead = true;
    }
  }

  const isReset = $derived(verifyResult?.purpose === "reset");
  const heading = $derived(isReset ? m.auth_verify_reset_password() : m.auth_verify_set_password());
  const buttonText = $derived(isReset ? m.auth_verify_reset_btn() : m.auth_verify_create_account());
</script>

<svelte:head>
  <title>{isReset ? m.auth_verify_title_reset() : m.auth_verify_title_signup()} - Archon</title>
</svelte:head>

<div class="min-h-shell flex items-center justify-center p-4">
  <div class="w-full max-w-md">
    <div class="text-center mb-8">
      <h1 class="text-4xl font-light text-accent mb-2">Archon</h1>
      <p class="text-ink-muted">{m.common_tagline()}</p>
    </div>

    <div class="bg-surface-card rounded-lg shadow-lg p-8 border border-line">
      {#if verifying}
        <div class="space-y-4 text-center">
          <div class="w-16 h-16 mx-auto flex items-center justify-center">
            <Loader2 class="w-10 h-10 animate-spin text-accent" />
          </div>
          <h2 class="text-lg font-medium text-ink-strong">{m.auth_verify_verifying()}</h2>
          <p class="text-ink-muted text-sm">{m.auth_verify_please_wait()}</p>
        </div>

      {:else if error}
        <div class="space-y-4 text-center">
          <div class="w-16 h-16 mx-auto banner-error border rounded-full flex items-center justify-center">
            <X class="w-8 h-8" />
          </div>
          <h2 class="text-lg font-medium text-ink-strong">{m.auth_verify_link_invalid()}</h2>
          <p class="text-ink-muted text-sm">{error}</p>
          <p class="text-ink-faint text-xs">
            {m.auth_verify_link_expired_msg()}
          </p>
          <a
            href="/login?recover=1"
            class="inline-block mt-4 px-6 py-2 bg-accent-strong hover:bg-accent-strong-hover text-white rounded-lg font-medium transition-colors"
          >
            {m.auth_verify_get_new_link()}
          </a>
          <a href="/login" class="block text-sm text-ink-muted hover:text-ink-bright">
            {m.auth_verify_back_to_login()}
          </a>
        </div>

      {:else if verifyResult}
        <div class="space-y-4">
          <h2 class="text-lg font-medium text-ink-strong text-center">{heading}</h2>
            {#if passwordError}
            <div class="p-3 banner-error border rounded-lg text-sm">
              {passwordError}
              {#if linkDead}
                <a href="/login?recover=1" class="block mt-2 underline">
                  {m.auth_verify_get_new_link()}
                </a>
              {/if}
            </div>
          {/if}

          <form onsubmit={(e) => { e.preventDefault(); handleSetPassword(); }} class="space-y-4">
            <div>
              <label for="email" class="block text-sm text-ink-muted mb-1">{m.common_email()}</label>
              <input
                type="email"
                id="email"
                name="email"
                autocomplete="username"
                value={verifyResult.email}
                readonly
                class="w-full px-4 py-3 bg-surface-muted/50 border border-line rounded-lg text-ink cursor-not-allowed"
              />
            </div>

            <div>
              <label for="new-password" class="block text-sm text-ink-muted mb-1">{m.common_password()}</label>
              <input
                type="password"
                id="new-password"
                name="new-password"
                autocomplete="new-password"
                bind:value={password}
                placeholder={m.auth_verify_password_placeholder()}
                disabled={auth.isLoading}
                minlength="8"
                required
                class="w-full px-4 py-3 bg-surface-muted border border-line-strong rounded-lg text-ink-strong placeholder-ink-faint focus:outline-none focus:border-accent-strong-hover disabled:opacity-50"
              />
            </div>

            <Button
              type="submit"
              variant="primary"
              size="lg"
              block
              loading={auth.isLoading}
              disabled={!password}
            >
              {buttonText}
            </Button>
          </form>

          <p class="text-center text-xs text-ink-faint mt-4">
            {m.auth_verify_password_hint()}
          </p>
        </div>
      {/if}
    </div>
  </div>
</div>
