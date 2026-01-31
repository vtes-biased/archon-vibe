<script lang="ts">
  import { goto } from "$app/navigation";
  import { onMount } from "svelte";
  import {
    getAuthState,
    isPasskeySupported,
    createAccountWithPasskey,
    loginWithPasskey,
    storeTokensFromCallback,
    requestMagicLink,
    login,
  } from "$lib/stores/auth.svelte";
  import Icon from "@iconify/svelte";

  const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

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

  async function handleCreateAccount() {
    const success = await createAccountWithPasskey();
    if (success) {
      goto("/");
    }
  }

  async function handlePasskeyLogin() {
    const success = await loginWithPasskey();
    if (success) {
      goto("/");
    }
  }

  async function handleEmailLogin() {
    if (!email.trim() || !password) return;
    const success = await login(email.trim(), password);
    if (success) {
      goto("/");
    }
  }

  function handleDiscordLogin() {
    window.location.href = `${API_BASE}/auth/discord/authorize`;
  }

  async function handleSignupMagicLink() {
    if (!email.trim()) return;
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
    const token = params.get("token");
    const refresh = params.get("refresh");
    const error = params.get("error");

    if (error) {
      const errorMessages: Record<string, string> = {
        invalid_state: "Invalid OAuth state. Please try again.",
        state_expired: "OAuth session expired. Please try again.",
        discord_token_failed: "Failed to authenticate with Discord.",
        discord_user_failed: "Failed to get Discord user info.",
        discord_error: "Discord authentication error.",
      };
      oauthError = errorMessages[error] || `Authentication error: ${error}`;
      window.history.replaceState({}, "", "/login");
      return;
    }

    if (token && refresh) {
      await storeTokensFromCallback(token, refresh);
      window.history.replaceState({}, "", "/login");
      goto("/");
    }
  });

  // Redirect if already authenticated
  $effect(() => {
    if (auth.isAuthenticated && !auth.isLoading) {
      goto("/");
    }
  });
</script>

<svelte:head>
  <title>Welcome - Archon</title>
</svelte:head>

<div class="min-h-screen flex items-center justify-center p-4">
  <div class="w-full max-w-md">
    <div class="text-center mb-8">
      <h1 class="text-4xl font-light text-crimson-500 mb-2">Archon</h1>
      <p class="text-ash-400">VEKN Tournament Management</p>
    </div>

    <div class="bg-dusk-950 rounded-lg shadow-lg p-8 border border-ash-800">
      <!-- Mode toggle (hidden when showing success states) -->
      {#if !magicLinkSent && !resetEmailSent && !forgotPassword}
        <div class="flex mb-6 bg-dusk-900 rounded-lg p-1">
          <button
            onclick={() => (mode = "login")}
            class="flex-1 py-2 px-4 rounded-md text-sm font-medium transition-colors {mode === 'login'
              ? 'bg-crimson-700 text-bone-100'
              : 'text-ash-400 hover:text-ash-200'}"
          >
            Login
          </button>
          <button
            onclick={() => (mode = "signup")}
            class="flex-1 py-2 px-4 rounded-md text-sm font-medium transition-colors {mode === 'signup'
              ? 'bg-crimson-700 text-bone-100'
              : 'text-ash-400 hover:text-ash-200'}"
          >
            Sign Up
          </button>
        </div>
      {/if}

      {#if auth.error || oauthError}
        <div class="mb-4 p-3 bg-red-900/30 border border-red-700 rounded-lg text-red-300 text-sm">
          {auth.error || oauthError}
        </div>
      {/if}

      {#if magicLinkSent}
        <!-- SIGNUP: MAGIC LINK SENT -->
        <div class="space-y-4 text-center">
          <div class="w-16 h-16 mx-auto bg-green-900/30 rounded-full flex items-center justify-center">
            <Icon icon="lucide:mail" class="w-8 h-8 text-green-400" />
          </div>
          <h2 class="text-lg font-medium text-bone-100">Check your email</h2>
          <p class="text-ash-400 text-sm">
            We sent a link to<br />
            <span class="text-bone-200 font-medium">{magicLinkEmail}</span>
          </p>
          <p class="text-ash-500 text-xs">
            Click the link to set your password and complete signup.<br />
            The link expires in 15 minutes.
          </p>
          <button
            onclick={() => { magicLinkSent = false; magicLinkEmail = ""; }}
            class="text-sm text-crimson-400 hover:text-crimson-300"
          >
            Use a different email
          </button>
        </div>

      {:else if resetEmailSent}
        <!-- PASSWORD RESET: EMAIL SENT -->
        <div class="space-y-4 text-center">
          <div class="w-16 h-16 mx-auto bg-green-900/30 rounded-full flex items-center justify-center">
            <Icon icon="lucide:mail" class="w-8 h-8 text-green-400" />
          </div>
          <h2 class="text-lg font-medium text-bone-100">Check your email</h2>
          <p class="text-ash-400 text-sm">
            We sent a password reset link to<br />
            <span class="text-bone-200 font-medium">{magicLinkEmail}</span>
          </p>
          <p class="text-ash-500 text-xs">
            Click the link to reset your password.<br />
            The link expires in 15 minutes.
          </p>
          <button
            onclick={() => { resetEmailSent = false; forgotPassword = false; email = ""; }}
            class="text-sm text-crimson-400 hover:text-crimson-300"
          >
            Back to login
          </button>
        </div>

      {:else if forgotPassword}
        <!-- FORGOT PASSWORD FORM -->
        <div class="space-y-4">
          <h2 class="text-lg font-medium text-bone-100 text-center">Reset your password</h2>
          <p class="text-ash-400 text-sm text-center">
            Enter your email and we'll send you a link to reset your password.
          </p>

          <form onsubmit={(e) => { e.preventDefault(); handleForgotPassword(); }} class="space-y-4">
            <div>
              <label for="reset-email" class="block text-sm text-ash-400 mb-1">Email</label>
              <input
                type="email"
                id="reset-email"
                name="email"
                autocomplete="username"
                bind:value={email}
                placeholder="you@example.com"
                disabled={auth.isLoading}
                class="w-full px-4 py-3 bg-dusk-900 border border-ash-700 rounded-lg text-bone-100 placeholder-ash-500 focus:outline-none focus:border-crimson-600 disabled:opacity-50"
              />
            </div>
            <button
              type="submit"
              disabled={auth.isLoading || !email.trim()}
              class="w-full py-3 bg-crimson-700 hover:bg-crimson-600 disabled:bg-ash-700 disabled:opacity-50 text-bone-100 rounded-lg font-medium transition-colors flex items-center justify-center gap-2 disabled:cursor-not-allowed"
            >
              {#if auth.isLoading}
                <Icon icon="lucide:loader-2" class="w-5 h-5 animate-spin" />
              {/if}
              Send Reset Link
            </button>
          </form>

          <button
            onclick={() => { forgotPassword = false; email = ""; }}
            class="w-full text-sm text-ash-400 hover:text-ash-200"
          >
            Back to login
          </button>
        </div>

      {:else if mode === "login"}
        <!-- LOGIN MODE -->
        <div class="space-y-4">
          <p class="text-ash-400 text-sm text-center mb-4">
            Welcome back! Sign in to your account.
          </p>

          <!-- Email + Password Form -->
          <form onsubmit={(e) => { e.preventDefault(); handleEmailLogin(); }} class="space-y-4">
            <div>
              <label for="login-email" class="block text-sm text-ash-400 mb-1">Email</label>
              <input
                type="email"
                id="login-email"
                name="email"
                autocomplete="username"
                bind:value={email}
                placeholder="you@example.com"
                disabled={auth.isLoading}
                class="w-full px-4 py-3 bg-dusk-900 border border-ash-700 rounded-lg text-bone-100 placeholder-ash-500 focus:outline-none focus:border-crimson-600 disabled:opacity-50"
              />
            </div>
            <div>
              <label for="login-password" class="block text-sm text-ash-400 mb-1">Password</label>
              <input
                type="password"
                id="login-password"
                name="password"
                autocomplete="current-password"
                bind:value={password}
                placeholder="Enter your password"
                disabled={auth.isLoading}
                class="w-full px-4 py-3 bg-dusk-900 border border-ash-700 rounded-lg text-bone-100 placeholder-ash-500 focus:outline-none focus:border-crimson-600 disabled:opacity-50"
              />
            </div>
            <button
              type="submit"
              disabled={auth.isLoading || !email.trim() || !password}
              class="w-full py-3 bg-crimson-700 hover:bg-crimson-600 disabled:bg-ash-700 disabled:opacity-50 text-bone-100 rounded-lg font-medium transition-colors flex items-center justify-center gap-2 disabled:cursor-not-allowed"
            >
              {#if auth.isLoading}
                <Icon icon="lucide:loader-2" class="w-5 h-5 animate-spin" />
              {/if}
              Sign In
            </button>
          </form>

          <button
            onclick={() => { forgotPassword = true; password = ""; }}
            class="w-full text-sm text-ash-400 hover:text-ash-200"
          >
            Forgot password?
          </button>

          <!-- Divider -->
          <div class="relative my-4">
            <div class="absolute inset-0 flex items-center">
              <div class="w-full border-t border-ash-700"></div>
            </div>
            <div class="relative flex justify-center text-sm">
              <span class="px-2 bg-dusk-950 text-ash-500">or</span>
            </div>
          </div>

          {#if passkeySupported}
            <button
              onclick={handlePasskeyLogin}
              disabled={auth.isLoading}
              class="w-full py-3 bg-ash-800 hover:bg-ash-700 disabled:bg-ash-700 text-bone-100 rounded-lg font-medium transition-colors flex items-center justify-center gap-2 disabled:cursor-not-allowed"
            >
              <Icon icon="lucide:key-round" class="w-5 h-5" />
              Sign in with Passkey
            </button>
          {/if}

          <!-- Discord OAuth -->
          <button
            onclick={handleDiscordLogin}
            disabled={auth.isLoading}
            class="w-full py-3 bg-[#5865F2] hover:bg-[#4752C4] disabled:bg-ash-700 text-white rounded-lg font-medium transition-colors flex items-center justify-center gap-2 disabled:cursor-not-allowed"
          >
            <Icon icon="simple-icons:discord" class="w-5 h-5" />
            Continue with Discord
          </button>

          {#if !passkeySupported}
            <p class="text-center text-sm text-ash-500">
              Passkeys are not supported in this browser.
            </p>
          {/if}
        </div>
      {:else}
        <!-- SIGNUP MODE -->
        <div class="space-y-4">
          <p class="text-ash-400 text-sm text-center mb-4">
            Create a new account to manage tournaments.
          </p>

          {#if passkeySupported}
            <button
              onclick={handleCreateAccount}
              disabled={auth.isLoading}
              class="w-full py-3 bg-crimson-700 hover:bg-crimson-600 disabled:bg-ash-700 text-bone-100 rounded-lg font-medium transition-colors flex items-center justify-center gap-2 disabled:cursor-not-allowed"
            >
              {#if auth.isLoading}
                <Icon icon="lucide:loader-2" class="w-5 h-5 animate-spin" />
              {:else}
                <Icon icon="lucide:key-round" class="w-5 h-5" />
              {/if}
              Create Account with Passkey
            </button>
          {/if}

          <!-- Discord OAuth -->
          <button
            onclick={handleDiscordLogin}
            disabled={auth.isLoading}
            class="w-full py-3 bg-[#5865F2] hover:bg-[#4752C4] disabled:bg-ash-700 text-white rounded-lg font-medium transition-colors flex items-center justify-center gap-2 disabled:cursor-not-allowed"
          >
            <Icon icon="simple-icons:discord" class="w-5 h-5" />
            Sign Up with Discord
          </button>

          <!-- Divider -->
          <div class="relative my-4">
            <div class="absolute inset-0 flex items-center">
              <div class="w-full border-t border-ash-700"></div>
            </div>
            <div class="relative flex justify-center text-sm">
              <span class="px-2 bg-dusk-950 text-ash-500">or sign up with email</span>
            </div>
          </div>

          <!-- Email signup form -->
          <form onsubmit={(e) => { e.preventDefault(); handleSignupMagicLink(); }} class="space-y-3">
            <input
              type="email"
              name="email"
              autocomplete="username"
              bind:value={email}
              placeholder="Enter your email"
              disabled={auth.isLoading}
              class="w-full px-4 py-3 bg-dusk-900 border border-ash-700 rounded-lg text-bone-100 placeholder-ash-500 focus:outline-none focus:border-crimson-600 disabled:opacity-50"
            />
            <button
              type="submit"
              disabled={auth.isLoading || !email.trim()}
              class="w-full py-3 bg-ash-800 hover:bg-ash-700 disabled:bg-ash-800 disabled:opacity-50 text-bone-100 rounded-lg font-medium transition-colors flex items-center justify-center gap-2 disabled:cursor-not-allowed"
            >
              {#if auth.isLoading}
                <Icon icon="lucide:loader-2" class="w-5 h-5 animate-spin" />
              {:else}
                <Icon icon="lucide:mail" class="w-5 h-5" />
              {/if}
              Continue with Email
            </button>
          </form>

          {#if !passkeySupported}
            <p class="text-center text-sm text-ash-500">
              Passkeys are not supported in this browser.
            </p>
          {/if}

          <p class="text-center text-xs text-ash-500 mt-4">
            By creating an account, you agree to our terms of service.
          </p>
        </div>
      {/if}
    </div>
  </div>
</div>
