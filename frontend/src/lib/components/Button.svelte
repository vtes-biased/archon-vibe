<script lang="ts">
  import { Loader2 } from "@lucide/svelte";
  import type { Snippet } from 'svelte';

  // One action button for the whole app. variant = colour/intent, size = density.
  // Owns disabled + loading so call-sites never hand-roll those states (the old
  // three-tier disabled rule collapses into the single `disabled:` block below).
  // Focus comes from the global :focus-visible ring — never add a bespoke outline.
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

  // Crimson is the brand colour AND the single positive-CTA colour: every
  // affirmative action (lifecycle CTA + form/auth submit) is `primary`.
  // Danger is a distinct VIOLET, never red — red and crimson are the same hue
  // family and collapse together (even under colourblindness), so destructive
  // actions get their own hue plus an icon/verb at the call-site. The crimson
  // and ash variants are scale-inverted (adapt to light mode directly); btn-danger
  // carries its own html.light override (violet has no inversion) and an inert
  // :disabled (a tier below the enabled bg, so disabled never reads as active).
  const VARIANT: Record<string, string> = {
    primary:   'bg-crimson-700 enabled:hover:bg-crimson-600 text-white disabled:bg-ash-900 disabled:text-ash-500',
    danger:    'btn-danger',
    secondary: 'bg-ash-800 enabled:hover:bg-ash-700 text-ash-200 disabled:bg-ash-900 disabled:text-ash-500',
    ghost:     'border border-ash-700 text-ash-300 enabled:hover:bg-ash-800/50 enabled:hover:text-ash-100 disabled:bg-ash-900 disabled:text-ash-500 disabled:border-transparent',
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
