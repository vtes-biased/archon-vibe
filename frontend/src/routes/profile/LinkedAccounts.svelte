<script lang="ts">
  import { KeyRound } from "lucide-svelte";
  import { isPasskeySupported } from "$lib/stores/passkeys.svelte";
  import DiscordIcon from "$lib/components/DiscordIcon.svelte";
  import * as m from '$lib/paraglide/messages.js';

  interface Props {
    hasDiscord: boolean;
    discordUsername: string | null;
    hasPasskey: boolean;
    discordMessage: string;
    discordError: string;
    passkeyMessage: string;
    error: string | null;
    onLinkDiscord: () => void;
    onRegisterPasskey: () => void;
  }
  let {
    hasDiscord, discordUsername, hasPasskey,
    discordMessage, discordError, passkeyMessage, error,
    onLinkDiscord, onRegisterPasskey,
  }: Props = $props();

  let registeringPasskey = $state(false);

  async function handleRegisterPasskey() {
    registeringPasskey = true;
    await onRegisterPasskey();
    registeringPasskey = false;
  }
</script>

<div class="p-6 border-t border-ash-800 space-y-4">
  <h3 class="text-sm font-medium text-ash-400 uppercase tracking-wide">{m.profile_linked_accounts()}</h3>

  <!-- Discord -->
  <div class="flex items-center justify-between">
    <div class="flex items-center gap-3">
      <DiscordIcon class="w-5 h-5 text-[#5865F2]" />
      <div>
        <p class="text-bone-100">Discord</p>
        {#if hasDiscord && discordUsername}
          <p class="text-sm text-ash-400">{discordUsername}</p>
        {:else}
          <p class="text-sm text-ash-400">{m.profile_not_linked()}</p>
        {/if}
      </div>
    </div>
    {#if !hasDiscord}
      <button onclick={onLinkDiscord}
        class="px-4 py-2 bg-[#5865F2] hover:bg-[#4752C4] text-white rounded font-medium transition-colors">
        {m.profile_link()}
      </button>
    {:else}
      <span class="px-3 py-1 text-sm text-green-500 bg-green-500/10 rounded">{m.profile_linked()}</span>
    {/if}
  </div>
  {#if discordMessage}
    <p class="text-sm text-green-500">{discordMessage}</p>
  {/if}
  {#if discordError}
    <p class="text-sm text-crimson-400">{discordError}</p>
  {/if}

  <!-- Passkey -->
  {#if isPasskeySupported()}
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-3">
        <KeyRound class="w-5 h-5 text-ash-400" />
        <div>
          <p class="text-bone-100">Passkey</p>
          <p class="text-sm text-ash-400">
            {hasPasskey ? m.profile_passkey_configured() : m.profile_passkey_not_setup()}
          </p>
        </div>
      </div>
      {#if !hasPasskey}
        <button onclick={handleRegisterPasskey} disabled={registeringPasskey}
          class="px-4 py-2 bg-ash-800 hover:bg-ash-700 disabled:bg-ash-700 text-bone-100 rounded font-medium transition-colors disabled:cursor-not-allowed">
          {registeringPasskey ? m.profile_passkey_adding() : m.common_add()}
        </button>
      {:else}
        <span class="px-3 py-1 text-sm text-green-500 bg-green-500/10 rounded">{m.profile_passkey_active()}</span>
      {/if}
    </div>
    {#if passkeyMessage}
      <p class="text-sm text-green-500">{passkeyMessage}</p>
    {/if}
  {/if}

  {#if error}
    <p class="text-sm text-crimson-400">{error}</p>
  {/if}
</div>
