<script lang="ts">
  import { Plus, Pencil } from "@lucide/svelte";
  import CommunityLinkEditor from "$lib/components/CommunityLinkEditor.svelte";
  import CommunityLinkPills from "$lib/components/CommunityLinkPills.svelte";
  import { updateProfile } from "$lib/stores/auth.svelte";
  import { showToast } from "$lib/stores/toast.svelte";
  import { isOfficial as engineIsOfficial } from "$lib/engine";
  import { COUNTRY_LANGUAGE } from "$lib/data/country-language";
  import { getLocale } from "$lib/paraglide/runtime.js";
  import type { CommunityLink } from "$lib/types";
  import * as m from '$lib/paraglide/messages.js';

  let { user }: { user: any } = $props();

  // Identity, not authority: it only decides which contact-visibility note to show.
  const isOfficial = $derived(engineIsOfficial(user ?? null));

  // svelte-ignore state_referenced_locally
  const initial = { ...user };
  let editContactEmail = $state(initial.contact_email || "");
  let editContactPhone = $state(initial.contact_phone || "");
  let editPhoneIsWhatsapp = $state(initial.phone_is_whatsapp ?? false);

  const editLinks = $derived<CommunityLink[]>(user.community_links ?? []);
  let editing = $state<{ link: CommunityLink | null } | null>(null);

  const defaultLanguage = $derived(COUNTRY_LANGUAGE[user.country] || getLocale());
  const maxLinks = $derived(isOfficial ? 10 : 5);

  let lastSaved: Record<string, unknown> = {
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

  function saveLinks(links: CommunityLink[], moderated?: { url: string; state: string }) {
    editing = null;
    const payload = moderated
      ? links.map(l => (l.url === moderated.url ? { ...l, state: moderated.state } : l))
      : links;
    saveField("community_links", payload);
  }

  const editedIndex = $derived(
    editing?.link ? editLinks.findIndex(l => l.url === editing!.link!.url) : -1
  );

  const inputClass = "w-full px-3 py-2 border border-line-strong rounded bg-surface-card text-ink-bright focus:ring-2 focus:ring-accent focus:border-transparent";
</script>

<div class="space-y-4">
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

{#if user.vekn_id}
  <div class="mt-6 pt-6 border-t border-line">
    <h3 class="text-sm font-medium text-ink-muted uppercase tracking-wide mb-4">{m.profile_community_links()}</h3>

    {#if !isOfficial}
      <div class="p-3 rounded border text-sm banner-info mb-4">
        {m.profile_community_links_member()}
      </div>
    {/if}

    <div class="space-y-2">
      {#each editLinks as link (link.url + link.type)}
        <div class="flex items-center justify-between gap-2 border border-line-strong rounded-lg p-2">
          <CommunityLinkPills links={[link]} />
          <button type="button" onclick={() => { editing = { link }; }}
            aria-label={m.community_edit_link()}
            class="grid place-items-center w-11 h-11 shrink-0 text-ink-faint hover:text-link transition-colors">
            <Pencil class="w-4 h-4" />
          </button>
        </div>
      {/each}
    </div>

    {#if editLinks.length < maxLinks}
      <button type="button" onclick={() => { editing = { link: null }; }}
        class="mt-3 flex items-center gap-1 min-h-11 text-sm text-link hover:text-link-soft transition-colors">
        <Plus class="w-4 h-4" />
        {m.profile_add_link()}
      </button>
    {/if}
  </div>
{/if}

{#if editing}
  <CommunityLinkEditor
    link={editing.link}
    ownerCountry={user.country || null}
    {defaultLanguage}
    onclose={() => { editing = null; }}
    onsave={(link, state) => saveLinks(
      editedIndex >= 0
        ? editLinks.map((l, i) => (i === editedIndex ? link : l))
        : [...editLinks, link],
      state ? { url: link.url, state } : undefined
    )}
    ondelete={editedIndex >= 0
      ? () => saveLinks(editLinks.filter((_, i) => i !== editedIndex))
      : undefined}
  />
{/if}
