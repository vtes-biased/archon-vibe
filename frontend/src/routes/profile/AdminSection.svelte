<script lang="ts">
  import { ChevronDown, Download, RefreshCw } from '@lucide/svelte';
  import * as m from '$lib/paraglide/messages.js';
  import {
    syncVeknMembers,
    syncVeknTournaments,
    syncTwdaDecks,
    getVeknStatus,
    downloadDataExport,
    type AdminSyncResult,
    type VeknStatusResponse,
  } from '$lib/api';
  import ConfirmActionModal from '$lib/components/ConfirmActionModal.svelte';
  import Button from '$lib/components/Button.svelte';

  let expanded = $state(false);

  // Sync-job health: last success/error of the scheduled VEKN jobs.
  // In-process server state, loaded on first expand (and after a manual run).
  let status = $state<VeknStatusResponse | null>(null);
  let statusLoading = $state(false);
  let statusFailed = $state(false);

  const statusJobs: { key: string; label: () => string }[] = [
    { key: 'member_sync', label: m.admin_status_member_sync },
    { key: 'tournament_sync', label: m.admin_status_tournament_sync },
    { key: 'batch_push', label: m.admin_status_batch_push },
  ];

  async function loadStatus() {
    statusLoading = true;
    statusFailed = false;
    try {
      status = await getVeknStatus();
    } catch {
      statusFailed = true;
    } finally {
      statusLoading = false;
    }
  }

  function toggle() {
    expanded = !expanded;
    if (expanded && status === null && !statusLoading) loadStatus();
  }

  // Short-month localized form (e.g. "Jun 10, 2026, 9:04 AM") — avoids the
  // ambiguous all-numeric "6/11/2026". Matches SanctionBadge/SanctionsManager,
  // with time added since sync timestamps need hour/minute.
  const fmt = (iso?: string) =>
    iso
      ? new Date(iso).toLocaleString(undefined, {
          year: 'numeric',
          month: 'short',
          day: 'numeric',
          hour: '2-digit',
          minute: '2-digit',
        })
      : '';

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

<div class="p-6 border-t border-line">
  <button onclick={toggle} class="flex items-center justify-between w-full text-left">
    <h3 class="text-sm font-medium text-ink-muted uppercase tracking-wide">{m.profile_admin_section()}</h3>
    <ChevronDown class="w-4 h-4 text-ink-muted transition-transform {expanded ? 'rotate-180' : ''}" />
  </button>
  {#if expanded}
    <div class="mt-4 space-y-3">
      <!-- Sync-job health -->
      <div class="bg-surface-muted rounded-lg border border-line-strong p-4">
        <div class="flex items-center justify-between gap-3">
          <div class="min-w-0">
            <h4 class="text-ink-strong font-medium text-sm">{m.admin_sync_status_title()}</h4>
            <p class="text-ink-faint text-xs mt-0.5">{m.admin_sync_status_subtitle()}</p>
          </div>
          <button
            onclick={loadStatus}
            disabled={statusLoading}
            class="p-1.5 text-ink-muted hover:text-ink-strong disabled:opacity-50 transition-colors shrink-0"
            aria-label={m.admin_status_refresh()}
          >
            <RefreshCw class="w-3.5 h-3.5 {statusLoading ? 'animate-spin' : ''}" />
          </button>
        </div>
        {#if statusFailed}
          <p class="text-link text-xs mt-3">{m.admin_status_load_error()}</p>
        {:else}
          <ul class="mt-3 space-y-2">
            {#each statusJobs as job}
              {@const j = status?.jobs?.[job.key]}
              {@const ok = j?.last_status === 'ok'}
              {@const err = j?.last_status === 'error'}
              <li class="flex items-start gap-2.5 text-xs">
                <span
                  class="mt-1 w-2 h-2 rounded-full shrink-0 {ok
                    ? 'bg-info'
                    : err
                      ? 'bg-accent'
                      : 'bg-surface-active'}"
                ></span>
                <div class="min-w-0">
                  <span class="text-ink-strong font-medium">{job.label()}</span>
                  {#if !j}
                    <span class="text-ink-faint"> — {m.admin_status_never()}</span>
                  {:else}
                    {#if j.last_success_at}
                      <div class="text-ink-muted">{m.admin_status_last_success()}: {fmt(j.last_success_at)}</div>
                    {/if}
                    {#if err && j.last_error}
                      <div class="text-link">
                        {m.admin_status_last_error()}: {fmt(j.last_error_at)} — {j.last_error}
                      </div>
                    {/if}
                  {/if}
                </div>
              </li>
            {/each}
          </ul>
        {/if}
      </div>

      <p class="text-ink-muted text-sm">{m.admin_subtitle()}</p>
      {#each ops as op}
        <div class="bg-surface-muted rounded-lg border border-line-strong p-4 flex items-start justify-between gap-3">
          <div class="min-w-0">
            <h4 class="text-ink-strong font-medium text-sm">{op.label}</h4>
            <p class="text-ink-faint text-xs mt-0.5">{op.desc}</p>
          </div>
          <Button variant="primary" size="lg" class="shrink-0" onclick={() => (activeOp = op)}>
            <RefreshCw class="w-3.5 h-3.5" />
            {m.admin_run_now()}
          </Button>
        </div>
      {/each}

      <div class="bg-surface-muted rounded-lg border border-line-strong p-4 flex items-start justify-between gap-3">
        <div class="min-w-0">
          <h4 class="text-ink-strong font-medium text-sm">{m.admin_export_label()}</h4>
          <p class="text-ink-faint text-xs mt-0.5">{m.admin_export_desc()}</p>
        </div>
        <Button variant="primary" size="lg" class="shrink-0" onclick={downloadDataExport}>
          <Download class="w-3.5 h-3.5" />
          {m.admin_export_button()}
        </Button>
      </div>
    </div>
  {/if}
</div>

{#if activeOp}
  <ConfirmActionModal
    title={activeOp.label}
    body={activeOp.confirmBody}
    confirmLabel={m.admin_run_now()}
    action={activeOp.run}
    onClose={() => {
      activeOp = null;
      loadStatus();
    }}
  />
{/if}
