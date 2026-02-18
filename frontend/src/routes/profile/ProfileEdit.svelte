<script lang="ts">
  import { getCountries, getCountryFlag } from "$lib/geonames";
  import CityAutocomplete from "$lib/components/CityAutocomplete.svelte";
  import * as m from '$lib/paraglide/messages.js';

  interface Props {
    user: any;
    error: string | null;
    onSave: (data: { name?: string; nickname?: string; country?: string; city?: string; contact_email?: string; contact_phone?: string }) => Promise<void>;
    onCancel: () => void;
  }
  let { user, error, onSave, onCancel }: Props = $props();

  const countries = getCountries();
  const sortedCountries = Object.values(countries).sort((a, b) => a.name.localeCompare(b.name));

  let saving = $state(false);
  let editName = $state(user.name || "");
  let editNickname = $state(user.nickname || "");
  let editCountry = $state(user.country || "");
  let editCity = $state(user.city || "");
  let editContactEmail = $state(user.contact_email || "");
  let editContactPhone = $state(user.contact_phone || "");

  async function handleSubmit() {
    saving = true;
    await onSave({
      name: editName || undefined,
      nickname: editNickname || undefined,
      country: editCountry || undefined,
      city: editCity || undefined,
      contact_email: editContactEmail || undefined,
      contact_phone: editContactPhone || undefined,
    });
    saving = false;
  }
</script>

<div class="bg-dusk-950 rounded-lg shadow border border-ash-800">
  <div class="p-6 border-b border-ash-800">
    <h2 class="text-xl font-medium text-bone-100">{m.profile_edit_title()}</h2>
  </div>

  <form onsubmit={(e) => { e.preventDefault(); handleSubmit(); }} class="p-6 space-y-4">
    <div>
      <label for="edit-name" class="block text-sm font-medium text-ash-400 mb-1">{m.common_name()}</label>
      <input id="edit-name" type="text" bind:value={editName}
        class="w-full px-3 py-2 border border-ash-600 rounded bg-dusk-950 text-ash-200 focus:ring-2 focus:ring-crimson-500 focus:border-transparent" />
    </div>

    <div>
      <label for="edit-nickname" class="block text-sm font-medium text-ash-400 mb-1">{m.common_nickname()}</label>
      <input id="edit-nickname" type="text" bind:value={editNickname}
        class="w-full px-3 py-2 border border-ash-600 rounded bg-dusk-950 text-ash-200 focus:ring-2 focus:ring-crimson-500 focus:border-transparent" />
    </div>

    <div>
      <label for="edit-country" class="block text-sm font-medium text-ash-400 mb-1">{m.common_country()}</label>
      <select id="edit-country" bind:value={editCountry} onchange={() => { editCity = ""; }}
        class="w-full px-3 py-2 border border-ash-600 rounded bg-dusk-950 text-ash-200 focus:ring-2 focus:ring-crimson-500 focus:border-transparent">
        <option value="">{m.user_country_placeholder()}</option>
        {#each sortedCountries as country}
          <option value={country.iso_code}>{country.name} {getCountryFlag(country.iso_code)}</option>
        {/each}
      </select>
    </div>

    <div>
      <label for="edit-city" class="block text-sm font-medium text-ash-400 mb-1">{m.common_city()}</label>
      <CityAutocomplete bind:value={editCity} countryCode={editCountry} disabled={!editCountry} />
      {#if !editCountry}
        <p class="mt-1 text-xs text-mist-500">{m.city_select_country_first()}</p>
      {/if}
    </div>

    <div class="pt-4 border-t border-ash-800">
      <h3 class="text-sm font-medium text-ash-400 uppercase tracking-wide mb-4">{m.profile_contact_info()}</h3>
      <div class="space-y-4">
        <div>
          <label for="edit-contact-email" class="block text-sm font-medium text-ash-400 mb-1">{m.common_email()}</label>
          <input id="edit-contact-email" type="email" bind:value={editContactEmail}
            class="w-full px-3 py-2 border border-ash-600 rounded bg-dusk-950 text-ash-200 focus:ring-2 focus:ring-crimson-500 focus:border-transparent" />
        </div>
        <div>
          <label for="edit-contact-phone" class="block text-sm font-medium text-ash-400 mb-1">{m.profile_phone()}</label>
          <input id="edit-contact-phone" type="tel" bind:value={editContactPhone}
            class="w-full px-3 py-2 border border-ash-600 rounded bg-dusk-950 text-ash-200 focus:ring-2 focus:ring-crimson-500 focus:border-transparent" />
        </div>
      </div>
    </div>

    {#if error}
      <div class="text-sm text-crimson-400">{error}</div>
    {/if}

    <div class="flex gap-2 pt-4">
      <button type="submit" disabled={saving}
        class="flex-1 px-4 py-2 bg-crimson-700 hover:bg-crimson-600 disabled:bg-ash-700 text-white rounded font-medium transition-colors disabled:cursor-not-allowed">
        {saving ? m.common_saving() : m.common_save()}
      </button>
      <button type="button" onclick={onCancel} disabled={saving}
        class="px-4 py-2 bg-ash-700 hover:bg-ash-600 text-ash-200 rounded font-medium transition-colors disabled:cursor-not-allowed">
        {m.common_cancel()}
      </button>
    </div>
  </form>
</div>
