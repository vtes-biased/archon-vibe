<script lang="ts">
  import { goto, replaceState } from "$app/navigation";
  import { onMount } from "svelte";
  import { getAuthState, verifyMagicLink, setPassword, type VerifyMagicLinkResult } from "$lib/stores/auth.svelte";
  import Icon from "@iconify/svelte";
  import * as m from '$lib/paraglide/messages.js';

  const auth = $derived(getAuthState());

  // States: verifying -> password_form -> submitting -> success/error
  let verifying = $state(true);
  let verifyResult = $state<VerifyMagicLinkResult | null>(null);
  let error = $state<string | null>(null);

  // Password form
  let password = $state("");
  let passwordError = $state<string | null>(null);

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
      replaceState("/auth/email/verify", {});
    } else {
      error = auth.error || "Verification failed";
    }
  });

  async function handleSetPassword() {
    passwordError = null;

    // Validate
    if (password.length < 8) {
      passwordError = m.auth_verify_error_password_length();
      return;
    }

    if (!verifyResult) {
      passwordError = m.auth_verify_error_session_expired();
      return;
    }

    const success = await setPassword(verifyResult.setPasswordToken, password);

    if (success) {
      goto("/");
    } else {
      passwordError = auth.error || "Failed to set password";
    }
  }

  const isSignup = $derived(verifyResult?.purpose === "signup");
  const heading = $derived(isSignup ? m.auth_verify_set_password() : m.auth_verify_reset_password());
  const buttonText = $derived(isSignup ? m.auth_verify_create_account() : m.auth_verify_reset_btn());
</script>

<svelte:head>
  <title>{isSignup ? m.auth_verify_title_signup() : m.auth_verify_title_reset()} - Archon</title>
</svelte:head>

<div class="min-h-screen flex items-center justify-center p-4">
  <div class="w-full max-w-md">
    <div class="text-center mb-8">
      <h1 class="text-4xl font-light text-crimson-500 mb-2">Archon</h1>
      <p class="text-ash-400">{m.common_tagline()}</p>
    </div>

    <div class="bg-dusk-950 rounded-lg shadow-lg p-8 border border-ash-800">
      {#if verifying}
        <!-- VERIFYING TOKEN -->
        <div class="space-y-4 text-center">
          <div class="w-16 h-16 mx-auto flex items-center justify-center">
            <Icon icon="lucide:loader-2" class="w-10 h-10 animate-spin text-crimson-500" />
          </div>
          <h2 class="text-lg font-medium text-bone-100">{m.auth_verify_verifying()}</h2>
          <p class="text-ash-400 text-sm">{m.auth_verify_please_wait()}</p>
        </div>

      {:else if error}
        <!-- ERROR -->
        <div class="space-y-4 text-center">
          <div class="w-16 h-16 mx-auto bg-red-900/30 rounded-full flex items-center justify-center">
            <Icon icon="lucide:x" class="w-8 h-8 text-red-400" />
          </div>
          <h2 class="text-lg font-medium text-bone-100">{m.auth_verify_link_invalid()}</h2>
          <p class="text-ash-400 text-sm">{error}</p>
          <p class="text-ash-500 text-xs">
            {m.auth_verify_link_expired_msg()}
          </p>
          <a
            href="/login"
            class="inline-block mt-4 px-6 py-2 bg-crimson-700 hover:bg-crimson-600 text-white rounded-lg font-medium transition-colors"
          >
            {m.auth_verify_back_to_login()}
          </a>
        </div>

      {:else if verifyResult}
        <!-- PASSWORD FORM -->
        <div class="space-y-4">
          <h2 class="text-lg font-medium text-bone-100 text-center">{heading}</h2>
            {#if passwordError}
            <div class="p-3 bg-red-900/30 border border-red-700 rounded-lg text-red-300 text-sm">
              {passwordError}
            </div>
          {/if}

          <form onsubmit={(e) => { e.preventDefault(); handleSetPassword(); }} class="space-y-4">
            <div>
              <label for="email" class="block text-sm text-ash-400 mb-1">{m.common_email()}</label>
              <input
                type="email"
                id="email"
                name="email"
                autocomplete="username"
                value={verifyResult.email}
                readonly
                class="w-full px-4 py-3 bg-dusk-900/50 border border-ash-800 rounded-lg text-ash-300 cursor-not-allowed"
              />
            </div>

            <div>
              <label for="new-password" class="block text-sm text-ash-400 mb-1">{m.common_password()}</label>
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
                class="w-full px-4 py-3 bg-dusk-900 border border-ash-700 rounded-lg text-bone-100 placeholder-ash-500 focus:outline-none focus:border-crimson-600 disabled:opacity-50"
              />
            </div>

            <button
              type="submit"
              disabled={auth.isLoading || !password}
              class="w-full py-3 bg-crimson-700 hover:bg-crimson-600 disabled:bg-ash-700 disabled:opacity-50 text-white rounded-lg font-medium transition-colors flex items-center justify-center gap-2 disabled:cursor-not-allowed"
            >
              {#if auth.isLoading}
                <Icon icon="lucide:loader-2" class="w-5 h-5 animate-spin" />
              {/if}
              {buttonText}
            </button>
          </form>

          <p class="text-center text-xs text-ash-500 mt-4">
            {m.auth_verify_password_hint()}
          </p>
        </div>
      {/if}
    </div>
  </div>
</div>
