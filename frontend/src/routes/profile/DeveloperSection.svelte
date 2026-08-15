<script lang="ts">
  import { getAuthState } from "$lib/stores/auth.svelte";
  import { apiRequest } from "$lib/api";
  import { showToast } from "$lib/stores/toast.svelte";
  import { ChevronDown, Plus, TriangleAlert, Copy, Loader2, Code2, RefreshCw, PowerOff } from "@lucide/svelte";
  import Button from "$lib/components/Button.svelte";
  import * as m from '$lib/paraglide/messages.js';
  import { dialogPanel } from "$lib/actions/dialog";

  const auth = $derived(getAuthState());

  let expanded = $state(false);
  let loaded = $state(false);

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
  let loading = $state(false);

  // Register form
  let showRegister = $state(false);
  let newName = $state("");
  let newRedirectUris = $state("");
  let newScopes = $state<string[]>(["profile:read"]);
  let registering = $state(false);

  // Secret display
  let displayedSecret = $state<string | null>(null);
  let displayedClientId = $state<string | null>(null);

  // Confirm dialog
  let confirmAction = $state<{ clientId: string; action: string } | null>(null);

  async function loadClients() {
    loading = true;
    try {
      clients = await apiRequest<OAuthClientInfo[]>("/oauth/clients");
    } catch {
      // Error handled by apiRequest
    }
    loading = false;
    loaded = true;
  }

  function toggle() {
    expanded = !expanded;
    if (expanded && !loaded) loadClients();
  }

  async function handleRegister() {
    if (!newName.trim() || !newRedirectUris.trim()) return;
    registering = true;
    try {
      const uris = newRedirectUris.split("\n").map((u) => u.trim()).filter(Boolean);
      const result = await apiRequest<{
        client_id: string;
        client_secret: string;
        name: string;
      }>("/oauth/clients", {
        method: "POST",
        body: JSON.stringify({ name: newName.trim(), redirect_uris: uris, scopes: newScopes }),
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

<div class="p-6 border-t border-line">
  <button
    onclick={toggle}
    class="flex items-center justify-between w-full text-left"
  >
    <h3 class="text-sm font-medium text-ink-muted uppercase tracking-wide">{m.profile_developer_section()}</h3>
    <ChevronDown class="w-4 h-4 text-ink-muted transition-transform {expanded ? 'rotate-180' : ''}" />
  </button>
  {#if expanded}
    <div class="mt-4 space-y-4">
      <!-- Header with register button -->
      <div class="flex items-center justify-between">
        <p class="text-ink-muted text-sm">{m.developer_subtitle()}</p>
        <Button variant="primary" size="lg" onclick={() => (showRegister = !showRegister)}>
          <Plus class="w-3.5 h-3.5" />
          {m.developer_register_btn()}
        </Button>
      </div>

      <!-- Secret display banner -->
      {#if displayedSecret}
        <div class="p-4 banner-warn border rounded-lg">
          <div class="flex items-start gap-3">
            <TriangleAlert class="w-5 h-5 mt-0.5 shrink-0" />
            <div class="flex-1 min-w-0">
              <p class="text-sm font-medium mb-2">{m.developer_secret_warning()}</p>
              <div class="flex items-center gap-2">
                <code class="text-xs bg-surface-muted px-3 py-2 rounded text-ink-strong break-all flex-1">{displayedSecret}</code>
                <button
                  onclick={() => copyToClipboard(displayedSecret!)}
                  class="p-2 bg-surface-muted hover:bg-surface-muted rounded transition-colors shrink-0"
                  title={m.developer_copy_secret()}
                >
                  <Copy class="w-4 h-4 text-ink" />
                </button>
              </div>
              {#if displayedClientId}
                <p class="text-ink-muted text-xs mt-2">{m.developer_client_id_label({ id: displayedClientId })}</p>
              {/if}
              <button
                onclick={() => { displayedSecret = null; displayedClientId = null; }}
                class="text-xs text-ink-muted hover:text-ink-bright mt-2"
              >{m.toast_dismiss()}</button>
            </div>
          </div>
        </div>
      {/if}

      <!-- Register form -->
      {#if showRegister}
        <div class="bg-surface-muted rounded-lg border border-line-strong p-4">
          <h4 class="text-sm font-medium text-ink-strong mb-3">{m.developer_register_title()}</h4>
          <form onsubmit={(e) => { e.preventDefault(); handleRegister(); }} class="space-y-3">
            <div>
              <label for="app-name" class="block text-xs text-ink-muted mb-1">{m.developer_app_name()}</label>
              <input type="text" id="app-name" bind:value={newName} placeholder="My App"
                class="w-full px-3 py-2 bg-surface-card border border-line-strong rounded text-sm text-ink-strong placeholder-ink-faint focus:outline-none focus:border-accent-strong-hover" />
            </div>
            <div>
              <label for="redirect-uris" class="block text-xs text-ink-muted mb-1">{m.developer_redirect_uris()}</label>
              <textarea id="redirect-uris" bind:value={newRedirectUris} placeholder="https://myapp.com/callback" rows="2"
                class="w-full px-3 py-2 bg-surface-card border border-line-strong rounded text-sm text-ink-strong placeholder-ink-faint focus:outline-none focus:border-accent-strong-hover font-mono"></textarea>
            </div>
            <div>
              <span class="block text-xs text-ink-muted mb-1">{m.developer_scopes()}</span>
              <div class="space-y-1.5">
                <label class="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" checked={newScopes.includes("profile:read")} onchange={() => toggleScope("profile:read")}
                    class="w-3.5 h-3.5 rounded border-line-strong bg-surface-muted text-accent focus:ring-accent-strong-hover" />
                  <div>
                    <span class="text-ink-strong text-xs">profile:read</span>
                    <span class="text-ink-faint text-xs ml-1">— {m.developer_scope_profile_read_desc()}</span>
                  </div>
                </label>
                <label class="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" checked={newScopes.includes("user:impersonate")} onchange={() => toggleScope("user:impersonate")}
                    class="w-3.5 h-3.5 rounded border-line-strong bg-surface-muted text-accent focus:ring-accent-strong-hover" />
                  <div>
                    <span class="text-ink-strong text-xs">user:impersonate</span>
                    <span class="text-ink-faint text-xs ml-1">— {m.developer_scope_impersonate_desc()}</span>
                  </div>
                </label>
              </div>
            </div>
            <div class="flex gap-2">
              <Button type="button" variant="secondary" size="lg" class="flex-1" onclick={() => (showRegister = false)}>{m.common_cancel()}</Button>
              <Button type="submit" variant="primary" size="lg" class="flex-1" loading={registering} disabled={!newName.trim() || !newRedirectUris.trim() || newScopes.length === 0}>
                {m.developer_register_submit()}
              </Button>
            </div>
          </form>
        </div>
      {/if}

      <!-- Client list -->
      {#if loading}
        <div class="flex items-center justify-center py-8">
          <Loader2 class="w-6 h-6 animate-spin text-ink-muted" />
        </div>
      {:else if clients.length === 0}
        <div class="text-center py-6">
          <Code2 class="w-10 h-10 text-ink-faint mx-auto mb-3" />
          <p class="text-ink-muted text-sm">{m.developer_no_clients()}</p>
          <p class="text-ink-faint text-xs mt-1">{m.developer_no_clients_hint()}</p>
        </div>
      {:else}
        <div class="space-y-3">
          {#each clients as client}
            <div class="bg-surface-muted rounded-lg border border-line-strong p-4">
              <div class="flex items-start justify-between">
                <div class="flex-1 min-w-0">
                  <div class="flex items-center gap-2">
                    <h4 class="text-ink-strong font-medium text-sm">{client.name}</h4>
                    {#if client.active}
                      <span class="px-1.5 py-0.5 badge-success text-xs rounded-full">{m.developer_status_active()}</span>
                    {:else}
                      <span class="px-1.5 py-0.5 badge-danger text-xs rounded-full">{m.developer_status_inactive()}</span>
                    {/if}
                  </div>
                  <div class="mt-1.5 space-y-0.5">
                    <div class="flex items-center gap-2">
                      <span class="text-ink-faint text-xs">{m.developer_client_id()}</span>
                      <code class="text-xs text-ink bg-surface-card px-1.5 py-0.5 rounded">{client.client_id}</code>
                      <button onclick={() => copyToClipboard(client.client_id)} class="text-ink-faint hover:text-ink" title={m.developer_copy()}>
                        <Copy class="w-3 h-3" />
                      </button>
                    </div>
                    <div class="flex items-center gap-2">
                      <span class="text-ink-faint text-xs">{m.developer_scopes_label()}</span>
                      <span class="text-xs text-ink">{client.scopes.join(", ")}</span>
                    </div>
                    <div class="text-xs text-ink-faint">{m.developer_redirect_uris_label({ uris: client.redirect_uris.join(", ") })}</div>
                  </div>
                </div>
                {#if client.active}
                  <div class="flex gap-1.5 shrink-0">
                    <button onclick={() => (confirmAction = { clientId: client.client_id, action: "regenerate" })}
                      class="p-1.5 text-ink-muted hover:text-ink-bright hover:bg-surface-card rounded transition-colors" title={m.developer_regenerate_title()}>
                      <RefreshCw class="w-4 h-4" />
                    </button>
                    <button onclick={() => (confirmAction = { clientId: client.client_id, action: "deactivate" })}
                      class="p-1.5 text-link hover:text-link-soft hover:bg-surface-card rounded transition-colors" title={m.developer_deactivate_title()}>
                      <PowerOff class="w-4 h-4" />
                    </button>
                  </div>
                {/if}
              </div>
            </div>
          {/each}
        </div>
      {/if}
    </div>
  {/if}
</div>

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
      class="bg-surface-card rounded-lg border border-line p-6 w-full max-w-sm"
      onclick={(e) => e.stopPropagation()}
      onkeydown={(e) => e.stopPropagation()}
      use:dialogPanel={() => confirmAction = null}
      role="dialog" aria-modal="true" tabindex="-1"
    >
      {#if confirmAction.action === "regenerate"}
        <h3 class="text-ink-strong font-medium mb-2">{m.developer_confirm_regenerate()}</h3>
        <p class="text-ink-muted text-sm mb-4">{m.developer_confirm_regenerate_msg()}</p>
        <div class="flex gap-3">
          <Button variant="secondary" size="md" class="flex-1" onclick={() => (confirmAction = null)}>{m.common_cancel()}</Button>
          <Button variant="danger" size="md" class="flex-1" onclick={() => handleRegenerate(confirmAction!.clientId)}><TriangleAlert class="w-4 h-4" aria-hidden="true" />{m.developer_regenerate_btn()}</Button>
        </div>
      {:else}
        <h3 class="text-ink-strong font-medium mb-2">{m.developer_confirm_deactivate()}</h3>
        <p class="text-ink-muted text-sm mb-4">{m.developer_confirm_deactivate_msg()}</p>
        <div class="flex gap-3">
          <Button variant="secondary" size="md" class="flex-1" onclick={() => (confirmAction = null)}>{m.common_cancel()}</Button>
          <Button variant="danger" size="md" class="flex-1" onclick={() => handleDeactivate(confirmAction!.clientId)}><TriangleAlert class="w-4 h-4" aria-hidden="true" />{m.developer_deactivate_btn()}</Button>
        </div>
      {/if}
    </div>
  </div>
{/if}
