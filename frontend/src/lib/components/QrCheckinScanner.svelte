<script lang="ts">
  import { onDestroy } from 'svelte';
  import { qrCheckin } from '$lib/api';
  import { saveTournament } from '$lib/db';
  import { X } from 'lucide-svelte';
  import * as m from '$lib/paraglide/messages.js';

  let {
    tournamentUid,
    onclose,
  }: {
    tournamentUid: string;
    onclose: () => void;
  } = $props();

  let videoEl = $state<HTMLVideoElement | null>(null);
  let scanner: any = null;
  let scanning = $state(false);
  let error = $state<string | null>(null);
  let success = $state(false);
  let loading = $state(false);

  async function startScanner() {
    if (!videoEl) return;
    const QrScanner = (await import('qr-scanner')).default;
    scanner = new QrScanner(videoEl, async (result: { data: string }) => {
      let code = result.data;
      // Parse URL format: extract checkin param from our app URLs
      if (code.startsWith('http')) {
        try {
          const url = new URL(code);
          const checkinParam = url.searchParams.get('checkin');
          if (!checkinParam) return; // Not our QR code
          code = checkinParam;
        } catch { return; }
      }
      if (loading || success) return;
      loading = true;
      error = null;
      try {
        const updated = await qrCheckin(tournamentUid, code);
        await saveTournament(updated);
        success = true;
        stopScanner();
      } catch (e: any) {
        error = e.detail || e.message || m.checkin_qr_error();
      } finally {
        loading = false;
      }
    }, {
      returnDetailedScanResult: true,
      highlightScanRegion: true,
      highlightCodeOutline: true,
    });
    try {
      await scanner.start();
      scanning = true;
    } catch (e: any) {
      error = m.checkin_qr_camera_error();
    }
  }

  function stopScanner() {
    if (scanner) {
      scanner.stop();
      scanner.destroy();
      scanner = null;
    }
    scanning = false;
  }

  $effect(() => {
    if (videoEl) startScanner();
  });

  onDestroy(() => stopScanner());
</script>

<div class="space-y-3">
  <div class="flex items-center justify-between">
    <p class="text-sm text-ash-400">{m.checkin_qr_hint()}</p>
    <button onclick={onclose} class="p-1 text-ash-400 hover:text-ash-200 transition-colors">
      <X class="w-5 h-5" />
    </button>
  </div>

  <div class="relative rounded-lg overflow-hidden bg-black">
    <!-- svelte-ignore element_invalid_self_closing_tag -->
    <video bind:this={videoEl} class="w-full max-h-64 object-cover" />
    {#if !scanning && !error}
      <p class="absolute inset-0 flex items-center justify-center text-ash-400 text-sm">{m.common_loading()}</p>
    {/if}
  </div>

  {#if loading}
    <p class="text-sm text-ash-400">{m.common_loading()}</p>
  {/if}
  {#if error}
    <p class="text-sm text-crimson-400">{error}</p>
  {/if}
  {#if success}
    <p class="text-sm text-emerald-400">{m.checkin_qr_success()}</p>
  {/if}
</div>
