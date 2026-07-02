<script lang="ts">
  import { Check, Copy, ExternalLink } from "@lucide/svelte";
  import DiscordIcon from "./DiscordIcon.svelte";
  import { showToast } from "$lib/stores/toast.svelte";
  import * as m from '$lib/paraglide/messages.js';

  // Discord's Add Friend flow is username-based and there is no public
  // add-friend deep link, so the primary action copies the username for
  // pasting into Discord; the profile link is a secondary affordance
  // (a friend-request button may appear there if privacy settings allow).
  let { discordId, username = null }: { discordId: string; username?: string | null } = $props();

  let copied = $state(false);

  async function copyUsername() {
    if (!username) return;
    try {
      await navigator.clipboard.writeText(username);
      copied = true;
      setTimeout(() => { copied = false; }, 2000);
      showToast({ type: "success", message: m.discord_username_copied() });
    } catch {
      // Copy is the primary path — never fail silently (the username stays visible to type manually)
      showToast({ type: "error", message: m.discord_copy_failed() });
    }
  }
</script>

{#if username}
  <!-- gap-3: the anchor's expanded hit box (-m-2) reaches into the gap; keep a buffer before the copy button -->
  <span class="inline-flex items-center gap-3 min-w-0 max-w-full">
    <button
      type="button"
      onclick={copyUsername}
      title={m.discord_copy_username({ username })}
      aria-label={m.discord_copy_username({ username })}
      class="inline-flex items-center gap-1 min-w-0 py-2 -my-2 text-link hover:text-link-soft"
    >
      <DiscordIcon class="w-3.5 h-3.5 shrink-0" />
      <span class="truncate">{username}</span>
      {#if copied}
        <Check class="w-3.5 h-3.5 shrink-0" />
      {:else}
        <Copy class="w-3.5 h-3.5 shrink-0" />
      {/if}
    </button>
    <a
      href="https://discord.com/users/{discordId}"
      target="_blank"
      rel="noopener noreferrer"
      title={m.discord_open_profile()}
      aria-label={m.discord_open_profile()}
      class="p-2 -m-2 text-link hover:text-link-soft"
    >
      <ExternalLink class="w-3.5 h-3.5" />
    </a>
  </span>
{:else}
  <a
    href="https://discord.com/users/{discordId}"
    target="_blank"
    rel="noopener noreferrer"
    class="inline-flex items-center gap-1 text-link hover:text-link-soft"
  >
    <DiscordIcon class="w-3.5 h-3.5" />
    <span>{m.profile_contact_discord()}</span>
  </a>
{/if}
