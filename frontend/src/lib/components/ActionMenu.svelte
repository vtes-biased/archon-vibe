<script lang="ts">
  import { MoreHorizontal } from "@lucide/svelte";
  import type { Component } from "svelte";

  // Overflow menu for secondary actions, so each state keeps ONE primary CTA.
  // Menu items are raw rows (not <Button> — per DESIGN.md, dropdown options
  // don't route through it). Closes on outside-click, Escape, or pick.
  type Item = { label: string; icon?: Component<any>; onclick: () => void; disabled?: boolean };
  let {
    label,
    items,
    align = "left",
    disabled = false,
  }: { label: string; items: Item[]; align?: "left" | "right"; disabled?: boolean } = $props();

  let open = $state(false);
  let root: HTMLDivElement | undefined;
  let triggerEl: HTMLButtonElement | undefined;

  function onWindowClick(e: MouseEvent) {
    if (open && root && !root.contains(e.target as Node)) open = false;
  }
  function onWindowKey(e: KeyboardEvent) {
    // Escape closes and returns focus to the trigger (WAI-ARIA menu-button).
    if (open && e.key === "Escape") {
      open = false;
      triggerEl?.focus();
    }
  }
  function pick(item: Item) {
    if (item.disabled) return;
    open = false;
    item.onclick();
  }
</script>

<svelte:window onclick={onWindowClick} onkeydown={onWindowKey} />

<div class="relative inline-block" bind:this={root}>
  <button
    type="button"
    bind:this={triggerEl}
    {disabled}
    onclick={() => (open = !open)}
    aria-haspopup="true"
    aria-expanded={open}
    class="inline-flex items-center gap-1.5 rounded-lg bg-ash-800 enabled:hover:bg-ash-700 text-ash-200 px-3 py-1.5 text-sm transition-colors disabled:bg-ash-900 disabled:text-ash-500"
  >
    <MoreHorizontal class="w-4 h-4" aria-hidden="true" />
    {label}
  </button>

  {#if open}
    <!-- Plain disclosure of buttons (Tab-navigable). Deliberately NOT role=menu:
         we don't implement arrow-key/type-ahead, so we don't advertise it. -->
    <div
      class="absolute z-30 mt-1 min-w-[12rem] {align === 'right' ? 'right-0' : 'left-0'} rounded-lg border border-ash-700 bg-dusk-900 py-1 shadow-lg"
    >
      {#each items as item}
        {@const Icon = item.icon}
        <button
          type="button"
          disabled={item.disabled}
          onclick={() => pick(item)}
          class="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-ash-200 transition-colors enabled:hover:bg-ash-800 disabled:text-ash-500"
        >
          {#if Icon}<Icon class="w-4 h-4 shrink-0" aria-hidden="true" />{/if}
          {item.label}
        </button>
      {/each}
    </div>
  {/if}
</div>
