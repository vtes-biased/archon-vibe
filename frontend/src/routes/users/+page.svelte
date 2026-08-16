<script lang="ts">
  import { page } from '$app/stores';
  import UserList from '$lib/components/UserList.svelte';
  import CommunityTab from '$lib/components/CommunityTab.svelte';
  import PromosTab from '$lib/components/promos/PromosTab.svelte';
  import { getAuthState } from '$lib/stores/auth.svelte';
  import * as m from '$lib/paraglide/messages.js';

  const auth = $derived(getAuthState());

  const urlTab = $derived($page.url.searchParams.get('tab'));
  // Sponsor mode: arrived from a "get sponsored" pointer — focus the officials directory
  const sponsorMode = $derived($page.url.searchParams.get('sponsor') !== null);
  let activeTab = $state<'community' | 'members' | 'promos'>('community');

  $effect(() => {
    if (urlTab === 'members') activeTab = 'members';
    else if (urlTab === 'promos') activeTab = 'promos';
    else if (urlTab === 'community') activeTab = 'community';
  });
</script>

<svelte:head>
  <title>{m.nav_community()} - Archon</title>
</svelte:head>

<div class="p-4 sm:p-8">
  <div class="max-w-6xl mx-auto">
    <h1 class="text-3xl font-semibold text-accent mb-6">{m.nav_community()}</h1>

    <!-- Tab Toggle: equal thirds on mobile, hug content on desktop -->
    <div class="grid grid-cols-3 sm:inline-flex sm:w-fit mb-6 bg-surface-card rounded-lg border border-line p-1">
      <button
        onclick={() => activeTab = 'community'}
        aria-pressed={activeTab === 'community'}
        class="px-4 py-2 text-sm font-medium rounded-md transition-colors {activeTab === 'community' ? 'bg-accent-strong text-white' : 'text-ink-muted hover:text-ink-bright'}"
      >
        {m.community_tab_community()}
      </button>
      <button
        onclick={() => activeTab = 'members'}
        aria-pressed={activeTab === 'members'}
        class="px-4 py-2 text-sm font-medium rounded-md transition-colors {activeTab === 'members' ? 'bg-accent-strong text-white' : 'text-ink-muted hover:text-ink-bright'}"
      >
        {m.community_tab_members()}
      </button>
      <button
        onclick={() => activeTab = 'promos'}
        aria-pressed={activeTab === 'promos'}
        class="px-4 py-2 text-sm font-medium rounded-md transition-colors {activeTab === 'promos' ? 'bg-accent-strong text-white' : 'text-ink-muted hover:text-ink-bright'}"
      >
        {m.community_tab_promos()}
      </button>
    </div>

    {#if activeTab === 'community'}
      <CommunityTab {sponsorMode} />
    {:else if activeTab === 'promos'}
      <PromosTab />
    {:else if auth.isAuthenticated}
      <UserList />
    {:else}
      <!-- Members directory is sign-in gated; show an inviting prompt, not the list. -->
      <div class="p-4 rounded-lg bg-surface-muted border border-line-strong text-sm text-ink">
        {m.members_login_prompt()}
        <a href="/login" class="underline text-link hover:text-link-soft ml-1">{m.community_sign_in()}</a>
      </div>
    {/if}
  </div>
</div>
