/**
 * SSE sync manager for real-time user updates.
 * Generic spec-based approach for all object types.
 */

import type { User, Sanction, Tournament, Rating } from '$lib/types';
import {
  saveUser,
  saveUsersBatch,
  saveSanction,
  saveSanctionsBatch,
  deleteSanction,
  saveTournament,
  saveTournamentsBatch,
  deleteTournament,
  saveRating,
  saveRatingsBatch,
  clearAllRatings,
  clearAllUsers,
  clearAllSanctions,
  clearAllTournaments,
  setLastSyncTimestamp,
  getLastSyncTimestamp,
  clearLastSyncTimestamp,
  clearChanges,
  clearChangeForUid,
} from './db';
import { getAccessToken } from '$lib/stores/auth.svelte';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

type SyncEventType = 'connected' | 'user' | 'sanction' | 'tournament' | 'rating' | 'sync_complete' | 'resync' | 'error' | 'disconnected';

interface SyncEvent {
  type: SyncEventType;
  data?: User | Sanction | Tournament | Rating;
  timestamp?: string | null;
  error?: string;
}

type SyncEventCallback = (event: SyncEvent) => void;

/** Spec for a synced object type */
interface ObjectSpec<T> {
  batchType: string;     // "users", "sanctions", "tournaments", "ratings"
  singleType: string;    // "user", "sanction", "tournament", "rating"
  save: (item: T) => Promise<void>;
  saveBatch: (items: T[]) => Promise<void>;
  del: (uid: string) => Promise<void>;
}

const SPECS: ObjectSpec<any>[] = [
  { batchType: 'users', singleType: 'user', save: saveUser, saveBatch: saveUsersBatch, del: async () => { /* users not deleted via SSE currently */ } },
  { batchType: 'sanctions', singleType: 'sanction', save: saveSanction, saveBatch: saveSanctionsBatch, del: deleteSanction },
  { batchType: 'tournaments', singleType: 'tournament', save: saveTournament, saveBatch: saveTournamentsBatch, del: deleteTournament },
  { batchType: 'ratings', singleType: 'rating', save: saveRating, saveBatch: saveRatingsBatch, del: async () => { /* ratings not deleted via SSE currently */ } },
];

class SyncManager {
  private eventSource: EventSource | null = null;
  private listeners: SyncEventCallback[] = [];
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000;

  // Generic buffers keyed by batch type
  private buffers: Map<string, any[]> = new Map();
  public isSynced = false;

  /**
   * Start syncing with the backend SSE stream.
   */
  async connect(): Promise<void> {
    await this.disconnect();
    this.isSynced = false;

    const lastSync = await getLastSyncTimestamp();
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

        // Handle resync: clear all stores and let full stream follow
        if (message.type === 'resync') {
          await this.clearAllStores();
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

        // Generic handling: find matching spec
        for (const spec of SPECS) {
          // Batch event (initial sync)
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
            if (item.deleted_at) {
              await spec.del(item.uid);
            } else {
              await spec.save(item);
            }
            await clearChangeForUid(item.uid);
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
          // Separate deleted items
          const toSave: any[] = [];
          const toDelete: string[] = [];
          for (const item of buf) {
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
   */
  private async clearAllStores(): Promise<void> {
    await clearAllUsers();
    await clearAllSanctions();
    await clearAllTournaments();
    await clearAllRatings();
    await clearChanges();
    await clearLastSyncTimestamp();
  }

  /**
   * Handle SSE error: disconnect (flushing buffers) then schedule reconnect.
   */
  private async handleError(): Promise<void> {
    await this.disconnect();
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);
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
   * Perform a full refresh: clear local data and resync everything.
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
