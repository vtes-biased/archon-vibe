<script lang="ts">
  import { User, Camera, SquarePen, Unlink } from "lucide-svelte";
  import { getCountries, getCountryFlag } from "$lib/geonames";
  import * as m from '$lib/paraglide/messages.js';

  interface Props {
    user: any;
    avatarCacheBust: number;
    onEdit: () => void;
    onAvatarClick: () => void;
    onAbandonVekn: () => void;
    onClaimVekn: () => void;
  }
  let { user, avatarCacheBust, onEdit, onAvatarClick, onAbandonVekn, onClaimVekn }: Props = $props();

  const countries = getCountries();

  function formatLocation(country: string | null, city?: string | null): string | null {
    if (!country) return null;
    const parts: string[] = [];
    if (city) parts.push(city);
    const countryName = countries[country]?.name || country;
    parts.push(`${getCountryFlag(country)} ${countryName}`);
    return parts.join(", ");
  }
</script>

<!-- Header -->
<div class="p-6 border-b border-ash-800">
  <div class="flex items-center justify-between">
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
      <div>
        <h2 class="text-xl font-medium text-bone-100">
          {user.name || m.profile_anonymous()}
        </h2>
        {#if user.nickname}
          <p class="text-ash-400">"{user.nickname}"</p>
        {/if}
      </div>
    </div>
    <button
      onclick={onEdit}
      class="p-2 text-ash-500 hover:text-crimson-400 transition-colors"
      title={m.profile_edit_btn()}
    >
      <SquarePen class="w-5 h-5" />
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

  {#if user.country}
    {@const location = formatLocation(user.country, user.city)}
    <div class="flex justify-between">
      <span class="text-ash-400">{m.profile_location()}</span>
      <span class="text-bone-100">{location}</span>
    </div>
  {/if}

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
{#if user.contact_email || user.contact_phone}
  <div class="p-6 border-t border-ash-800 space-y-4">
    <h3 class="text-sm font-medium text-ash-400 uppercase tracking-wide">{m.profile_contact()}</h3>
    {#if user.contact_email}
      <div class="flex justify-between">
        <span class="text-ash-400">{m.common_email()}</span>
        <a href="mailto:{user.contact_email}" class="text-crimson-500 hover:text-crimson-400">{user.contact_email}</a>
      </div>
    {/if}
    {#if user.contact_phone}
      <div class="flex justify-between">
        <span class="text-ash-400">{m.profile_phone()}</span>
        <span class="text-bone-100">{user.contact_phone}</span>
      </div>
    {/if}
  </div>
{/if}
