<script lang="ts">
  import '../app.css';
  import { page } from '$app/stores';
  import { openLastView } from '$lib/last-view';
  import { syncManager } from '$lib/sync';
  import { initAuth } from '$lib/stores/auth.svelte';
  import { initEngine } from '$lib/engine-instance';
  import { initServiceWorker, getUpdateAvailable, applyUpdate } from '$lib/stores/sw.svelte';
  import { initOfflineState, getOfflineTournamentUids } from '$lib/stores/offline.svelte';
  import { reconcilePush } from '$lib/stores/push.svelte';
  import { onMount } from 'svelte';
  import { Wifi, WifiOff, RefreshCw, Download, TriangleAlert, Trophy, BarChart3, Medal, Users, User, BookOpen } from '@lucide/svelte';
  import Toast from '$lib/components/Toast.svelte';
  import WhatsNewModal from '$lib/components/WhatsNewModal.svelte';
  import * as m from '$lib/paraglide/messages.js';
  import { getLocale } from '$lib/paraglide/runtime.js';
  import { initTheme } from '$lib/stores/theme.svelte';

  let { children } = $props();

  // Not onMount: that delays the fetch by a full mount cycle.
  const engineInit = initEngine();

  let isOnline = $state(navigator.onLine);
  let isSyncing = $state(true);
  let syncError = $state(false);
  let streamLost = $state(false);
  let streamDown = $derived(!isOnline || streamLost);
  // Suppressed while offline-locked (mid-event refresh is the wrong nudge);
  // tracked in state and refreshed on sync events since the getter isn't reactive.
  let hasOfflineLocked = $state(false);

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

  $effect(() => {
    document.documentElement.lang = getLocale();
  });

  onMount(() => {
    initTheme();
    initServiceWorker();

    initAuth().then(() => {
      syncManager.connect();
      // Lazy-reconcile the push subscription once authed (#314): re-register a
      // subscription the SW rotated/re-created while the app was closed.
      reconcilePush();
    });

    initOfflineState()
      .then(() => { hasOfflineLocked = getOfflineTournamentUids().size > 0; })
      .catch(err => console.error('Failed to init offline state:', err));

    const handleSyncEvent = (event: { type: string; error?: string }) => {
      hasOfflineLocked = getOfflineTournamentUids().size > 0;
      if (event.type === 'syncing') {
        isSyncing = true;
      } else if (event.type === 'connected') {
        streamLost = false;
      } else if (event.type === 'sync_complete') {
        syncError = false;
        isSyncing = false;
      } else if (event.type === 'error') {
        // Keep the raw reason in the console for diagnostics; the user sees a
        // localized banner with a manual Reconnect instead of raw error text.
        if (event.error) console.error('Sync error:', event.error);
        syncError = true;
        isSyncing = false;
      } else if (event.type === 'disconnected') {
        streamLost = true;
        isSyncing = false;
      }
    };

    syncManager.addEventListener(handleSyncEvent);

    // Debounced clear only: flapping venue wifi strobes online/offline, so offline
    // shows immediately but the banner clears after a few stable seconds.
    let onlineStableTimer: ReturnType<typeof setTimeout> | undefined;
    const handleOnline = () => {
      syncManager.connect();
      clearTimeout(onlineStableTimer);
      onlineStableTimer = setTimeout(() => {
        isOnline = true;
      }, 4000);
    };
    const handleOffline = () => {
      clearTimeout(onlineStableTimer);
      isOnline = false;
    };

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    return () => {
      syncManager.removeEventListener(handleSyncEvent);
      syncManager.disconnect();
      clearTimeout(onlineStableTimer);
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

<!-- dvh, not vh: on iOS 100vh is the LARGE viewport (bar hidden), so the shell
     overflows and leaves dead scroll under the fixed nav. -->
<div class="min-h-dvh bg-surface pt-safe-t pb-navbar sm:pb-safe-b">
  <!-- Sticky stack, not overlay, so banners push content down and stack as block
       siblings; sticks at safe-t, not 0, or a stuck banner slides under the
       status bar in the installed PWA. -->
  {#if !isOnline || syncError || (getUpdateAvailable() && !hasOfflineLocked)}
    <div class="sticky top-safe-t z-50">
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
              <button onclick={() => syncManager.connect()} class="underline hover:no-underline font-medium">{m.sync_reconnect()}</button>
            </span>
          {/if}
        </div>
      {/if}

      {#if getUpdateAvailable() && !hasOfflineLocked}
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

  <!-- pr-safe-r clears the notch when the phone is held camera-right; the left
       side is already cleared by the rail's width. -->
  <main class="sm:ml-rail pr-safe-r">
    {#await engineInit}
      <div class="flex items-center justify-center py-24 text-sm text-ink-muted">{m.common_loading()}</div>
    {:then}
      {@render children()}
    {:catch}
      <div role="alert" class="flex flex-col items-center gap-4 py-24 px-4 text-center">
        <TriangleAlert class="w-8 h-8 text-accent-strong" aria-hidden="true" />
        <p class="text-sm text-ink-muted max-w-sm">{m.engine_load_error()}</p>
        <button onclick={() => location.reload()} class="underline hover:no-underline font-medium text-link">{m.update_refresh()}</button>
      </div>
    {/await}
  </main>

  <!-- h-navbar is declared, not emergent, or a gap shows between the CTA and the
       nav; transform-gpu is a scroll-compositing win, not a WebKit 297779 fix. -->
  <nav class="fixed bottom-0 left-0 right-0 z-40 h-navbar pb-safe-b transform-gpu bg-surface-card border-t border-line sm:hidden">
    <div class="flex h-full justify-around">
      {#each navItems as item}
        {@const active = isActive(item.href, $page.url.pathname)}
        <!-- Icon-only: labels truncate to ambiguity in longer locales (es/pt),
             so the destination name lives in aria-label/title. -->
        <a
          href={item.href}
          onclick={(e) => openLastView(e, item.href)}
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

  <!-- The rail absorbs three insets under viewport-fit=cover: py-4 grows for
       top/bottom (iPad standalone), w-rail+pl-safe-l keeps icons off the notch
       on landscape phones (>=640px, so rail not bottom nav). -->
  <nav class="hidden sm:flex fixed left-0 top-0 bottom-0 w-rail pl-safe-l bg-surface-card border-r border-line flex-col items-center pt-[calc(1rem+var(--spacing-safe-t))] pb-[calc(1rem+var(--spacing-safe-b))] z-40">
    <a href="/tournaments" onclick={(e) => openLastView(e, '/tournaments')} class="mb-6 text-link hover:text-link-soft" title={m.nav_home()}>
      <img src="/favicon.svg" alt="Archon" class="w-16 h-16" />
    </a>

    <div class="flex-1 flex flex-col gap-2 w-full">
      {#each navItems as item}
        {@const active = isActive(item.href, $page.url.pathname)}
        <a
          href={item.href}
          onclick={(e) => openLastView(e, item.href)}
          class="flex flex-col items-center py-3 px-2 rounded-lg transition-colors {active ? 'bg-accent-soft/50 text-link' : 'text-ink-muted hover:text-ink-bright hover:bg-surface-hover/50'}"
          title={item.labelFn()}
        >
          {@render navIcon(item.icon, 'w-6 h-6')}
          <span class="text-xs mt-1">{item.labelFn()}</span>
        </a>
      {/each}
    </div>

    <div class="mt-auto pt-4">
      <!-- data-sync-state is a stable, color-independent hook for E2E (the visual
           cue is icon + semantic color, which a design refactor can freely change). -->
      <div
        class="flex flex-col items-center gap-1"
        data-sync-state={streamDown ? 'offline' : isSyncing ? 'syncing' : 'synced'}
      >
        {#if streamDown}
          <WifiOff class="w-4 h-4 text-link" aria-hidden="true" />
        {:else if isSyncing}
          <RefreshCw class="w-4 h-4 text-warn animate-spin motion-reduce:animate-none" aria-hidden="true" />
        {:else}
          <Wifi class="w-4 h-4 text-info" aria-hidden="true" />
        {/if}
        <span class="text-[10px] text-ink-faint">{streamDown ? m.status_offline() : isSyncing ? m.status_syncing() : m.status_online()}</span>
      </div>
    </div>
  </nav>

  <!-- Paints bg-surface over the strip pt-safe-t only reserves (content scrolls
       through it otherwise). z-45: above the page's sticky surfaces, below modals
       (z-50) and the lightbox (z-60), which paint their own colour. -->
  <div aria-hidden="true" class="fixed top-0 left-0 right-0 sm:left-rail h-safe-t z-[45] bg-surface pointer-events-none"></div>

  <Toast />
  <WhatsNewModal />
</div>
