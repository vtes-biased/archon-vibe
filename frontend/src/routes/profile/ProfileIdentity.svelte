<script lang="ts">
  import { User, Camera, Unlink, Share2, Check, CloudOff } from "@lucide/svelte";
  import { getSortedCountries, getCountryFlag } from "$lib/geonames";
  import CityAutocomplete from "$lib/components/CityAutocomplete.svelte";
  import Button from "$lib/components/Button.svelte";
  import { updateProfile } from "$lib/stores/auth.svelte";
  import { showToast } from "$lib/stores/toast.svelte";
  import { canChangeCountry } from "$lib/engine";
  import Badge from "$lib/components/Badge.svelte";
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

  const sortedCountries = getSortedCountries();
  let copied = $state(false);

  // An official can't move their own country: that would shift the scope their
  // FULL projection is computed for, an authority self-service never has.
  const isCountryLocked = $derived(!!user && !canChangeCountry(user, user).allowed);

  // svelte-ignore state_referenced_locally
  const initial = { ...user };
  let editName = $state(initial.name || "");
  let editNickname = $state(initial.nickname || "");
  let editCountry = $state(initial.country || "");
  let editCity = $state(initial.city || "");
  let editCityGeonameId = $state<number | null>(initial.city_geoname_id ?? null);

  let lastSaved: Record<string, unknown> = {
    name: initial.name || "",
    nickname: initial.nickname || "",
    country: initial.country || "",
    city: initial.city || "",
    city_geoname_id: initial.city_geoname_id ?? null,
  };

  async function saveField(field: string, value: unknown) {
    if (lastSaved[field] === value) return;
    const ok = await updateProfile({ [field]: value });
    if (ok) {
      lastSaved[field] = value;
    } else {
      showToast({ type: "error", message: m.profile_save_error() });
    }
  }

  async function saveFields(data: Record<string, unknown>) {
    const changed: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(data)) {
      if (lastSaved[k] !== v) changed[k] = v;
    }
    if (Object.keys(changed).length === 0) return;
    const ok = await updateProfile(changed);
    if (ok) {
      for (const [k, v] of Object.entries(changed)) lastSaved[k] = v;
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

<div class="p-6 space-y-4">
  {#if user.vekn_id}
    <div class="flex justify-between items-center">
      <span class="text-ink-muted">{m.add_player_vekn_id_label()}</span>
      <div class="flex items-center gap-2">
        {#if veknSyncPending}
          <Badge kind="status" tone="pending" title={m.vekn_sync_pending_hint()}>
            <CloudOff class="w-3 h-3" aria-hidden="true" />
            {m.vekn_sync_pending_member()}
          </Badge>
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
    <!-- Not gated on country: a brand-new user without one still needs the
         pointer; the community page prompts for country. -->
    <div class="p-3 rounded border text-sm banner-warn">
      {m.profile_sponsorship_banner()}
      <a href="/users?tab=community&sponsor=1" class="underline hover:text-warn ml-1">{m.profile_find_coordinator()}</a>
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
