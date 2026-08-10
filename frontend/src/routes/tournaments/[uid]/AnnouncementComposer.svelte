<script lang="ts">
  import type { Tournament } from "$lib/types";
  import { postAnnouncement, deleteAnnouncement } from "$lib/api";
  import { Megaphone, Trash2, Send, ChevronDown, ChevronRight } from "@lucide/svelte";
  import Button from "$lib/components/Button.svelte";
  import * as m from '$lib/paraglide/messages.js';

  let { tournament }: { tournament: Tournament } = $props();

  // The composer folds; the posted announcements never do — those are what
  // anyone came to read.
  let composing = $state(false);

  const MAX_LEN = 280;  // soft UI cap; backend enforces MAX_ANNOUNCEMENT_LEN

  let text = $state("");
  let posting = $state(false);
  let deletingId = $state<string | null>(null);

  const trimmedLen = $derived(text.trim().length);
  const remaining = $derived(MAX_LEN - trimmedLen);
  const canPost = $derived(trimmedLen > 0 && remaining >= 0 && !posting);

  const sorted = $derived(
    [...(tournament.announcements ?? [])].sort((a, b) => b.created_at.localeCompare(a.created_at))
  );

  function formatTime(iso: string): string {
    return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  async function post() {
    if (!canPost) return;
    posting = true;
    try {
      await postAnnouncement(tournament.uid, text.trim());
      text = "";  // SSE delivers the new state into IndexedDB
    } catch {
      // apiRequest surfaces the error toast
    } finally {
      posting = false;
    }
  }

  async function remove(id: string) {
    deletingId = id;
    try {
      await deleteAnnouncement(tournament.uid, id);
    } catch {
      // apiRequest surfaces the error toast
    } finally {
      deletingId = null;
    }
  }
</script>

<div class="bg-surface-card rounded-lg shadow border border-line mb-4">
  <button
    type="button"
    onclick={() => (composing = !composing)}
    aria-expanded={composing}
    class="flex w-full items-center gap-2 px-3 sm:px-4 py-3 min-h-[44px] text-left"
  >
    <Megaphone class="w-4 h-4 text-ink-muted shrink-0" aria-hidden="true" />
    <span class="text-sm font-medium text-ink-strong">{m.announcement_composer_title()}</span>
    {#if sorted.length > 0}
      <span class="text-xs px-2 py-0.5 rounded bg-surface-active text-ink-muted">{sorted.length}</span>
    {/if}
    <span class="flex-1"></span>
    {#if composing}
      <ChevronDown class="w-4 h-4 shrink-0 text-ink-faint" aria-hidden="true" />
    {:else}
      <ChevronRight class="w-4 h-4 shrink-0 text-ink-faint" aria-hidden="true" />
    {/if}
  </button>

  {#if composing}
    <div class="px-3 sm:px-4 pb-3">
      <textarea
        bind:value={text}
        rows="2"
        maxlength={MAX_LEN + 50}
        placeholder={m.announcement_composer_placeholder()}
        aria-label={m.announcement_composer_title()}
        class="w-full px-3 py-2 text-sm bg-surface-card border border-line-strong rounded-lg text-ink-bright focus:border-line-strong focus:outline-none resize-y"
      ></textarea>

      <div class="flex items-center justify-between mt-2">
        <span class="text-xs {remaining < 0 ? 'text-error' : 'text-ink-faint'}">{remaining}</span>
        <Button variant="primary" size="sm" loading={posting} disabled={!canPost} onclick={post}>
          <Send class="w-4 h-4 inline mr-1" />
          {m.announcement_post()}
        </Button>
      </div>
    </div>
  {/if}

  {#if sorted.length > 0}
    <div class="px-3 sm:px-4 pb-3 pt-3 space-y-1.5 border-t border-line">
      {#each sorted as a (a.id)}
        <div class="flex items-start justify-between gap-2 text-sm">
          <div class="min-w-0">
            <p class="text-ink whitespace-pre-wrap break-words">{a.body}</p>
            <p class="text-xs text-ink-faint mt-0.5">{a.author_name} &middot; {formatTime(a.created_at)}</p>
          </div>
          <button onclick={() => remove(a.id)} disabled={deletingId === a.id} class="text-ink-muted hover:text-error transition-colors p-1 shrink-0 disabled:opacity-50" title={m.announcement_delete()} aria-label={m.announcement_delete()}>
            <Trash2 class="w-4 h-4" />
          </button>
        </div>
      {/each}
    </div>
  {/if}
</div>
