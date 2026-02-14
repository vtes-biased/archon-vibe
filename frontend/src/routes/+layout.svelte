<script lang="ts">
  import '../app.css';
  import { page } from '$app/stores';
  import { syncManager } from '$lib/sync';
  import { initAuth, hasAnyRole } from '$lib/stores/auth.svelte';
  import { initEngine } from '$lib/engine';
  import { onMount } from 'svelte';
  import Icon from '@iconify/svelte';
  import Toast from '$lib/components/Toast.svelte';

  let { children } = $props();

  // Connection status
  let isOnline = $state(navigator.onLine);
  let isSyncing = $state(true);
  let syncError = $state<string | null>(null);

  // Navigation items
  const baseNavItems = [
    { href: '/tournaments', label: 'Tournaments', icon: 'trophy' },
    { href: '/leagues', label: 'Leagues', icon: 'chart' },
    { href: '/rankings', label: 'Rankings', icon: 'ranking' },
    { href: '/users', label: 'Users', icon: 'users' },
    { href: '/profile', label: 'Profile', icon: 'user' },
  ];
  const navItems = $derived(
    hasAnyRole('DEV', 'IC')
      ? [...baseNavItems, { href: '/developer', label: 'Developer', icon: 'code' }]
      : baseNavItems
  );

  function isActive(href: string, currentPath: string): boolean {
    if (href === '/') return currentPath === '/';
    return currentPath.startsWith(href);
  }

  onMount(() => {
    // Initialize engine (WASM) for permission checks
    initEngine().catch(err => console.error('Failed to initialize engine:', err));

    // Initialize auth state
    initAuth();

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
          Offline - Changes will sync when reconnected
        </span>
      {:else if syncError}
        <span>{syncError}</span>
      {/if}
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
          <span class="text-xs mt-1">{item.label}</span>
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
          title={item.label}
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
          <span class="text-xs mt-1">{item.label}</span>
        </a>
      {/each}
    </div>

    <!-- Connection status indicator -->
    <div class="mt-auto pt-4">
      <div class="flex flex-col items-center gap-1">
        <div class="w-3 h-3 rounded-full {isOnline ? (isSyncing ? 'bg-amber-500 animate-pulse' : 'bg-emerald-500') : 'bg-crimson-500'}"></div>
        <span class="text-[10px] text-ash-500">{isOnline ? (isSyncing ? 'Syncing' : 'Online') : 'Offline'}</span>
      </div>
    </div>
  </nav>

  <!-- Global toast notifications -->
  <Toast />
</div>
