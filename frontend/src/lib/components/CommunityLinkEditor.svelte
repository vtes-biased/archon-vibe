<script lang="ts">
  import { dialogPanel } from "$lib/actions/dialog";
  import { apiRequest } from "$lib/api";
  import Button from "$lib/components/Button.svelte";
  import { LABELS } from "$lib/components/CommunityLinkPills.svelte";
  import { LANGUAGES, LANGUAGE_NAMES } from "$lib/data/languages";
  import { canModerateLink, canPromoteLinkGlobal, canPromoteLinkNational, getCommunityLinkReference } from "$lib/engine";
  import { getAuthState } from "$lib/stores/auth.svelte";
  import { getSortedCountries, getCountryFlag } from "$lib/geonames";
  import type { CommunityLink, CommunityLinkType } from "$lib/types";
  import { Loader2, Trash2, X } from "@lucide/svelte";
  import * as m from '$lib/paraglide/messages.js';

  interface Props {
    link: CommunityLink | null;
    ownerCountry: string | null;
    canEditUrl?: boolean;
    defaultLanguage: string;
    onclose: () => void;
    onsave: (link: CommunityLink, state: string | null) => void;
    ondelete?: () => void;
  }
  let { link, ownerCountry, canEditUrl = true, defaultLanguage, onclose, onsave, ondelete }: Props = $props();

  const MAX_LANGUAGES = 5;
  const sortedCountries = getSortedCountries();

  // Snapshot at open: an SSE frame must not rewrite the form mid-edit.
  /* svelte-ignore state_referenced_locally */
  const original = link;
  let type = $state<CommunityLinkType>(original?.type ?? "discord");
  let url = $state(original?.url ?? "");
  let label = $state(original?.label ?? "");
  // svelte-ignore state_referenced_locally
  let languages = $state<string[]>([...(original?.languages ?? (original ? [] : [defaultLanguage]))]);
  // svelte-ignore state_referenced_locally
  let country = $state(original?.country ?? ownerCountry ?? "");
  let suggestion = $state("");
  let fetching = $state(false);
  let touched = $state(false);

  const auth = $derived(getAuthState());
  const currentModeration = original?.moderation ?? "none";
  let moderation = $state<string>(currentModeration);
  const canPinNational = $derived(canPromoteLinkNational(auth.user, country || null).allowed);
  const canPinGlobal = $derived(canPromoteLinkGlobal(auth.user).allowed);
  const canHide = $derived(canModerateLink(auth.user, country || null).allowed);
  const moderationChoices = $derived([
    ...(canHide ? [{ value: "none", label: m.community_pin_none() }] : []),
    ...(canPinNational ? [{ value: "national", label: m.community_moderate_promote_national() }] : []),
    ...(canPinGlobal ? [{ value: "global", label: m.community_moderate_promote_global() }] : []),
    ...(canHide ? [{ value: "hidden", label: m.community_moderate_hide() }] : []),
  ]);

  const reference = $derived(getCommunityLinkReference());
  const isContent = $derived(reference.placement[type] === "content");
  const linkTypes = $derived(reference.types);
  const needsLanguage = $derived(isContent && languages.length === 0);
  const dropsPin = $derived(!!original?.moderation && url.trim() !== original.url);

  async function suggestLabel() {
    const trimmed = url.trim();
    if (!trimmed.startsWith("http")) return;
    fetching = true;
    try {
      const result = await apiRequest<{ title: string | null }>(
        `/auth/me/link-title?url=${encodeURIComponent(trimmed)}`,
        {},
        { suppressErrorToast: true }
      );
      if (!result.title) return;
      if (label.trim()) suggestion = result.title;
      else label = result.title;
    } catch {
      suggestion = "";
    } finally {
      fetching = false;
    }
  }

  function save() {
    touched = true;
    if (!url.trim().startsWith("http") || needsLanguage || !country) return;
    onsave(
      {
        type,
        url: url.trim(),
        label: label.trim(),
        languages: isContent ? languages : [],
        country: country || null,
      },
      moderation === currentModeration ? null : moderation
    );
  }

  const inputClass = "w-full px-3 py-2 border border-line-strong rounded bg-surface-card text-ink-bright focus:ring-2 focus:ring-accent focus:border-transparent";
</script>

<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
<div
  class="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm sm:flex sm:items-center sm:justify-center sm:p-4"
  role="presentation"
  onclick={onclose}
>
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
  <div
    use:dialogPanel={onclose}
    role="dialog"
    aria-modal="true"
    aria-labelledby="link-editor-title"
    tabindex="-1"
    class="bg-surface-card w-full h-full overflow-y-auto pt-safe-t pb-safe-b sm:pt-0 sm:h-auto sm:max-h-[85dvh] sm:max-w-lg sm:rounded-lg sm:border sm:border-line sm:shadow-xl"
    onclick={(e) => e.stopPropagation()}
    onkeydown={(e) => e.stopPropagation()}
  >
    <div class="p-6 border-b border-line flex items-center justify-between gap-4">
      <h2 id="link-editor-title" class="text-xl font-medium text-ink-strong">
        {original ? m.community_edit_link() : m.community_add_link()}
      </h2>
      <button onclick={onclose} aria-label={m.common_close()} class="p-2 text-ink-faint hover:text-link transition-colors">
        <X class="w-5 h-5" />
      </button>
    </div>

    <div class="p-6 space-y-4">
      <div>
        <label for="link-type" class="block text-sm font-medium text-ink-muted mb-1">{m.community_link_type()}</label>
        <select id="link-type" bind:value={type} class={inputClass}>
          {#each linkTypes as value}
            <option {value}>{LABELS[value]}</option>
          {/each}
        </select>
      </div>

      <div>
        <label for="link-url" class="block text-sm font-medium text-ink-muted mb-1">{m.community_link_url()}</label>
        <div class="relative">
          <input id="link-url" type="url" bind:value={url} onblur={suggestLabel} disabled={!canEditUrl}
            placeholder="https://..." class="{inputClass} disabled:opacity-50" />
          {#if fetching}
            <Loader2 class="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-ink-faint animate-spin motion-reduce:animate-none" />
          {/if}
        </div>
        {#if touched && !url.trim().startsWith("http")}
          <p class="mt-1 text-xs text-link">{m.community_link_url_invalid()}</p>
        {/if}
      </div>

      <div>
        <label for="link-label" class="block text-sm font-medium text-ink-muted mb-1">{m.community_link_label()}</label>
        <input id="link-label" type="text" bind:value={label} placeholder={LABELS[type]} class={inputClass} />
        {#if suggestion && suggestion !== label}
          <button type="button" onclick={() => { label = suggestion; suggestion = ""; }}
            class="mt-1 text-xs text-link hover:text-link-soft transition-colors">
            {m.community_link_use_title()} “{suggestion}”
          </button>
        {/if}
      </div>

      <div>
        <label for="link-country" class="block text-sm font-medium text-ink-muted mb-1">{m.common_country()}</label>
        <select id="link-country" bind:value={country} class={inputClass}>
          <option value="" disabled>{m.user_country_placeholder()}</option>
          {#each sortedCountries as option}
            <option value={option.iso_code}>{option.name} {getCountryFlag(option.iso_code)}</option>
          {/each}
        </select>
        {#if touched && !country}
          <p class="mt-1 text-xs text-link">{m.community_link_country_required()}</p>
        {/if}
        <p class="mt-1 text-xs text-ink-faint">{m.community_link_country_hint()}</p>
      </div>

      {#if isContent}
        <div>
          <span class="block text-sm font-medium text-ink-muted mb-1">{m.community_link_languages()}</span>
          <div class="flex flex-wrap items-center gap-1.5">
            {#each languages as code (code)}
              <span class="inline-flex items-center gap-1 pl-2 pr-1 py-1 rounded-full bg-surface-hover text-ink-bright text-xs">
                {LANGUAGE_NAMES[code] ?? code}
                <button type="button" aria-label={m.profile_remove_language({ lang: LANGUAGE_NAMES[code] ?? code })}
                  onclick={() => { languages = languages.filter(c => c !== code); }}
                  class="grid place-items-center w-6 h-6 -m-1 rounded-full text-ink-faint hover:text-link cursor-pointer">
                  <X class="w-3.5 h-3.5" />
                </button>
              </span>
            {/each}
            {#if languages.length < MAX_LANGUAGES}
              <select value="" aria-label={m.profile_add_language()}
                onchange={(e) => {
                  const c = e.currentTarget.value; e.currentTarget.value = "";
                  if (c && !languages.includes(c)) languages = [...languages, c];
                }}
                class="px-2 py-1.5 border border-line-strong rounded bg-surface-card text-ink-muted text-xs">
                <option value="" disabled selected>+ {m.profile_add_language()}</option>
                {#each LANGUAGES.filter(l => !languages.includes(l.value)) as language}
                  <option value={language.value}>{language.label}</option>
                {/each}
              </select>
            {/if}
          </div>
          {#if touched && needsLanguage}
            <p class="mt-1 text-xs text-link">{m.community_link_language_required()}</p>
          {/if}
        </div>
      {/if}

      {#if moderationChoices.length > 1}
        <div>
          <span class="block text-sm font-medium text-ink-muted mb-1">{m.community_card_pinned()}</span>
          <div class="flex flex-wrap gap-2">
            {#each moderationChoices as choice}
              <button type="button" onclick={() => { moderation = choice.value; }}
                aria-pressed={moderation === choice.value}
                class="px-3 min-h-11 rounded-full text-sm font-medium transition-colors {moderation === choice.value ? 'bg-accent-strong text-white' : 'bg-surface-hover text-ink hover:bg-surface-active'}"
              >{choice.label}</button>
            {/each}
          </div>
        </div>
      {/if}

      {#if dropsPin}
        <div class="p-3 rounded border text-sm banner-warn">{m.community_link_pin_drop_warning()}</div>
      {/if}
    </div>

    <div class="p-6 border-t border-line flex items-center justify-between gap-3">
      {#if ondelete}
        <Button variant="danger" size="lg" onclick={ondelete}>
          <Trash2 class="w-4 h-4" />
          {m.common_delete()}
        </Button>
      {:else}
        <span></span>
      {/if}
      <Button variant="primary" size="lg" onclick={save}>{m.common_save()}</Button>
    </div>
  </div>
</div>
