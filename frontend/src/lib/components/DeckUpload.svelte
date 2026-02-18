<script lang="ts">
  import { onDestroy } from 'svelte';
  import type { User } from '$lib/types';
  import { getFilteredUsers } from '$lib/db';
  import { getCountryFlag } from '$lib/geonames';
  import * as m from '$lib/paraglide/messages.js';

  let {
    tournamentUid,
    playerUid = undefined,
    playerName = undefined,
    playerVekn = undefined,
    onuploaded,
  }: {
    tournamentUid: string;
    playerUid?: string;
    playerName?: string;
    playerVekn?: string;
    onuploaded?: () => void;
  } = $props();

  let mode = $state<'text' | 'url' | 'qr'>('text');
  let deckText = $state('');
  let deckUrl = $state('');
  let deckName = $state('');
  let attribution = $state<'self' | 'anonymous' | 'other'>('self');
  let attributionVekn = $state('');
  let attributionSearch = $state('');
  let attributionName = $state(''); // resolved display name from autocomplete
  let attrResults = $state<User[]>([]);
  let attrTotal = $state(0);
  let attrSelectedIndex = $state(-1);
  const ATTR_SEARCH_LIMIT = 10;
  let loading = $state(false);
  let error = $state<string | null>(null);
  let success = $state(false);

  // Attribution autocomplete
  async function searchAttribution() {
    attrSelectedIndex = -1;
    if (attributionSearch.trim().length < 2) {
      attrResults = [];
      attrTotal = 0;
      return;
    }
    const results = await getFilteredUsers(undefined, undefined, attributionSearch.trim());
    attrTotal = results.length;
    attrResults = results.slice(0, ATTR_SEARCH_LIMIT);
  }

  function selectAttrUser(user: User) {
    attributionVekn = user.vekn_id || user.name;
    attributionName = user.name;
    attributionSearch = user.name + (user.vekn_id ? ` (${user.vekn_id})` : '');
    attrResults = [];
  }

  function handleAttrKeydown(e: KeyboardEvent) {
    if (!attrResults.length) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      attrSelectedIndex = Math.min(attrSelectedIndex + 1, attrResults.length - 1);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      attrSelectedIndex = Math.max(attrSelectedIndex - 1, 0);
    } else if (e.key === 'Enter' && attrSelectedIndex >= 0) {
      e.preventDefault();
      const user = attrResults[attrSelectedIndex];
      if (user) selectAttrUser(user);
    }
  }

  // QR scanner
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
      error = `Camera access failed: ${e.message || e}`;
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

  // Start scanner when QR mode is selected
  $effect(() => {
    if (mode === 'qr' && videoEl) {
      startQrScanner();
    } else if (mode !== 'qr') {
      stopQrScanner();
    }
  });

  onDestroy(() => stopQrScanner());

  const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

  async function upload() {
    loading = true;
    error = null;
    success = false;

    try {
      const token = (await import('$lib/stores/auth.svelte')).getAccessToken();
      const endpoint = playerUid
        ? `${API_URL}/api/tournaments/${tournamentUid}/decks/${playerUid}`
        : `${API_URL}/api/tournaments/${tournamentUid}/decks`;
      const method = playerUid ? 'PUT' : 'POST';

      const body: Record<string, string | null> = { name: deckName };
      if (mode === 'text') body.text = deckText;
      else body.url = deckUrl;

      // Attribution: set both attribution (structured VEKN/name) and author (display name)
      if (attribution === 'anonymous') {
        body.attribution = null;
      } else if (attribution === 'self' && playerUid) {
        body.attribution = playerVekn || playerName || null;
        if (playerName) body.author = playerName;
      } else if (attribution === 'other') {
        const val = attributionVekn.trim() || attributionSearch.trim();
        if (val) {
          body.attribution = val;
          body.author = attributionName || attributionSearch.trim();
        }
      }

      const resp = await fetch(endpoint, {
        method,
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(body),
      });

      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || `Upload failed (${resp.status})`);
      }

      success = true;
      deckText = '';
      deckUrl = '';
      deckName = '';
      onuploaded?.();
    } catch (e: any) {
      error = e.message || 'Upload failed';
    } finally {
      loading = false;
    }
  }
</script>

<div class="space-y-3">
  <div class="flex gap-2 flex-wrap">
    <button
      onclick={() => mode = 'text'}
      class="px-3 py-1.5 text-sm rounded-lg transition-colors {mode === 'text' ? 'bg-crimson-600 text-white' : 'bg-ash-800 text-ash-300 hover:bg-ash-700'}"
    >{m.deck_upload_paste()}</button>
    <button
      onclick={() => mode = 'url'}
      class="px-3 py-1.5 text-sm rounded-lg transition-colors {mode === 'url' ? 'bg-crimson-600 text-white' : 'bg-ash-800 text-ash-300 hover:bg-ash-700'}"
    >{m.deck_upload_from_url()}</button>
    <button
      onclick={() => mode = 'qr'}
      class="px-3 py-1.5 text-sm rounded-lg transition-colors {mode === 'qr' ? 'bg-crimson-600 text-white' : 'bg-ash-800 text-ash-300 hover:bg-ash-700'}"
    >{m.deck_upload_scan_qr()}</button>
  </div>

  {#if mode === 'qr'}
    <div class="relative rounded-lg overflow-hidden bg-black">
      <!-- svelte-ignore element_invalid_self_closing_tag -->
      <video bind:this={videoEl} class="w-full max-h-64 object-cover" />
      {#if !qrScanning}
        <p class="absolute inset-0 flex items-center justify-center text-ash-400 text-sm">{m.deck_upload_qr_starting()}</p>
      {/if}
    </div>
    <p class="text-xs text-ash-500">{m.deck_upload_qr_hint()}</p>
  {:else}
    <input
      type="text"
      bind:value={deckName}
      placeholder={m.deck_upload_name_placeholder()}
      class="w-full px-3 py-2 bg-ash-900 border border-ash-700 rounded-lg text-ash-200 placeholder-ash-500 text-sm"
    />

    {#if mode === 'text'}
      <textarea
        bind:value={deckText}
        placeholder={m.deck_upload_text_placeholder()}
        rows="12"
        class="w-full px-3 py-2 bg-ash-900 border border-ash-700 rounded-lg text-ash-200 placeholder-ash-500 text-sm font-mono resize-y"
      ></textarea>
    {:else}
      <input
        type="url"
        bind:value={deckUrl}
        placeholder={m.deck_upload_url_placeholder()}
        class="w-full px-3 py-2 bg-ash-900 border border-ash-700 rounded-lg text-ash-200 placeholder-ash-500 text-sm"
      />
      <p class="text-xs text-ash-500">{m.deck_upload_supported_sites()}</p>
    {/if}

    <!-- Attribution -->
    <div class="flex items-center gap-3 text-sm flex-wrap">
      <span class="text-ash-400">{m.deck_upload_attribution()}:</span>
      <label class="flex items-center gap-1 text-ash-200">
        <input type="radio" bind:group={attribution} value="self" class="accent-crimson-500" />
        {playerUid ? m.deck_upload_attr_player({ name: playerName || '?' }) : m.deck_upload_attr_self()}
      </label>
      <label class="flex items-center gap-1 text-ash-200">
        <input type="radio" bind:group={attribution} value="anonymous" class="accent-crimson-500" />
        {m.deck_upload_attr_anonymous()}
      </label>
      <label class="flex items-center gap-1 text-ash-200">
        <input type="radio" bind:group={attribution} value="other" class="accent-crimson-500" />
        {m.deck_upload_attr_other()}
      </label>
    </div>
    {#if attribution === 'other'}
      <div class="relative">
        <input
          type="text"
          bind:value={attributionSearch}
          oninput={() => { attributionVekn = attributionSearch; attributionName = ''; searchAttribution(); }}
          onkeydown={handleAttrKeydown}
          placeholder={m.deck_upload_attr_other_placeholder()}
          class="w-full px-3 py-2 bg-ash-900 border border-ash-700 rounded-lg text-ash-200 placeholder-ash-500 text-sm"
        />
        {#if attrResults.length > 0}
          <div class="absolute z-10 mt-1 w-full bg-dusk-950 border border-ash-700 rounded-lg divide-y divide-ash-800 max-h-48 overflow-y-auto shadow-lg">
            {#each attrResults as user, i}
              <button
                onclick={() => selectAttrUser(user)}
                class="w-full px-3 py-2 text-left text-sm text-ash-200 transition-colors {i === attrSelectedIndex ? 'bg-ash-700' : 'hover:bg-ash-800'}"
              >
                {#if user.country}<span class="mr-1">{getCountryFlag(user.country)}</span>{/if}{user.name}
                {#if user.vekn_id}
                  <span class="text-ash-500 ml-2">({user.vekn_id})</span>
                {/if}
              </button>
            {/each}
            {#if attrTotal > ATTR_SEARCH_LIMIT}
              <div class="px-3 py-2 text-xs text-ash-500 text-center">
                {m.add_player_more_results({ count: (attrTotal - ATTR_SEARCH_LIMIT).toString() })}
              </div>
            {/if}
          </div>
        {/if}
      </div>
    {/if}
  {/if}

  {#if error}
    <p class="text-sm text-red-400">{error}</p>
  {/if}
  {#if success}
    <p class="text-sm text-emerald-400">{m.deck_upload_success()}</p>
  {/if}

  {#if mode !== 'qr'}
    <button
      onclick={upload}
      disabled={loading || (mode === 'text' ? !deckText.trim() : !deckUrl.trim())}
      class="px-4 py-2 text-sm font-medium text-white bg-crimson-600 hover:bg-crimson-500 disabled:bg-ash-700 disabled:text-ash-500 rounded-lg transition-colors"
    >
      {loading ? m.deck_upload_uploading() : m.deck_upload_submit()}
    </button>
  {/if}
</div>
