<!--
  Per-tournament Web Push opt-in (#314). Primary discovery surface: shown to a checked-in
  participant of a live tournament. The Enable tap is the user gesture iOS requires. On
  iOS in a browser tab (not installed) push is impossible, so the tap surfaces an
  Add-to-Home-Screen nudge instead. Dismissal is remembered per tournament (≤1 prompt).
-->
<script lang="ts">
  import { onMount } from "svelte";
  import { Bell, Share } from "@lucide/svelte";
  import * as m from "$lib/paraglide/messages.js";
  import Button from "$lib/components/Button.svelte";
  import { showToast } from "$lib/stores/toast.svelte";
  import {
    pushSupported,
    isPushSubscribed,
    isPushBusy,
    getPushPermission,
    enablePush,
    isIOS,
    isStandalone,
    refreshPushState,
  } from "$lib/stores/push.svelte";

  let { tournamentUid, eligible }: { tournamentUid: string; eligible: boolean } = $props();

  const dismissKey = () => `push-optin-dismissed:${tournamentUid}`;
  let dismissed = $state(true); // assume dismissed until localStorage is read (avoids flash)
  let showIosNudge = $state(false);

  onMount(() => {
    dismissed = localStorage.getItem(dismissKey()) === "1";
    refreshPushState();
  });

  const visible = $derived(
    eligible &&
      !dismissed &&
      pushSupported() &&
      !isPushSubscribed() &&
      getPushPermission() !== "denied"
  );

  function dismiss() {
    dismissed = true;
    showIosNudge = false;
    try {
      localStorage.setItem(dismissKey(), "1");
    } catch {
      /* private mode — fine, it just re-shows next visit */
    }
  }

  async function onEnable() {
    if (isIOS() && !isStandalone()) {
      showIosNudge = true; // can't subscribe in an iOS tab — show how to install first
      return;
    }
    const ok = await enablePush();
    showToast({
      type: ok ? "success" : "error",
      message: ok ? m.notifications_enabled_toast() : m.notifications_denied_toast(),
    });
    if (ok) dismiss();
  }
</script>

{#if visible}
  {#if showIosNudge}
    <div role="status" class="bg-surface-card border border-line rounded-lg p-4 mb-4 flex gap-3 items-start">
      <Share class="w-5 h-5 text-accent-strong shrink-0 mt-0.5" />
      <div class="flex-1 space-y-3 text-sm">
        <p class="font-medium text-ink">{m.notifications_ios_title()}</p>
        <p class="text-ink-muted">{m.notifications_ios_body()}</p>
        <Button variant="secondary" onclick={dismiss} class="min-h-[44px]">
          {m.notifications_ios_dismiss()}
        </Button>
      </div>
    </div>
  {:else}
    <div class="bg-surface-card border border-line rounded-lg p-4 mb-4 flex gap-3 items-start">
      <Bell class="w-5 h-5 text-accent-strong shrink-0 mt-0.5" />
      <div class="flex-1 space-y-3 text-sm">
        <p class="font-medium text-ink">{m.notifications_prompt_title()}</p>
        <p class="text-ink-muted">{m.notifications_prompt_body()}</p>
        <div class="flex gap-2">
          <Button variant="primary" loading={isPushBusy()} onclick={onEnable} class="min-h-[44px]">
            {m.notifications_prompt_enable()}
          </Button>
          <Button variant="ghost" onclick={dismiss} class="min-h-[44px]">
            {m.notifications_prompt_dismiss()}
          </Button>
        </div>
      </div>
    </div>
  {/if}
{/if}
