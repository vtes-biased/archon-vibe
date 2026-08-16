import type { User, Sanction, Tournament, DeckObject, League, Promo } from '$lib/types';
import {
  saveUser,
  saveUsersBatch,
  deleteUser,
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
  savePromo,
  savePromosBatch,
  deletePromo,
  clearAllUsers,
  clearAllSanctions,
  clearAllTournaments,
  clearAllDecks,
  clearAllLeagues,
  clearAllPromos,
  setLastSyncTimestamp,
  getLastSyncTimestamp,
  clearLastSyncTimestamp,
  setLastSyncGeneratedAt,
  getLastSyncGeneratedAt,
  clearLastSyncGeneratedAt,
  setLastSyncAccessVersion,
  getLastSyncAccessVersion,
  clearLastSyncAccessVersion,
  getSnapshotIngesting,
  setSnapshotIngesting,
  clearSnapshotIngesting,
  getTournament,
  getUser,
  getSanction,
  getDeck,
  getOfflinePlayers,
  getOfflineSanctionUids,
  getOfflineDeckUids,
  getDeviceId,
} from './db';
import { getAccessToken, ensureSyncToken, refreshTokens } from '$lib/stores/auth.svelte';
import { isOffline, getOfflineTournamentUids, lostOfflineLock, handleOfflineLockLost } from '$lib/stores/offline.svelte';

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

// Must match backend snapshots.SNAPSHOT_FORMAT_VERSION; a mismatch is refused
// outright rather than half-ingested into the stores.
const SNAPSHOT_FORMAT_VERSION = 2;

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

interface ObjectSpec<T> {
  batchType: string;
  singleType: string;
  save: (item: T) => Promise<void>;
  saveBatch: (items: T[]) => Promise<void>;
  // Hard-deletes by uid on a tombstone; `item` carries the soft-deleted
  // payload when available, but isn't needed.
  del: (uid: string, item?: T) => Promise<void>;
}

const SPECS: ObjectSpec<any>[] = [
  // Users hard-delete safely: every deletable member is VEKN-less, and tournament participation
  // requires a vekn_id, so a deleted user is never a live player ref.
  { batchType: 'users', singleType: 'user', save: saveUser, saveBatch: saveUsersBatch, del: deleteUser },
  { batchType: 'sanctions', singleType: 'sanction', save: saveSanction, saveBatch: saveSanctionsBatch, del: deleteSanction },
  { batchType: 'tournaments', singleType: 'tournament', save: saveTournament, saveBatch: saveTournamentsBatch, del: deleteTournament },
  { batchType: 'decks', singleType: 'deck', save: saveDeck, saveBatch: saveDecksBatch, del: deleteDeck },
  { batchType: 'leagues', singleType: 'league', save: saveLeague, saveBatch: saveLeaguesBatch, del: deleteLeague },
  {
    batchType: 'promos',
    singleType: 'promo',
    save: async (p: Promo) => { await savePromo(p); prefetchPromoImages([p]); },
    saveBatch: async (ps: Promo[]) => { await savePromosBatch(ps); prefetchPromoImages(ps); },
    del: deletePromo,
  },
];

// Prefetches into the SW cache since it only populates on fetch; offline
// raffle display needs the bytes even if this device never viewed the promo.
function prefetchPromoImages(promos: Promo[]): void {
  const apiBase = import.meta.env.VITE_API_URL ?? "";
  for (const p of promos) {
    if (p.active && p.image_path && !p.deleted_at) {
      fetch(`${apiBase}${p.image_path}`).catch(() => {});
    }
  }
}

class SyncManager {
  private eventSource: EventSource | null = null;
  private listeners: SyncEventCallback[] = [];
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000;
  private maxReconnectDelay = 120_000;

  // Resets only on sync_complete; assumes the server always closes a catch-up stream with
  // sync_complete, else a healthy client accrues a false streak and self-throttles.
  private resyncStreak = 0;
  // Counts non-warm-up failures (503 is expected first-sync warm-up, never counted); surfaces a
  // console signal once broken repeatedly instead of failing silently forever.
  private snapshotFailStreak = 0;
  private static readonly SNAPSHOT_FAIL_WARN = 5;
  private static readonly RESYNC_BACKOFF_AFTER = 1;
  // Rows buffered per type before a saveBatch during snapshot ingest. Bounds peak
  // heap to one batch; the file itself is streamed, never materialised.
  private static readonly SNAPSHOT_BATCH = 500;

  // Bumped at the top of every connect(); a stale epoch aborts at its next await, guarding overlapping
  // connect()/refresh() cycles from clobbering IndexedDB with stale data.
  private connectEpoch = 0;

  private buffers: Map<string, any[]> = new Map();
  public isSynced = false;

  // Advances on sync_complete AND every applied live event, so the since= catch-up window stays
  // minimal instead of growing unbounded and tripping the 3-day resync guard.
  private lastTimestamp: string | null = null;

  private superseded(epoch: number): boolean {
    return epoch !== this.connectEpoch;
  }

  // If a newer connect() starts while this snapshot fetch is in flight, bail
  // before touching IndexedDB.
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
        // 503 = first-sync warm-up (snapshot generator hasn't run yet): expected, self-heals, retried
        // indefinitely by connect(). Anything else is a genuinely broken snapshot.
        this.noteSnapshotFailure(response.status === 503 ? null : `status ${response.status}`);
        return null;
      }

      // Seed the access-version fingerprint from the response header BEFORE opening /stream, so the
      // first connect echoes a matching `av` and doesn't resync — it's per-user, so it can't live in the shared snapshot body.
      const accessVersion = response.headers.get('X-Access-Version');

      if (!response.body) {
        this.noteSnapshotFailure('no response body');
        return null;
      }

      // Streams gunzip→decode→split→parse→save→drop so no step holds the whole corpus (previous shape
      // OOM-killed mid-range phones). Sniffs the magic bytes since not every proxy honors Content-Encoding: gzip.
      const reader = response.body.getReader();
      const first = await reader.read();
      const head = first.value;
      const stillGzipped = !!head && head[0] === 0x1f && head[1] === 0x8b;
      const source = new ReadableStream<BufferSource>({
        start(controller) {
          if (head) controller.enqueue(head);
          if (first.done) controller.close();
        },
        async pull(controller) {
          const { value, done } = await reader.read();
          if (done) controller.close();
          else controller.enqueue(value);
        },
        cancel(reason) {
          void reader.cancel(reason);
        },
      });
      let byteStream: ReadableStream<BufferSource> = source;
      if (stillGzipped) byteStream = source.pipeThrough(new DecompressionStream('gzip'));
      const textStream = byteStream.pipeThrough(new TextDecoderStream());

      // A newer connect() may have superseded us while the snapshot was in flight; bail before
      // touching IndexedDB so we don't clear/clobber the data the newer cycle is loading.
      if (this.superseded(epoch)) return null;

      // Mark BEFORE the clear: everything from here to the eof line leaves the stores in a partial
      // state that looks valid, so a crash/close/truncation in between must be detectable on the next boot.
      await setSnapshotIngesting();
      await this.clearAllStores();
      if (this.superseded(epoch)) return null;

      // Per-type buffers flushed through the existing saveBatch, so a single
      // unordered pass of interleaved types still writes in batches.
      const buffers = new Map<string, any[]>();
      const flush = async (spec: ObjectSpec<any>) => {
        const items = buffers.get(spec.batchType);
        if (!items?.length) return;
        buffers.set(spec.batchType, []);
        await spec.saveBatch(items);
      };

      let timestamp: string | null = null;
      let generatedAt: string | null = null;
      let sawEof = false;
      let objectLines = 0;

      const handleLine = async (line: string): Promise<void> => {
        const entry = JSON.parse(line) as {
          type: string;
          data?: any;
          version?: number;
          timestamp?: string;
          generated_at?: string;
          count?: number;
        };
        if (entry.type === 'header') {
          if (entry.version !== SNAPSHOT_FORMAT_VERSION) {
            throw new Error(`unsupported snapshot version ${entry.version}`);
          }
          timestamp = entry.timestamp || null;
          generatedAt = entry.generated_at || null;
          return;
        }
        if (entry.type === 'eof') {
          if (entry.count !== objectLines) {
            throw new Error(`snapshot truncated: ${objectLines}/${entry.count} objects`);
          }
          sawEof = true;
          return;
        }
        // Counted BEFORE the spec lookup: an unknown type is simply ignored, so a backend that adds
        // an object type before clients ship support doesn't look truncated to every one of them.
        objectLines++;
        const spec = SPECS.find(s => s.singleType === entry.type);
        if (!spec || !entry.data) return;
        // Skip tournaments this device holds offline — UNLESS the server shows we've lost the lock
        // (force-unlock/takeover), in which case reconcile and apply the authoritative copy.
        if (spec.batchType === 'tournaments') {
          if (lostOfflineLock(entry.data)) {
            await handleOfflineLockLost(entry.data.uid);
          } else if (isOffline(entry.data.uid)) {
            return;
          }
        }
        const buf = buffers.get(spec.batchType) ?? [];
        buf.push(entry.data);
        buffers.set(spec.batchType, buf);
        if (buf.length >= SyncManager.SNAPSHOT_BATCH) await flush(spec);
      };

      const lines = textStream.getReader();
      let pending = '';
      for (;;) {
        const { value, done } = await lines.read();
        if (done) break;
        if (this.superseded(epoch)) {
          void lines.cancel();
          return null;
        }
        const parts = (pending + value).split('\n');
        pending = parts.pop() ?? '';
        for (const line of parts) {
          if (line) await handleLine(line);
        }
      }
      if (pending.trim()) await handleLine(pending);

      for (const spec of SPECS) await flush(spec);

      // No eof line = the file ended early (dropped connection, partial write). Leave the ingest marker
      // set so the next boot refetches instead of trusting a corpus silently missing rows.
      if (!sawEof) throw new Error('snapshot ended without eof');

      // Cleared before the supersede check: eof landed and every batch is flushed, so the stores are
      // whole even if a newer connect() is about to discard this cycle.
      await clearSnapshotIngesting();

      if (this.superseded(epoch)) return null;
      if (timestamp) {
        await setLastSyncTimestamp(timestamp);
      }
      if (generatedAt) {
        await setLastSyncGeneratedAt(generatedAt);
      }
      if (accessVersion) {
        await setLastSyncAccessVersion(accessVersion);
      }

      this.snapshotFailStreak = 0;
      return timestamp;
    } catch (e) {
      // Corrupt gzip / JSON parse / truncation / network throw: broken, not warm-up.
      // The ingest marker is deliberately NOT cleared — see setSnapshotIngesting.
      this.noteSnapshotFailure(String(e));
      return null;
    }
  }

  /** `detail === null` is the expected warm-up 503 — not counted. A string keeps retrying but warns
   * once repeated. Deliberately console-only, not emit({type:'error'}) — +layout treats that as terminal and shows a Reconnect banner, wrong for an active auto-retry. */
  private noteSnapshotFailure(detail: string | null): void {
    if (detail === null) return;
    this.snapshotFailStreak++;
    if (this.snapshotFailStreak >= SyncManager.SNAPSHOT_FAIL_WARN) {
      console.error(`Snapshot broken (${detail}) after ${this.snapshotFailStreak} attempts; still retrying — check the server`);
    }
  }

  /** After clearAllStores(), lastSync is null so connect() naturally fetches snapshot first. */
  async connect(): Promise<void> {
    // Each connect() supersedes any still-running earlier one; after every await we re-check the epoch
    // and bail if a newer cycle started, so a slow stale one can't clear IndexedDB on top of newer data.
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

    // A marker surviving from a previous session means the stores hold a partial snapshot: the rows
    // present look valid, so nothing downstream could notice — clear and refetch before reading the cursor.
    if (await getSnapshotIngesting()) {
      console.warn('Snapshot ingest was interrupted; discarding partial data');
      await this.clearAllStores();
      await clearSnapshotIngesting();
    }
    if (this.superseded(epoch)) return;

    let lastSync: string | null = await getLastSyncTimestamp();
    if (this.superseded(epoch)) return;

    if (!lastSync) {
      lastSync = await this.fetchSnapshot(epoch, token);
      if (this.superseded(epoch)) return;
      if (!lastSync) {
        // Snapshot unavailable (first-VEKN-sync warm-up) — must NOT fall through to /stream: with no
        // `av` the handshake always mismatches and resyncs immediately, a tight clear/reconnect loop. Retry the snapshot; it self-heals once the first sync lands.
        void this.handleError(true);
        return;
      }
    }

    this.lastTimestamp = lastSync;

    // Snapshot freshness signal: lets the server's staleness/access guards measure real
    // client-away time instead of the data's last-modified time.
    const generatedAt = await getLastSyncGeneratedAt();
    if (this.superseded(epoch)) return;

    // Opaque entitlement fingerprint: the server resyncs us if it no longer matches the
    // access we currently have (level/role/country/organizer-set change while away).
    const accessVersion = await getLastSyncAccessVersion();
    if (this.superseded(epoch)) return;

    const params = new URLSearchParams();
    if (lastSync) params.set('since', lastSync);
    if (generatedAt) params.set('generated_at', generatedAt);
    if (accessVersion) params.set('av', accessVersion);
    if (token) params.set('token', token);
    // Identifies this device so the server can self-exclude it from its own offline-lock writes
    // (go-online), whose echo would otherwise race ahead of the HTTP response.
    params.set('device_id', getDeviceId());
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

        if (message.type === 'resync') {
          // Clear buffers before disconnect(): its flushAllBuffers() would
          // otherwise re-populate the stores we just wiped.
          this.buffers.clear();
          await this.clearAllStores();
          await this.disconnect();
          this.emit({ type: 'resync' });
          // First resync reconnects immediately; if resyncs keep coming with no sync_complete between
          // them, back off so a persistent cause can't spin a full-speed clear+reconnect loop.
          this.resyncStreak++;
          if (this.resyncStreak <= SyncManager.RESYNC_BACKOFF_AFTER) {
            void this.connect();
          } else {
            const delay = Math.min(
              this.reconnectDelay * Math.pow(2, this.resyncStreak - 1),
              this.maxReconnectDelay,
            );
            console.error(`SSE resync loop: ${this.resyncStreak} resyncs without sync_complete, backing off ${delay}ms`);
            setTimeout(() => { void this.connect(); }, delay);
          }
          return;
        }

        if (message.type === 'sync_complete') {
          this.resyncStreak = 0;
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

        for (const spec of SPECS) {
          if (message.type === spec.batchType) {
            const items = message.data as any[];
            const buf = this.buffers.get(spec.batchType) || [];
            buf.push(...items);
            this.buffers.set(spec.batchType, buf);
            return;
          }

          if (message.type === spec.singleType) {
            const item = message.data as any;
            // Skip SSE updates for tournaments in local offline mode — unless the server shows we've
            // lost the lock (force-unlock/takeover): then reconcile and apply the authoritative update.
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
            // Advances the cursor past this applied event using the envelope `ts` (authoritative
            // modified_at) — NOT item.modified (an app-clock value in a different format). Monotonic guard against out-of-order events.
            const ts: string | undefined = message.ts;
            if (ts && (this.lastTimestamp === null || ts > this.lastTimestamp)) {
              this.lastTimestamp = ts;
              try { await setLastSyncTimestamp(ts); } catch (e) { console.error('Save cursor failed:', e); }
            }
            // A targeted entitlement frame carries the new fingerprint so the next reconnect doesn't
            // mismatch. Trusted blindly: `av` must ride ONLY per-user frames — a shared av would be wrong for some recipients and resync-loop them.
            const newAv: string | undefined = message.av;
            if (newAv) {
              try { await setLastSyncAccessVersion(newAv); } catch (e) { console.error('Save access version failed:', e); }
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
      // EventSource fires onerror on every transient drop before auto-reconnecting; we run our own backoff
      // in handleError(). Log at debug so an expected reconnect doesn't spam error-level noise.
      console.debug('SSE connection error (will reconnect):', error);
      void this.handleError();
    };
  }

  private async flushAllBuffers(): Promise<void> {
    for (const spec of SPECS) {
      const buf = this.buffers.get(spec.batchType);
      if (buf && buf.length > 0) {
        this.buffers.set(spec.batchType, []);
        try {
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

  private async clearAllStores(): Promise<void> {
    // Preserve unsynced offline-tournament data before clearing (not re-fetchable from SSE): the
    // offline_* metadata keys survive, but the rows they point to live in the cleared stores — rescue them or go-online's getSanction/getDeck lookups return undefined.
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
    await clearAllPromos();
    await clearLastSyncTimestamp();
    await clearLastSyncGeneratedAt();
    await clearLastSyncAccessVersion();

    if (tournaments.length > 0) await saveTournamentsBatch(tournaments);
    if (users.length > 0) await saveUsersBatch(users);
    if (sanctions.length > 0) await saveSanctionsBatch(sanctions);
    if (decks.length > 0) await saveDecksBatch(decks);
  }

  /** When any tournament is offline, or on `transient` (snapshot not generated yet — first-sync
   * warm-up), retries indefinitely with the capped backoff instead of giving up after maxReconnectAttempts. */
  private async handleError(transient = false): Promise<void> {
    await this.disconnect();
    const hasOfflineTournaments = getOfflineTournamentUids().size > 0;
    const maxAttempts = transient || hasOfflineTournaments ? Infinity : this.maxReconnectAttempts;

    if (this.reconnectAttempts < maxAttempts) {
      this.reconnectAttempts++;
      const delay = Math.min(
        this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1),
        this.maxReconnectDelay,
      );
      setTimeout(() => { void this.connect(); }, delay);
    } else {
      // Terminal: reconnect budget exhausted. This is the genuine failure worth
      // an error-level log (the per-drop onerror above stays at debug).
      console.error(`SSE connection failed after ${this.reconnectAttempts} attempts`);
      this.emit({ type: 'error', error: 'Failed to connect after multiple attempts' });
    }
  }

  async disconnect(): Promise<void> {
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
      await this.flushAllBuffers();
      this.emit({ type: 'disconnected' });
    }
  }

  isConnected(): boolean {
    return this.eventSource !== null && this.eventSource.readyState === EventSource.OPEN;
  }

  async reset(): Promise<void> {
    await this.disconnect();
    await this.clearAllStores();
  }

  /** After clearAllStores(), lastSync is null so connect() fetches snapshot first. */
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

  /** Re-runs the same UI refresh hooks SSE events trigger, for LOCAL IndexedDB mutations on a device-
   * locked offline tournament (no SSE will arrive). Keep this narrow — online mutations must keep flowing through server → SSE. */
  notifyLocalMutation(type: 'sanction' | 'deck' | 'tournament', data?: Sanction | DeckObject | Tournament): void {
    this.emit({ type, data });
  }
}

export const syncManager = new SyncManager();
