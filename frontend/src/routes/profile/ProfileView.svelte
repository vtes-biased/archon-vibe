<script lang="ts">
  import { User, Camera, Unlink, Share2, Check, Plus, Trash2 } from "lucide-svelte";
  import { getCountries, getCountryFlag } from "$lib/geonames";
  import CityAutocomplete from "$lib/components/CityAutocomplete.svelte";
  import CommunityLinkPills from "$lib/components/CommunityLinkPills.svelte";
  import { updateProfile } from "$lib/stores/auth.svelte";
  import { showToast } from "$lib/stores/toast.svelte";
  import type { CommunityLinkType } from "$lib/types";
  import * as m from '$lib/paraglide/messages.js';

  interface Props {
    user: any;
    avatarCacheBust: number;
    onAvatarClick: () => void;
    onAbandonVekn: () => void;
    onClaimVekn: () => void;
  }
  let { user, avatarCacheBust, onAvatarClick, onAbandonVekn, onClaimVekn }: Props = $props();

  const countries = getCountries();
  const sortedCountries = Object.values(countries).sort((a, b) => a.name.localeCompare(b.name));
  let copied = $state(false);

  const isOfficial = $derived(
    user?.roles?.some((r: string) => r === "IC" || r === "NC" || r === "Prince") ?? false
  );

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

  interface EditLink { type: CommunityLinkType; url: string; label: string; language: string }
  let editLinks = $state<EditLink[]>(
    (initial.community_links || []).map((l: any) => ({ type: l.type, url: l.url, label: l.label, language: l.language || "" }))
  );

  // Country → default language
  const COUNTRY_LANGUAGE: Record<string, string> = {
    US: "en", GB: "en", AU: "en", CA: "en", NZ: "en", IE: "en", ZA: "en",
    FR: "fr", BE: "fr", CH: "fr",
    ES: "es", MX: "es", AR: "es", CO: "es", CL: "es", PE: "es", VE: "es",
    PT: "pt", BR: "pt",
    IT: "it",
    DE: "de", AT: "de",
    PL: "pl", FI: "fi", SE: "sv", NL: "nl", NO: "no", DK: "da",
    JP: "ja", CN: "zh", TW: "zh", KR: "ko", RU: "ru",
    CZ: "cs", HU: "hu", RO: "ro", BG: "bg", HR: "hr", GR: "el", TR: "tr",
  };
  const defaultLanguage = $derived(COUNTRY_LANGUAGE[editCountry] || "en");

  const CONTENT_TYPES = new Set(["youtube", "twitch", "blog", "website", "instagram", "other"]);
  const LANGUAGES = [
    { value: "en", label: "English" }, { value: "es", label: "Español" },
    { value: "fr", label: "Français" }, { value: "pt", label: "Português" },
    { value: "it", label: "Italiano" }, { value: "de", label: "Deutsch" },
    { value: "pl", label: "Polski" }, { value: "fi", label: "Suomi" },
    { value: "sv", label: "Svenska" }, { value: "nl", label: "Nederlands" },
    { value: "ja", label: "日本語" }, { value: "zh", label: "中文" },
    { value: "ko", label: "한국어" }, { value: "ru", label: "Русский" },
    { value: "cs", label: "Čeština" }, { value: "hu", label: "Magyar" },
    { value: "ro", label: "Română" }, { value: "hr", label: "Hrvatski" },
    { value: "el", label: "Ελληνικά" }, { value: "tr", label: "Türkçe" },
    { value: "th", label: "ไทย" },
  ];

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
    editLinks = [...editLinks, { type: "discord", url: "", label: "", language: defaultLanguage }];
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

  const inputClass = "w-full px-3 py-2 border border-ash-600 rounded bg-dusk-950 text-ash-200 focus:ring-2 focus:ring-crimson-500 focus:border-transparent";
</script>

<!-- Header -->
<div class="p-6 border-b border-ash-800">
  <div class="flex items-center gap-4">
    <div class="flex flex-col items-center gap-1">
      <button
        onclick={onAvatarClick}
        class="relative group"
        title={m.user_change_avatar()}
      >
        {#if user.avatar_path}
          <img
            src={avatarCacheBust ? `${user.avatar_path}?v=${avatarCacheBust}` : user.avatar_path}
            alt="Avatar"
            class="w-16 h-16 rounded-full object-cover"
          />
        {:else}
          <div class="w-16 h-16 rounded-full bg-ash-800 flex items-center justify-center">
            <User class="h-8 w-8 text-ash-500" />
          </div>
        {/if}
        <div class="absolute inset-0 rounded-full bg-black/50 opacity-0 group-hover:opacity-100 flex items-center justify-center transition-opacity">
          <Camera class="h-6 w-6 text-white" />
        </div>
      </button>
      <button
        onclick={onAvatarClick}
        class="text-xs text-ash-400 hover:text-crimson-400 sm:hidden"
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
      class="p-2 text-ash-500 hover:text-crimson-400 transition-colors self-start"
      title={m.profile_share()}
    >
      {#if copied}
        <Check class="w-5 h-5 text-emerald-400" />
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
      <span class="text-ash-400">{m.add_player_vekn_id_label()}</span>
      <div class="flex items-center gap-2">
        <span class="text-bone-100 font-mono">{user.vekn_id}</span>
        <button
          onclick={onAbandonVekn}
          class="p-1 text-ash-500 hover:text-crimson-400 transition-colors"
          title={m.profile_abandon_vekn_tooltip()}
        >
          <Unlink class="w-4 h-4" />
        </button>
      </div>
    </div>
  {:else}
    <div class="flex justify-between items-center">
      <span class="text-ash-400">{m.add_player_vekn_id_label()}</span>
      <button
        onclick={onClaimVekn}
        class="px-3 py-1 text-sm bg-crimson-700 hover:bg-crimson-600 text-white rounded transition-colors"
      >
        {m.profile_claim_vekn_title()}
      </button>
    </div>
  {/if}

  <div>
    <label for="edit-country" class="block text-sm font-medium text-ash-400 mb-1">{m.common_country()}</label>
    <select id="edit-country" bind:value={editCountry} onchange={handleCountryChange}
      class="{inputClass}">
      <option value="">{m.user_country_placeholder()}</option>
      {#each sortedCountries as country}
        <option value={country.iso_code}>{country.name} {getCountryFlag(country.iso_code)}</option>
      {/each}
    </select>
  </div>

  <div>
    <label for="edit-city" class="block text-sm font-medium text-ash-400 mb-1">{m.common_city()}</label>
    <CityAutocomplete bind:value={editCity} bind:geonameId={editCityGeonameId} countryCode={editCountry} disabled={!editCountry} onselect={handleCitySelect} />
    {#if !editCountry}
      <p class="mt-1 text-xs text-mist-500">{m.city_select_country_first()}</p>
    {/if}
  </div>

  {#if user.roles.length > 0}
    <div class="flex justify-between items-start">
      <span class="text-ash-400">{m.common_roles()}</span>
      <div class="flex flex-wrap gap-2 justify-end">
        {#each user.roles as role}
          <span class="px-2 py-1 text-xs rounded bg-ash-800 text-bone-100">{role}</span>
        {/each}
      </div>
    </div>
  {/if}
</div>

<!-- Contact Info -->
<div class="p-6 border-t border-ash-800 space-y-4">
  <h3 class="text-sm font-medium text-ash-400 uppercase tracking-wide">{m.profile_contact_info()}</h3>

  {#if isOfficial}
    <div class="p-3 rounded border text-sm banner-blue">
      {#if user.roles?.includes("IC")}
        {m.profile_ic_contact_visibility()}
      {:else}
        {m.profile_official_contact_visibility()}
      {/if}
    </div>
  {/if}

  <div class="space-y-4">
    <div>
      <label for="edit-contact-email" class="block text-sm font-medium text-ash-400 mb-1">{m.profile_contact_email()}</label>
      <input id="edit-contact-email" type="email" bind:value={editContactEmail}
        onblur={() => saveField("contact_email", editContactEmail || undefined)}
        class={inputClass} />
    </div>
    <div>
      <label for="edit-contact-phone" class="block text-sm font-medium text-ash-400 mb-1">{m.profile_phone()}</label>
      <input id="edit-contact-phone" type="tel" bind:value={editContactPhone}
        onblur={() => saveField("contact_phone", editContactPhone || undefined)}
        class={inputClass} />
      <label class="flex items-center gap-2 mt-2 text-sm text-ash-400 cursor-pointer">
        <input type="checkbox" bind:checked={editPhoneIsWhatsapp}
          onchange={() => saveField("phone_is_whatsapp", editPhoneIsWhatsapp)}
          class="rounded border-ash-600 bg-dusk-950 text-crimson-500 focus:ring-crimson-500" />
        {m.profile_phone_is_whatsapp()}
      </label>
    </div>
  </div>
</div>

<!-- Community Links -->
{#if user.vekn_id}
  <div class="p-6 border-t border-ash-800">
    <h3 class="text-sm font-medium text-ash-400 uppercase tracking-wide mb-4">{m.profile_community_links()}</h3>

    {#if !isOfficial}
      <div class="p-3 rounded border text-sm banner-blue mb-4">
        {m.profile_community_links_member()}
      </div>
    {/if}

    <div class="space-y-3">
      {#each editLinks as link, i}
        <div class="border border-ash-700 rounded-lg p-3 space-y-2">
          <div class="flex items-center gap-2">
            <select bind:value={link.type} onchange={saveLinks}
              class="flex-1 px-2 py-2 border border-ash-600 rounded bg-dusk-950 text-ash-200 text-sm">
              {#each LINK_TYPES as lt}
                <option value={lt.value}>{lt.label}</option>
              {/each}
            </select>
            {#if CONTENT_TYPES.has(link.type)}
              <select bind:value={link.language} onchange={saveLinks}
                class="px-2 py-2 border border-ash-600 rounded bg-dusk-950 text-ash-200 text-sm w-32">
                {#each LANGUAGES as lang}
                  <option value={lang.value}>{lang.label}</option>
                {/each}
              </select>
            {/if}
            <button type="button" onclick={() => removeLink(i)}
              class="p-2 text-ash-500 hover:text-crimson-400 transition-colors shrink-0">
              <Trash2 class="w-4 h-4" />
            </button>
          </div>
          <input type="url" bind:value={link.url} placeholder="https://..."
            onblur={saveLinks}
            class="{inputClass} text-sm" />
          <input type="text" bind:value={link.label} placeholder={m.profile_link_label_placeholder()}
            onblur={saveLinks}
            class="{inputClass} text-sm" />
        </div>
      {/each}
    </div>

    {#if editLinks.length < maxLinks}
      <button type="button" onclick={addLink}
        class="mt-3 flex items-center gap-1 text-sm text-crimson-500 hover:text-crimson-400 transition-colors">
        <Plus class="w-4 h-4" />
        {m.profile_add_link()}
      </button>
    {/if}
  </div>
{/if}

<!-- Sponsorship banner for non-members -->
{#if !user.vekn_id && user.country}
  <div class="p-6 border-t border-ash-800">
    <div class="p-3 rounded border text-sm banner-amber">
      {m.profile_sponsorship_banner()}
      <a href="/users?tab=community" class="underline hover:text-amber-200 ml-1">{m.profile_find_coordinator()}</a>
    </div>
  </div>
{/if}
