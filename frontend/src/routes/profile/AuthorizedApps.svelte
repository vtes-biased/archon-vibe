<script lang="ts">
  import { apiRequest } from "$lib/api";
  import { showToast } from "$lib/stores/toast.svelte";
  import { ChevronDown, Loader2, AppWindow, TriangleAlert } from "@lucide/svelte";
  import Button from "$lib/components/Button.svelte";
  import * as m from '$lib/paraglide/messages.js';

  interface AuthorizedApp {
    client_id: string;
    name: string;
    scopes: string[];
    granted_at: string;
  }

  let expanded = $state(false);
  let loaded = $state(false);
  let loading = $state(false);
  let apps = $state<AuthorizedApp[]>([]);

  let confirmRevoke = $state<AuthorizedApp | null>(null);
  let revoking = $state(false);

  // Friendly per-scope text, reusing the developer-facing scope descriptions.
  const scopeDesc: Record<string, () => string> = {
    "profile:read": m.developer_scope_profile_read_desc,
    "user:impersonate": m.developer_scope_impersonate_desc,
  };

  async function loadApps() {
    loading = true;
    try {
      apps = await apiRequest<AuthorizedApp[]>("/oauth/consents");
    } catch {
      // Error handled by apiRequest
    }
    loading = false;
    loaded = true;
  }

  function toggle() {
    expanded = !expanded;
    if (expanded && !loaded) loadApps();
  }

  async function handleRevoke(app: AuthorizedApp) {
    revoking = true;
    try {
      await apiRequest(`/oauth/consents/${app.client_id}`, { method: "DELETE" });
      apps = apps.filter((a) => a.client_id !== app.client_id);
      confirmRevoke = null;
      showToast({ type: "success", message: m.authorized_apps_revoked() });
    } catch {
      // handled by apiRequest
    }
    revoking = false;
  }

  function formatDate(iso: string): string {
    return new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
  }
</script>

<div class="p-6 border-t border-line">
  <button onclick={toggle} class="flex items-center justify-between w-full text-left">
    <h3 class="text-sm font-medium text-ink-muted uppercase tracking-wide">{m.profile_authorized_apps_section()}</h3>
    <ChevronDown class="w-4 h-4 text-ink-muted transition-transform {expanded ? 'rotate-180' : ''}" />
  </button>
  {#if expanded}
    <div class="mt-4 space-y-4">
      <p class="text-ink-muted text-sm">{m.authorized_apps_subtitle()}</p>

      {#if loading}
        <div class="flex items-center justify-center py-8">
          <Loader2 class="w-6 h-6 animate-spin text-ink-muted" />
        </div>
      {:else if apps.length === 0}
        <div class="text-center py-6">
          <AppWindow class="w-10 h-10 text-ink-faint mx-auto mb-3" />
          <p class="text-ink-muted text-sm">{m.authorized_apps_none()}</p>
          <p class="text-ink-faint text-xs mt-1">{m.authorized_apps_none_hint()}</p>
        </div>
      {:else}
        <div class="space-y-3">
          {#each apps as app}
            <div class="bg-surface-muted rounded-lg border border-line-strong p-4">
              <div class="flex items-start justify-between gap-3">
                <div class="flex-1 min-w-0">
                  <h4 class="text-ink-strong font-medium text-sm">{app.name}</h4>
                  <ul class="mt-1.5 space-y-0.5">
                    {#each app.scopes as scope}
                      <li class="text-xs text-ink">• {scopeDesc[scope] ? scopeDesc[scope]() : scope}</li>
                    {/each}
                  </ul>
                  <div class="text-xs text-ink-faint mt-1.5">{m.authorized_apps_granted({ date: formatDate(app.granted_at) })}</div>
                </div>
                <Button variant="secondary" size="md" class="shrink-0" onclick={() => (confirmRevoke = app)}>
                  {m.authorized_apps_revoke()}
                </Button>
              </div>
            </div>
          {/each}
        </div>
      {/if}
    </div>
  {/if}
</div>

<!-- Revoke confirm dialog -->
{#if confirmRevoke}
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
  <div
    class="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4"
    role="presentation"
    onclick={() => (confirmRevoke = null)}
    onkeydown={(e) => { if (e.key === 'Escape') confirmRevoke = null; }}
  >
    <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
    <div
      class="bg-surface-card rounded-lg border border-line p-6 w-full max-w-sm"
      onclick={(e) => e.stopPropagation()}
      onkeydown={(e) => e.stopPropagation()}
      role="dialog" aria-modal="true" tabindex="-1"
    >
      <h3 class="text-ink-strong font-medium mb-2">{m.authorized_apps_confirm_title()}</h3>
      <p class="text-ink-muted text-sm mb-4">{m.authorized_apps_confirm_msg({ name: confirmRevoke.name })}</p>
      <div class="flex gap-3">
        <Button variant="secondary" size="md" class="flex-1" disabled={revoking} onclick={() => (confirmRevoke = null)}>{m.common_cancel()}</Button>
        <Button variant="danger" size="md" class="flex-1" loading={revoking} onclick={() => handleRevoke(confirmRevoke!)}>
          <TriangleAlert class="w-4 h-4" aria-hidden="true" />
          {m.authorized_apps_revoke()}
        </Button>
      </div>
    </div>
  </div>
{/if}
