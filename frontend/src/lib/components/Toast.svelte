<script lang="ts">
  import { getToasts, dismissToast, type Toast } from '$lib/stores/toast.svelte';
  import Icon from '@iconify/svelte';

  const toasts = $derived(getToasts());

  function getIcon(type: Toast['type']): string {
    switch (type) {
      case 'success':
        return 'lucide:check-circle';
      case 'error':
        return 'lucide:x-circle';
      case 'warning':
        return 'lucide:alert-triangle';
      case 'info':
        return 'lucide:info';
    }
  }

  function getStyles(type: Toast['type']): string {
    switch (type) {
      case 'success':
        return 'bg-emerald-900/90 border-emerald-700 text-emerald-100';
      case 'error':
        return 'bg-crimson-900/90 border-crimson-700 text-crimson-100';
      case 'warning':
        return 'bg-amber-900/90 border-amber-700 text-amber-100';
      case 'info':
        return 'bg-dusk-900/90 border-ash-600 text-bone-100';
    }
  }

  function getIconColor(type: Toast['type']): string {
    switch (type) {
      case 'success':
        return 'text-emerald-400';
      case 'error':
        return 'text-crimson-400';
      case 'warning':
        return 'text-amber-400';
      case 'info':
        return 'text-ash-300';
    }
  }
</script>

<!-- Toast Container -->
<div class="fixed top-14 right-4 z-[100] flex flex-col gap-2 max-w-sm w-full pointer-events-none">
  {#each toasts as toast (toast.id)}
    <div
      class="pointer-events-auto flex items-start gap-3 p-4 rounded-lg border shadow-lg backdrop-blur-sm animate-slide-in {getStyles(toast.type)}"
      role="alert"
    >
      <Icon icon={getIcon(toast.type)} class="w-5 h-5 flex-shrink-0 mt-0.5 {getIconColor(toast.type)}" />
      <div class="flex-1 min-w-0">
        <p class="text-sm font-medium">{toast.message}</p>
        {#if toast.action}
          <button
            onclick={() => {
              toast.action?.onClick();
              dismissToast(toast.id);
            }}
            class="mt-2 text-sm font-medium underline hover:no-underline"
          >
            {toast.action.label}
          </button>
        {/if}
      </div>
      <button
        onclick={() => dismissToast(toast.id)}
        class="flex-shrink-0 p-1 -m-1 rounded hover:bg-white/10 transition-colors"
        aria-label="Dismiss"
      >
        <Icon icon="lucide:x" class="w-4 h-4" />
      </button>
    </div>
  {/each}
</div>

<style>
  @keyframes slide-in {
    from {
      transform: translateX(100%);
      opacity: 0;
    }
    to {
      transform: translateX(0);
      opacity: 1;
    }
  }

  .animate-slide-in {
    animation: slide-in 0.2s ease-out;
  }

  @media (prefers-reduced-motion: reduce) {
    .animate-slide-in {
      animation: none;
    }
  }
</style>
