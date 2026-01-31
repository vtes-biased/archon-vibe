<script lang="ts">
  import { goto } from "$app/navigation";
  import { onMount } from "svelte";
  import { getAuthState, verifyMagicLink, setPassword, type VerifyMagicLinkResult } from "$lib/stores/auth.svelte";
  import Icon from "@iconify/svelte";

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
      error = "Missing verification token";
      verifying = false;
      return;
    }

    const result = await verifyMagicLink(token);
    verifying = false;

    if (result) {
      verifyResult = result;
      // Clear URL params for security
      window.history.replaceState({}, "", "/auth/email/verify");
    } else {
      error = auth.error || "Verification failed";
    }
  });

  async function handleSetPassword() {
    passwordError = null;

    // Validate
    if (password.length < 8) {
      passwordError = "Password must be at least 8 characters";
      return;
    }

    if (!verifyResult) {
      passwordError = "Session expired. Please request a new link.";
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
  const heading = $derived(isSignup ? "Set your password" : "Reset your password");
  const buttonText = $derived(isSignup ? "Create Account" : "Reset Password");
</script>

<svelte:head>
  <title>{isSignup ? "Complete Signup" : "Reset Password"} - Archon</title>
</svelte:head>

<div class="min-h-screen flex items-center justify-center p-4">
  <div class="w-full max-w-md">
    <div class="text-center mb-8">
      <h1 class="text-4xl font-light text-crimson-500 mb-2">Archon</h1>
      <p class="text-ash-400">VEKN Tournament Management</p>
    </div>

    <div class="bg-dusk-950 rounded-lg shadow-lg p-8 border border-ash-800">
      {#if verifying}
        <!-- VERIFYING TOKEN -->
        <div class="space-y-4 text-center">
          <div class="w-16 h-16 mx-auto flex items-center justify-center">
            <Icon icon="lucide:loader-2" class="w-10 h-10 animate-spin text-crimson-500" />
          </div>
          <h2 class="text-lg font-medium text-bone-100">Verifying link...</h2>
          <p class="text-ash-400 text-sm">Please wait</p>
        </div>

      {:else if error}
        <!-- ERROR -->
        <div class="space-y-4 text-center">
          <div class="w-16 h-16 mx-auto bg-red-900/30 rounded-full flex items-center justify-center">
            <Icon icon="lucide:x" class="w-8 h-8 text-red-400" />
          </div>
          <h2 class="text-lg font-medium text-bone-100">Link expired or invalid</h2>
          <p class="text-ash-400 text-sm">{error}</p>
          <p class="text-ash-500 text-xs">
            The link may have expired or already been used.
          </p>
          <a
            href="/login"
            class="inline-block mt-4 px-6 py-2 bg-crimson-700 hover:bg-crimson-600 text-bone-100 rounded-lg font-medium transition-colors"
          >
            Back to Login
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
              <label for="email" class="block text-sm text-ash-400 mb-1">Email</label>
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
              <label for="new-password" class="block text-sm text-ash-400 mb-1">Password</label>
              <input
                type="password"
                id="new-password"
                name="new-password"
                autocomplete="new-password"
                bind:value={password}
                placeholder="At least 8 characters"
                disabled={auth.isLoading}
                minlength="8"
                required
                class="w-full px-4 py-3 bg-dusk-900 border border-ash-700 rounded-lg text-bone-100 placeholder-ash-500 focus:outline-none focus:border-crimson-600 disabled:opacity-50"
              />
            </div>

            <button
              type="submit"
              disabled={auth.isLoading || !password}
              class="w-full py-3 bg-crimson-700 hover:bg-crimson-600 disabled:bg-ash-700 disabled:opacity-50 text-bone-100 rounded-lg font-medium transition-colors flex items-center justify-center gap-2 disabled:cursor-not-allowed"
            >
              {#if auth.isLoading}
                <Icon icon="lucide:loader-2" class="w-5 h-5 animate-spin" />
              {/if}
              {buttonText}
            </button>
          </form>

          <p class="text-center text-xs text-ash-500 mt-4">
            Your password must be at least 8 characters.
          </p>
        </div>
      {/if}
    </div>
  </div>
</div>
