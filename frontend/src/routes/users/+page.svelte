<script lang="ts">
  import { page } from '$app/stores';
  import UserList from '$lib/components/UserList.svelte';
  import CommunityTab from '$lib/components/CommunityTab.svelte';
  import PromosTab from '$lib/components/promos/PromosTab.svelte';
  import Button from '$lib/components/Button.svelte';
  import { Plus } from '@lucide/svelte';
  import { getAuthState } from '$lib/stores/auth.svelte';
  import { isOfficial } from '$lib/engine';
  import { syncQueryParams, currentParams } from '$lib/url-filters';
  import * as m from '$lib/paraglide/messages.js';

  const auth = $derived(getAuthState());
  let addingLink = $state(false);
  const canAddLink = $derived(
    auth.isAuthenticated &&
    !!auth.user?.vekn_id &&
    (auth.user.community_links?.length ?? 0) < (isOfficial(auth.user) ? 10 : 5)
  );

  type Tab = 'community' | 'members' | 'promos';
  const TAB_VALUES: Tab[] = ['community', 'members', 'promos'];

  // Sponsor mode: arrived from a "get sponsored" pointer — focus the officials directory
  const sponsorMode = $derived($page.url.searchParams.get('sponsor') !== null);

  const urlTab = currentParams().get('tab') as Tab | null;
  let activeTab = $state<Tab>(urlTab && TAB_VALUES.includes(urlTab) ? urlTab : 'community');

  $effect(() => {
    syncQueryParams({ tab: activeTab === 'community' ? null : activeTab });
  });
</script>

<svelte:head>
  <title>{m.nav_community()} - Archon</title>
</svelte:head>

<div class="p-4 sm:p-8">
  <div class="max-w-6xl mx-auto">
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-3xl font-semibold text-accent">{m.nav_community()}</h1>

      {#if activeTab === 'community' && !sponsorMode && canAddLink}
        <Button variant="create" size="lg" onclick={() => addingLink = true}>
          <Plus class="w-4 h-4" aria-hidden="true" />
          {m.community_add_link()}
        </Button>
      {/if}
    </div>

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
      <CommunityTab {sponsorMode} bind:adding={addingLink} />
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
