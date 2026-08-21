<script lang="ts">
  import { getToasts, dismissToast, type Toast } from '$lib/stores/toast.svelte';
  import { CircleCheck, CircleX, TriangleAlert, Info, X } from '@lucide/svelte';
  import * as m from '$lib/paraglide/messages.js';

  const toasts = $derived(getToasts());

  const variants: Record<Toast['type'], { icon: typeof CircleCheck; box: string; tint: string }> = {
    success: { icon: CircleCheck, box: 'toast-success', tint: 'text-info' },
    error: { icon: CircleX, box: 'toast-error', tint: 'text-link' },
    warning: { icon: TriangleAlert, box: 'toast-warn', tint: 'text-warn' },
    info: { icon: Info, box: 'toast-info', tint: 'text-info' },
  };
</script>

<div
  class="fixed top-14 mt-safe-t left-4 ml-safe-l right-4 mr-safe-r z-[100] flex flex-col items-end gap-2 pointer-events-none"
>
  {#each toasts as toast (toast.id)}
    {@const variant = variants[toast.type]}
    {@const ToastIcon = variant.icon}
    <div
      class="pointer-events-auto w-full max-w-sm flex items-start gap-3 p-4 rounded-lg border shadow-lg backdrop-blur-sm animate-slide-in {variant.box}"
      role="alert"
    >
      <ToastIcon class="w-5 h-5 flex-shrink-0 mt-0.5 {variant.tint}" />
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
        aria-label={m.toast_dismiss()}
      >
        <X class="w-4 h-4" />
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
