<script lang="ts">
  import { page } from '$app/stores';
  import UserList from '$lib/components/UserList.svelte';
  import CommunityTab from '$lib/components/CommunityTab.svelte';
  import * as m from '$lib/paraglide/messages.js';

  // Read tab from URL query param
  const urlTab = $derived($page.url.searchParams.get('tab'));
  let activeTab = $state<'community' | 'members'>('community');

  $effect(() => {
    if (urlTab === 'members') activeTab = 'members';
    else if (urlTab === 'community') activeTab = 'community';
  });
</script>

<svelte:head>
  <title>{m.nav_community()} - Archon</title>
</svelte:head>

<div class="p-4 sm:p-8">
  <div class="max-w-6xl mx-auto">
    <h1 class="text-3xl font-semibold text-accent mb-6">{m.nav_community()}</h1>

    <!-- Tab Toggle -->
    <div class="flex mb-6 bg-surface-card rounded-lg border border-line p-1 w-fit">
      <button
        onclick={() => activeTab = 'community'}
        class="px-4 py-2 text-sm font-medium rounded-md transition-colors {activeTab === 'community' ? 'bg-accent-strong text-white' : 'text-ink-muted hover:text-ink-bright'}"
      >
        {m.community_tab_community()}
      </button>
      <button
        onclick={() => activeTab = 'members'}
        class="px-4 py-2 text-sm font-medium rounded-md transition-colors {activeTab === 'members' ? 'bg-accent-strong text-white' : 'text-ink-muted hover:text-ink-bright'}"
      >
        {m.community_tab_members()}
      </button>
    </div>

    {#if activeTab === 'community'}
      <CommunityTab />
    {:else}
      <UserList />
    {/if}
  </div>
</div>
