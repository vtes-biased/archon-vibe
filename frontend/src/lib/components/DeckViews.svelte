<script lang="ts">
  import type { DeckView } from "$lib/types";
  import { getUser } from "$lib/db";
  import { Eye } from "@lucide/svelte";
  import * as m from '$lib/paraglide/messages.js';

  let { views, roundCount }: { views: DeckView[]; roundCount: number } = $props();

  let names = $state<Record<string, string>>({});

  $effect(() => {
    const uids = views.map(v => v.user_uid);
    Promise.all(uids.map(u => getUser(u))).then(users => {
      names = Object.fromEntries(uids.map((u, i) => [u, users[i]?.name || u.slice(0, 8)]));
    });
  });

  function entry(v: DeckView): string {
    const name = names[v.user_uid] || "…";
    if (v.round >= roundCount) return m.decks_view_entry_finals({ name });
    return m.decks_view_entry_round({ name, n: String(v.round + 1) });
  }
</script>

{#if views.length > 0}
  <p class="text-xs text-ink-faint flex items-center gap-1.5">
    <Eye class="w-3.5 h-3.5 shrink-0" />
    {m.decks_viewed_by({ names: views.map(entry).join(", ") })}
  </p>
{/if}
