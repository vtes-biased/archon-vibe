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
  setLastSyncGeneratedAt,
  getLastSyncGeneratedAt,
  clearLastSyncGeneratedAt,
  getTournament,
  getUser,
  getSanction,
  getDeck,
  getOfflinePlayers,
  getOfflineSanctionUids,
  getOfflineDeckUids,
} from './db';
import { getAccessToken, ensureSyncToken, refreshTokens } from '$lib/stores/auth.svelte';
import { isOffline, getOfflineTournamentUids, lostOfflineLock, handleOfflineLockLost } from '$lib/stores/offline.svelte';

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

type SyncEventType = 'connected' | 'user' | 'sanction' | 'tournament' | 'deck' | 'league' | 'judge_call' | 'sync_complete' | 'syncing' | 'resync' | 'error' | 'disconnected';

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
  // `item` carries the full (soft-deleted) payload when available. Most types
  // hard-delete by uid; users instead persist the deleted_at-marked row (see
  // the users spec) so getUser still resolves it for tournament player refs.
  del: (uid: string, item?: T) => Promise<void>;
}

const SPECS: ObjectSpec<any>[] = [
  // Users are never hard-deleted from the cache: a soft-deleted user (e.g. a
  // merge_users dup) may still be referenced by tournament players, so we keep
  // the row (saving its deleted_at) for getUser to resolve, and filter it out of
  // the list/search queries instead (pst #77). Without the payload we no-op.
  { batchType: 'users', singleType: 'user', save: saveUser, saveBatch: saveUsersBatch, del: async (_uid, item) => { if (item) await saveUser(item); } },
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

  // Monotonic connect generation. Bumped at the top of every connect(); a
  // cycle whose epoch is stale aborts at its next await instead of mutating
  // shared state. Guards against overlapping refresh()/connect() cycles
  // (e.g. logout→login→claim in quick succession) racing on IndexedDB and
  // this.eventSource, which could otherwise leave a stale lower-access-level
  // stream's data installed on top of the newest one's.
  private connectEpoch = 0;

  // Generic buffers keyed by batch type
  private buffers: Map<string, any[]> = new Map();
  public isSynced = false;

  // High-water mark of the sync cursor, mirrored to IndexedDB. Advanced on
  // sync_complete AND on every applied live event so the `since=` catch-up
  // window after a reconnect stays minimal (the server re-streams everything
  // modified after this; if it only moved on sync_complete the backlog would
  // grow unbounded and eventually trip the 3-day full-resync guard).
  private lastTimestamp: string | null = null;

  /** True if a newer connect() has started since `epoch` was captured. */
  private superseded(epoch: number): boolean {
    return epoch !== this.connectEpoch;
  }

  /**
   * Fetch and load a gzip snapshot from the server.
   * Returns the snapshot timestamp, or null on failure (or if superseded).
   * `epoch` is the connect generation that requested this snapshot; if a newer
   * connect() starts while we're in flight we bail before touching IndexedDB.
   */
  private async fetchSnapshot(epoch: number, token: string | null): Promise<string | null> {
    const buildUrl = (t: string | null) => {
      const params = new URLSearchParams();
      if (t) params.set('token', t);
      const qs = params.toString();
      return qs ? `${API_URL}/snapshot?${qs}` : `${API_URL}/snapshot`;
    };

    try {
      let response = await fetch(buildUrl(token));
      if (this.superseded(epoch)) return null;
      // Stale token → 401: refresh+retry once instead of falling through to a
      // stream connect with the same bad token.
      if (response.status === 401 && token) {
        const refreshed = await refreshTokens();
        if (this.superseded(epoch)) return null;
        if (refreshed) {
          response = await fetch(buildUrl(getAccessToken()));
          if (this.superseded(epoch)) return null;
        }
      }
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

      const sections = JSON.parse(text) as {
        type: string;
        data?: any[];
        timestamp?: string;
        generated_at?: string;
      }[];

      // A newer connect() may have superseded us while the snapshot was in
      // flight; bail before touching IndexedDB so we don't clear/clobber the
      // data the newer cycle is loading.
      if (this.superseded(epoch)) return null;

      // Clear stores before loading (preserve offline tournaments)
      await this.clearAllStores();
      if (this.superseded(epoch)) return null;

      // Load each section into IDB
      let timestamp: string | null = null;
      let generatedAt: string | null = null;
      for (const section of sections) {
        if (this.superseded(epoch)) return null;
        if (section.type === 'meta') {
          timestamp = section.timestamp || null;
          generatedAt = section.generated_at || null;
          continue;
        }
        // Find matching spec by singleType (snapshot uses singular: "user", "tournament", etc.)
        const spec = SPECS.find(s => s.singleType === section.type);
        if (spec && section.data && section.data.length > 0) {
          let items = section.data;
          // Skip tournaments this device holds offline — UNLESS the server shows
          // we've lost the lock (force-unlock / takeover), in which case reconcile
          // and apply the authoritative copy so the device "gets the memo".
          if (spec.batchType === 'tournaments') {
            const kept: any[] = [];
            for (const t of items) {
              if (lostOfflineLock(t)) {
                await handleOfflineLockLost(t.uid);
                kept.push(t);
              } else if (!isOffline(t.uid)) {
                kept.push(t);
              }
            }
            items = kept;
          }
          if (items.length > 0) await spec.saveBatch(items);
        }
      }

      if (this.superseded(epoch)) return null;
      if (timestamp) {
        await setLastSyncTimestamp(timestamp);
      }
      if (generatedAt) {
        await setLastSyncGeneratedAt(generatedAt);
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
    // Each connect() supersedes any still-running earlier one. After every
    // await we re-check the epoch and bail if a newer connect()/refresh() has
    // started, so a slow stale cycle (e.g. the pre-claim public-level stream)
    // can't clear IndexedDB or install its EventSource on top of newer data.
    const epoch = ++this.connectEpoch;
    await this.disconnect();
    if (this.superseded(epoch)) return;
    this.isSynced = false;
    this.emit({ type: 'syncing' });

    // Refresh on demand so neither the snapshot nor the stream opens with a
    // stale token. One token feeds both requests below.
    const auth = await ensureSyncToken();
    if (this.superseded(epoch)) return;
    if (auth.kind === 'retry') {
      void this.handleError();  // transient: back off, don't connect stale
      return;
    }
    if (auth.kind === 'downgrade') {
      // Drop to anonymous via clear-then-refill, not a since-overlay that would
      // mix member + public rows.
      void this.refresh();
      return;
    }
    const token = auth.kind === 'token' ? auth.token : null;

    let lastSync: string | null = await getLastSyncTimestamp();
    if (this.superseded(epoch)) return;

    // If no sync timestamp, fetch snapshot first
    if (!lastSync) {
      lastSync = await this.fetchSnapshot(epoch, token);
      if (this.superseded(epoch)) return;
      // If snapshot failed, fall back to full SSE sync (no since param)
    }

    // Seed the in-memory high-water mark from the cursor we connect with.
    this.lastTimestamp = lastSync;

    // Snapshot freshness signal: lets the server's staleness/access guards measure real
    // client-away time instead of the data's last-modified time (see backend stream guard).
    const generatedAt = await getLastSyncGeneratedAt();
    if (this.superseded(epoch)) return;

    const params = new URLSearchParams();
    if (lastSync) params.set('since', lastSync);
    if (generatedAt) params.set('generated_at', generatedAt);
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
          try { if (message.timestamp) { this.lastTimestamp = message.timestamp; await setLastSyncTimestamp(message.timestamp); } } catch (e) { console.error('Save timestamp failed:', e); }
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
            // Skip SSE updates for tournaments in local offline mode — unless the
            // server shows we've lost the lock (force-unlock / takeover): then
            // reconcile and fall through to apply the authoritative update.
            if (spec.singleType === 'tournament' && isOffline(item.uid)) {
              if (lostOfflineLock(item)) {
                await handleOfflineLockLost(item.uid);
              } else {
                return;
              }
            }
            if (item.deleted_at) {
              await spec.del(item.uid, item);
            } else {
              await spec.save(item);
            }
            // Advance the sync cursor past this applied event so a reconnect
            // resumes from here rather than re-streaming since the last
            // sync_complete. Use the envelope `ts` (authoritative modified_at,
            // same value space as the server's `since` filter and sync_complete)
            // — NOT item.modified, which is an app-clock payload value in a
            // different format. Monotonic guard against any out-of-order event.
            const ts: string | undefined = message.ts;
            if (ts && (this.lastTimestamp === null || ts > this.lastTimestamp)) {
              this.lastTimestamp = ts;
              try { await setLastSyncTimestamp(ts); } catch (e) { console.error('Save cursor failed:', e); }
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
          const toDelete: any[] = [];
          for (const item of buf) {
            if (spec.batchType === 'tournaments' && isOffline(item.uid)) {
              if (lostOfflineLock(item)) {
                await handleOfflineLockLost(item.uid);
              } else {
                continue;
              }
            }
            if (item.deleted_at) {
              toDelete.push(item);
            } else {
              toSave.push(item);
            }
          }
          if (toSave.length > 0) await spec.saveBatch(toSave);
          for (const item of toDelete) await spec.del(item.uid, item);
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
    // Preserve unsynced offline-tournament data before clearing — it isn't
    // re-fetchable from SSE (offline tournaments are locked to this device).
    // The offline_* metadata keys survive (only the last_sync_* cursor keys are removed),
    // but the rows they point to live in the cleared stores, so rescue them too —
    // otherwise go-online's getSanction/getDeck lookups return undefined and the
    // offline sanctions/decks are silently dropped from reconciliation (pst #14).
    const offlineUids = getOfflineTournamentUids();
    const tournaments: Tournament[] = [];
    const users: User[] = [];
    const sanctions: Sanction[] = [];
    const decks: DeckObject[] = [];
    for (const uid of offlineUids) {
      const t = await getTournament(uid);
      if (t) tournaments.push(t);
      for (const p of await getOfflinePlayers(uid)) {
        const u = await getUser(p.temp_uid);
        if (u) users.push(u);
      }
      for (const sUid of await getOfflineSanctionUids(uid)) {
        const s = await getSanction(sUid);
        if (s) sanctions.push(s);
      }
      for (const dUid of await getOfflineDeckUids(uid)) {
        const d = await getDeck(dUid);
        if (d) decks.push(d);
      }
    }

    await clearAllUsers();
    await clearAllSanctions();
    await clearAllTournaments();
    await clearAllDecks();
    await clearAllLeagues();
    await clearLastSyncTimestamp();
    await clearLastSyncGeneratedAt();

    // Restore preserved offline data.
    if (tournaments.length > 0) await saveTournamentsBatch(tournaments);
    if (users.length > 0) await saveUsersBatch(users);
    if (sanctions.length > 0) await saveSanctionsBatch(sanctions);
    if (decks.length > 0) await saveDecksBatch(decks);
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
