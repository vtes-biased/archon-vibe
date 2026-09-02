<script lang="ts">
  import type { Announcement } from "$lib/types";
  import { showToast } from "$lib/stores/toast.svelte";
  import { Megaphone, X } from "@lucide/svelte";
  import FoldableSection from "$lib/components/FoldableSection.svelte";
  import * as m from '$lib/paraglide/messages.js';

  let {
    announcements = [],
    tournamentUid,
    tournamentState,
  }: {
    announcements?: Announcement[];
    tournamentUid: string;
    tournamentState: string;
  } = $props();

  // Local-only, per-device dismissal (never round-trips to the server).
  const storeKey = () => `announce-dismissed-${tournamentUid}`;
  let dismissed = $state<Set<string>>(loadDismissed());
  let showHistory = $state(false);

  function loadDismissed(): Set<string> {
    try {
      const raw = localStorage.getItem(storeKey());
      return new Set(raw ? (JSON.parse(raw) as string[]) : []);
    } catch {
      return new Set();
    }
  }

  function persist(ids: Set<string>) {
    try {
      if (ids.size) localStorage.setItem(storeKey(), JSON.stringify([...ids]));
      else localStorage.removeItem(storeKey());  // nothing dismissed → drop the key
    } catch {
      // Storage unavailable — dismissal stays in-memory for this session
    }
  }

  function dismiss(id: string) {
    dismissed = new Set(dismissed).add(id);
    persist(dismissed);
  }

  // Evict dismissals whose announcement no longer exists (pruned past cap or
  // deleted), keeping this key bounded by the live list instead of growing forever.
  $effect(() => {
    const live = new Set(announcements.map((a) => a.id));
    if ([...dismissed].some((id) => !live.has(id))) {
      dismissed = new Set([...dismissed].filter((id) => live.has(id)));
      persist(dismissed);
    }
  });

  const sorted = $derived(
    [...announcements].sort((a, b) => b.created_at.localeCompare(a.created_at))
  );
  const active = $derived(sorted.filter((a) => !dismissed.has(a.id)));
  const history = $derived(sorted.filter((a) => dismissed.has(a.id)));

  // Post-event, announcements are archival: only the most recent shows as a calm,
  // non-dismissible banner, the rest drop into history, and no arrival toast fires.
  const finished = $derived(tournamentState === "Finished");
  const shown = $derived(finished ? sorted.slice(0, 1) : active);
  const rest = $derived(finished ? sorted.slice(1) : history);

  function formatTime(iso: string): string {
    return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  // Arrival cue: toast announcements that land after mount (not pre-existing,
  // not already dismissed on this device). Floats over whatever the player is doing.
  let baseline = $state(false);
  const reacted = new Set<string>();
  $effect(() => {
    const ids = announcements.map((a) => a.id);
    if (!baseline) {
      ids.forEach((id) => reacted.add(id));
      baseline = true;
      return;
    }
    for (const a of announcements) {
      if (reacted.has(a.id)) continue;
      reacted.add(a.id);
      if (!finished && !dismissed.has(a.id)) {
        showToast({ type: "info", message: a.body.slice(0, 120) });
      }
    }
  });
</script>

{#if shown.length > 0 || rest.length > 0}
  <div class="space-y-2 mb-4">
    {#each shown as a (a.id)}
      <div class="banner-info border rounded-lg p-3 flex items-start justify-between gap-2 animate-in">
        <div class="flex items-start gap-2 min-w-0">
          <Megaphone class="w-5 h-5 shrink-0 mt-0.5" />
          <div class="min-w-0">
            <p class="text-sm whitespace-pre-wrap break-words">{a.body}</p>
            <p class="text-xs text-ink-muted mt-0.5">{a.author_name} &middot; {formatTime(a.created_at)}</p>
          </div>
        </div>
        {#if !finished}
          <button onclick={() => dismiss(a.id)} class="text-ink-muted hover:text-ink-bright transition-colors p-1 shrink-0" title={m.announcement_dismiss()} aria-label={m.announcement_dismiss()}>
            <X class="w-4 h-4" />
          </button>
        {/if}
      </div>
    {/each}

    {#if rest.length > 0}
      <FoldableSection
        title={m.announcement_history({ count: String(rest.length) })}
        bind:open={showHistory}
      >
        {#each rest as a (a.id)}
          <div class="border border-line rounded-lg p-2.5 opacity-70">
            <p class="text-sm text-ink whitespace-pre-wrap break-words">{a.body}</p>
            <p class="text-xs text-ink-faint mt-0.5">{a.author_name} &middot; {formatTime(a.created_at)}</p>
          </div>
        {/each}
      </FoldableSection>
    {/if}
  </div>
{/if}

<style>
  .animate-in {
    animation: slideIn 0.2s ease-out;
  }
  @keyframes slideIn {
    from { opacity: 0; transform: translateY(-8px); }
    to { opacity: 1; transform: translateY(0); }
  }
</style>
