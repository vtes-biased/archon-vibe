<script lang="ts">
  import '../app.css';
  import { page } from '$app/stores';
  import { syncManager } from '$lib/sync';
  import { initAuth } from '$lib/stores/auth.svelte';
  import { initEngine } from '$lib/engine';
  import { engineLoadFailed } from '$lib/stores/engine-ready.svelte';
  import { initServiceWorker, getUpdateAvailable, applyUpdate } from '$lib/stores/sw.svelte';
  import { initOfflineState } from '$lib/stores/offline.svelte';
  import { onMount } from 'svelte';
  import { Wifi, WifiOff, RefreshCw, Download, TriangleAlert, Trophy, BarChart3, Medal, Users, User, BookOpen } from '@lucide/svelte';
  import Toast from '$lib/components/Toast.svelte';
  import * as m from '$lib/paraglide/messages.js';
  import { getLocale } from '$lib/paraglide/runtime.js';
  import { initTheme } from '$lib/stores/theme.svelte';

  let { children } = $props();

  // Connection status
  let isOnline = $state(navigator.onLine);
  let isSyncing = $state(true);
  let syncError = $state(false);

  // Manual recovery from a terminal sync failure (the auto-retry gives up after a
  // few attempts) — the banner exposes this so the user isn't stuck on stale data.
  function reconnectSync() {
    syncError = false;
    isSyncing = true;
    syncManager.connect();
  }

  // Navigation items - fixed 6 items, no conditional developer
  const navItems = [
    { href: '/tournaments', labelFn: () => m.nav_tournaments(), icon: 'trophy' },
    { href: '/leagues', labelFn: () => m.nav_leagues(), icon: 'chart' },
    { href: '/rankings', labelFn: () => m.nav_rankings(), icon: 'ranking' },
    { href: '/users', labelFn: () => m.nav_community(), icon: 'users' },
    { href: '/help', labelFn: () => m.nav_help(), icon: 'help' },
    { href: '/profile', labelFn: () => m.nav_profile(), icon: 'user' },
  ];

  function isActive(href: string, currentPath: string): boolean {
    if (href === '/') return currentPath === '/';
    return currentPath.startsWith(href);
  }

  // Keep <html lang> in sync with locale
  $effect(() => {
    document.documentElement.lang = getLocale();
  });

  onMount(() => {
    // Initialize theme (sync .light class with preference)
    initTheme();

    // Initialize service worker for offline asset caching
    initServiceWorker();

    // Initialize engine (WASM) for permission checks
    initEngine().catch(err => console.error('Failed to initialize engine:', err));

    // Initialize auth state, then connect SSE with valid token
    initAuth().then(() => syncManager.connect());

    // Restore offline tournament state from IndexedDB
    initOfflineState().catch(err => console.error('Failed to init offline state:', err));

    // Listen for sync events
    const handleSyncEvent = (event: { type: string; error?: string }) => {
      if (event.type === 'syncing') {
        isSyncing = true;
        syncError = false;
      } else if (event.type === 'connected') {
        syncError = false;
      } else if (event.type === 'sync_complete') {
        isSyncing = false;
      } else if (event.type === 'error') {
        // Keep the raw reason in the console for diagnostics; the user sees a
        // localized banner with a manual Reconnect instead of raw error text.
        if (event.error) console.error('Sync error:', event.error);
        syncError = true;
        isSyncing = false;
      } else if (event.type === 'disconnected') {
        isSyncing = false;
      }
    };

    syncManager.addEventListener(handleSyncEvent);

    const handleOnline = () => {
      isOnline = true;
      syncManager.connect();
    };
    const handleOffline = () => {
      isOnline = false;
    };

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    return () => {
      syncManager.removeEventListener(handleSyncEvent);
      syncManager.disconnect();
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  });
</script>

{#snippet navIcon(icon: string, size: string)}
  {#if icon === 'trophy'}
    <Trophy class={size} />
  {:else if icon === 'chart'}
    <BarChart3 class={size} />
  {:else if icon === 'ranking'}
    <Medal class={size} />
  {:else if icon === 'users'}
    <Users class={size} />
  {:else if icon === 'help'}
    <BookOpen class={size} />
  {:else if icon === 'user'}
    <User class={size} />
  {/if}
{/snippet}

<div class="min-h-screen bg-surface pb-16 sm:pb-0">
  <!-- Status/update banners: a normal-flow sticky stack so they push content
       down instead of overlaying the page header; multiple banners stack as
       block siblings (no hard-coded per-banner top offsets). -->
  {#if engineLoadFailed() || !isOnline || syncError || getUpdateAvailable()}
    <div class="sticky top-0 z-50">
      <!-- A WASM engine load failure degrades the app (permission checks,
           optimistic writes and standings stop working): a durable banner, not
           a transient toast, since the state persists until reload. -->
      {#if engineLoadFailed()}
        <div role="alert" class="px-4 py-2 text-center text-sm bg-accent-strong text-white">
          <span class="inline-flex items-center gap-2 flex-wrap justify-center">
            <TriangleAlert class="w-4 h-4 shrink-0" aria-hidden="true" />
            {m.engine_load_error()}
            <button onclick={() => location.reload()} class="underline hover:no-underline font-medium">{m.update_refresh()}</button>
          </span>
        </div>
      {/if}
      {#if !isOnline || syncError}
        <div class="px-4 py-2 text-center text-sm {!isOnline ? 'status-offline' : 'bg-accent-soft/90 text-link-soft'}">
          {#if !isOnline}
            <span class="inline-flex items-center gap-2">
              <WifiOff class="w-4 h-4" />
              {m.status_offline_banner()}
            </span>
          {:else if syncError}
            <span class="inline-flex items-center gap-2">
              {m.sync_error_disconnected()}
              <button onclick={reconnectSync} class="underline hover:no-underline font-medium">{m.sync_reconnect()}</button>
            </span>
          {/if}
        </div>
      {/if}

      {#if getUpdateAvailable()}
        <div class="px-4 py-2 text-center text-sm status-update">
          <span class="inline-flex items-center gap-2">
            <Download class="w-4 h-4" />
            {m.update_available()}
            <button onclick={applyUpdate} class="ml-2 underline hover:no-underline font-medium">{m.update_refresh()}</button>
          </span>
        </div>
      {/if}
    </div>
  {/if}

  <!-- Main content -->
  <main class="sm:ml-20">
    {@render children()}
  </main>

  <!-- Bottom navigation (mobile) — icon-only: visible labels truncated to
       ambiguity in longer locales (es/pt), so the destination name lives in
       aria-label/title (announced by AT, shown on hover) instead. -->
  <nav class="fixed bottom-0 left-0 right-0 z-40 bg-surface-card border-t border-line sm:hidden">
    <div class="flex justify-around">
      {#each navItems as item}
        {@const active = isActive(item.href, $page.url.pathname)}
        <a
          href={item.href}
          aria-label={item.labelFn()}
          aria-current={active ? 'page' : undefined}
          title={item.labelFn()}
          class="flex items-center justify-center py-3 px-1 flex-1 border-t-2 {active ? 'border-link text-link' : 'border-transparent text-ink-muted hover:text-ink-bright'}"
        >
          {@render navIcon(item.icon, 'w-6 h-6')}
        </a>
      {/each}
    </div>
  </nav>

  <!-- Side navigation (desktop) -->
  <nav class="hidden sm:flex fixed left-0 top-0 bottom-0 w-20 bg-surface-card border-r border-line flex-col items-center py-4 z-40">
    <!-- Logo -->
    <a href="/tournaments" class="mb-6 text-link hover:text-link-soft" title={m.nav_home()}>
      <img src="/favicon.svg" alt="Archon" class="w-16 h-16" />
    </a>

    <div class="flex-1 flex flex-col gap-2">
      {#each navItems as item}
        {@const active = isActive(item.href, $page.url.pathname)}
        <a
          href={item.href}
          class="flex flex-col items-center py-3 px-2 rounded-lg transition-colors {active ? 'bg-accent-soft/50 text-link' : 'text-ink-muted hover:text-ink-bright hover:bg-surface-hover/50'}"
          title={item.labelFn()}
        >
          {@render navIcon(item.icon, 'w-6 h-6')}
          <span class="text-xs mt-1">{item.labelFn()}</span>
        </a>
      {/each}
    </div>

    <!-- Connection status indicator -->
    <div class="mt-auto pt-4">
      <div class="flex flex-col items-center gap-1">
        {#if !isOnline}
          <WifiOff class="w-4 h-4 text-link" aria-hidden="true" />
        {:else if isSyncing}
          <RefreshCw class="w-4 h-4 text-warn animate-spin motion-reduce:animate-none" aria-hidden="true" />
        {:else}
          <Wifi class="w-4 h-4 text-info" aria-hidden="true" />
        {/if}
        <span class="text-[10px] text-ink-faint">{isOnline ? (isSyncing ? m.status_syncing() : m.status_online()) : m.status_offline()}</span>
      </div>
    </div>
  </nav>

  <!-- Global toast notifications -->
  <Toast />
</div>
