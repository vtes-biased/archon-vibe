<script lang="ts">
  import '../app.css';
  import { page } from '$app/stores';
  import { syncManager } from '$lib/sync';
  import { initAuth } from '$lib/stores/auth.svelte';
  import { initEngine } from '$lib/engine';
  import { initServiceWorker, getUpdateAvailable, applyUpdate } from '$lib/stores/sw.svelte';
  import { initOfflineState } from '$lib/stores/offline.svelte';
  import { onMount } from 'svelte';
  import { WifiOff, Download, Trophy, BarChart3, Medal, Users, User, BookOpen } from 'lucide-svelte';
  import Toast from '$lib/components/Toast.svelte';
  import * as m from '$lib/paraglide/messages.js';
  import { getLocale } from '$lib/paraglide/runtime.js';
  import { initTheme } from '$lib/stores/theme.svelte';

  let { children } = $props();

  // Connection status
  let isOnline = $state(navigator.onLine);
  let isSyncing = $state(true);
  let syncError = $state<string | null>(null);

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

<div class="min-h-screen bg-bone-950 pb-16 sm:pb-0">
  <!-- Status bar (shows sync/offline status) -->
  {#if !isOnline || syncError}
    <div class="fixed top-0 left-0 right-0 z-50 px-4 py-2 text-center text-sm {!isOnline ? 'status-offline' : 'bg-crimson-900/90 text-crimson-100'}">
      {#if !isOnline}
        <span class="inline-flex items-center gap-2">
          <WifiOff class="w-4 h-4" />
          {m.status_offline_banner()}
        </span>
      {:else if syncError}
        <span>{syncError}</span>
      {/if}
    </div>
  {/if}

  <!-- Update available banner -->
  {#if getUpdateAvailable()}
    <div class="fixed top-0 left-0 right-0 z-50 px-4 py-2 text-center text-sm status-update" class:top-10={!isOnline || syncError}>
      <span class="inline-flex items-center gap-2">
        <Download class="w-4 h-4" />
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
          class="flex flex-col items-center py-2 px-1 min-w-0 flex-1 {active ? 'text-crimson-500' : 'text-ash-400 hover:text-ash-200'}"
        >
          {@render navIcon(item.icon, 'w-5 h-5')}
          <span class="text-[10px] mt-0.5 truncate">{item.labelFn()}</span>
        </a>
      {/each}
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
          {@render navIcon(item.icon, 'w-6 h-6')}
          <span class="text-xs mt-1">{item.labelFn()}</span>
        </a>
      {/each}
    </div>

    <!-- Connection status indicator -->
    <div class="mt-auto pt-4">
      <div class="flex flex-col items-center gap-1">
        <div class="w-3 h-3 rounded-full {isOnline ? (isSyncing ? 'bg-amber-500 animate-pulse' : 'bg-emerald-500') : 'bg-crimson-500'}"></div>
        <span class="text-[10px] text-ash-500">{isOnline ? (isSyncing ? m.status_syncing() : m.status_online()) : m.status_offline()}</span>
      </div>
    </div>
  </nav>

  <!-- Global toast notifications -->
  <Toast />
</div>
