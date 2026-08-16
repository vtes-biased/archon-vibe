<script lang="ts">
  // Progressive disclosure: anyone sees the gallery (public, offline-capable), signed-in holders see
  // their own stock, officials get the inventory panel, IC additionally mints/edits catalog entries.
  import type { Promo } from "$lib/types";
  import { getAllPromos, getUser } from "$lib/db";
  import { syncManager } from "$lib/sync";
  import { getAuthState } from "$lib/stores/auth.svelte";
  import { ApiError, updatePromo, deletePromoCatalogEntry } from "$lib/api";
  import { showToast } from "$lib/stores/toast.svelte";
  import { toUserMessage } from "$lib/errors";
  import Button from "$lib/components/Button.svelte";
  import PromoGallery from "./PromoGallery.svelte";
  import PromoEditModal from "./PromoEditModal.svelte";
  import PromoInventoryPanel from "./PromoInventoryPanel.svelte";
  import OwnStockCard from "./OwnStockCard.svelte";
  import { Plus } from "@lucide/svelte";
  import * as m from '$lib/paraglide/messages.js';
  import { canManagePromos, canViewFullPromoLedger } from "$lib/engine";

  const auth = $derived(getAuthState());
  const canManagePromo = $derived(canManagePromos(auth.user).allowed);
  // NC records intakes and sees the whole ledger, in any country — the promo
  // inventory chain (IC -> NC -> organizer) is not country-scoped.
  const canViewLedger = $derived(canViewFullPromoLedger(auth.user).allowed);

  let promos = $state<Promo[]>([]);
  let ownStock = $state<Record<string, number>>({});
  let loaded = $state(false);

  async function loadData() {
    const all = (await getAllPromos()).filter((p) => !p.deleted_at);
    // Newest release first; undated entries last, then by name.
    all.sort((a, b) => {
      const ad = a.release_date ?? "";
      const bd = b.release_date ?? "";
      if (ad !== bd) return bd.localeCompare(ad);
      return a.name.localeCompare(b.name);
    });
    promos = all;
    const uid = getAuthState().user?.uid;
    ownStock = uid ? ((await getUser(uid))?.promo_stock ?? {}) : {};
    loaded = true;
  }

  // Load on mount and refresh on sync (promo catalog + own promo_stock).
  $effect(() => {
    loadData();
    const handler = (event: { type: string }) => {
      if (event.type === "promo" || event.type === "user" || event.type === "sync_complete") loadData();
    };
    syncManager.addEventListener(handler);
    return () => syncManager.removeEventListener(handler);
  });

  // Modal state (captured at open — SSE updates never mutate an open form).
  let showEdit = $state(false);
  let editingPromo = $state<Promo | null>(null);

  function openCreate() {
    editingPromo = null;
    showEdit = true;
  }

  function openEdit(promo: Promo) {
    editingPromo = promo;
    showEdit = true;
  }

  async function toggleActive(promo: Promo) {
    try {
      await updatePromo(promo.uid, { active: !promo.active });
      showToast({ type: "success", message: promo.active ? m.promo_retired_toast() : m.promo_reactivated_toast() });
      await loadData();
    } catch {
      // Error toast shown by apiRequest
    }
  }

  async function handleDelete(promo: Promo) {
    try {
      await deletePromoCatalogEntry(promo.uid);
      showToast({ type: "success", message: m.promo_deleted_toast() });
      await loadData();
    } catch (e) {
      // The helper suppresses the toast; 409 (referenced) gets the retire hint.
      const message =
        e instanceof ApiError && e.status === 409
          ? m.promo_delete_referenced()
          : toUserMessage(e, m.promo_delete_failed());
      showToast({ type: "error", message });
    }
  }
</script>

{#if !loaded}
  <div class="text-center py-8 text-ink-muted">{m.common_loading()}</div>
{:else}
  <!-- Actionable stock first: the gallery is reference material and can be long. -->
  {#if auth.isAuthenticated && Object.keys(ownStock).length > 0}
    <div class="mb-8">
      <OwnStockCard stock={ownStock} {promos} />
    </div>
  {/if}

  {#if canViewLedger}
    <div class="mb-8">
      <PromoInventoryPanel {promos} {canManagePromo} />
    </div>
  {/if}

  <div class="flex items-center justify-between gap-3 mb-4">
    <h2 class="text-lg font-medium text-ink-strong">{m.promo_catalog_title()}</h2>
    {#if canManagePromo && promos.some((p) => p.active)}
      <!-- With no active promos displayed, the create CTA lives in the gallery
           empty state instead (one primary per surface). -->
      <Button variant="primary" onclick={openCreate}>
        <Plus class="w-4 h-4" aria-hidden="true" />
        {m.promo_new()}
      </Button>
    {/if}
  </div>

  <PromoGallery
    {promos}
    {canManagePromo}
    {canViewLedger}
    onedit={openEdit}
    ontoggleactive={toggleActive}
    ondelete={handleDelete}
    oncreate={openCreate}
  />
{/if}

{#if showEdit}
  <PromoEditModal promo={editingPromo} onclose={() => (showEdit = false)} onsaved={loadData} />
{/if}
