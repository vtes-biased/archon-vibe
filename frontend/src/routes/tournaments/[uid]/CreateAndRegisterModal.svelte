<script lang="ts">
  import type { Tournament, User } from "$lib/types";
  import { getFilteredUsers, getUser, isUserCurrentlySanctioned } from "$lib/db";
  import { getAuthState } from "$lib/stores/auth.svelte";
  import { getCountryFlag } from "$lib/geonames";
  import Button from "$lib/components/Button.svelte";
  import { TriangleAlert, Flower2, Ban } from "@lucide/svelte";
  import { sponsorVeknMember, createUser, isOnline, ApiError } from "$lib/api";
  import { showToast } from "$lib/stores/toast.svelte";
  import { canSponsorVekn, type TournamentEventType } from "$lib/engine";
  import * as m from '$lib/paraglide/messages.js';

  let {
    tournament,
    doAction,
    addPlayerByUser,
    showCreateModal = $bindable(),
    sponsorTarget = $bindable(),
  }: {
    tournament: Tournament;
    doAction: (action: TournamentEventType, body?: any) => Promise<string | null>;
    // Parent add path: register, or route a no-VEKN member here as sponsorTarget.
    addPlayerByUser: (user: User) => Promise<void>;
    showCreateModal: boolean;
    sponsorTarget: User | null;
  } = $props();

  const auth = getAuthState();

  function focusOnMount(node: HTMLElement) {
    node.focus();
  }

  // Sponsor modal state
  let sponsorLoading = $state(false);
  // Deliberately cross-country: a visiting official can sponsor newcomers abroad.
  const sponsorEligible = $derived(canSponsorVekn(auth.user).allowed);

  // Create-and-register modal state
  let createName = $state('');
  let createEmail = $state('');
  // '' is equivalent to tournament.country: every use falls back through
  // `createCountry || tournament.country || ''` (reset re-syncs it anyway).
  let createCountry = $state('');
  let createLoading = $state(false);
  // Dedup review: look-alike members surfaced before a create is allowed to mint.
  let createCandidates = $state<User[]>([]);
  let candidateSuspended = $state<Set<string>>(new Set());
  let dedupHeading = $state<HTMLElement | null>(null);
  // Deceased look-alikes are addable (backfilling a past event) but must be
  // confirmed — mirror AddPlayerForm's warn-not-block guard on the new add paths.
  let pendingDeceased = $state<User | null>(null);

  // Announce the form→review swap to keyboard/SR users by moving focus to the
  // review heading (the DOM changes in place with no navigation otherwise).
  $effect(() => {
    if (createCandidates.length > 0) dedupHeading?.focus();
  });

  function resetCreateModal() {
    showCreateModal = false;
    createName = '';
    createEmail = '';
    createCountry = tournament.country ?? '';
    createCandidates = [];
    candidateSuspended = new Set();
  }

  async function handleSponsorAndRegister() {
    if (!sponsorTarget || !sponsorEligible) return;
    sponsorLoading = true;
    try {
      const result = await sponsorVeknMember(sponsorTarget.uid);
      showToast({ type: "success", message: result.message });
      await doAction("AddPlayer", { user_uid: sponsorTarget.uid, vekn_id: result.user.vekn_id });
      sponsorTarget = null;
    } catch {
      // Error toast shown by apiRequest
    } finally {
      sponsorLoading = false;
    }
  }

  // Picking a surfaced duplicate pivots into the normal add path (register, or
  // sponsor+register for a no-VEKN member) — no new member is minted. Suspended
  // rows are non-interactive; deceased ones route through the confirm.
  function chooseCandidate(user: User) {
    resetCreateModal();
    if (user.deceased_at) { pendingDeceased = user; return; }
    addPlayerByUser(user);
  }

  function confirmDeceasedAdd() {
    const u = pendingDeceased;
    pendingDeceased = null;
    if (u) addPlayerByUser(u);
  }

  async function handleCreateAndRegister() {
    if (!createName.trim() || !createEmail.trim()) return;

    if (!isOnline()) {
      // Offline mode: temp player, no dedup (the member list isn't authoritative
      // offline and the WASM engine reconciles on go-online).
      createLoading = true;
      try {
        const tempUid = crypto.randomUUID();
        const tempVeknId = `TEMP-${tempUid.slice(0, 8)}`;
        const { addOfflinePlayer } = await import('$lib/stores/offline.svelte');
        await addOfflinePlayer(tournament.uid, {
          temp_uid: tempUid,
          name: createName.trim(),
          vekn_id: tempVeknId,
          email: createEmail.trim(),
        });
        await doAction('AddPlayer', { user_uid: tempUid, vekn_id: tempVeknId });
        resetCreateModal();
      } catch {
        // Error toast shown by apiRequest
      } finally {
        createLoading = false;
      }
      return;
    }

    // Guard the whole online path (dedup lookup + mint) so a double-tap can't
    // fire two creates during the await, and the review button never sticks.
    createLoading = true;
    try {
      // Dedup gate: surface same-country name look-alikes (incl. accountless
      // VEKN-synced members — the member projection carries them all) before
      // minting. Email dedup is the server's job (create_user 409, cross-country
      // authoritative). Skip once the review has been shown and dismissed.
      if (createCandidates.length === 0) {
        const country = createCountry || tournament.country || '';
        const registered = new Set(tournament.players?.map(p => p.user_uid) ?? []);
        const byName = await getFilteredUsers(country || undefined, undefined, createName.trim());
        const matches = byName.filter(u => !registered.has(u.uid)).slice(0, 8);
        if (matches.length > 0) {
          createCandidates = matches;
          const susp = new Set<string>();
          await Promise.all(matches.map(async (u) => {
            if (await isUserCurrentlySanctioned(u.uid)) susp.add(u.uid);
          }));
          candidateSuspended = susp;
          return;
        }
      }

      // No look-alike, or the official dismissed the review → mint.
      const newUser = await createUser(
        createName.trim(), createCountry || tournament.country || '', null, null, createEmail.trim(),
        undefined, null, { suppressErrorToast: true }
      );
      await doAction("AddPlayer", { user_uid: newUser.uid, vekn_id: newUser.vekn_id });
      resetCreateModal();
    } catch (e) {
      // Cross-country email collision the client couldn't see locally: the
      // backend 409 carries the matched uid — pivot to sponsor+register it.
      if (e instanceof ApiError && e.code === 'user.email_exists' && e.params?.uid) {
        const matched = await getUser(e.params.uid);
        if (matched) { chooseCandidate(matched); return; }
        // Match not in the local mirror yet: keep the modal, tell them to search.
        showToast({ type: 'error', message: m.create_dedup_email_exists_search() });
        return;
      }
      if (e instanceof ApiError) showToast({ type: 'error', message: e.message });
    } finally {
      createLoading = false;
    }
  }
</script>

<!-- Sponsor & Register Modal -->
{#if sponsorTarget}
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
  <div
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4"
    role="presentation"
    onclick={() => { if (!sponsorLoading) sponsorTarget = null; }}
    onkeydown={(e) => { if (e.key === 'Escape' && !sponsorLoading) sponsorTarget = null; }}
  >
    <div
      use:focusOnMount
      class="bg-surface-card border border-line-strong rounded-lg p-6 max-w-sm w-full mx-4 space-y-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="sponsor-modal-title"
      tabindex="-1"
      onclick={(e) => e.stopPropagation()}
      onkeydown={(e) => e.stopPropagation()}
    >
      <h3 id="sponsor-modal-title" class="text-lg font-medium text-ink-strong">{m.vekn_sponsor_to_register_title()}</h3>
      <p class="text-sm text-ink">{m.vekn_sponsor_to_register_message({ name: sponsorTarget.name })}</p>
      {#if !sponsorEligible}
        <p class="text-sm text-warn inline-flex items-start gap-1.5">
          <TriangleAlert class="w-4 h-4 shrink-0 mt-0.5" />
          {m.vekn_sponsor_ineligible()}
        </p>
      {/if}
      <div class="flex gap-2 justify-end">
        <Button
          variant="ghost"
          size="lg"
          onclick={() => sponsorTarget = null}
        >{m.common_cancel()}</Button>
        <Button
          variant="primary"
          size="lg"
          loading={sponsorLoading}
          disabled={!sponsorEligible}
          onclick={handleSponsorAndRegister}
        >{m.vekn_sponsor_and_register()}</Button>
      </div>
    </div>
  </div>
{/if}

<!-- Create & Register Modal -->
{#if showCreateModal}
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
  <div
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4"
    role="presentation"
    onclick={() => { if (!createLoading) resetCreateModal(); }}
    onkeydown={(e) => { if (e.key === 'Escape' && !createLoading) resetCreateModal(); }}
  >
    <div
      use:focusOnMount
      class="bg-surface-card border border-line-strong rounded-lg p-6 max-w-sm w-full mx-4 space-y-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="create-modal-title"
      tabindex="-1"
      onclick={(e) => e.stopPropagation()}
      onkeydown={(e) => e.stopPropagation()}
    >
      {#if createCandidates.length > 0}
        <!-- Dedup review: pick an existing member instead of minting a duplicate -->
        <h3 id="create-modal-title" bind:this={dedupHeading} tabindex="-1" class="text-lg font-medium text-ink-strong outline-none">{m.create_dedup_title()}</h3>
        <p class="text-sm text-ink">{m.create_dedup_message()}</p>
        <div class="border border-line-strong rounded-lg divide-y divide-line max-h-56 overflow-y-auto">
          {#each createCandidates as u}
            {@const isSuspended = candidateSuspended.has(u.uid)}
            <button
              onclick={() => !isSuspended && chooseCandidate(u)}
              disabled={isSuspended}
              class="w-full min-h-[44px] px-3 py-2 text-left text-sm transition-colors inline-flex items-center gap-1 {isSuspended ? 'text-ink-faint cursor-not-allowed' : 'text-ink-bright hover:bg-surface-hover'}"
            >
              {#if u.country}<span class="mr-1">{getCountryFlag(u.country)}</span>{/if}{u.name}
              {#if u.deceased_at}
                <Flower2 class="w-3.5 h-3.5 text-ink-muted ml-1" />
              {/if}
              {#if u.vekn_id}
                <span class="text-ink-faint ml-1">({u.vekn_id})</span>
              {:else}
                <span class="inline-flex items-center gap-0.5 ml-1 text-xs text-warn">
                  <TriangleAlert class="w-3 h-3" />{m.add_player_no_vekn_id()}
                </span>
              {/if}
              {#if isSuspended}
                <Ban class="w-3.5 h-3.5 text-link ml-1" />
                <span class="text-xs text-link">{m.error_suspended_cannot_register()}</span>
              {/if}
            </button>
          {/each}
        </div>
        <div class="flex gap-2 justify-end">
          <Button variant="ghost" size="lg" onclick={resetCreateModal}>{m.common_cancel()}</Button>
          <Button
            variant="primary"
            size="lg"
            loading={createLoading}
            onclick={handleCreateAndRegister}
          >{m.create_dedup_create_new()}</Button>
        </div>
      {:else}
        <h3 id="create-modal-title" class="text-lg font-medium text-ink-strong">{m.create_and_register_title()}</h3>
        <p class="text-sm text-ink">{m.create_and_register_message()}</p>
        <div class="space-y-2">
          <input
            type="text"
            bind:value={createName}
            placeholder={m.offline_player_name()}
            class="w-full px-3 py-2 bg-surface-hover border border-line-strong rounded text-sm text-ink-strong placeholder-ink-faint"
          />
          <input
            type="email"
            bind:value={createEmail}
            placeholder={m.common_email()}
            class="w-full px-3 py-2 bg-surface-hover border border-line-strong rounded text-sm text-ink-strong placeholder-ink-faint"
          />
        </div>
        <div class="flex gap-2 justify-end">
          <Button
            variant="ghost"
            size="lg"
            onclick={resetCreateModal}
          >{m.common_cancel()}</Button>
          <Button
            variant="primary"
            size="lg"
            loading={createLoading}
            disabled={!createName.trim() || !createEmail.trim()}
            onclick={handleCreateAndRegister}
          >{m.create_and_register_btn()}</Button>
        </div>
      {/if}
    </div>
  </div>
{/if}

<!-- Deceased-member add confirmation (dedup pick / email pivot) -->
{#if pendingDeceased}
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
  <div
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4"
    role="presentation"
    onclick={() => pendingDeceased = null}
    onkeydown={(e) => { if (e.key === 'Escape') pendingDeceased = null; }}
  >
    <div
      use:focusOnMount
      class="bg-surface-card border border-line-strong rounded-lg p-6 max-w-sm w-full mx-4 space-y-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="deceased-add-title"
      tabindex="-1"
      onclick={(e) => e.stopPropagation()}
      onkeydown={(e) => e.stopPropagation()}
    >
      <h3 id="deceased-add-title" class="text-lg font-medium text-ink-strong inline-flex items-center gap-2">
        <Flower2 class="w-5 h-5 text-ink-muted" aria-hidden="true" />
        {m.deceased_badge()}
      </h3>
      <p class="text-sm text-ink">{m.add_player_deceased_warn({ name: pendingDeceased.name })}</p>
      <div class="flex gap-2 justify-end">
        <Button variant="ghost" size="lg" onclick={() => pendingDeceased = null}>{m.common_cancel()}</Button>
        <Button variant="primary" size="lg" onclick={confirmDeceasedAdd}>{m.add_player_deceased_confirm()}</Button>
      </div>
    </div>
  </div>
{/if}
