<script lang="ts">
  import { goto } from "$app/navigation";
  import { page } from "$app/stores";
  import { onMount } from "svelte";
  import { getAuthState, getAccessToken } from "$lib/stores/auth.svelte";
  import Icon from "@iconify/svelte";
  import * as m from '$lib/paraglide/messages.js';

  const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

  const auth = $derived(getAuthState());

  // Authorization request details from the API
  let clientName = $state("");
  let scopes = $state<string[]>([]);
  let scopeDescriptions = $state<Record<string, string>>({});
  let redirectUri = $state("");
  let stateParam = $state("");
  let clientId = $state("");
  let codeChallenge = $state("");
  let loading = $state(true);
  let submitting = $state(false);
  let error = $state<string | null>(null);

  // If the user was auto-redirected (existing consent), this won't render

  onMount(async () => {
    if (!auth.isAuthenticated) {
      // Redirect to login, then back here
      const currentUrl = window.location.href;
      goto(`/login?redirect=${encodeURIComponent(currentUrl)}`);
      return;
    }

    // Forward the original query params to the authorize endpoint
    const params = new URLSearchParams(window.location.search);
    const token = getAccessToken();
    if (!token) {
      error = m.oauth_error_not_authenticated();
      loading = false;
      return;
    }

    try {
      const response = await fetch(
        `${API_BASE}/oauth/authorize?${params.toString()}`,
        {
          headers: { Authorization: `Bearer ${token}` },
          redirect: "manual",
        },
      );

      if (response.type === "opaqueredirect" || response.status === 302) {
        // Auto-approved (existing consent), browser handles redirect
        window.location.href = response.headers.get("Location") || "";
        return;
      }

      if (!response.ok) {
        const data = await response.json();
        error = data.detail || "Authorization request failed";
        loading = false;
        return;
      }

      const data = await response.json();
      clientName = data.client_name;
      scopes = data.scopes;
      scopeDescriptions = data.scope_descriptions;
      redirectUri = data.redirect_uri;
      stateParam = data.state;
      clientId = data.client_id;
      codeChallenge = data.code_challenge;
    } catch (e) {
      error = e instanceof Error ? e.message : m.oauth_error_load_failed();
    }

    loading = false;
  });

  async function handleApprove() {
    submitting = true;
    const token = getAccessToken();

    try {
      const response = await fetch(`${API_BASE}/oauth/authorize`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          client_id: clientId,
          redirect_uri: redirectUri,
          scope: scopes.join(" "),
          state: stateParam,
          code_challenge: codeChallenge,
          approved: true,
        }),
      });

      if (!response.ok) {
        const data = await response.json();
        error = data.detail || "Authorization failed";
        submitting = false;
        return;
      }

      const data = await response.json();
      window.location.href = data.redirect_url;
    } catch (e) {
      error = e instanceof Error ? e.message : "Authorization failed";
      submitting = false;
    }
  }

  async function handleDeny() {
    submitting = true;
    const token = getAccessToken();

    try {
      const response = await fetch(`${API_BASE}/oauth/authorize`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          client_id: clientId,
          redirect_uri: redirectUri,
          scope: scopes.join(" "),
          state: stateParam,
          code_challenge: codeChallenge,
          approved: false,
        }),
      });

      if (!response.ok) {
        const data = await response.json();
        error = data.detail || "Failed to deny";
        submitting = false;
        return;
      }

      const data = await response.json();
      window.location.href = data.redirect_url;
    } catch {
      // On deny, redirect with error
      const params = new URLSearchParams({ error: "access_denied" });
      if (stateParam) params.set("state", stateParam);
      window.location.href = `${redirectUri}?${params.toString()}`;
    }
  }
</script>

<svelte:head>
  <title>{m.oauth_page_title()} - Archon</title>
</svelte:head>

<div class="min-h-screen flex items-center justify-center p-4">
  <div class="w-full max-w-md">
    <div class="text-center mb-6">
      <h1 class="text-2xl font-light text-crimson-500">Archon</h1>
      <p class="text-ash-400 text-sm">{m.oauth_subtitle()}</p>
    </div>

    <div class="bg-dusk-950 rounded-lg shadow-lg p-8 border border-ash-800">
      {#if loading}
        <div class="flex items-center justify-center py-8">
          <Icon icon="lucide:loader-2" class="w-8 h-8 animate-spin text-ash-400" />
        </div>
      {:else if error}
        <div class="text-center space-y-4">
          <div class="w-16 h-16 mx-auto bg-red-900/30 rounded-full flex items-center justify-center">
            <Icon icon="lucide:alert-circle" class="w-8 h-8 text-red-400" />
          </div>
          <p class="text-red-300 text-sm">{error}</p>
          <button
            onclick={() => goto("/")}
            class="text-sm text-crimson-400 hover:text-crimson-300"
          >
            {m.oauth_return_to_archon()}
          </button>
        </div>
      {:else}
        <div class="space-y-6">
          <div class="text-center">
            <div class="w-16 h-16 mx-auto bg-dusk-900 rounded-full flex items-center justify-center mb-4">
              <Icon icon="lucide:shield-check" class="w-8 h-8 text-crimson-400" />
            </div>
            <h2 class="text-lg font-medium text-bone-100">
              {clientName}
            </h2>
            <p class="text-ash-400 text-sm mt-1">
              {m.oauth_wants_access()}
            </p>
          </div>

          <div class="space-y-3">
            <p class="text-sm text-ash-300 font-medium">{m.oauth_allow_application()}</p>
            {#each scopes as scope}
              <div class="flex items-start gap-3 p-3 bg-dusk-900 rounded-lg">
                <Icon icon="lucide:check-circle" class="w-5 h-5 text-green-400 mt-0.5 shrink-0" />
                <div>
                  <p class="text-bone-200 text-sm">{scope}</p>
                  {#if scopeDescriptions[scope]}
                    <p class="text-ash-400 text-xs mt-0.5">{scopeDescriptions[scope]}</p>
                  {/if}
                </div>
              </div>
            {/each}
          </div>

          <div class="flex gap-3">
            <button
              onclick={handleDeny}
              disabled={submitting}
              class="flex-1 py-3 bg-ash-800 hover:bg-ash-700 disabled:opacity-50 text-bone-100 rounded-lg font-medium transition-colors"
            >
              {m.oauth_deny()}
            </button>
            <button
              onclick={handleApprove}
              disabled={submitting}
              class="flex-1 py-3 bg-crimson-700 hover:bg-crimson-600 disabled:opacity-50 text-white rounded-lg font-medium transition-colors flex items-center justify-center gap-2"
            >
              {#if submitting}
                <Icon icon="lucide:loader-2" class="w-5 h-5 animate-spin" />
              {/if}
              {m.oauth_approve()}
            </button>
          </div>

          <p class="text-center text-xs text-ash-500">
            {m.oauth_logged_in_as({ name: auth.user?.name ?? '' })}
          </p>
        </div>
      {/if}
    </div>
  </div>
</div>
