<script lang="ts">
  import type { Tournament, User } from "$lib/types";
  import { tournamentAction } from "$lib/tournament-actions";
  import { toUserMessage } from "$lib/errors";
  import { showToast } from "$lib/stores/toast.svelte";
  import { seatDisplay, type PlayerInfoMap } from "$lib/tournament-utils";
  import UserPicker from "$lib/components/UserPicker.svelte";
  import Button from "$lib/components/Button.svelte";
  import { Crown, X } from "@lucide/svelte";
  import * as m from '$lib/paraglide/messages.js';

  let {
    tournament,
    playerInfo,
    onupdate,
  }: {
    tournament: Tournament;
    playerInfo: PlayerInfoMap;
    onupdate: (tournament: Tournament) => void;
  } = $props();

  // svelte-ignore state_referenced_locally
  let roster = $state<string[]>((tournament.players ?? []).map(p => p.user_uid).filter((u): u is string => !!u));
  // svelte-ignore state_referenced_locally
  let winner = $state(tournament.winner ?? "");
  // svelte-ignore state_referenced_locally
  let count = $state<number | null>(tournament.reported_player_count || null);
  let names = $state<Record<string, string>>({});
  let saving = $state(false);

  const label = (uid: string) => names[uid] ?? seatDisplay(uid, playerInfo);
  const invalid = $derived(!winner || !count || count < roster.length);

  function add(user: User) {
    names = { ...names, [user.uid]: user.vekn_id ? `${user.name} (${user.vekn_id})` : user.name };
    if (!roster.includes(user.uid)) roster = [...roster, user.uid];
    if (!winner) winner = user.uid;
  }

  function remove(uid: string) {
    roster = roster.filter(u => u !== uid);
    if (winner === uid) winner = "";
  }

  async function save() {
    if (invalid) return;
    saving = true;
    try {
      onupdate(await tournamentAction(tournament.uid, 'SetArchivalResults', {
        winner,
        players: roster,
        reported_player_count: count,
      }));
      showToast({ type: "success", message: m.archival_saved() });
    } catch (e) {
      showToast({ type: "error", message: toUserMessage(e, m.archival_error_save()) });
    } finally {
      saving = false;
    }
  }
</script>

<div>
  <p class="text-xs text-ink-faint mb-3">{m.archival_hint()}</p>

  <label class="block text-xs text-ink-faint mb-1" for="archival-count">{m.archival_player_count()}</label>
  <input
    id="archival-count"
    type="number"
    bind:value={count}
    min={roster.length || 1}
    max={9999}
    class="w-24 px-2 py-1 min-h-[44px] mb-3 text-sm bg-surface-muted border rounded text-ink-strong text-center focus:border-accent-strong-hover focus:outline-none {count && count >= roster.length ? 'border-line-strong' : 'border-warn'}"
  />

  <p class="text-xs text-ink-faint mb-1">{m.archival_roster()}</p>
  {#if roster.length}
    <ul class="space-y-1 mb-2">
      {#each roster as uid (uid)}
        <li class="flex items-center gap-1 text-sm text-ink-strong">
          <button
            type="button"
            onclick={() => (winner = uid)}
            aria-label={m.archival_set_winner()}
            aria-pressed={winner === uid}
            class="min-w-[32px] min-h-[32px] flex items-center justify-center transition-colors {winner === uid ? 'text-accent-strong' : 'text-ink-faint hover:text-ink-strong'}"
          ><Crown class="w-4 h-4" /></button>
          <span class="flex-1 min-w-0 truncate">{label(uid)}</span>
          <button
            type="button"
            onclick={() => remove(uid)}
            aria-label={m.archival_remove_player()}
            class="min-w-[32px] min-h-[32px] flex items-center justify-center text-ink-faint hover:text-link transition-colors"
          ><X class="w-4 h-4" /></button>
        </li>
      {/each}
    </ul>
  {/if}
  <UserPicker onselect={add} excludeUids={roster} placeholder={m.archival_add_player()} />

  <p class="text-xs text-ink-faint mt-3 mb-2">{m.archival_roster_hint()}</p>
  <Button variant="primary" size="md" onclick={save} disabled={invalid || saving}>
    {m.common_save()}
  </Button>
</div>
