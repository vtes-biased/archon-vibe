<script lang="ts">
  import { User, Camera, Unlink, Share2, Check, Plus, Trash2, CloudOff, X } from "@lucide/svelte";
  import { getCountries, getCountryFlag } from "$lib/geonames";
  import CityAutocomplete from "$lib/components/CityAutocomplete.svelte";
  import CommunityLinkPills from "$lib/components/CommunityLinkPills.svelte";
  import Button from "$lib/components/Button.svelte";
  import { updateProfile } from "$lib/stores/auth.svelte";
  import { showToast } from "$lib/stores/toast.svelte";
  import { canChangeCountry, isOfficial as engineIsOfficial } from "$lib/engine";
  import { COUNTRY_LANGUAGE } from "$lib/data/country-language";
  import { LANGUAGES, LANGUAGE_NAMES } from "$lib/data/languages";
  import type { CommunityLinkType } from "$lib/types";
  import * as m from '$lib/paraglide/messages.js';

  interface Props {
    user: any;
    onAvatarClick: () => void;
    onAbandonVekn: () => void;
    onClaimVekn: () => void;
  }
  let { user, onAvatarClick, onAbandonVekn, onClaimVekn }: Props = $props();

  const veknPush = import.meta.env.VITE_VEKN_PUSH === "true";
  // Strict false: undefined means the viewer's projection omits the field
  const veknSyncPending = $derived(
    veknPush && !!user.vekn_id && user.vekn_synced === false
  );

  const countries = getCountries();
  const sortedCountries = Object.values(countries).sort((a, b) => a.name.localeCompare(b.name));
  let copied = $state(false);

  // Identity, not authority: it only decides which contact-visibility note to show.
  const isOfficial = $derived(engineIsOfficial(user ?? null));

  // An official may not move their own country — it would move the scope their
  // FULL projection is computed for, so it takes the authority that could change
  // their highest role, which self-service never has.
  const isCountryLocked = $derived(!!user && !canChangeCountry(user, user).allowed);

  // svelte-ignore state_referenced_locally
  const initial = { ...user };
  // Editable field values — initialized from user
  let editName = $state(initial.name || "");
  let editNickname = $state(initial.nickname || "");
  let editCountry = $state(initial.country || "");
  let editCity = $state(initial.city || "");
  let editCityGeonameId = $state<number | null>(initial.city_geoname_id ?? null);
  let editContactEmail = $state(initial.contact_email || "");
  let editContactPhone = $state(initial.contact_phone || "");
  let editPhoneIsWhatsapp = $state(initial.phone_is_whatsapp ?? false);

  interface EditLink { type: CommunityLinkType; url: string; label: string; languages: string[] }
  let editLinks = $state<EditLink[]>(
    (initial.community_links || []).map((l: any) => ({ type: l.type, url: l.url, label: l.label, languages: l.languages || [] }))
  );

  const defaultLanguage = $derived(COUNTRY_LANGUAGE[editCountry] || "en");
  const MAX_LANGUAGES = 5;

  const CONTENT_TYPES = new Set(["youtube", "twitch", "blog", "website", "instagram", "other"]);

  const maxLinks = $derived(isOfficial ? 10 : 5);

  const LINK_TYPES: { value: CommunityLinkType; label: string }[] = [
    { value: "discord", label: "Discord" },
    { value: "telegram", label: "Telegram" },
    { value: "whatsapp", label: "WhatsApp" },
    { value: "forum", label: "Forum" },
    { value: "facebook", label: "Facebook" },
    { value: "website", label: "Website" },
    { value: "twitch", label: "Twitch" },
    { value: "youtube", label: "YouTube" },
    { value: "reddit", label: "Reddit" },
    { value: "instagram", label: "Instagram" },
    { value: "blog", label: "Blog" },
    { value: "other", label: "Other" },
  ];

  // Track last-saved values to avoid redundant saves
  let lastSaved: Record<string, unknown> = {
    name: initial.name || "",
    nickname: initial.nickname || "",
    country: initial.country || "",
    city: initial.city || "",
    city_geoname_id: initial.city_geoname_id ?? null,
    contact_email: initial.contact_email || "",
    contact_phone: initial.contact_phone || "",
    phone_is_whatsapp: initial.phone_is_whatsapp ?? false,
    community_links: JSON.stringify(initial.community_links || []),
  };

  async function saveField(field: string, value: unknown) {
    const cmp = field === "community_links" ? JSON.stringify(value) : value;
    if (lastSaved[field] === cmp) return;
    const ok = await updateProfile({ [field]: value });
    if (ok) {
      lastSaved[field] = cmp;
    } else {
      showToast({ type: "error", message: m.profile_save_error() });
    }
  }

  async function saveFields(data: Record<string, unknown>) {
    // Check if anything changed
    const changed: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(data)) {
      const cmp = k === "community_links" ? JSON.stringify(v) : v;
      if (lastSaved[k] !== cmp) changed[k] = v;
    }
    if (Object.keys(changed).length === 0) return;
    const ok = await updateProfile(changed);
    if (ok) {
      for (const [k, v] of Object.entries(changed)) {
        lastSaved[k] = k === "community_links" ? JSON.stringify(v) : v;
      }
    } else {
      showToast({ type: "error", message: m.profile_save_error() });
    }
  }

  function handleCountryChange() {
    editCity = "";
    editCityGeonameId = null;
    saveFields({ country: editCountry || undefined, city: undefined, city_geoname_id: null });
  }

  function handleCitySelect() {
    saveFields({
      city: editCity || undefined,
      city_geoname_id: editCity ? editCityGeonameId : null,
      country: editCountry || undefined,
    });
  }

  function saveLinks() {
    const cleaned = editLinks.filter(l => l.url.trim());
    saveField("community_links", cleaned);
  }

  function addLink() {
    if (editLinks.length >= maxLinks) return;
    editLinks = [...editLinks, { type: "discord", url: "", label: "", languages: [defaultLanguage] }];
  }

  function removeLink(index: number) {
    editLinks = editLinks.filter((_, i) => i !== index);
    saveLinks();
  }

  async function shareProfile() {
    const url = `${window.location.origin}/users/${user.uid}`;
    if (navigator.share) {
      try {
        await navigator.share({ title: user.name, url });
        return;
      } catch { /* user cancelled or not supported */ }
    }
    try {
      await navigator.clipboard.writeText(url);
      copied = true;
      setTimeout(() => { copied = false; }, 2000);
    } catch { /* noop */ }
  }

  const inputClass = "w-full px-3 py-2 border border-line-strong rounded bg-surface-card text-ink-bright focus:ring-2 focus:ring-accent focus:border-transparent";
</script>

<!-- Header -->
<div class="p-6 border-b border-line">
  <div class="flex items-center gap-4">
    <div class="flex flex-col items-center gap-1">
      <button
        onclick={onAvatarClick}
        class="relative group"
        title={m.user_change_avatar()}
      >
        {#if user.avatar_path}
          <img
            src={user.avatar_path}
            alt="Avatar"
            class="w-16 h-16 rounded-full object-cover"
          />
        {:else}
          <div class="w-16 h-16 rounded-full bg-surface-hover flex items-center justify-center">
            <User class="h-8 w-8 text-ink-faint" />
          </div>
        {/if}
        <div class="absolute inset-0 rounded-full bg-black/50 opacity-0 group-hover:opacity-100 flex items-center justify-center transition-opacity">
          <Camera class="h-6 w-6 text-white" />
        </div>
      </button>
      <button
        onclick={onAvatarClick}
        class="text-xs text-ink-muted hover:text-link sm:hidden"
      >{m.user_change_photo()}</button>
    </div>
    <div class="flex-1 space-y-2">
      <input type="text" bind:value={editName} placeholder={m.common_name()}
        onblur={() => saveField("name", editName || undefined)}
        class="{inputClass} text-lg font-medium" />
      <input type="text" bind:value={editNickname} placeholder={m.common_nickname()}
        onblur={() => saveField("nickname", editNickname || undefined)}
        class="{inputClass} text-sm" />
    </div>
    <button
      onclick={shareProfile}
      class="p-2 text-ink-faint hover:text-link transition-colors self-start"
      title={m.profile_share()}
    >
      {#if copied}
        <Check class="w-5 h-5 text-info" />
      {:else}
        <Share2 class="w-5 h-5" />
      {/if}
    </button>
  </div>
</div>

<!-- Details -->
<div class="p-6 space-y-4">
  {#if user.vekn_id}
    <div class="flex justify-between items-center">
      <span class="text-ink-muted">{m.add_player_vekn_id_label()}</span>
      <div class="flex items-center gap-2">
        {#if veknSyncPending}
          <span class="px-2 py-0.5 rounded text-xs font-medium banner-warn border inline-flex items-center gap-1"
                title={m.vekn_sync_pending_hint()}>
            <CloudOff class="w-3 h-3" aria-hidden="true" />
            {m.vekn_sync_pending_member()}
          </span>
        {/if}
        <span class="text-ink-strong font-mono">{user.vekn_id}</span>
        <button
          onclick={onAbandonVekn}
          class="p-1 text-ink-faint hover:text-link transition-colors"
          title={m.profile_abandon_vekn_tooltip()}
        >
          <Unlink class="w-4 h-4" />
        </button>
      </div>
    </div>
  {:else}
    <div class="flex justify-between items-center">
      <span class="text-ink-muted">{m.add_player_vekn_id_label()}</span>
      <Button variant="primary" size="md" onclick={onClaimVekn}>
        {m.profile_claim_vekn_title()}
      </Button>
    </div>
  {/if}

  <div>
    <label for="edit-country" class="block text-sm font-medium text-ink-muted mb-1">{m.common_country()}</label>
    <select id="edit-country" bind:value={editCountry} onchange={handleCountryChange}
      disabled={isCountryLocked}
      aria-describedby={isCountryLocked ? "edit-country-help" : undefined}
      class="{inputClass} disabled:opacity-50">
      <option value="">{m.user_country_placeholder()}</option>
      {#each sortedCountries as country}
        <option value={country.iso_code}>{country.name} {getCountryFlag(country.iso_code)}</option>
      {/each}
    </select>
    {#if isCountryLocked}
      <p id="edit-country-help" class="mt-1 text-xs text-ink-faint">{m.profile_country_locked_help()}</p>
    {/if}
  </div>

  <div>
    <label for="edit-city" class="block text-sm font-medium text-ink-muted mb-1">{m.common_city()}</label>
    <CityAutocomplete bind:value={editCity} bind:geonameId={editCityGeonameId} countryCode={editCountry} disabled={!editCountry} onselect={handleCitySelect} />
    {#if !editCountry}
      <p class="mt-1 text-xs text-ink-faint">{m.city_select_country_first()}</p>
    {/if}
  </div>

  {#if user.roles.length > 0}
    <div class="flex justify-between items-start">
      <span class="text-ink-muted">{m.common_roles()}</span>
      <div class="flex flex-wrap gap-2 justify-end">
        {#each user.roles as role}
          <span class="px-2 py-1 text-xs rounded bg-surface-hover text-ink-strong">{role}</span>
        {/each}
      </div>
    </div>
  {/if}
</div>

<!-- Contact Info -->
<div class="p-6 border-t border-line space-y-4">
  <h3 class="text-sm font-medium text-ink-muted uppercase tracking-wide">{m.profile_contact_info()}</h3>

  {#if isOfficial}
    <div class="p-3 rounded border text-sm banner-info">
      {#if user.roles?.includes("IC")}
        {m.profile_ic_contact_visibility()}
      {:else}
        {m.profile_official_contact_visibility()}
      {/if}
    </div>
  {/if}

  <div class="space-y-4">
    <div>
      <label for="edit-contact-email" class="block text-sm font-medium text-ink-muted mb-1">{m.profile_contact_email()}</label>
      <input id="edit-contact-email" type="email" bind:value={editContactEmail}
        onblur={() => saveField("contact_email", editContactEmail || undefined)}
        class={inputClass} />
    </div>
    <div>
      <label for="edit-contact-phone" class="block text-sm font-medium text-ink-muted mb-1">{m.profile_phone()}</label>
      <input id="edit-contact-phone" type="tel" bind:value={editContactPhone}
        onblur={() => saveField("contact_phone", editContactPhone || undefined)}
        class={inputClass} />
      <label class="flex items-center gap-2 mt-2 text-sm text-ink-muted cursor-pointer">
        <input type="checkbox" bind:checked={editPhoneIsWhatsapp}
          onchange={() => saveField("phone_is_whatsapp", editPhoneIsWhatsapp)}
          class="rounded border-line-strong bg-surface-card text-accent focus:ring-accent" />
        {m.profile_phone_is_whatsapp()}
      </label>
    </div>
  </div>
</div>

<!-- Community Links -->
{#if user.vekn_id}
  <div class="p-6 border-t border-line">
    <h3 class="text-sm font-medium text-ink-muted uppercase tracking-wide mb-4">{m.profile_community_links()}</h3>

    {#if !isOfficial}
      <div class="p-3 rounded border text-sm banner-info mb-4">
        {m.profile_community_links_member()}
      </div>
    {/if}

    <div class="space-y-3">
      {#each editLinks as link, i}
        <div class="border border-line-strong rounded-lg p-3 space-y-2">
          <div class="flex items-center gap-2">
            <select bind:value={link.type} onchange={saveLinks}
              class="flex-1 px-2 py-2 border border-line-strong rounded bg-surface-card text-ink-bright text-sm">
              {#each LINK_TYPES as lt}
                <option value={lt.value}>{lt.label}</option>
              {/each}
            </select>
            <button type="button" onclick={() => removeLink(i)}
              class="p-2 text-ink-faint hover:text-link transition-colors shrink-0">
              <Trash2 class="w-4 h-4" />
            </button>
          </div>
          <input type="url" bind:value={link.url} placeholder="https://..."
            onblur={saveLinks}
            class="{inputClass} text-sm" />
          <input type="text" bind:value={link.label} placeholder={m.profile_link_label_placeholder()}
            onblur={saveLinks}
            class="{inputClass} text-sm" />
          {#if CONTENT_TYPES.has(link.type)}
            <div class="flex flex-wrap items-center gap-1.5">
              {#each link.languages as code (code)}
                <span class="inline-flex items-center gap-1 pl-2 pr-1 py-1 rounded-full bg-surface-hover text-ink-bright text-xs">
                  {LANGUAGE_NAMES[code] ?? code}
                  <button type="button" aria-label={m.profile_remove_language({ lang: LANGUAGE_NAMES[code] ?? code })}
                    onclick={() => { link.languages = link.languages.filter(c => c !== code); saveLinks(); }}
                    class="grid place-items-center w-6 h-6 -m-1 rounded-full text-ink-faint hover:text-link cursor-pointer">
                    <X class="w-3.5 h-3.5" />
                  </button>
                </span>
              {/each}
              {#if link.languages.length === 0}
                <span class="text-xs text-ink-faint">{m.profile_link_all_languages()}</span>
              {/if}
              {#if link.languages.length < MAX_LANGUAGES}
                <select value="" aria-label={m.profile_add_language()}
                  onchange={(e) => {
                    const c = e.currentTarget.value; e.currentTarget.value = "";
                    if (c && !link.languages.includes(c)) { link.languages = [...link.languages, c]; saveLinks(); }
                  }}
                  class="px-2 py-1.5 border border-line-strong rounded bg-surface-card text-ink-muted text-xs">
                  <option value="" disabled selected>+ {m.profile_add_language()}</option>
                  {#each LANGUAGES.filter(l => !link.languages.includes(l.value)) as lang}
                    <option value={lang.value}>{lang.label}</option>
                  {/each}
                </select>
              {/if}
            </div>
          {/if}
        </div>
      {/each}
    </div>

    {#if editLinks.length < maxLinks}
      <button type="button" onclick={addLink}
        class="mt-3 flex items-center gap-1 text-sm text-link hover:text-link-soft transition-colors">
        <Plus class="w-4 h-4" />
        {m.profile_add_link()}
      </button>
    {/if}
  </div>
{/if}

<!-- Sponsorship banner for non-members (not gated on country: a brand-new user
     without one still needs the pointer; the community page prompts for country) -->
{#if !user.vekn_id}
  <div class="p-6 border-t border-line">
    <div class="p-3 rounded border text-sm banner-warn">
      {m.profile_sponsorship_banner()}
      <a href="/users?tab=community&sponsor=1" class="underline hover:text-warn ml-1">{m.profile_find_coordinator()}</a>
    </div>
  </div>
{/if}
