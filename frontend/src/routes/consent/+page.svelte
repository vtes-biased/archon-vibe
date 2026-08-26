<script lang="ts">
  import { toUserMessage } from '$lib/errors';
  import { goto } from "$app/navigation";
  import { page } from "$app/stores";
  import { onMount } from "svelte";
  import { getAuthState, getAccessToken, initAuth } from "$lib/stores/auth.svelte";
  import { Loader2, CircleAlert, ShieldCheck, CircleCheck } from '@lucide/svelte';
  import Button from '$lib/components/Button.svelte';
  import * as m from '$lib/paraglide/messages.js';

  const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

  const auth = $derived(getAuthState());

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

  onMount(async () => {
    // Root layout's auth hydration fires AFTER this page's onMount, so
    // auth.isAuthenticated is stale here on load; settle it first or a
    // logged-in user loops back to login instead of seeing the prompt.
    if (auth.isLoading) await initAuth();

    if (!auth.isAuthenticated) {
      const currentPath = window.location.pathname + window.location.search;
      const params = new URLSearchParams(window.location.search);
      const loginHint = params.get("login_hint");
      const loginParams = new URLSearchParams({ redirect: currentPath });
      if (loginHint) loginParams.set("login_hint", loginHint);
      goto(`/login?${loginParams.toString()}`);
      return;
    }

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
        { headers: { Authorization: `Bearer ${token}` } },
      );

      if (!response.ok) {
        const data = await response.json();
        error = data.detail || m.oauth_error_load_failed();
        loading = false;
        return;
      }

      const data = await response.json();
      if (data.redirect_url) {
        // Consent already on file: no prompt, straight back to the app.
        window.location.href = data.redirect_url;
        return;
      }

      clientName = data.client_name;
      scopes = data.scopes;
      scopeDescriptions = data.scope_descriptions;
      redirectUri = data.redirect_uri;
      stateParam = data.state;
      clientId = data.client_id;
      codeChallenge = data.code_challenge;
    } catch (e) {
      error = toUserMessage(e, m.oauth_error_load_failed());
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
        error = data.detail || m.oauth_error_authorize();
        submitting = false;
        return;
      }

      const data = await response.json();
      window.location.href = data.redirect_url;
    } catch (e) {
      error = toUserMessage(e, m.oauth_error_authorize());
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
        error = data.detail || m.oauth_error_deny();
        submitting = false;
        return;
      }

      const data = await response.json();
      window.location.href = data.redirect_url;
    } catch {
      const params = new URLSearchParams({ error: "access_denied" });
      if (stateParam) params.set("state", stateParam);
      window.location.href = `${redirectUri}?${params.toString()}`;
    }
  }
</script>

<svelte:head>
  <title>{m.oauth_page_title()} - Archon</title>
</svelte:head>

<div class="min-h-shell flex items-center justify-center p-4">
  <div class="w-full max-w-md">
    <div class="text-center mb-6">
      <h1 class="text-2xl font-semibold text-accent">Archon</h1>
      <p class="text-ink-muted text-sm">{m.oauth_subtitle()}</p>
    </div>

    <div class="bg-surface-card rounded-lg shadow-lg p-8 border border-line">
      {#if loading}
        <div class="flex items-center justify-center py-8">
          <Loader2 class="w-8 h-8 animate-spin text-ink-muted" />
        </div>
      {:else if error}
        <div class="text-center space-y-4">
          <div class="w-16 h-16 mx-auto banner-error border rounded-full flex items-center justify-center">
            <CircleAlert class="w-8 h-8" />
          </div>
          <p class="text-link-soft text-sm">{error}</p>
          <button
            onclick={() => goto("/")}
            class="text-sm text-link hover:text-link-soft"
          >
            {m.oauth_return_to_archon()}
          </button>
        </div>
      {:else}
        <div class="space-y-6">
          <div class="text-center">
            <div class="w-16 h-16 mx-auto bg-surface-muted rounded-full flex items-center justify-center mb-4">
              <ShieldCheck class="w-8 h-8 text-link" />
            </div>
            <h2 class="text-lg font-medium text-ink-strong">
              {clientName}
            </h2>
            <p class="text-ink-muted text-sm mt-1">
              {m.oauth_wants_access()}
            </p>
          </div>

          <div class="space-y-3">
            <p class="text-sm text-ink font-medium">{m.oauth_allow_application()}</p>
            {#each scopes as scope}
              <div class="flex items-start gap-3 p-3 bg-surface-muted rounded-lg">
                <CircleCheck class="w-5 h-5 text-info mt-0.5 shrink-0" />
                <div>
                  <p class="text-ink-strong text-sm">{scope}</p>
                  {#if scopeDescriptions[scope]}
                    <p class="text-ink-muted text-xs mt-0.5">{scopeDescriptions[scope]}</p>
                  {/if}
                </div>
              </div>
            {/each}
          </div>

          <div class="flex gap-3">
            <Button
              variant="secondary"
              size="lg"
              class="flex-1"
              disabled={submitting}
              onclick={handleDeny}
            >
              {m.oauth_deny()}
            </Button>
            <Button
              variant="primary"
              size="lg"
              class="flex-1"
              loading={submitting}
              onclick={handleApprove}
            >
              {m.oauth_approve()}
            </Button>
          </div>

          <p class="text-center text-xs text-ink-faint">
            {m.oauth_logged_in_as({ name: auth.user?.name ?? '' })}
          </p>
        </div>
      {/if}
    </div>
  </div>
</div>
