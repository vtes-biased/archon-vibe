<script lang="ts">
  import type { User } from "$lib/types";
  import { deobfuscateContact } from "$lib/contact";
  import DiscordContact from "$lib/components/DiscordContact.svelte";
  import CommunityLinkPills from "$lib/components/CommunityLinkPills.svelte";
  import * as m from '$lib/paraglide/messages.js';

  let { user }: { user: User } = $props();

  const email = $derived(deobfuscateContact(user.contact_email));
  const phone = $derived(deobfuscateContact(user.contact_phone));
</script>

<section>
  <h2 class="text-lg font-semibold text-ink-bright mb-3">{m.profile_contact()}</h2>
  <div class="bg-surface-card border border-line rounded-lg p-4 space-y-1 text-sm">
    {#if email}
      <div><a href="mailto:{email}" class="text-link hover:text-link-soft">{email}</a></div>
    {/if}
    {#if user.discord_id}
      <div><DiscordContact discordId={user.discord_id} username={user.contact_discord} /></div>
    {/if}
    {#if phone}
      {#if user.phone_is_whatsapp}
        <a href="https://wa.me/{phone.replace(/[^0-9]/g, '')}" target="_blank" rel="noopener noreferrer" class="text-link hover:text-link-soft">WhatsApp: {phone}</a>
      {:else}
        <div class="text-ink">{phone}</div>
      {/if}
    {/if}
    {#if !email && !user.discord_id && !phone}
      <p class="text-ink-faint">{m.user_detail_no_contact()}</p>
    {/if}
  </div>
</section>

{#if user.community_links?.length}
  <section class="mt-6">
    <h2 class="text-lg font-semibold text-ink-bright mb-3">{m.profile_community_links()}</h2>
    <div class="bg-surface-card border border-line rounded-lg p-4">
      <CommunityLinkPills links={user.community_links} />
    </div>
  </section>
{/if}
