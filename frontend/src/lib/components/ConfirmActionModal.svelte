<script lang="ts">
  import { toUserMessage } from '$lib/errors';
  import * as m from '$lib/paraglide/messages.js';
  import { CircleCheck, TriangleAlert } from '@lucide/svelte';
  import Button from '$lib/components/Button.svelte';

  let {
    title,
    body,
    confirmLabel,
    action,
    onClose,
  }: {
    title: string;
    body: string;
    confirmLabel: string;
    /** Runs the operation; may resolve with a stats map (or { stats }) to display. */
    action: () => Promise<unknown>;
    onClose: () => void;
  } = $props();

  let status = $state<'idle' | 'loading' | 'success' | 'error'>('idle');
  let stats = $state<[string, unknown][]>([]);
  let started = $state(false);
  let errorMsg = $state('');

  function flatten(value: unknown): string {
    if (value === null || typeof value !== 'object') return String(value);
    return JSON.stringify(value);
  }

  async function run() {
    status = 'loading';
    errorMsg = '';
    started = false;
    try {
      const result = await action();
      // Background-dispatched jobs (the admin syncs) return
      // {status:'started'|'already_running'} with no stats — the outcome shows
      // up in the status panel, not here.
      const s = result && typeof result === 'object' ? (result as { status?: unknown }).status : undefined;
      if (s === 'started' || s === 'already_running') {
        started = true;
        status = 'success';
        return;
      }
      const data =
        result && typeof result === 'object' && 'stats' in result
          ? (result as { stats: unknown }).stats
          : result;
      stats = data && typeof data === 'object' ? Object.entries(data) : [];
      status = 'success';
    } catch (e) {
      errorMsg = toUserMessage(e, String(e));
      status = 'error';
    }
  }

  /** Backdrop/Escape close is disabled mid-run so a job's result is never lost. */
  function requestClose() {
    if (status !== 'loading') onClose();
  }

  function focusOnMount(node: HTMLElement) {
    node.focus();
  }
</script>

<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
<div
  class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4"
  role="presentation"
  onclick={requestClose}
  onkeydown={(e) => { if (e.key === 'Escape') requestClose(); }}
>
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
  <div
    use:focusOnMount
    class="bg-surface-card rounded-lg shadow-xl border border-line w-full max-w-md mx-4"
    onclick={(e) => e.stopPropagation()}
    onkeydown={(e) => e.stopPropagation()}
    role="dialog"
    aria-modal="true"
    aria-labelledby="confirm-action-title"
    tabindex="-1"
  >
    <div class="p-6 border-b border-line">
      <h2 id="confirm-action-title" class="text-xl font-medium text-ink-strong">{title}</h2>
    </div>
    <div class="p-6">
      {#if status === 'success'}
        <div class="flex items-center gap-2 text-info mb-4">
          <CircleCheck class="w-5 h-5 shrink-0" />
          <span class="font-medium">{started ? m.admin_op_started() : m.admin_op_success()}</span>
        </div>
        {#if started}
          <p class="text-ink-muted text-sm mb-6">{m.admin_op_started_hint()}</p>
        {:else if stats.length > 0}
          <dl class="text-sm bg-surface-muted border border-line-strong rounded-lg p-3 space-y-1 mb-6 max-h-60 overflow-auto">
            {#each stats as [key, value]}
              <div class="flex justify-between gap-4">
                <dt class="text-ink-muted font-mono">{key}</dt>
                <dd class="text-ink-strong font-mono text-right break-all">{flatten(value)}</dd>
              </div>
            {/each}
          </dl>
        {/if}
        <Button variant="secondary" size="lg" block onclick={onClose}>{m.common_close()}</Button>
      {:else if status === 'error'}
        <div class="flex items-start gap-2 text-link mb-4">
          <TriangleAlert class="w-5 h-5 shrink-0 mt-0.5" />
          <span class="text-sm break-words">{errorMsg || m.admin_op_error()}</span>
        </div>
        <div class="flex gap-2">
          <Button variant="primary" size="lg" class="flex-1" onclick={run}>{m.common_retry()}</Button>
          <Button variant="secondary" size="lg" onclick={onClose}>{m.common_close()}</Button>
        </div>
      {:else}
        <p class="text-ink mb-6">{body}</p>
        <div class="flex gap-2">
          <Button variant="primary" size="lg" class="flex-1" loading={status === 'loading'} onclick={run}>
            {#if status === 'loading'}{m.admin_op_running()}{:else}{confirmLabel}{/if}
          </Button>
          <Button variant="secondary" size="lg" disabled={status === 'loading'} onclick={requestClose}>{m.common_cancel()}</Button>
        </div>
      {/if}
    </div>
  </div>
</div>
