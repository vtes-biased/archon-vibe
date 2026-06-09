<script lang="ts">
  import { toUserMessage } from '$lib/errors';
  import * as m from '$lib/paraglide/messages.js';
  import { Loader2, CircleCheck, TriangleAlert } from 'lucide-svelte';

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
  let errorMsg = $state('');

  function flatten(value: unknown): string {
    if (value === null || typeof value !== 'object') return String(value);
    return JSON.stringify(value);
  }

  async function run() {
    status = 'loading';
    errorMsg = '';
    try {
      const result = await action();
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
    class="bg-dusk-950 rounded-lg shadow-xl border border-ash-800 w-full max-w-md mx-4"
    onclick={(e) => e.stopPropagation()}
    onkeydown={(e) => e.stopPropagation()}
    role="dialog"
    aria-modal="true"
    aria-labelledby="confirm-action-title"
    tabindex="-1"
  >
    <div class="p-6 border-b border-ash-800">
      <h2 id="confirm-action-title" class="text-xl font-medium text-bone-100">{title}</h2>
    </div>
    <div class="p-6">
      {#if status === 'success'}
        <div class="flex items-center gap-2 text-emerald-400 mb-4">
          <CircleCheck class="w-5 h-5 shrink-0" />
          <span class="font-medium">{m.admin_op_success()}</span>
        </div>
        {#if stats.length > 0}
          <dl class="text-sm bg-dusk-900 border border-ash-700 rounded-lg p-3 space-y-1 mb-6 max-h-60 overflow-auto">
            {#each stats as [key, value]}
              <div class="flex justify-between gap-4">
                <dt class="text-ash-400 font-mono">{key}</dt>
                <dd class="text-bone-200 font-mono text-right break-all">{flatten(value)}</dd>
              </div>
            {/each}
          </dl>
        {/if}
        <button
          onclick={onClose}
          class="w-full px-4 py-2 bg-ash-700 hover:bg-ash-600 text-ash-100 rounded font-medium transition-colors"
        >{m.common_close()}</button>
      {:else if status === 'error'}
        <div class="flex items-start gap-2 text-crimson-400 mb-4">
          <TriangleAlert class="w-5 h-5 shrink-0 mt-0.5" />
          <span class="text-sm break-words">{errorMsg || m.admin_op_error()}</span>
        </div>
        <div class="flex gap-2">
          <button
            onclick={run}
            class="flex-1 px-4 py-2 bg-crimson-700 hover:bg-crimson-600 text-white rounded font-medium transition-colors"
          >{m.common_retry()}</button>
          <button
            onclick={onClose}
            class="px-4 py-2 bg-ash-700 hover:bg-ash-600 text-ash-200 rounded font-medium transition-colors"
          >{m.common_close()}</button>
        </div>
      {:else}
        <p class="text-ash-300 mb-6">{body}</p>
        <div class="flex gap-2">
          <button
            onclick={run}
            disabled={status === 'loading'}
            class="flex-1 px-4 py-2 bg-crimson-700 hover:bg-crimson-600 disabled:bg-ash-800 disabled:text-ash-500 text-white rounded font-medium transition-colors flex items-center justify-center gap-1.5"
          >
            {#if status === 'loading'}
              <Loader2 class="w-4 h-4 animate-spin" />
              {m.admin_op_running()}
            {:else}
              {confirmLabel}
            {/if}
          </button>
          <button
            onclick={requestClose}
            disabled={status === 'loading'}
            class="px-4 py-2 bg-ash-700 hover:bg-ash-600 disabled:opacity-50 text-ash-200 rounded font-medium transition-colors"
          >{m.common_cancel()}</button>
        </div>
      {/if}
    </div>
  </div>
</div>
