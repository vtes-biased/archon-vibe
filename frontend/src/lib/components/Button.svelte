<script lang="ts">
  import { Loader2 } from "@lucide/svelte";
  import type { Snippet } from 'svelte';

  // Owns disabled + loading so call-sites never hand-roll those states. Focus comes from the global
  // :focus-visible ring — never add a bespoke outline.
  let {
    variant = 'secondary',
    size = 'md',
    block = false,
    loading = false,
    disabled = false,
    type = 'button',
    class: extra = '',
    children,
    ...rest
  }: {
    variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
    size?: 'sm' | 'md' | 'lg';
    block?: boolean;
    loading?: boolean;
    disabled?: boolean;
    type?: 'button' | 'submit';
    class?: string;
    children?: Snippet;
    [key: string]: unknown;
  } = $props();

  // btn-danger is its own light-dark() class (violet is off-palette) with an inert :disabled — a tier
  // below the enabled bg, so disabled never reads as active.
  const VARIANT: Record<string, string> = {
    primary:   'bg-accent-strong enabled:hover:bg-accent-strong-hover text-white disabled:bg-surface-muted disabled:text-ink-faint',
    danger:    'btn-danger',
    secondary: 'bg-surface-hover enabled:hover:bg-surface-active text-ink-bright disabled:bg-surface-muted disabled:text-ink-faint',
    ghost:     'border border-line-strong text-ink enabled:hover:bg-surface-hover/50 enabled:hover:text-ink-strong disabled:bg-surface-muted disabled:text-ink-faint disabled:border-transparent',
  };
  const SIZE: Record<string, string> = {
    sm: 'px-2 py-1 text-xs gap-1',
    md: 'px-3 py-1.5 text-sm gap-1.5',
    lg: 'px-4 py-2 text-sm font-medium gap-2',
  };
  const SPIN: Record<string, string> = { sm: 'w-3.5 h-3.5', md: 'w-4 h-4', lg: 'w-4 h-4' };
</script>

<button
  {type}
  disabled={disabled || loading}
  aria-busy={loading}
  class="inline-flex items-center justify-center rounded-lg transition-colors {SIZE[size]} {VARIANT[variant]} {block ? 'w-full' : ''} {extra}"
  {...rest}
>
  {#if loading}<Loader2 class="animate-spin {SPIN[size]}" aria-hidden="true" />{/if}
  {@render children?.()}
</button>
