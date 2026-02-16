<script lang="ts">
  import '../app.css';
  import { page } from '$app/stores';
  import { syncManager } from '$lib/sync';
  import { initAuth, hasAnyRole } from '$lib/stores/auth.svelte';
  import { initEngine } from '$lib/engine';
  import { initServiceWorker, getUpdateAvailable, applyUpdate } from '$lib/stores/sw.svelte';
  import { initOfflineState } from '$lib/stores/offline.svelte';
  import { onMount } from 'svelte';
  import Icon from '@iconify/svelte';
  import Toast from '$lib/components/Toast.svelte';
  import * as m from '$lib/paraglide/messages.js';
  import { getLocale } from '$lib/paraglide/runtime.js';
  import LocaleSwitcher from '$lib/components/LocaleSwitcher.svelte';
  import { getTheme, cycleTheme, initTheme } from '$lib/stores/theme.svelte';

  let { children } = $props();

  // Connection status
  let isOnline = $state(navigator.onLine);
  let isSyncing = $state(true);
  let syncError = $state<string | null>(null);

  // Navigation items - use message keys, resolve labels reactively
  const baseNavItems = [
    { href: '/tournaments', labelFn: () => m.nav_tournaments(), icon: 'trophy' },
    { href: '/leagues', labelFn: () => m.nav_leagues(), icon: 'chart' },
    { href: '/rankings', labelFn: () => m.nav_rankings(), icon: 'ranking' },
    { href: '/users', labelFn: () => m.nav_users(), icon: 'users' },
    { href: '/profile', labelFn: () => m.nav_profile(), icon: 'user' },
  ];
  const navItems = $derived(
    hasAnyRole('DEV', 'IC')
      ? [...baseNavItems, { href: '/developer', labelFn: () => m.nav_developer(), icon: 'code' }]
      : baseNavItems
  );

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

    // Initialize auth state
    initAuth();

    // Restore offline tournament state from IndexedDB
    initOfflineState().catch(err => console.error('Failed to init offline state:', err));

    // Connect to SSE stream
    syncManager.connect();

    // Listen for sync events
    const handleSyncEvent = (event: { type: string; error?: string }) => {
      if (event.type === 'connected') {
        syncError = null;
      } else if (event.type === 'sync_complete') {
        isSyncing = false;
      } else if (event.type === 'error') {
        syncError = event.error || 'Sync error occurred';
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

<div class="min-h-screen bg-bone-950 pb-16 sm:pb-0">
  <!-- Status bar (shows sync/offline status) -->
  {#if !isOnline || syncError}
    <div class="fixed top-0 left-0 right-0 z-50 px-4 py-2 text-center text-sm {!isOnline ? 'bg-amber-900/90 text-amber-100' : 'bg-crimson-900/90 text-crimson-100'}">
      {#if !isOnline}
        <span class="inline-flex items-center gap-2">
          <Icon icon="lucide:wifi-off" class="w-4 h-4" />
          {m.status_offline_banner()}
        </span>
      {:else if syncError}
        <span>{syncError}</span>
      {/if}
    </div>
  {/if}

  <!-- Update available banner -->
  {#if getUpdateAvailable()}
    <div class="fixed top-0 left-0 right-0 z-50 px-4 py-2 text-center text-sm bg-indigo-900/90 text-indigo-100" class:top-10={!isOnline || syncError}>
      <span class="inline-flex items-center gap-2">
        <Icon icon="lucide:download" class="w-4 h-4" />
        {m.update_available()}
        <button onclick={applyUpdate} class="ml-2 underline hover:no-underline font-medium">{m.update_refresh()}</button>
      </span>
    </div>
  {/if}

  <!-- Main content -->
  <main class="sm:ml-20">
    {@render children()}
  </main>

  <!-- Bottom navigation (mobile) -->
  <nav class="fixed bottom-0 left-0 right-0 z-40 bg-dusk-950 border-t border-ash-800 sm:hidden">
    <div class="flex justify-around">
      {#each navItems as item}
        {@const active = isActive(item.href, $page.url.pathname)}
        <a
          href={item.href}
          class="flex flex-col items-center py-3 px-3 min-w-[64px] {active ? 'text-crimson-500' : 'text-ash-400 hover:text-ash-200'}"
        >
          {#if item.icon === 'trophy'}
            <Icon icon="lucide:trophy" class="w-6 h-6" />
          {:else if item.icon === 'chart'}
            <Icon icon="lucide:bar-chart-3" class="w-6 h-6" />
          {:else if item.icon === 'ranking'}
            <Icon icon="lucide:medal" class="w-6 h-6" />
          {:else if item.icon === 'users'}
            <Icon icon="lucide:users" class="w-6 h-6" />
          {:else if item.icon === 'user'}
            <Icon icon="lucide:user" class="w-6 h-6" />
          {:else if item.icon === 'code'}
            <Icon icon="lucide:code-2" class="w-6 h-6" />
          {/if}
          <span class="text-xs mt-1">{item.labelFn()}</span>
        </a>
      {/each}
      <button
        onclick={cycleTheme}
        class="flex flex-col items-center py-3 px-3 min-w-[64px] text-ash-400 hover:text-ash-200"
      >
        {#if getTheme() === 'system'}
          <Icon icon="lucide:monitor" class="w-6 h-6" />
        {:else if getTheme() === 'light'}
          <Icon icon="lucide:sun" class="w-6 h-6" />
        {:else}
          <Icon icon="lucide:moon" class="w-6 h-6" />
        {/if}
        <span class="text-xs mt-1">
          {#if getTheme() === 'system'}{m.theme_system()}{:else if getTheme() === 'light'}{m.theme_light()}{:else}{m.theme_dark()}{/if}
        </span>
      </button>
    </div>
  </nav>

  <!-- Side navigation (desktop) -->
  <nav class="hidden sm:flex fixed left-0 top-0 bottom-0 w-20 bg-dusk-950 border-r border-ash-800 flex-col items-center py-4 z-40">
    <!-- Logo -->
    <a href="/tournaments" class="mb-6 text-crimson-500 hover:text-crimson-400" title="Home">
      <img src="/favicon.svg" alt="Archon" class="w-16 h-16" />
    </a>

    <div class="flex-1 flex flex-col gap-2">
      {#each navItems as item}
        {@const active = isActive(item.href, $page.url.pathname)}
        <a
          href={item.href}
          class="flex flex-col items-center py-3 px-2 rounded-lg transition-colors {active ? 'bg-crimson-900/50 text-crimson-400' : 'text-ash-400 hover:text-ash-200 hover:bg-ash-800/50'}"
          title={item.labelFn()}
        >
          {#if item.icon === 'trophy'}
            <Icon icon="lucide:trophy" class="w-6 h-6" />
          {:else if item.icon === 'chart'}
            <Icon icon="lucide:bar-chart-3" class="w-6 h-6" />
          {:else if item.icon === 'ranking'}
            <Icon icon="lucide:medal" class="w-6 h-6" />
          {:else if item.icon === 'users'}
            <Icon icon="lucide:users" class="w-6 h-6" />
          {:else if item.icon === 'user'}
            <Icon icon="lucide:user" class="w-6 h-6" />
          {:else if item.icon === 'code'}
            <Icon icon="lucide:code-2" class="w-6 h-6" />
          {/if}
          <span class="text-xs mt-1">{item.labelFn()}</span>
        </a>
      {/each}
    </div>

    <!-- Theme toggle -->
    <div class="mt-auto pt-4">
      <button
        onclick={cycleTheme}
        class="flex flex-col items-center text-ash-400 hover:text-ash-200 transition-colors"
        title={getTheme() === 'system' ? 'System theme' : getTheme() === 'light' ? 'Light theme' : 'Dark theme'}
      >
        {#if getTheme() === 'system'}
          <Icon icon="lucide:monitor" class="w-5 h-5" />
        {:else if getTheme() === 'light'}
          <Icon icon="lucide:sun" class="w-5 h-5" />
        {:else}
          <Icon icon="lucide:moon" class="w-5 h-5" />
        {/if}
      </button>
    </div>

    <!-- Locale switcher -->
    <div class="pt-2">
      <LocaleSwitcher />
    </div>

    <!-- Connection status indicator -->
    <div class="pt-2">
      <div class="flex flex-col items-center gap-1">
        <div class="w-3 h-3 rounded-full {isOnline ? (isSyncing ? 'bg-amber-500 animate-pulse' : 'bg-emerald-500') : 'bg-crimson-500'}"></div>
        <span class="text-[10px] text-ash-500">{isOnline ? (isSyncing ? m.status_syncing() : m.status_online()) : m.status_offline()}</span>
      </div>
    </div>
  </nav>

  <!-- Global toast notifications -->
  <Toast />
</div>
