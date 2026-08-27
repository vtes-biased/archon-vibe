<script lang="ts" generics="T extends string">
  import type { Component } from "svelte";

  let { tabs, active = $bindable() }: {
    tabs: { id: T; label: string; icon: Component<any> }[];
    active: T;
  } = $props();
</script>

<div class="flex border-b border-line overflow-x-auto">
  {#each tabs as tab}
    {@const TabIcon = tab.icon}
    {@const isActive = active === tab.id}
    <button
      onclick={() => (active = tab.id)}
      aria-label={tab.label}
      aria-current={isActive ? 'page' : undefined}
      class="flex items-center gap-1.5 px-4 py-3 text-sm font-medium whitespace-nowrap transition-colors border-b-2 {isActive ? 'border-accent text-ink-strong' : 'border-transparent text-ink-muted hover:text-ink-bright hover:border-line-strong'}"
    >
      <TabIcon class="w-4 h-4 shrink-0" aria-hidden="true" />
      <span class={isActive ? '' : 'hidden sm:inline'}>{tab.label}</span>
    </button>
  {/each}
</div>
