<script lang="ts">
  import { goto } from "$app/navigation";
  import { getAuthState, getAccessToken, hasRole } from "$lib/stores/auth.svelte";
  import { apiRequest } from "$lib/api";
  import { showToast } from "$lib/stores/toast.svelte";
  import { Plus, TriangleAlert, Copy, Loader2, Code2, RefreshCw, PowerOff } from "lucide-svelte";
  import * as m from '$lib/paraglide/messages.js';

  const auth = $derived(getAuthState());
  const isDev = $derived(hasRole("DEV") || hasRole("IC"));

  interface OAuthClientInfo {
    uid: string;
    name: string;
    client_id: string;
    redirect_uris: string[];
    scopes: string[];
    active: boolean;
    modified: string;
  }

  let clients = $state<OAuthClientInfo[]>([]);
  let loading = $state(true);

  // Register form
  let showRegister = $state(false);
  let newName = $state("");
  let newRedirectUris = $state("");
  let newScopes = $state<string[]>(["profile:read"]);
  let registering = $state(false);

  // Secret display (shown once after creation or regeneration)
  let displayedSecret = $state<string | null>(null);
  let displayedClientId = $state<string | null>(null);

  // Confirm dialog
  let confirmAction = $state<{ clientId: string; action: string } | null>(null);

  $effect(() => {
    if (!auth.isLoading && auth.isAuthenticated && isDev) {
      loadClients();
    }
    if (!auth.isLoading && (!auth.isAuthenticated || !isDev)) {
      goto("/");
    }
  });

  async function loadClients() {
    loading = true;
    try {
      clients = await apiRequest<OAuthClientInfo[]>("/oauth/clients");
    } catch {
      // Error handled by apiRequest
    }
    loading = false;
  }

  async function handleRegister() {
    if (!newName.trim() || !newRedirectUris.trim()) return;
    registering = true;

    try {
      const uris = newRedirectUris
        .split("\n")
        .map((u) => u.trim())
        .filter(Boolean);

      const result = await apiRequest<{
        client_id: string;
        client_secret: string;
        name: string;
      }>("/oauth/clients", {
        method: "POST",
        body: JSON.stringify({
          name: newName.trim(),
          redirect_uris: uris,
          scopes: newScopes,
        }),
      });

      displayedSecret = result.client_secret;
      displayedClientId = result.client_id;
      showRegister = false;
      newName = "";
      newRedirectUris = "";
      newScopes = ["profile:read"];
      await loadClients();
      showToast({ type: "success", message: m.developer_client_registered() });
    } catch {
      // handled by apiRequest
    }
    registering = false;
  }

  async function handleRegenerate(clientId: string) {
    try {
      const result = await apiRequest<{
        client_id: string;
        client_secret: string;
      }>(`/oauth/clients/${clientId}/regenerate-secret`, { method: "POST" });

      displayedSecret = result.client_secret;
      displayedClientId = result.client_id;
      confirmAction = null;
      showToast({ type: "success", message: m.developer_secret_regenerated() });
    } catch {
      // handled
    }
  }

  async function handleDeactivate(clientId: string) {
    try {
      await apiRequest(`/oauth/clients/${clientId}`, { method: "DELETE" });
      confirmAction = null;
      await loadClients();
      showToast({ type: "success", message: m.developer_client_deactivated() });
    } catch {
      // handled
    }
  }

  function copyToClipboard(text: string) {
    navigator.clipboard.writeText(text);
    showToast({ type: "success", message: m.developer_copied() });
  }

  function toggleScope(scope: string) {
    if (newScopes.includes(scope)) {
      newScopes = newScopes.filter((s) => s !== scope);
    } else {
      newScopes = [...newScopes, scope];
    }
  }
</script>

<svelte:head>
  <title>{m.developer_page_title()} - Archon</title>
</svelte:head>

<div class="max-w-3xl mx-auto p-4 sm:p-8">
  <div class="flex items-center justify-between mb-6">
    <div>
      <h1 class="text-2xl font-light text-bone-100">{m.developer_title()}</h1>
      <p class="text-ash-400 text-sm">{m.developer_subtitle()}</p>
    </div>
    <button
      onclick={() => (showRegister = !showRegister)}
      class="px-4 py-2 bg-crimson-700 hover:bg-crimson-600 text-white rounded-lg text-sm font-medium transition-colors flex items-center gap-2"
    >
      <Plus class="w-4 h-4" />
      {m.developer_register_btn()}
    </button>
  </div>

  <!-- Secret display banner -->
  {#if displayedSecret}
    <div class="mb-6 p-4 bg-yellow-900/30 border border-yellow-700 rounded-lg">
      <div class="flex items-start gap-3">
        <TriangleAlert class="w-5 h-5 text-yellow-400 mt-0.5 shrink-0" />
        <div class="flex-1 min-w-0">
          <p class="text-yellow-200 text-sm font-medium mb-2">
            {m.developer_secret_warning()}
          </p>
          <div class="flex items-center gap-2">
            <code class="text-xs bg-dusk-900 px-3 py-2 rounded text-bone-200 break-all flex-1">
              {displayedSecret}
            </code>
            <button
              onclick={() => copyToClipboard(displayedSecret!)}
              class="p-2 bg-dusk-900 hover:bg-dusk-800 rounded transition-colors shrink-0"
              title={m.developer_copy_secret()}
            >
              <Copy class="w-4 h-4 text-ash-300" />
            </button>
          </div>
          {#if displayedClientId}
            <p class="text-ash-400 text-xs mt-2">{m.developer_client_id_label({ id: displayedClientId })}</p>
          {/if}
          <button
            onclick={() => { displayedSecret = null; displayedClientId = null; }}
            class="text-xs text-ash-400 hover:text-ash-200 mt-2"
          >
            {m.toast_dismiss()}
          </button>
        </div>
      </div>
    </div>
  {/if}

  <!-- Register form -->
  {#if showRegister}
    <div class="mb-6 bg-dusk-950 rounded-lg border border-ash-800 p-6">
      <h2 class="text-lg font-medium text-bone-100 mb-4">{m.developer_register_title()}</h2>
      <form onsubmit={(e) => { e.preventDefault(); handleRegister(); }} class="space-y-4">
        <div>
          <label for="app-name" class="block text-sm text-ash-400 mb-1">{m.developer_app_name()}</label>
          <input
            type="text"
            id="app-name"
            bind:value={newName}
            placeholder="My App"
            class="w-full px-4 py-3 bg-dusk-900 border border-ash-700 rounded-lg text-bone-100 placeholder-ash-500 focus:outline-none focus:border-crimson-600"
          />
        </div>
        <div>
          <label for="redirect-uris" class="block text-sm text-ash-400 mb-1">{m.developer_redirect_uris()}</label>
          <textarea
            id="redirect-uris"
            bind:value={newRedirectUris}
            placeholder="https://myapp.com/callback"
            rows="3"
            class="w-full px-4 py-3 bg-dusk-900 border border-ash-700 rounded-lg text-bone-100 placeholder-ash-500 focus:outline-none focus:border-crimson-600 font-mono text-sm"
          ></textarea>
        </div>
        <div>
          <span class="block text-sm text-ash-400 mb-2">{m.developer_scopes()}</span>
          <div class="space-y-2">
            <label class="flex items-center gap-3 cursor-pointer">
              <input
                type="checkbox"
                checked={newScopes.includes("profile:read")}
                onchange={() => toggleScope("profile:read")}
                class="w-4 h-4 rounded border-ash-600 bg-dusk-900 text-crimson-600 focus:ring-crimson-600"
              />
              <div>
                <span class="text-bone-200 text-sm">profile:read</span>
                <p class="text-ash-500 text-xs">{m.developer_scope_profile_read_desc()}</p>
              </div>
            </label>
            <label class="flex items-center gap-3 cursor-pointer">
              <input
                type="checkbox"
                checked={newScopes.includes("user:impersonate")}
                onchange={() => toggleScope("user:impersonate")}
                class="w-4 h-4 rounded border-ash-600 bg-dusk-900 text-crimson-600 focus:ring-crimson-600"
              />
              <div>
                <span class="text-bone-200 text-sm">user:impersonate</span>
                <p class="text-ash-500 text-xs">{m.developer_scope_impersonate_desc()}</p>
              </div>
            </label>
          </div>
        </div>
        <div class="flex gap-3">
          <button
            type="button"
            onclick={() => (showRegister = false)}
            class="flex-1 py-3 bg-ash-800 hover:bg-ash-700 text-bone-100 rounded-lg font-medium transition-colors"
          >
            {m.common_cancel()}
          </button>
          <button
            type="submit"
            disabled={registering || !newName.trim() || !newRedirectUris.trim() || newScopes.length === 0}
            class="flex-1 py-3 bg-crimson-700 hover:bg-crimson-600 disabled:opacity-50 text-white rounded-lg font-medium transition-colors flex items-center justify-center gap-2"
          >
            {#if registering}
              <Loader2 class="w-5 h-5 animate-spin" />
            {/if}
            {m.developer_register_submit()}
          </button>
        </div>
      </form>
    </div>
  {/if}

  <!-- Client list -->
  {#if loading}
    <div class="flex items-center justify-center py-12">
      <Loader2 class="w-8 h-8 animate-spin text-ash-400" />
    </div>
  {:else if clients.length === 0}
    <div class="text-center py-12">
      <Code2 class="w-12 h-12 text-ash-600 mx-auto mb-4" />
      <p class="text-ash-400">{m.developer_no_clients()}</p>
      <p class="text-ash-500 text-sm mt-1">{m.developer_no_clients_hint()}</p>
    </div>
  {:else}
    <div class="space-y-4">
      {#each clients as client}
        <div class="bg-dusk-950 rounded-lg border border-ash-800 p-5">
          <div class="flex items-start justify-between">
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2">
                <h3 class="text-bone-100 font-medium">{client.name}</h3>
                {#if client.active}
                  <span class="px-2 py-0.5 bg-green-900/30 text-green-400 text-xs rounded-full">{m.developer_status_active()}</span>
                {:else}
                  <span class="px-2 py-0.5 bg-red-900/30 text-red-400 text-xs rounded-full">{m.developer_status_inactive()}</span>
                {/if}
              </div>
              <div class="mt-2 space-y-1">
                <div class="flex items-center gap-2">
                  <span class="text-ash-500 text-xs">{m.developer_client_id()}</span>
                  <code class="text-xs text-ash-300 bg-dusk-900 px-2 py-0.5 rounded">{client.client_id}</code>
                  <button
                    onclick={() => copyToClipboard(client.client_id)}
                    class="text-ash-500 hover:text-ash-300"
                    title={m.developer_copy()}
                  >
                    <Copy class="w-3.5 h-3.5" />
                  </button>
                </div>
                <div class="flex items-center gap-2">
                  <span class="text-ash-500 text-xs">{m.developer_scopes_label()}</span>
                  <span class="text-xs text-ash-300">{client.scopes.join(", ")}</span>
                </div>
                <div class="text-xs text-ash-500">
                  {m.developer_redirect_uris_label({ uris: client.redirect_uris.join(", ") })}
                </div>
              </div>
            </div>
            {#if client.active}
              <div class="flex gap-2 shrink-0">
                <button
                  onclick={() => (confirmAction = { clientId: client.client_id, action: "regenerate" })}
                  class="p-2 text-ash-400 hover:text-ash-200 hover:bg-dusk-900 rounded transition-colors"
                  title={m.developer_regenerate_title()}
                >
                  <RefreshCw class="w-4 h-4" />
                </button>
                <button
                  onclick={() => (confirmAction = { clientId: client.client_id, action: "deactivate" })}
                  class="p-2 text-red-400 hover:text-red-300 hover:bg-dusk-900 rounded transition-colors"
                  title={m.developer_deactivate_title()}
                >
                  <PowerOff class="w-4 h-4" />
                </button>
              </div>
            {/if}
          </div>
        </div>
      {/each}
    </div>
  {/if}

  <!-- Confirm dialog -->
  {#if confirmAction}
    <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
    <div
      class="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4"
      role="presentation"
      onclick={() => (confirmAction = null)}
      onkeydown={(e) => { if (e.key === 'Escape') confirmAction = null; }}
    >
      <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
      <div
        class="bg-dusk-950 rounded-lg border border-ash-800 p-6 w-full max-w-sm"
        onclick={(e) => e.stopPropagation()}
        onkeydown={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        tabindex="-1"
      >
        {#if confirmAction.action === "regenerate"}
          <h3 id="confirm-dialog-title" class="text-bone-100 font-medium mb-2">{m.developer_confirm_regenerate()}</h3>
          <p class="text-ash-400 text-sm mb-4">
            {m.developer_confirm_regenerate_msg()}
          </p>
          <div class="flex gap-3">
            <button
              onclick={() => (confirmAction = null)}
              class="flex-1 py-2 bg-ash-800 hover:bg-ash-700 text-bone-100 rounded-lg text-sm transition-colors"
            >
              {m.common_cancel()}
            </button>
            <button
              onclick={() => handleRegenerate(confirmAction!.clientId)}
              class="flex-1 py-2 bg-crimson-700 hover:bg-crimson-600 text-white rounded-lg text-sm transition-colors"
            >
              {m.developer_regenerate_btn()}
            </button>
          </div>
        {:else}
          <h3 id="confirm-dialog-title" class="text-bone-100 font-medium mb-2">{m.developer_confirm_deactivate()}</h3>
          <p class="text-ash-400 text-sm mb-4">
            {m.developer_confirm_deactivate_msg()}
          </p>
          <div class="flex gap-3">
            <button
              onclick={() => (confirmAction = null)}
              class="flex-1 py-2 bg-ash-800 hover:bg-ash-700 text-bone-100 rounded-lg text-sm transition-colors"
            >
              {m.common_cancel()}
            </button>
            <button
              onclick={() => handleDeactivate(confirmAction!.clientId)}
              class="flex-1 py-2 bg-red-700 hover:bg-red-600 text-bone-100 rounded-lg text-sm transition-colors"
            >
              {m.developer_deactivate_btn()}
            </button>
          </div>
        {/if}
      </div>
    </div>
  {/if}
</div>
