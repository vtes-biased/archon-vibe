<script lang="ts">
  import Button from '$lib/components/Button.svelte';
  import { Check, Users } from "@lucide/svelte";
  import * as m from '$lib/paraglide/messages.js';

  let {
    selfName,
    candidates,
    submitting = false,
    onSubmit,
    onClose,
  }: {
    selfName: string;
    // Other eligible players the initiator can seat (already filtered upstream).
    candidates: { uid: string; name: string }[];
    submitting?: boolean;
    // picked = the chosen others; the initiator is added by the caller.
    onSubmit: (picked: string[]) => void;
    onClose: () => void;
  } = $props();

  // A pod is one table: initiator + 3 or 4 picked = 4 or 5 total.
  const MAX_PICKED = 4;
  let picked = $state<Set<string>>(new Set());
  // $state Set needs reassignment to trigger reactivity.
  const total = $derived(picked.size + 1);
  const valid = $derived(total >= 4 && total <= 5);

  function toggle(uid: string) {
    const next = new Set(picked);
    if (next.has(uid)) {
      next.delete(uid);
    } else if (next.size < MAX_PICKED) {
      next.add(uid);
    }
    picked = next;
  }

  function focusOnMount(node: HTMLElement) {
    node.focus();
  }

  function submit() {
    if (!valid || submitting) return;
    onSubmit([...picked]);
  }
</script>

<div
  role="presentation"
  class="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/50 backdrop-blur-sm"
  onclick={(e) => { e.stopPropagation(); if (e.target === e.currentTarget) onClose(); }}
>
  <div
    role="dialog"
    aria-modal="true"
    aria-labelledby="self-organize-title"
    tabindex="-1"
    use:focusOnMount
    onkeydown={(e) => e.key === 'Escape' && onClose()}
    onclick={(e) => e.stopPropagation()}
    class="bg-surface-card rounded-t-lg sm:rounded-lg shadow-xl border border-line w-full sm:max-w-md sm:mx-4 max-h-[90vh] flex flex-col"
  >
    <div class="p-6 border-b border-line">
      <h2 id="self-organize-title" class="text-xl font-medium text-ink-strong flex items-center gap-2">
        <Users class="w-5 h-5 text-link shrink-0" aria-hidden="true" />
        {m.self_organize_title()}
      </h2>
      <p class="mt-1 text-sm text-ink-muted">{m.self_organize_help()}</p>
    </div>

    <div class="p-6 overflow-y-auto space-y-2">
      <!-- The initiator is always seated; shown locked at the top of the pod. -->
      <div class="flex items-center gap-3 p-3 rounded-lg bg-accent-soft/20 border border-accent-soft-border">
        <span class="w-5 h-5 rounded flex items-center justify-center bg-accent-strong text-white shrink-0">
          <Check class="w-3.5 h-3.5" aria-hidden="true" />
        </span>
        <span class="text-sm text-ink-bright truncate">{selfName}</span>
        <span class="ml-auto text-xs text-ink-muted shrink-0">{m.self_organize_you()}</span>
      </div>

      {#if candidates.length === 0}
        <p class="text-sm text-ink-muted py-2">{m.self_organize_no_candidates()}</p>
      {:else}
        {#each candidates as c (c.uid)}
          {@const isPicked = picked.has(c.uid)}
          {@const atLimit = !isPicked && picked.size >= MAX_PICKED}
          <label
            class="flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-colors min-h-[44px]
              {isPicked ? 'bg-accent-soft/20 border-accent-soft-border' : 'bg-surface-muted/50 border-line hover:bg-surface-hover/50'}
              {atLimit ? 'opacity-40 cursor-not-allowed' : ''}"
          >
            <input
              type="checkbox"
              checked={isPicked}
              disabled={atLimit || submitting}
              onchange={() => toggle(c.uid)}
              class="w-5 h-5 rounded border-line-strong bg-surface-card text-accent focus:ring-accent shrink-0"
            />
            <span class="text-sm text-ink-bright truncate">{c.name}</span>
          </label>
        {/each}
      {/if}
    </div>

    <div class="p-6 border-t border-line space-y-3">
      <p class="text-xs text-ink-faint">{m.self_organize_count_hint({ count: String(total) })}</p>
      <div class="flex gap-2">
        <Button variant="ghost" size="lg" class="flex-1" onclick={onClose} disabled={submitting}>
          {m.common_cancel()}
        </Button>
        <Button
          variant="primary"
          size="lg"
          class="flex-1"
          onclick={submit}
          disabled={!valid}
          loading={submitting}
        >
          {m.self_organize_seat_btn()}
        </Button>
      </div>
    </div>
  </div>
</div>
