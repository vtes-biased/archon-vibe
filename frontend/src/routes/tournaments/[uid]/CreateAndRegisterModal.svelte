<script lang="ts">
  import type { Tournament, User } from "$lib/types";
  import { getFilteredUsers, getUser, getRegistrationBarredUids } from "$lib/db";
  import { getAuthState } from "$lib/stores/auth.svelte";
  import { isOffline, addOfflinePlayer } from "$lib/stores/offline.svelte";
  import { getCountryFlag } from "$lib/geonames";
  import Button from "$lib/components/Button.svelte";
  import { TriangleAlert, Flower2, Ban } from "@lucide/svelte";
  import { sponsorVeknMember, createUser, ApiError } from "$lib/api";
  import { showToast } from "$lib/stores/toast.svelte";
  import { toUserMessage } from "$lib/errors";
  import { canSponsorMember, type TournamentEventType } from "$lib/engine";
  import { dialogPanel } from "$lib/actions/dialog";
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

  let sponsorLoading = $state(false);
  // Minting a member and issuing a VEKN ID are one authority: officials-only,
  // deliberately cross-country — the copy states the rule rather than hiding
  // the option, so an organizer who can't act knows who can.
  const canSponsor = $derived(canSponsorMember(auth.user).allowed);
  // The device lock, not browser connectivity — must match the fact doAction
  // uses to skip the server POST (tournament-actions.ts), or a disconnected
  // device mints a temp player/user stub go-online will never reconcile.
  const offlineCreate = $derived(isOffline(tournament.uid));

  let createName = $state('');
  let createEmail = $state('');
  // Offline only: a player who knows their VEKN ID gives go-online an exact
  // match instead of falling back to email.
  let createVeknId = $state('');
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
    createVeknId = '';
    createCountry = tournament.country ?? '';
    createCandidates = [];
    candidateSuspended = new Set();
  }

  async function handleSponsorAndRegister() {
    if (!sponsorTarget || !canSponsor) return;
    sponsorLoading = true;
    try {
      const result = await sponsorVeknMember(sponsorTarget.uid);
      showToast({ type: "success", message: result.message });
      // doAction reports rather than throws: closing here would claim a success
      // the organizer didn't get, after a VEKN ID has already been allocated.
      const err = await doAction("AddPlayer", { user_uid: sponsorTarget.uid, vekn_id: result.user.vekn_id });
      if (err) { showToast({ type: 'error', message: err }); return; }
      sponsorTarget = null;
    } catch {
      // Error toast shown by apiRequest
    } finally {
      sponsorLoading = false;
    }
  }

  // Picking a surfaced duplicate pivots into the normal add path (register, or
  // sponsor+register) — no new member is minted. Suspended rows are
  // non-interactive; deceased ones route through the confirm.
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
    if (!createName.trim() || !createEmail.trim() || !canSponsor) return;

    // Guard the whole path (dedup lookup + mint) so a double-tap can't fire two
    // creates during the await, and the review button never sticks.
    createLoading = true;
    try {
      // A typed VEKN ID that already belongs to someone was never a create:
      // go-online matches on vekn_id first and never re-checks the name, so a
      // transposed digit binds seat, results and ratings to another member.
      const typedVekn = createVeknId.trim();
      if (typedVekn) {
        const holder = (await getFilteredUsers(undefined, undefined, typedVekn))
          .find(u => u.vekn_id === typedVekn);
        if (holder) { chooseCandidate(holder); return; }
      }

      // Dedup gate: surface same-country look-alikes before minting. Runs
      // offline too — go-online matches on email alone in batch, so an
      // unreviewed offline create mints a duplicate account.
      if (createCandidates.length === 0) {
        const country = createCountry || tournament.country || '';
        const registered = new Set(tournament.players?.map(p => p.user_uid) ?? []);
        const search = async (c: string | undefined) =>
          (await getFilteredUsers(c, undefined, createName.trim())).filter(u => !registered.has(u.uid));
        let matches = await search(country || undefined);
        // Offline there's no server-side email 409 behind this, so a
        // cross-country duplicate would go uncaught — and a visiting player is
        // exactly who an offline event collects; widen rather than miss them.
        if (matches.length === 0 && offlineCreate && country) matches = await search(undefined);
        matches = matches.slice(0, 8);
        if (matches.length > 0) {
          createCandidates = matches;
          candidateSuspended = await getRegistrationBarredUids();
          return;
        }
      }

      if (offlineCreate) {
        // No server to mint against: a temp player the go-online push resolves.
        const tempUid = crypto.randomUUID();
        const veknId = typedVekn || `TEMP-${tempUid.slice(0, 8)}`;
        await addOfflinePlayer(tournament.uid, {
          temp_uid: tempUid,
          name: createName.trim(),
          vekn_id: veknId,
          email: createEmail.trim(),
        });
        const offlineErr = await doAction('AddPlayer', { user_uid: tempUid, vekn_id: veknId });
        if (offlineErr) { showToast({ type: 'error', message: offlineErr }); return; }
        resetCreateModal();
        return;
      }

      // No look-alike, or the official dismissed the review → mint.
      const newUser = await createUser(
        createName.trim(), createCountry || tournament.country || '', null, null, createEmail.trim(),
        undefined, null, { suppressErrorToast: true }
      );
      // The member now exists: keep the modal open on a failed add so the
      // organizer can retry rather than watch it close on a half-done job.
      const addErr = await doAction("AddPlayer", { user_uid: newUser.uid, vekn_id: newUser.vekn_id });
      if (addErr) { showToast({ type: 'error', message: addErr }); return; }
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
      // Offline the engine throws EngineError, not ApiError — an ApiError-only
      // toast would leave the organizer with a modal that just doesn't respond.
      showToast({ type: 'error', message: toUserMessage(e, m.tournament_error_action()) });
    } finally {
      createLoading = false;
    }
  }
</script>

{#if sponsorTarget}
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
  <div
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4"
    role="presentation"
    onclick={() => { if (!sponsorLoading) sponsorTarget = null; }}
    onkeydown={(e) => { if (e.key === 'Escape' && !sponsorLoading) sponsorTarget = null; }}
  >
    <div
      use:dialogPanel={() => { if (!sponsorLoading) sponsorTarget = null; }}
      class="bg-surface-card border border-line-strong rounded-lg p-6 max-w-sm w-full mx-4 space-y-4 max-h-[85dvh] overflow-y-auto"
      role="dialog"
      aria-modal="true"
      aria-labelledby="sponsor-modal-title"
      tabindex="-1"
      onclick={(e) => e.stopPropagation()}
      onkeydown={(e) => e.stopPropagation()}
    >
      <h3 id="sponsor-modal-title" class="text-lg font-medium text-ink-strong">{m.vekn_sponsor_to_register_title()}</h3>
      {#if !canSponsor}
        <!-- Nothing to offer this organizer: state the rule and who can act,
             rather than leaving a dead confirm button on the screen. -->
        <p class="text-sm text-ink inline-flex items-start gap-1.5">
          <TriangleAlert class="w-4 h-4 shrink-0 mt-0.5 text-warn" />
          {m.official_required_to_add_player()}
        </p>
        <div class="flex justify-end">
          <Button variant="primary" size="lg" onclick={() => sponsorTarget = null}>{m.common_close()}</Button>
        </div>
      {:else}
        <p class="text-sm text-ink">{m.vekn_sponsor_to_register_message({ name: sponsorTarget.name })}</p>
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
            disabled={!canSponsor}
            onclick={handleSponsorAndRegister}
          >{m.vekn_sponsor_and_register()}</Button>
        </div>
      {/if}
    </div>
  </div>
{/if}

{#if showCreateModal}
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
  <div
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4"
    role="presentation"
    onclick={() => { if (!createLoading) resetCreateModal(); }}
    onkeydown={(e) => { if (e.key === 'Escape' && !createLoading) resetCreateModal(); }}
  >
    <div
      use:dialogPanel={() => { if (!createLoading) resetCreateModal(); }}
      class="bg-surface-card border border-line-strong rounded-lg p-6 max-w-sm w-full mx-4 space-y-4 max-h-[85dvh] overflow-y-auto"
      role="dialog"
      aria-modal="true"
      aria-labelledby="create-modal-title"
      tabindex="-1"
      onclick={(e) => e.stopPropagation()}
      onkeydown={(e) => e.stopPropagation()}
    >
      {#if !canSponsor}
        <!-- Explain instead of offering a form that can never be submitted: a
             filled-in name and email followed by a dead button teaches nothing. -->
        <h3 id="create-modal-title" class="text-lg font-medium text-ink-strong">{m.create_and_register_title()}</h3>
        <p class="text-sm text-ink inline-flex items-start gap-1.5">
          <TriangleAlert class="w-4 h-4 shrink-0 mt-0.5 text-warn" />
          {m.official_required_to_add_player()}
        </p>
        <div class="flex justify-end">
          <Button variant="primary" size="lg" onclick={resetCreateModal}>{m.common_close()}</Button>
        </div>
      {:else if createCandidates.length > 0}
        <h3 id="create-modal-title" bind:this={dedupHeading} tabindex="-1" class="text-lg font-medium text-ink-strong outline-none">{m.create_dedup_title()}</h3>
        <p class="text-sm text-ink">{m.create_dedup_message()}</p>
        <div class="border border-line-strong rounded-lg divide-y divide-line max-h-56 overflow-y-auto">
          {#each createCandidates as u}
            {@const isSuspended = candidateSuspended.has(u.uid)}
            <!-- Sponsoring a VEKN-less candidate needs the server, so offline the
                 pick would dead-end on a network failure — show it, don't offer it. -->
            {@const needsServer = offlineCreate && !u.vekn_id}
            {@const blocked = isSuspended || needsServer}
            <button
              onclick={() => !blocked && chooseCandidate(u)}
              disabled={blocked}
              class="w-full min-h-[44px] px-3 py-2 text-left text-sm transition-colors inline-flex items-center gap-1 {blocked ? 'text-ink-faint cursor-not-allowed' : 'text-ink-bright hover:bg-surface-hover'}"
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
              {:else if needsServer}
                <span class="text-xs text-link ml-1">{m.error_action_requires_online()}</span>
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
          <!-- Placeholders vanish on the first keystroke: name the fields too. -->
          <input
            type="text"
            bind:value={createName}
            aria-label={m.offline_player_name()}
            placeholder={m.offline_player_name()}
            class="w-full px-3 py-2 bg-surface-hover border border-line-strong rounded text-sm text-ink-strong placeholder-ink-faint"
          />
          <input
            type="email"
            bind:value={createEmail}
            aria-label={m.common_email()}
            placeholder={m.common_email()}
            class="w-full px-3 py-2 bg-surface-hover border border-line-strong rounded text-sm text-ink-strong placeholder-ink-faint"
          />
          {#if offlineCreate}
            <input
              type="text"
              bind:value={createVeknId}
              aria-label={m.offline_player_vekn_id()}
              placeholder={m.offline_player_vekn_id()}
              class="w-full px-3 py-2 bg-surface-hover border border-line-strong rounded text-sm text-ink-strong placeholder-ink-faint"
            />
          {/if}
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
            disabled={!createName.trim() || !createEmail.trim() || !canSponsor}
            onclick={handleCreateAndRegister}
          >{m.create_and_register_btn()}</Button>
        </div>
      {/if}
    </div>
  </div>
{/if}

{#if pendingDeceased}
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
  <div
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4"
    role="presentation"
    onclick={() => pendingDeceased = null}
    onkeydown={(e) => { if (e.key === 'Escape') pendingDeceased = null; }}
  >
    <div
      use:dialogPanel={() => pendingDeceased = null}
      class="bg-surface-card border border-line-strong rounded-lg p-6 max-w-sm w-full mx-4 space-y-4 max-h-[85dvh] overflow-y-auto"
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
