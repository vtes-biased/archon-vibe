<script lang="ts">
  import { toUserMessage } from '$lib/errors';
  import { onDestroy } from 'svelte';
  import { getTournament } from '$lib/db';
  import { validateDeck, type ValidationError } from '$lib/engine';
  import type { DeckAttribution } from '$lib/types';
  import { isSettableCredit } from '$lib/deck-credit';
  import { CircleX, TriangleAlert } from '@lucide/svelte';
  import AttributionPicker from '$lib/components/AttributionPicker.svelte';
  import Button from '$lib/components/Button.svelte';
  import * as m from '$lib/paraglide/messages.js';

  let {
    tournamentUid,
    playerUid = undefined,
    playerName = undefined,
    round = undefined,
    multideck = false,
    onuploaded,
  }: {
    tournamentUid: string;
    playerUid?: string;
    playerName?: string;
    round?: number;
    multideck?: boolean;
    onuploaded?: () => void;
  } = $props();

  let mode = $state<'text' | 'url' | 'qr'>(navigator.onLine ? 'url' : 'text');
  let deckText = $state('');
  let deckUrl = $state('');
  let deckName = $state('');
  let attribution = $state<DeckAttribution>({ kind: 'Owner', vekn_id: '', name: '' });
  let loading = $state(false);
  let error = $state<string | null>(null);
  let warnings = $state<string[]>([]);
  let success = $state(false);
  // Format validation results, shown right here at the upload moment — a 90-card paste must not read
  // as a green success. null = validation unavailable (engine/card DB not ready).
  let validationErrors = $state<ValidationError[] | null>([]);

  // URL/QR import fetch through the backend proxy, so gate them on connectivity; text import stays
  // local. `navigator.onLine` isn't reactive — mirror it and fall back to text if we drop offline.
  let online = $state(navigator.onLine);
  $effect(() => {
    const on = () => (online = true);
    const off = () => (online = false);
    window.addEventListener('online', on);
    window.addEventListener('offline', off);
    return () => {
      window.removeEventListener('online', on);
      window.removeEventListener('offline', off);
    };
  });
  $effect(() => {
    if (!online && mode !== 'text') mode = 'text';
  });


  let videoEl = $state<HTMLVideoElement | null>(null);
  let scanner: any = null;
  let qrScanning = $state(false);

  async function startQrScanner() {
    if (!videoEl) return;
    const QrScanner = (await import('qr-scanner')).default;
    scanner = new QrScanner(videoEl, (result: { data: string }) => {
      const url = result.data;
      if (url.startsWith('http')) {
        deckUrl = url;
        stopQrScanner();
        mode = 'url';
      }
    }, {
      returnDetailedScanResult: true,
      highlightScanRegion: true,
      highlightCodeOutline: true,
    });
    try {
      await scanner.start();
      qrScanning = true;
    } catch (e: any) {
      console.error('Camera start failed:', e); // keep the raw reason for diagnostics
      error = m.deck_error_camera();
    }
  }

  function stopQrScanner() {
    if (scanner) {
      scanner.stop();
      scanner.destroy();
      scanner = null;
    }
    qrScanning = false;
  }

  $effect(() => {
    if (mode === 'qr' && videoEl) {
      startQrScanner();
    } else if (mode !== 'qr') {
      stopQrScanner();
    }
  });

  onDestroy(() => stopQrScanner());

  async function upload() {
    loading = true;
    error = null;
    warnings = [];
    validationErrors = [];
    success = false;

    try {
      const { tournamentAction } = await import('$lib/tournament-actions');
      const { fetchDeckFromUrl, parseDeckText } = await import('$lib/deck-fetch');
      const { getCards } = await import('$lib/cards');

      let deck: { name: string; comments: string; cards: Record<string, number>; warnings?: string[] };
      if (mode === 'text') {
        deck = await parseDeckText(deckText);
      } else {
        deck = await fetchDeckFromUrl(deckUrl);
      }

      const uploadWarnings: string[] = [...(deck.warnings ?? [])];

      try {
        const cardsDb = await getCards();
        if (cardsDb.size > 0) {
          const unknownIds: string[] = [];
          for (const id of Object.keys(deck.cards)) {
            if (!cardsDb.has(parseInt(id))) unknownIds.push(id);
          }
          if (unknownIds.length > 0) {
            uploadWarnings.push(m.deck_unknown_cards({ count: unknownIds.length, ids: unknownIds.join(', ') }));
          }
        }
      } catch { /* card DB unavailable — skip check */ }

      if (deckName) deck.name = deckName;

      const deckData: Record<string, unknown> = {
        name: deck.name,
        comments: deck.comments,
        cards: deck.cards,
        attribution,
      };
      if (round !== undefined) deckData.round = round;

      const targetUid = playerUid || (await import('$lib/stores/auth.svelte')).getAuthState().user?.uid;
      await tournamentAction(tournamentUid, 'UpsertDeck', {
        player_uid: targetUid,
        deck: deckData,
        multideck,
      });

      success = true;
      warnings = uploadWarnings;
      // Store-and-warn: the upload is already saved (never gated); validation
      // renders inline below so problems surface now, not at check-in.
      try {
        const t = await getTournament(tournamentUid);
        validationErrors = await validateDeck(
          { cards: deck.cards, name: deck.name },
          t?.format ?? 'Standard'
        );
      } catch {
        validationErrors = null;
      }
      deckText = '';
      deckUrl = '';
      deckName = '';
      onuploaded?.();
    } catch (e: any) {
      const { DeckFetchError } = await import('$lib/deck-fetch');
      error = e instanceof DeckFetchError ? e.message : toUserMessage(e, m.deck_error_upload());
    } finally {
      loading = false;
    }
  }
</script>

<div class="space-y-3">
  <div class="flex gap-2 flex-wrap">
    <button
      onclick={() => mode = 'url'}
      disabled={!online}
      class="px-3 py-1.5 text-sm rounded-lg transition-colors {mode === 'url' ? 'bg-accent-strong-hover text-white' : 'bg-surface-hover text-ink hover:bg-surface-active'} {!online ? 'opacity-40 cursor-not-allowed' : ''}"
    >{m.deck_upload_from_url()}</button>
    <button
      onclick={() => mode = 'text'}
      class="px-3 py-1.5 text-sm rounded-lg transition-colors {mode === 'text' ? 'bg-accent-strong-hover text-white' : 'bg-surface-hover text-ink hover:bg-surface-active'}"
    >{m.deck_upload_paste()}</button>
    <button
      onclick={() => mode = 'qr'}
      disabled={!online}
      class="px-3 py-1.5 text-sm rounded-lg transition-colors {mode === 'qr' ? 'bg-accent-strong-hover text-white' : 'bg-surface-hover text-ink hover:bg-surface-active'} {!online ? 'opacity-40 cursor-not-allowed' : ''}"
    >{m.deck_upload_scan_qr()}</button>
  </div>
  {#if !online}
    <p class="text-xs text-ink-faint">{m.deck_upload_online_only()}</p>
  {/if}

  {#if mode === 'qr'}
    <div class="relative rounded-lg overflow-hidden bg-black">
      <!-- svelte-ignore element_invalid_self_closing_tag -->
      <video bind:this={videoEl} class="w-full max-h-64 object-cover" />
      {#if !qrScanning}
        <p class="absolute inset-0 flex items-center justify-center text-ink-muted text-sm">{m.deck_upload_qr_starting()}</p>
      {/if}
    </div>
    <p class="text-xs text-ink-faint">{m.deck_upload_qr_hint()}</p>
  {:else}
    <input
      type="text"
      bind:value={deckName}
      placeholder={m.deck_upload_name_placeholder()}
      class="w-full px-3 py-2 bg-surface-muted border border-line-strong rounded-lg text-ink-bright placeholder-ink-faint text-sm"
    />

    {#if mode === 'text'}
      <textarea
        bind:value={deckText}
        placeholder={m.deck_upload_text_placeholder()}
        rows="12"
        class="w-full px-3 py-2 bg-surface-muted border border-line-strong rounded-lg text-ink-bright placeholder-ink-faint text-sm font-mono resize-y"
      ></textarea>
    {:else}
      <input
        type="url"
        bind:value={deckUrl}
        placeholder={m.deck_upload_url_placeholder()}
        class="w-full px-3 py-2 bg-surface-muted border border-line-strong rounded-lg text-ink-bright placeholder-ink-faint text-sm"
      />
      <p class="text-xs text-ink-faint">{m.deck_upload_supported_sites()}</p>
    {/if}

    <AttributionPicker bind:attribution {playerUid} {playerName} />
  {/if}

  {#if error}
    <p class="text-sm text-link">{error}</p>
  {/if}
  {#if warnings.length > 0}
    <div class="space-y-1">
      {#each warnings as w}
        <p class="text-sm text-warn">{w}</p>
      {/each}
    </div>
  {/if}
  {#if success}
    <p class="text-sm text-info">{m.deck_upload_success()}</p>
    {#if validationErrors === null}
      <p class="text-sm text-ink-muted">
        <TriangleAlert class="w-4 h-4 inline mr-1" aria-hidden="true" />
        {m.deck_validation_unavailable()}
      </p>
    {:else if validationErrors.length > 0}
      <div class="space-y-1">
        {#each validationErrors as err}
          <p class="text-sm {err.severity === 'error' ? 'text-link' : 'text-warn'}">
            {#if err.severity === 'error'}<CircleX class="w-4 h-4 inline mr-1" aria-hidden="true" />{:else}<TriangleAlert class="w-4 h-4 inline mr-1" aria-hidden="true" />{/if}
            {err.message}
          </p>
        {/each}
      </div>
    {/if}
  {/if}

  {#if mode !== 'qr'}
    <Button
      variant="primary"
      size="lg"
      loading={loading}
      disabled={(mode === 'text' ? !deckText.trim() : !deckUrl.trim()) || !isSettableCredit(attribution)}
      onclick={upload}
    >
      {loading ? m.deck_upload_uploading() : m.deck_upload_submit()}
    </Button>
  {/if}
</div>
