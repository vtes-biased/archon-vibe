<script lang="ts">
  import { onDestroy } from 'svelte';
  import { Printer } from 'lucide-svelte';
  import * as m from '$lib/paraglide/messages.js';

  let {
    code,
    tournamentUid,
    tournamentName,
  }: {
    code: string;
    tournamentUid: string;
    tournamentName: string;
  } = $props();

  let canvasEl = $state<HTMLCanvasElement | null>(null);

  // Encode a URL so phone camera scanning opens the tournament page
  const qrUrl = $derived(
    `${typeof window !== 'undefined' ? window.location.origin : ''}/tournaments/${tournamentUid}?checkin=${code}`
  );

  $effect(() => {
    if (!canvasEl || !qrUrl) return;
    import('qrcode').then(QRCode => {
      QRCode.toCanvas(canvasEl!, qrUrl, {
        width: 256,
        margin: 2,
        color: { dark: '#000000', light: '#ffffff' },
      });
    });
  });

  function printQr() {
    if (!canvasEl) return;
    const dataUrl = canvasEl.toDataURL('image/png');
    const css = `body{font-family:"Segoe UI","Helvetica Neue",Arial,sans-serif;text-align:center;margin:40px;color:#000}`;
    const html = `<!DOCTYPE html><html><head><meta charset="utf-8"><title>${tournamentName}</title><style>${css}</style></head><body>`
      + `<div style="font-size:20pt;font-weight:bold;margin-bottom:8px">${tournamentName}</div>`
      + `<div style="font-size:14pt;color:#444;margin-bottom:24px">${m.checkin_qr_scan_instruction()}</div>`
      + `<img src="${dataUrl}" style="width:256px;height:256px" />`
      + `<script>window.onload=()=>window.print()<\/script></body></html>`;
    const w = window.open('', '_blank');
    if (w) { w.document.write(html); w.document.close(); }
  }
</script>

<div class="space-y-3">
  <div class="flex items-center justify-center">
    <canvas bind:this={canvasEl} class="rounded-lg"></canvas>
  </div>
  <p class="text-xs text-ash-500 text-center">{m.checkin_qr_organizer_hint()}</p>
  <div class="flex justify-center">
    <button onclick={printQr} class="px-3 py-1.5 text-sm text-ash-300 bg-ash-800 hover:bg-ash-700 rounded-lg transition-colors flex items-center gap-1.5">
      <Printer class="w-4 h-4" />
      {m.checkin_qr_print()}
    </button>
  </div>
</div>
