<script lang="ts">
  import type { JudgeCallData } from "$lib/sync";
  import { X, Gavel } from "lucide-svelte";
  import * as m from '$lib/paraglide/messages.js';

  let {
    tournamentUid,
  }: {
    tournamentUid: string;
  } = $props();

  let calls = $state<(JudgeCallData & { id: number; ts: number })[]>([]);
  let nextId = 0;

  export function addCall(data: JudgeCallData) {
    if (data.tournament_uid !== tournamentUid) return;
    const id = nextId++;
    const ts = Date.now();
    calls = [...calls, { ...data, id, ts }];
    // Play audio chime
    playChime();
    // Auto-dismiss after 120s
    setTimeout(() => dismiss(id), 120_000);
  }

  function dismiss(id: number) {
    calls = calls.filter(c => c.id !== id);
  }

  function playChime() {
    try {
      const ctx = new AudioContext();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.frequency.value = 880;
      osc.type = 'sine';
      gain.gain.setValueAtTime(0.3, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.3);
      osc.start(ctx.currentTime);
      osc.stop(ctx.currentTime + 0.3);
    } catch {
      // Audio not available
    }
  }
</script>

{#if calls.length > 0}
  <div class="space-y-2 mb-4">
    {#each calls as call (call.id)}
      <div class="banner-amber border rounded-lg p-3 flex items-center justify-between animate-in">
        <div class="flex items-center gap-2">
          <Gavel class="w-5 h-5 text-amber-400 shrink-0" />
          <div>
            <span class="text-sm font-medium text-bone-100">{m.judge_call_alert()}</span>
            <span class="text-sm text-ash-300 ml-1">
              {call.table_label} &mdash; {call.player_name}
            </span>
          </div>
        </div>
        <button onclick={() => dismiss(call.id)} class="text-ash-400 hover:text-ash-200 transition-colors p-1" title={m.judge_call_dismiss()}>
          <X class="w-4 h-4" />
        </button>
      </div>
    {/each}
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
