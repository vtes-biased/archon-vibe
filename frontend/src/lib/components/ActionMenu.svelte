<script lang="ts">
  import { MoreHorizontal } from "@lucide/svelte";
  import type { Component, Snippet } from "svelte";

  // Overflow menu for secondary actions, so each state keeps ONE primary CTA.
  // Menu items are raw rows (not <Button> — per wiki/design.md, dropdown options
  // don't route through it). Closes on outside-click, Escape, or pick.
  //
  // `children` swaps the item list for arbitrary panel content (settings
  // popovers). It shares this component rather than growing a second popover
  // because the dismiss handling and the viewport clamp below are the fragile
  // part, and a copy of them would drift.
  type Item = { label: string; icon?: Component<any>; onclick: () => void; disabled?: boolean };
  let {
    label,
    items = [],
    align = "left",
    disabled = false,
    icon = MoreHorizontal,
    indicator = false,
    children,
  }: {
    label: string;
    items?: Item[];
    align?: "left" | "right";
    disabled?: boolean;
    icon?: Component<any>;
    // Dot on the trigger: the panel currently holds a non-default setting.
    indicator?: boolean;
    children?: Snippet;
  } = $props();
  const Icon = $derived(icon);

  let open = $state(false);
  let root: HTMLDivElement | undefined;
  let triggerEl: HTMLButtonElement | undefined;
  let menuEl = $state<HTMLDivElement | null>(null);

  // Anchored to the trigger, the panel can run off a narrow viewport — and an
  // absolutely-positioned box still extends the document's scrollable area, so
  // the whole page gains a horizontal scroll. Nudge it back inside after open
  // (and on resize). Imperative on purpose: writing the offset to reactive
  // state would re-trigger the measurement that produced it.
  const VIEWPORT_MARGIN = 8;
  function clampToViewport() {
    const el = menuEl;
    if (!el) return;
    el.style.transform = "";
    const { left, right } = el.getBoundingClientRect();
    const overRight = right - (window.innerWidth - VIEWPORT_MARGIN);
    const overLeft = VIEWPORT_MARGIN - left;
    if (overRight > 0) el.style.transform = `translateX(${-overRight}px)`;
    else if (overLeft > 0) el.style.transform = `translateX(${overLeft}px)`;
  }
  $effect(() => {
    if (!open || !menuEl) return;
    clampToViewport();
  });

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

<svelte:window onclick={onWindowClick} onkeydown={onWindowKey} onresize={() => open && clampToViewport()} />

<div class="relative inline-block" bind:this={root}>
  <button
    type="button"
    bind:this={triggerEl}
    {disabled}
    onclick={() => (open = !open)}
    aria-haspopup="true"
    aria-expanded={open}
    class="inline-flex items-center gap-1.5 rounded-lg bg-surface-hover enabled:hover:bg-surface-active text-ink-bright px-3 py-1.5 text-sm transition-colors disabled:bg-surface-muted disabled:text-ink-faint"
  >
    <Icon class="w-4 h-4" aria-hidden="true" />
    {label}
    {#if indicator}<span class="w-1.5 h-1.5 rounded-full bg-accent" aria-hidden="true"></span>{/if}
  </button>

  {#if open}
    <!-- Plain disclosure of buttons (Tab-navigable). Deliberately NOT role=menu:
         we don't implement arrow-key/type-ahead, so we don't advertise it. -->
    <div
      bind:this={menuEl}
      class="absolute z-30 mt-1 min-w-[12rem] max-w-[calc(100vw-1rem)] {align === 'right' ? 'right-0' : 'left-0'} rounded-lg border border-line-strong bg-surface-muted py-1 shadow-lg"
    >
      {#if children}
        <div class="px-3 py-2">{@render children()}</div>
      {/if}
      {#each items as item}
        {@const Icon = item.icon}
        <button
          type="button"
          disabled={item.disabled}
          onclick={() => pick(item)}
          class="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-ink-bright transition-colors enabled:hover:bg-surface-hover disabled:text-ink-faint"
        >
          {#if Icon}<Icon class="w-4 h-4 shrink-0" aria-hidden="true" />{/if}
          {item.label}
        </button>
      {/each}
    </div>
  {/if}
</div>
