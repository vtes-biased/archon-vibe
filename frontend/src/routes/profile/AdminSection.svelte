<script lang="ts">
  import { ChevronDown, RefreshCw } from 'lucide-svelte';
  import * as m from '$lib/paraglide/messages.js';
  import {
    syncVeknMembers,
    syncVeknTournaments,
    syncTwdaDecks,
    type AdminSyncResult,
  } from '$lib/api';
  import ConfirmActionModal from '$lib/components/ConfirmActionModal.svelte';

  let expanded = $state(false);

  interface Op {
    key: string;
    label: string;
    desc: string;
    confirmBody: string;
    run: () => Promise<AdminSyncResult>;
  }

  const ops: Op[] = [
    {
      key: 'vekn',
      label: m.admin_sync_vekn_label(),
      desc: m.admin_sync_vekn_desc(),
      confirmBody: m.admin_sync_vekn_confirm(),
      run: syncVeknMembers,
    },
    {
      key: 'vekn-tournaments',
      label: m.admin_sync_vekn_tournaments_label(),
      desc: m.admin_sync_vekn_tournaments_desc(),
      confirmBody: m.admin_sync_vekn_tournaments_confirm(),
      run: syncVeknTournaments,
    },
    {
      key: 'twda',
      label: m.admin_sync_twda_label(),
      desc: m.admin_sync_twda_desc(),
      confirmBody: m.admin_sync_twda_confirm(),
      run: syncTwdaDecks,
    },
  ];

  let activeOp = $state<Op | null>(null);
</script>

<div class="p-6 border-t border-ash-800">
  <button onclick={() => (expanded = !expanded)} class="flex items-center justify-between w-full text-left">
    <h3 class="text-sm font-medium text-ash-400 uppercase tracking-wide">{m.profile_admin_section()}</h3>
    <ChevronDown class="w-4 h-4 text-ash-400 transition-transform {expanded ? 'rotate-180' : ''}" />
  </button>
  {#if expanded}
    <div class="mt-4 space-y-3">
      <p class="text-ash-400 text-sm">{m.admin_subtitle()}</p>
      {#each ops as op}
        <div class="bg-dusk-900 rounded-lg border border-ash-700 p-4 flex items-start justify-between gap-3">
          <div class="min-w-0">
            <h4 class="text-bone-100 font-medium text-sm">{op.label}</h4>
            <p class="text-ash-500 text-xs mt-0.5">{op.desc}</p>
          </div>
          <button
            onclick={() => (activeOp = op)}
            class="px-3 py-1.5 bg-crimson-700 hover:bg-crimson-600 text-white rounded text-sm font-medium transition-colors flex items-center gap-1.5 shrink-0"
          >
            <RefreshCw class="w-3.5 h-3.5" />
            {m.admin_run_now()}
          </button>
        </div>
      {/each}
    </div>
  {/if}
</div>

{#if activeOp}
  <ConfirmActionModal
    title={activeOp.label}
    body={activeOp.confirmBody}
    confirmLabel={m.admin_run_now()}
    action={activeOp.run}
    onClose={() => (activeOp = null)}
  />
{/if}
