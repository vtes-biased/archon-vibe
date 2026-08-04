<script lang="ts">
  // Record a promo inventory movement (officials). Intake = print batch
  // received from BCP (NC for themselves, IC for anyone); assignment = stock
  // handed to a member; distribution = copies handed out to players outside a
  // tournament report. Negative qty records a compensating correction.
  import type { Promo, PromoLedgerKind, User } from "$lib/types";
  import { createPromoLedgerEntry } from "$lib/api";
  import { getAuthState } from "$lib/stores/auth.svelte";
  import { getCountryFlag } from "$lib/geonames";
  import { showToast } from "$lib/stores/toast.svelte";
  import Button from "$lib/components/Button.svelte";
  import UserPicker from "$lib/components/UserPicker.svelte";
  import { X } from "@lucide/svelte";
  import * as m from '$lib/paraglide/messages.js';

  let {
    promos,
    canManagePromo = false,
    onclose,
    onrecorded,
  }: {
    promos: Promo[]; // active promos
    canManagePromo?: boolean;
    onclose: () => void;
    onrecorded: () => void;
  } = $props();

  const auth = $derived(getAuthState());

  let kind = $state<PromoLedgerKind>("assignment");
  let promoUid = $state("");
  let qty = $state<number | null>(1);
  let note = $state("");
  let toUser = $state<User | null>(null);
  // IC only: null = self (the server default).
  let fromUser = $state<User | null>(null);

  // Local today (toISOString would shift the date near midnight).
  const now = new Date();
  let happenedAt = $state(
    `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
  );

  let saving = $state(false);
  const canSubmit = $derived(
    !!promoUid &&
      qty !== null &&
      Number.isInteger(qty) &&
      qty !== 0 &&
      !!happenedAt &&
      (kind !== "assignment" || !!toUser) &&
      !saving
  );

  // Stock lifecycle order: in, move, out.
  const kinds: PromoLedgerKind[] = ["intake", "assignment", "distribution"];
  const kindLabels: Record<PromoLedgerKind, () => string> = {
    intake: m.promo_ledger_kind_intake,
    assignment: m.promo_ledger_kind_assignment,
    distribution: m.promo_ledger_kind_distribution,
  };
  const submitLabels: Record<PromoLedgerKind, () => string> = {
    intake: m.promo_movement_submit_intake,
    assignment: m.promo_movement_submit_assignment,
    distribution: m.promo_movement_submit_distribution,
  };

  async function submit() {
    if (!canSubmit) return;
    saving = true;
    try {
      await createPromoLedgerEntry({
        kind,
        promo_uid: promoUid,
        qty: qty!,
        to_uid: kind === "assignment" ? toUser!.uid : undefined,
        from_uid: canManagePromo && fromUser ? fromUser.uid : undefined,
        note: note.trim() || undefined,
        // Local noon → stable calendar date in every timezone.
        happened_at: new Date(`${happenedAt}T12:00:00`).toISOString(),
      });
      showToast({ type: "success", message: m.promo_movement_recorded() });
      onrecorded();
      onclose();
    } catch {
      // Error toast shown by apiRequest
    } finally {
      saving = false;
    }
  }

  function requestClose() {
    if (!saving) onclose();
  }

  function focusOnMount(node: HTMLElement) {
    const input = node.querySelector<HTMLElement>("select, input, textarea");
    (input ?? node).focus();
  }

  const inputClass =
    'w-full px-3 py-2 text-sm border border-line-strong rounded-lg bg-surface-card text-ink-bright focus:ring-2 focus:ring-accent focus:border-transparent';
</script>

{#snippet userChip(user: User, onclear: () => void)}
  <span class="inline-flex items-center gap-1.5 px-3 py-1.5 bg-surface-hover rounded-lg text-sm text-ink-strong">
    {#if user.country}
      <span>{getCountryFlag(user.country)}</span>
    {/if}
    {user.name}
    {#if user.vekn_id}
      <span class="text-ink-faint">#{user.vekn_id}</span>
    {/if}
    <!-- 44px tap target padded out; negative margin keeps the chip compact -->
    <button
      type="button"
      onclick={onclear}
      class="ml-0 -m-2.5 p-2.5 min-w-[44px] min-h-[44px] inline-flex items-center justify-center text-ink-faint hover:text-link transition-colors"
      aria-label={m.common_delete()}
    >
      <X class="w-3.5 h-3.5" aria-hidden="true" />
    </button>
  </span>
{/snippet}

<!-- Full-screen sheet on mobile, centered card at sm:+ -->
<div
  role="presentation"
  class="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm sm:flex sm:items-center sm:justify-center sm:p-4"
  onclick={(e) => { e.stopPropagation(); if (e.target === e.currentTarget) requestClose(); }}
>
  <div
    role="dialog"
    aria-modal="true"
    aria-labelledby="promo-movement-title"
    tabindex="-1"
    use:focusOnMount
    onkeydown={(e) => { e.stopPropagation(); if (e.key === 'Escape') requestClose(); }}
    class="bg-surface-card w-full h-full overflow-y-auto sm:h-auto sm:max-h-[90vh] sm:max-w-md sm:rounded-lg sm:border sm:border-line sm:shadow-xl"
  >
    <div class="p-6 border-b border-line">
      <h2 id="promo-movement-title" class="text-xl font-medium text-ink-strong">{m.promo_movement_title()}</h2>
    </div>

    <form onsubmit={(e) => { e.preventDefault(); submit(); }} class="p-6 space-y-4">
      <!-- Kind segmented toggle -->
      <div class="grid grid-cols-3 bg-surface-muted rounded-lg border border-line p-1">
        {#each kinds as k (k)}
          <button
            type="button"
            onclick={() => (kind = k)}
            class="px-3 py-2 min-h-[44px] text-sm font-medium rounded-md transition-colors {kind === k ? 'bg-accent-strong text-white' : 'text-ink-muted hover:text-ink-bright'}"
          >
            {kindLabels[k]()}
          </button>
        {/each}
      </div>

      <div>
        <label for="movement-promo" class="block text-sm text-ink-muted mb-1">{m.promo_movement_promo_label()} *</label>
        <select id="movement-promo" bind:value={promoUid} required class={inputClass}>
          <option value="" disabled>{m.promos_select()}</option>
          {#each promos as promo (promo.uid)}
            <option value={promo.uid}>{promo.name}</option>
          {/each}
        </select>
      </div>

      {#if kind === "assignment"}
        <!-- The effective source can't be the recipient: a self-assignment nets
             to zero in the recompute (intake covers self-crediting). -->
        <div>
          <span class="block text-sm text-ink-muted mb-1">{m.promo_movement_to_label()} *</span>
          {#if toUser}
            {@render userChip(toUser, () => (toUser = null))}
          {:else}
            <UserPicker
              onselect={(u) => (toUser = u)}
              excludeUids={auth.user ? [fromUser?.uid ?? auth.user.uid] : []}
            />
          {/if}
        </div>
      {/if}

      {#if canManagePromo}
        <!-- from_uid doubles as the receiving holder for intakes -->
        <div>
          <span class="block text-sm text-ink-muted mb-1">
            {kind === "intake" ? m.promo_movement_received_by_label() : m.promo_movement_from_label()}
          </span>
          {#if fromUser}
            {@render userChip(fromUser, () => (fromUser = null))}
          {:else if auth.user}
            <p class="text-sm text-ink mb-2">
              {kind === "intake"
                ? m.promo_movement_received_by_self({ name: auth.user.name })
                : m.promo_movement_from_self({ name: auth.user.name })}
            </p>
            <UserPicker
              onselect={(u) => (fromUser = u)}
              excludeUids={toUser ? [auth.user.uid, toUser.uid] : [auth.user.uid]}
            />
          {/if}
        </div>
      {/if}

      <div>
        <label for="movement-qty" class="block text-sm text-ink-muted mb-1">{m.promo_movement_qty_label()} *</label>
        <input id="movement-qty" type="number" bind:value={qty} step="1" required class={inputClass} />
        <p class="mt-1 text-xs text-ink-faint">{m.promo_movement_qty_hint()}</p>
      </div>

      <div>
        <label for="movement-date" class="block text-sm text-ink-muted mb-1">{m.promo_movement_date_label()}</label>
        <input id="movement-date" type="date" bind:value={happenedAt} class={inputClass} />
      </div>

      <div>
        <label for="movement-note" class="block text-sm text-ink-muted mb-1">{m.promo_movement_note_label()}</label>
        <input id="movement-note" type="text" bind:value={note} maxlength="500" class={inputClass} />
      </div>

      <div class="flex gap-2 pt-2">
        <Button type="submit" variant="primary" size="lg" class="flex-1" loading={saving} disabled={!canSubmit}>
          {submitLabels[kind]()}
        </Button>
        <Button variant="secondary" size="lg" disabled={saving} onclick={requestClose}>
          {m.common_cancel()}
        </Button>
      </div>
    </form>
  </div>
</div>
