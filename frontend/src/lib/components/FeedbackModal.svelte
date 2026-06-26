<script lang="ts">
  import * as m from '$lib/paraglide/messages.js';
  import { getLocale } from '$lib/paraglide/runtime.js';
  import { CircleCheck, TriangleAlert } from '@lucide/svelte';
  import GithubIcon from '$lib/components/GithubIcon.svelte';
  import Button from '$lib/components/Button.svelte';
  import { submitFeedback } from '$lib/api';
  import { getAuthState, getAccessToken } from '$lib/stores/auth.svelte';
  import { toUserMessage } from '$lib/errors';

  const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

  let { onClose }: { onClose: () => void } = $props();

  const auth = $derived(getAuthState());

  type Category = 'bug' | 'feature' | 'question';
  let category = $state<Category>('bug');
  let title = $state('');
  let description = $state('');
  let status = $state<'idle' | 'loading' | 'success' | 'error'>('idle');
  let errorMsg = $state('');
  let issueUrl = $state('');

  // Live online state — `navigator.onLine` is non-reactive, so mirror it into a
  // rune and track the browser events (same pattern as +layout / UserList).
  let online = $state(navigator.onLine);
  $effect(() => {
    const on = () => (online = true);
    const off = () => (online = false);
    window.addEventListener('online', on);
    window.addEventListener('offline', off);
    return () => {
      window.removeEventListener('online', on);
      window.removeEventListener('offline', off);
    };
  });
  const offline = $derived(!online);
  const canSubmit = $derived(
    !offline && title.trim().length > 0 && description.trim().length > 0
  );

  // Shown before the fields: linking is a full-page redirect that drops the draft.
  const showGithubNudge = $derived(!offline && !!auth.user && !auth.user.github_login);

  function linkGithub() {
    const token = getAccessToken();
    if (!token) return;
    window.location.href = `${API_BASE}/auth/github/authorize?token=${encodeURIComponent(token)}`;
  }

  const categories: { value: Category; label: () => string }[] = [
    { value: 'bug', label: () => m.feedback_category_bug() },
    { value: 'feature', label: () => m.feedback_category_feature() },
    { value: 'question', label: () => m.feedback_category_question() },
  ];

  async function submit() {
    if (!canSubmit || status === 'loading') return;
    status = 'loading';
    errorMsg = '';
    try {
      const res = await submitFeedback(
        {
          category,
          title: title.trim(),
          description: description.trim(),
          app_version: __APP_VERSION__,
          route: location.pathname,
          locale: getLocale(),
          user_agent: navigator.userAgent,
        },
        { suppressErrorToast: true }
      );
      issueUrl = res.issue_url;
      status = 'success';
    } catch (e) {
      errorMsg = toUserMessage(e, m.feedback_error());
      status = 'error';
    }
  }

  /** Backdrop/Escape close is disabled mid-submit so a result is never lost. */
  function requestClose() {
    if (status !== 'loading') onClose();
  }
  function focusOnMount(node: HTMLElement) {
    node.focus();
  }

  const inputClass =
    'w-full px-3 py-2 text-sm border border-line-strong rounded-lg bg-surface-card text-ink-bright focus:ring-2 focus:ring-accent focus:border-transparent';
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
    aria-labelledby="feedback-title"
    tabindex="-1"
  >
    <div class="p-6 border-b border-line">
      <h2 id="feedback-title" class="text-xl font-medium text-ink-strong">{m.feedback_title()}</h2>
    </div>

    <div class="p-6">
      {#if status === 'success'}
        <div class="flex items-center gap-2 text-info mb-3" aria-live="polite">
          <CircleCheck class="w-5 h-5 shrink-0" />
          <span class="font-medium">{m.feedback_success_title()}</span>
        </div>
        <p class="text-ink-muted text-sm mb-4">{m.feedback_success_body()}</p>
        <a
          href={issueUrl}
          target="_blank"
          rel="noopener noreferrer"
          class="text-link hover:underline text-sm break-all"
        >{m.feedback_view_issue()}</a>
        <div class="mt-6">
          <Button variant="secondary" size="lg" block onclick={onClose}>{m.common_close()}</Button>
        </div>
      {:else}
        <p class="text-ink-muted text-sm mb-4">{m.feedback_intro()}</p>

        {#if showGithubNudge}
          <div class="flex items-start gap-2 mb-4 p-3 rounded-lg bg-surface-muted border border-line">
            <GithubIcon class="w-4 h-4 shrink-0 mt-0.5 text-ink-strong" />
            <span class="flex-1 text-xs text-ink-muted">{m.feedback_github_nudge()}</span>
            <button onclick={linkGithub} class="shrink-0 text-xs font-medium text-link hover:underline">
              {m.profile_link()}
            </button>
          </div>
        {/if}

        <div class="space-y-4">
          <div>
            <label for="fb-category" class="block text-sm text-ink-muted mb-1">{m.feedback_category_label()}</label>
            <select id="fb-category" bind:value={category} class={inputClass}>
              {#each categories as c}
                <option value={c.value}>{c.label()}</option>
              {/each}
            </select>
          </div>

          <div>
            <label for="fb-subject" class="block text-sm text-ink-muted mb-1">{m.feedback_subject_label()}</label>
            <input
              id="fb-subject"
              type="text"
              bind:value={title}
              maxlength="120"
              placeholder={m.feedback_subject_placeholder()}
              class={inputClass}
            />
          </div>

          <div>
            <label for="fb-description" class="block text-sm text-ink-muted mb-1">{m.feedback_description_label()}</label>
            <textarea
              id="fb-description"
              bind:value={description}
              rows="4"
              maxlength="4000"
              placeholder={m.feedback_description_placeholder()}
              class="{inputClass} resize-y"
            ></textarea>
          </div>
        </div>

        {#if status === 'error'}
          <div class="flex items-start gap-2 text-link mt-4" aria-live="polite">
            <TriangleAlert class="w-5 h-5 shrink-0 mt-0.5" />
            <span class="text-sm break-words">{errorMsg || m.feedback_error()}</span>
          </div>
        {:else if offline}
          <p class="text-ink-muted text-xs mt-4">{m.feedback_offline_hint()}</p>
        {/if}

        <div class="flex gap-2 mt-6">
          <Button
            variant="primary"
            size="lg"
            class="flex-1"
            loading={status === 'loading'}
            disabled={!canSubmit}
            onclick={submit}
          >
            {status === 'loading' ? m.feedback_submitting() : m.feedback_submit()}
          </Button>
          <Button variant="secondary" size="lg" disabled={status === 'loading'} onclick={requestClose}>
            {m.common_cancel()}
          </Button>
        </div>
      {/if}
    </div>
  </div>
</div>
