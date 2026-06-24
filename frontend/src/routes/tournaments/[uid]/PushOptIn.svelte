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
    isIOSSafari,
    isStandalone,
    refreshPushState,
  } from "$lib/stores/push.svelte";

  let {
    tournamentUid,
    eligible,
    isOrganizer = false,
  }: { tournamentUid: string; eligible: boolean; isOrganizer?: boolean } = $props();

  const dismissKey = () => `push-optin-dismissed:${tournamentUid}`;
  let dismissed = $state(true); // assume dismissed until localStorage is read (avoids flash)
  let showIosNudge = $state(false);

  onMount(() => {
    dismissed = localStorage.getItem(dismissKey()) === "1";
    refreshPushState();
  });

  // On an iOS browser tab PushManager/Notification don't exist, so pushSupported()
  // is false — yet this is exactly the user who must be nudged to install. Show the
  // card when push is usable OR when installing on iOS would make it usable.
  const iosNeedsInstall = $derived(isIOS() && !isStandalone());
  const visible = $derived(
    eligible &&
      !dismissed &&
      !isPushSubscribed() &&
      getPushPermission() !== "denied" &&
      (pushSupported() || iosNeedsInstall)
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
    if (iosNeedsInstall) {
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
        <!-- iOS push only works from a Safari-installed PWA; other iOS browsers
             (Chrome/Firefox/in-app webviews) must open the page in Safari first. -->
        <p class="text-ink-muted">
          {isIOSSafari() ? m.notifications_ios_body() : m.notifications_ios_open_safari()}
        </p>
        <a href="/help/player-guide#installing-the-app" class="inline-block text-link hover:underline">
          {m.notifications_ios_learn_more()}
        </a>
        <div>
          <Button variant="secondary" onclick={dismiss} class="min-h-[44px]">
            {m.notifications_ios_dismiss()}
          </Button>
        </div>
      </div>
    </div>
  {:else}
    <div class="bg-surface-card border border-line rounded-lg p-4 mb-4 flex gap-3 items-start">
      <Bell class="w-5 h-5 text-accent-strong shrink-0 mt-0.5" />
      <div class="flex-1 space-y-3 text-sm">
        <p class="font-medium text-ink">
          {isOrganizer ? m.notifications_prompt_title_organizer() : m.notifications_prompt_title()}
        </p>
        <p class="text-ink-muted">
          {isOrganizer ? m.notifications_prompt_body_organizer() : m.notifications_prompt_body()}
        </p>
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
