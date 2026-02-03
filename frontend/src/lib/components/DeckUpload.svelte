<script lang="ts">
  import type { Tournament } from "$lib/types";

  let {
    tournamentUid,
    playerUid = undefined,
    onuploaded,
  }: {
    tournamentUid: string;
    playerUid?: string;
    onuploaded?: () => void;
  } = $props();

  let mode = $state<'text' | 'url'>('text');
  let deckText = $state('');
  let deckUrl = $state('');
  let deckName = $state('');
  let loading = $state(false);
  let error = $state<string | null>(null);
  let success = $state(false);

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

      const body: Record<string, string> = { name: deckName };
      if (mode === 'text') body.text = deckText;
      else body.url = deckUrl;

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
  <div class="flex gap-2">
    <button
      onclick={() => mode = 'text'}
      class="px-3 py-1.5 text-sm rounded-lg transition-colors {mode === 'text' ? 'bg-crimson-600 text-bone-100' : 'bg-ash-800 text-ash-300 hover:bg-ash-700'}"
    >Paste Deck</button>
    <button
      onclick={() => mode = 'url'}
      class="px-3 py-1.5 text-sm rounded-lg transition-colors {mode === 'url' ? 'bg-crimson-600 text-bone-100' : 'bg-ash-800 text-ash-300 hover:bg-ash-700'}"
    >From URL</button>
  </div>

  <input
    type="text"
    bind:value={deckName}
    placeholder="Deck name (optional)"
    class="w-full px-3 py-2 bg-ash-900 border border-ash-700 rounded-lg text-ash-200 placeholder-ash-500 text-sm"
  />

  {#if mode === 'text'}
    <textarea
      bind:value={deckText}
      placeholder="Paste your deck list here...&#10;&#10;Example:&#10;2x .44 Magnum&#10;3 Govern the Unaligned&#10;..."
      rows="12"
      class="w-full px-3 py-2 bg-ash-900 border border-ash-700 rounded-lg text-ash-200 placeholder-ash-500 text-sm font-mono resize-y"
    ></textarea>
  {:else}
    <input
      type="url"
      bind:value={deckUrl}
      placeholder="VDB, VTESDecks, or Amaranth URL"
      class="w-full px-3 py-2 bg-ash-900 border border-ash-700 rounded-lg text-ash-200 placeholder-ash-500 text-sm"
    />
    <p class="text-xs text-ash-500">Supported: vdb.im, vtesdecks.com, amaranth.vtes.co.nz</p>
  {/if}

  {#if error}
    <p class="text-sm text-red-400">{error}</p>
  {/if}
  {#if success}
    <p class="text-sm text-emerald-400">Deck uploaded successfully</p>
  {/if}

  <button
    onclick={upload}
    disabled={loading || (mode === 'text' ? !deckText.trim() : !deckUrl.trim())}
    class="px-4 py-2 text-sm font-medium text-bone-100 bg-crimson-600 hover:bg-crimson-500 disabled:bg-ash-700 disabled:text-ash-500 rounded-lg transition-colors"
  >
    {loading ? 'Uploading...' : 'Upload Deck'}
  </button>
</div>
