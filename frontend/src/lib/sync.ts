/**
 * SSE sync manager with snapshot-based initial load.
 *
 * Flow:
 * 1. First connect (no last_sync_timestamp): fetch gzip snapshot, load into IDB
 * 2. Connect SSE with since=<timestamp> for catch-up + real-time updates
 * 3. On resync: re-fetch snapshot, reconnect SSE
 */

import type { User, Sanction, Tournament, DeckObject, League } from '$lib/types';
import {
  saveUser,
  saveUsersBatch,
  saveSanction,
  saveSanctionsBatch,
  deleteSanction,
  saveTournament,
  saveTournamentsBatch,
  deleteTournament,
  saveDeck,
  saveDecksBatch,
  deleteDeck,
  saveLeague,
  saveLeaguesBatch,
  deleteLeague,
  clearAllUsers,
  clearAllSanctions,
  clearAllTournaments,
  clearAllDecks,
  clearAllLeagues,
  setLastSyncTimestamp,
  getLastSyncTimestamp,
  clearLastSyncTimestamp,
  getTournament,
} from './db';
import { getAccessToken } from '$lib/stores/auth.svelte';
import { isOffline, getOfflineTournamentUids } from '$lib/stores/offline.svelte';

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

type SyncEventType = 'connected' | 'user' | 'sanction' | 'tournament' | 'deck' | 'league' | 'judge_call' | 'sync_complete' | 'resync' | 'error' | 'disconnected';

export interface JudgeCallData {
  tournament_uid: string;
  table: number;
  table_label: string;
  player_name: string;
}

interface SyncEvent {
  type: SyncEventType;
  data?: User | Sanction | Tournament | DeckObject | League | JudgeCallData;
  timestamp?: string | null;
  error?: string;
}

type SyncEventCallback = (event: SyncEvent) => void;

/** Spec for a synced object type */
interface ObjectSpec<T> {
  batchType: string;     // "users", "sanctions", "tournaments", "decks", "leagues"
  singleType: string;    // "user", "sanction", "tournament", "deck", "league"
  save: (item: T) => Promise<void>;
  saveBatch: (items: T[]) => Promise<void>;
  del: (uid: string) => Promise<void>;
}

const SPECS: ObjectSpec<any>[] = [
  { batchType: 'users', singleType: 'user', save: saveUser, saveBatch: saveUsersBatch, del: async () => { /* users not deleted via SSE currently */ } },
  { batchType: 'sanctions', singleType: 'sanction', save: saveSanction, saveBatch: saveSanctionsBatch, del: deleteSanction },
  { batchType: 'tournaments', singleType: 'tournament', save: saveTournament, saveBatch: saveTournamentsBatch, del: deleteTournament },
  { batchType: 'decks', singleType: 'deck', save: saveDeck, saveBatch: saveDecksBatch, del: deleteDeck },
  { batchType: 'leagues', singleType: 'league', save: saveLeague, saveBatch: saveLeaguesBatch, del: deleteLeague },
];

class SyncManager {
  private eventSource: EventSource | null = null;
  private listeners: SyncEventCallback[] = [];
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000;
  private maxReconnectDelay = 120_000; // 2 minutes ceiling

  // Generic buffers keyed by batch type
  private buffers: Map<string, any[]> = new Map();
  public isSynced = false;

  /**
   * Fetch and load a gzip snapshot from the server.
   * Returns the snapshot timestamp, or null on failure.
   */
  private async fetchSnapshot(): Promise<string | null> {
    const token = getAccessToken();
    const params = new URLSearchParams();
    if (token) params.set('token', token);
    const qs = params.toString();
    const url = qs ? `${API_URL}/snapshot?${qs}` : `${API_URL}/snapshot`;

    try {
      const response = await fetch(url);
      if (!response.ok) {
        console.error(`Snapshot fetch failed: ${response.status}`);
        return null;
      }

      // Browser may auto-decompress gzip via Content-Encoding header.
      // If not, detect gzip magic bytes and decompress manually.
      const arrayBuffer = await response.arrayBuffer();
      const bytes = new Uint8Array(arrayBuffer);
      let text: string;

      if (bytes[0] === 0x1f && bytes[1] === 0x8b) {
        // Still gzipped — decompress with DecompressionStream
        const ds = new DecompressionStream('gzip');
        const decompressedStream = new Blob([arrayBuffer]).stream().pipeThrough(ds);
        text = await new Response(decompressedStream).text();
      } else {
        text = new TextDecoder().decode(bytes);
      }

      const sections = JSON.parse(text) as { type: string; data?: any[]; timestamp?: string }[];

      // Clear stores before loading (preserve offline tournaments)
      await this.clearAllStores();

      // Load each section into IDB
      let timestamp: string | null = null;
      for (const section of sections) {
        if (section.type === 'meta') {
          timestamp = section.timestamp || null;
          continue;
        }
        // Find matching spec by singleType (snapshot uses singular: "user", "tournament", etc.)
        const spec = SPECS.find(s => s.singleType === section.type);
        if (spec && section.data && section.data.length > 0) {
          let items = section.data;
          // Skip offline tournaments
          if (spec.batchType === 'tournaments') {
            items = items.filter((t: any) => !isOffline(t.uid));
          }
          if (items.length > 0) await spec.saveBatch(items);
        }
      }

      if (timestamp) {
        await setLastSyncTimestamp(timestamp);
      }

      return timestamp;
    } catch (e) {
      console.error('Snapshot fetch/load failed:', e);
      return null;
    }
  }

  /**
   * Start syncing with the backend.
   * First connect: fetch snapshot, then connect SSE for catch-up + real-time.
   * Subsequent connects: SSE only with since= parameter.
   * After clearAllStores(), lastSync is null so connect() naturally fetches snapshot first.
   */
  async connect(): Promise<void> {
    await this.disconnect();
    this.isSynced = false;

    let lastSync: string | null = await getLastSyncTimestamp();

    // If no sync timestamp, fetch snapshot first
    if (!lastSync) {
      lastSync = await this.fetchSnapshot();
      // If snapshot failed, fall back to full SSE sync (no since param)
    }

    const params = new URLSearchParams();
    if (lastSync) params.set('since', lastSync);
    const token = getAccessToken();
    if (token) params.set('token', token);
    const qs = params.toString();
    const url = qs ? `${API_URL}/stream?${qs}` : `${API_URL}/stream`;

    this.eventSource = new EventSource(url);

    this.eventSource.onopen = () => {
      this.reconnectAttempts = 0;
      this.reconnectDelay = 1000;
      this.emit({ type: 'connected' });
    };

    this.eventSource.onmessage = async (event) => {
      try {
        const message = JSON.parse(event.data);

        // Handle resync: server says data is too stale — reconnect with full stream
        if (message.type === 'resync') {
          this.buffers.clear();
          await this.clearAllStores();
          await this.disconnect();
          void this.connect();
          this.emit({ type: 'resync' });
          return;
        }

        // Handle sync_complete
        if (message.type === 'sync_complete') {
          try { await this.flushAllBuffers(); } catch (e) { console.error('Flush failed:', e); }
          try { if (message.timestamp) await setLastSyncTimestamp(message.timestamp); } catch (e) { console.error('Save timestamp failed:', e); }
          this.isSynced = true;
          this.emit({ type: 'sync_complete', timestamp: message.timestamp });
          return;
        }

        // Judge call: ephemeral pass-through (no IndexedDB storage)
        if (message.type === 'judge_call') {
          this.emit({ type: 'judge_call', data: message.data });
          return;
        }

        // Generic handling: find matching spec
        for (const spec of SPECS) {
          // Batch event (catch-up after snapshot)
          if (message.type === spec.batchType) {
            const items = message.data as any[];
            const buf = this.buffers.get(spec.batchType) || [];
            buf.push(...items);
            this.buffers.set(spec.batchType, buf);
            return;
          }

          // Single event (real-time update)
          if (message.type === spec.singleType) {
            const item = message.data as any;
            // Skip SSE updates for tournaments in local offline mode
            if (spec.singleType === 'tournament' && isOffline(item.uid)) {
              return;
            }
            if (item.deleted_at) {
              await spec.del(item.uid);
            } else {
              await spec.save(item);
            }
            this.emit({ type: spec.singleType as SyncEventType, data: item });
            return;
          }
        }
      } catch (error) {
        console.error('Error processing SSE message:', error);
        this.emit({ type: 'error', error: String(error) });
      }
    };

    this.eventSource.onerror = (error) => {
      console.error('SSE connection error:', error);
      void this.handleError();
    };
  }

  /**
   * Flush all buffered data to IndexedDB.
   */
  private async flushAllBuffers(): Promise<void> {
    for (const spec of SPECS) {
      const buf = this.buffers.get(spec.batchType);
      if (buf && buf.length > 0) {
        this.buffers.set(spec.batchType, []);
        try {
          // Separate deleted items; skip offline tournaments from batch sync
          const toSave: any[] = [];
          const toDelete: string[] = [];
          for (const item of buf) {
            if (spec.batchType === 'tournaments' && isOffline(item.uid)) continue;
            if (item.deleted_at) {
              toDelete.push(item.uid);
            } else {
              toSave.push(item);
            }
          }
          if (toSave.length > 0) await spec.saveBatch(toSave);
          for (const uid of toDelete) await spec.del(uid);
        } catch (e) {
          console.error(`Flush ${spec.batchType} failed:`, e);
        }
      }
    }
  }

  /**
   * Clear all IndexedDB stores (used on resync and refresh).
   * Preserves offline tournament data to avoid data loss.
   */
  private async clearAllStores(): Promise<void> {
    // Preserve offline tournaments before clearing
    const offlineUids = getOfflineTournamentUids();
    const preserved: any[] = [];
    for (const uid of offlineUids) {
      const t = await getTournament(uid);
      if (t) preserved.push(t);
    }

    await clearAllUsers();
    await clearAllSanctions();
    await clearAllTournaments();
    await clearAllDecks();
    await clearAllLeagues();
    await clearLastSyncTimestamp();

    // Restore offline tournaments
    if (preserved.length > 0) {
      await saveTournamentsBatch(preserved);
    }
  }

  /**
   * Handle SSE error: disconnect (flushing buffers) then schedule reconnect.
   * When any tournament is offline, retry indefinitely with a higher backoff ceiling.
   */
  private async handleError(): Promise<void> {
    await this.disconnect();
    const { getOfflineTournamentUids } = await import('$lib/stores/offline.svelte');
    const hasOfflineTournaments = getOfflineTournamentUids().size > 0;
    const maxAttempts = hasOfflineTournaments ? Infinity : this.maxReconnectAttempts;

    if (this.reconnectAttempts < maxAttempts) {
      this.reconnectAttempts++;
      const delay = Math.min(
        this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1),
        this.maxReconnectDelay,
      );
      setTimeout(() => { void this.connect(); }, delay);
    } else {
      this.emit({ type: 'error', error: 'Failed to connect after multiple attempts' });
    }
  }

  /**
   * Disconnect from SSE stream, flushing any buffered data.
   */
  async disconnect(): Promise<void> {
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
      await this.flushAllBuffers();
      this.emit({ type: 'disconnected' });
    }
  }

  /**
   * Check if currently connected to SSE stream.
   */
  isConnected(): boolean {
    return this.eventSource !== null && this.eventSource.readyState === EventSource.OPEN;
  }

  /**
   * Reset: disconnect and clear all local data (used on logout).
   */
  async reset(): Promise<void> {
    await this.disconnect();
    await this.clearAllStores();
  }

  /**
   * Perform a full refresh: clear local data and resync everything.
   * After clearAllStores(), lastSync is null so connect() fetches snapshot first.
   */
  async refresh(): Promise<void> {
    await this.clearAllStores();
    await this.connect();
  }

  addEventListener(callback: SyncEventCallback): void {
    this.listeners.push(callback);
  }

  removeEventListener(callback: SyncEventCallback): void {
    this.listeners = this.listeners.filter(cb => cb !== callback);
  }

  private emit(event: SyncEvent): void {
    this.listeners.forEach(callback => callback(event));
  }
}

// Singleton instance
export const syncManager = new SyncManager();
