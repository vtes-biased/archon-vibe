<script lang="ts">
  import { goto } from '$app/navigation';
  import { onMount } from 'svelte';
  import { getAccessToken } from '$lib/stores/auth.svelte';
  import Button from '$lib/components/Button.svelte';
  import * as m from '$lib/paraglide/messages.js';

  // The stored token, never `isAuthenticated`: initAuth() reports false whenever
  // /auth/me is unreachable, and this route is the PWA's start_url, so reading
  // auth state would drop a signed-in organizer onto the landing page offline.
  const signedIn = getAccessToken() !== null;

  onMount(() => {
    if (signedIn) goto('/tournaments', { replaceState: true });
  });

  const point = (deg: number, r: number) => {
    const a = ((deg - 90) * Math.PI) / 180;
    return { x: 100 + r * Math.cos(a), y: 100 + r * Math.sin(a) };
  };
  const seats = [0, 1, 2, 3, 4].map((i) => point(i * 72, 62));
  const arcs = seats.map((_, i) => {
    const from = point(i * 72 + 17, 62);
    const to = point(i * 72 + 55, 62);
    return `M ${from.x.toFixed(2)} ${from.y.toFixed(2)} A 62 62 0 0 1 ${to.x.toFixed(2)} ${to.y.toFixed(2)}`;
  });
</script>

<svelte:head>
  <title>Archon - {m.common_tagline()}</title>
</svelte:head>

{#if !signedIn}
  <div class="min-h-shell flex items-center justify-center p-6">
    <div class="w-full max-w-lg text-center">
      <svg
        viewBox="0 0 200 200"
        class="w-36 h-36 sm:w-44 sm:h-44 mx-auto mb-8 text-accent"
        aria-hidden="true"
        focusable="false"
      >
        <defs>
          <marker id="prey" viewBox="0 0 8 8" refX="8" refY="4" markerWidth="4" markerHeight="4" orient="auto">
            <path d="M 0 0 L 8 4 L 0 8 z" fill="currentColor" />
          </marker>
        </defs>
        {#each arcs as d}
          <path {d} fill="none" stroke="currentColor" stroke-width="2" opacity="0.8" marker-end="url(#prey)" />
        {/each}
        {#each seats as seat, i}
          <circle
            cx={seat.x}
            cy={seat.y}
            r="9"
            stroke="currentColor"
            stroke-width="2"
            fill={i === 0 ? 'currentColor' : 'none'}
          />
        {/each}
      </svg>

      <h1 class="text-4xl font-light text-accent mb-4">Archon</h1>

      <h2 class="text-xl sm:text-2xl font-medium text-ink-strong mb-4 text-balance">
        {m.landing_headline()}
      </h2>

      <p class="text-ink mb-8">{m.landing_intro()}</p>

      <div class="flex flex-col sm:flex-row gap-3 sm:justify-center">
        <Button variant="primary" size="lg" href="/login?mode=signup">{m.landing_signup()}</Button>
        <Button variant="secondary" size="lg" href="/tournaments">{m.landing_browse()}</Button>
      </div>

      <p class="text-sm text-ink-muted mt-6">
        {m.landing_have_account()}
        <a href="/login" class="text-link hover:text-link-soft focus-visible:text-link-soft underline ml-1"
          >{m.landing_sign_in()}</a
        >
      </p>
    </div>
  </div>
{/if}
