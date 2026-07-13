/**
 * Per-tournament offline state management.
 * Tracks which tournaments are in local offline mode, persisted in IndexedDB metadata.
 */

import type { Tournament, Sanction, DeckObject, OfflinePlayer } from '$lib/types';
import {
  getMetadata, setMetadata, deleteMetadata, getMetadataByPrefix,
  getDeviceId, getTournament, saveTournament,
  getOfflinePlayers, addOfflinePlayer as dbAddOfflinePlayer,
  setOfflinePlayers, getOfflineSanctionUids, addOfflineSanctionUid,
  getOfflineDeckUids, getDeck,
  getSanction, saveUser, deleteUser,
} from '$lib/db';
import { apiRequest, ApiError } from '$lib/api';
import { showToast } from '$lib/stores/toast.svelte';
import * as m from '$lib/paraglide/messages.js';

// Reactive set of offline tournament UIDs
let offlineTournamentUids = $state<Set<string>>(new Set());

// Last sync timestamps per tournament
let lastSyncTimes = $state<Map<string, string>>(new Map());

// Debounce timer per tournament for opportunistic sync
const syncTimers = new Map<string, ReturnType<typeof setTimeout>>();
const SYNC_DEBOUNCE_MS = 30_000;

// Tournaments this device is actively bringing back online. While a go-online
// is in flight its HTTP response is the sole authority on the lock outcome, so
// any SSE lock-state frame for the tournament is ignored until it resolves (see
// lostOfflineLock). The server already self-excludes this device from the
// go-online echo (broadcast exclude_device_id); this guard is the tab-precise
// backstop and also collapses a concurrent force-unlock/takeover frame into the
// single warning the 410/409 response path raises. See lostOfflineLock.
const goingOnlineUids = new Set<string>();

/** Initialize offline state from IndexedDB on app startup. */
export async function initOfflineState(): Promise<void> {
  const entries = await getMetadataByPrefix('offline_tournament:');
  const uids = new Set<string>();
  for (const [key] of entries) {
    uids.add(key.replace('offline_tournament:', ''));
  }
  offlineTournamentUids = uids;

  // Load last sync times
  const syncEntries = await getMetadataByPrefix('offline_last_sync:');
  const times = new Map<string, string>();
  for (const [key, value] of syncEntries) {
    times.set(key.replace('offline_last_sync:', ''), value);
  }
  lastSyncTimes = times;
}

/** Check if a tournament is in local offline mode. */
export function isOffline(tournamentUid: string): boolean {
  return offlineTournamentUids.has(tournamentUid);
}

/** Get the set of offline tournament UIDs (reactive). */
export function getOfflineTournamentUids(): Set<string> {
  return offlineTournamentUids;
}

/** Get the last opportunistic sync time for a tournament. */
export function getLastSyncTime(tournamentUid: string): string | undefined {
  return lastSyncTimes.get(tournamentUid);
}

/** Mark a tournament as offline locally (after server lock confirmed). */
export async function markOffline(tournamentUid: string): Promise<void> {
  await setMetadata(`offline_tournament:${tournamentUid}`, 'true');
  offlineTournamentUids = new Set([...offlineTournamentUids, tournamentUid]);
}

/** Clear offline state for a tournament (after go-online confirmed). */
export async function clearOfflineState(tournamentUid: string): Promise<void> {
  await deleteMetadata(`offline_tournament:${tournamentUid}`);
  await deleteMetadata(`offline_players:${tournamentUid}`);
  await deleteMetadata(`offline_sanctions:${tournamentUid}`);
  await deleteMetadata(`offline_decks:${tournamentUid}`);
  await deleteMetadata(`offline_last_sync:${tournamentUid}`);

  const newSet = new Set(offlineTournamentUids);
  newSet.delete(tournamentUid);
  offlineTournamentUids = newSet;

  const newTimes = new Map(lastSyncTimes);
  newTimes.delete(tournamentUid);
  lastSyncTimes = newTimes;

  // Clear debounce timer
  const timer = syncTimers.get(tournamentUid);
  if (timer) {
    clearTimeout(timer);
    syncTimers.delete(tournamentUid);
  }
}

/**
 * True if a locally-offline tournament has lost its lock on the server — i.e.
 * this device went offline but an organizer/IC has since force-unlocked (cleared
 * offline_mode) or force-taken-over (moved the lock to another device). When
 * true, this device's unsynced offline work can no longer be committed.
 */
export function lostOfflineLock(t: {
  uid: string;
  offline_mode?: boolean;
  offline_device_id?: string;
}): boolean {
  if (!isOffline(t.uid)) return false;
  // A go-online we initiated is in flight: its HTTP response decides the lock
  // outcome (success, 410 force-unlock, or 409 takeover all reconcile there), so
  // ignore every SSE lock-state frame for this tournament until then — the
  // server's own offline_mode=false echo AND a concurrent unlock/takeover alike.
  // Acting on them here would double-report the transition the response handles.
  if (goingOnlineUids.has(t.uid)) return false;
  return t.offline_mode !== true || t.offline_device_id !== getDeviceId();
}

/**
 * Reconcile after this device lost its offline lock: drop the now-orphaned local
 * offline state and warn the holder that its unsynced changes are gone. Called
 * from the SSE/snapshot path the moment the authoritative (unlocked) tournament
 * reaches the device — so a lost/recovered device "gets the memo" on reconnect.
 */
export async function handleOfflineLockLost(tournamentUid: string): Promise<void> {
  await clearOfflineState(tournamentUid);
  // Irreversible data loss: persist until dismissed, never auto-fade.
  showToast({ type: 'error', message: m.offline_lock_lost_warning(), duration: 0 });
}

/** The offline lock was lost during go-online; the loss toast is already shown. */
export class OfflineLockLostError extends Error {}

/** Request the server to lock a tournament for offline use. */
export async function goOffline(tournamentUid: string): Promise<void> {
  const deviceId = getDeviceId();
  await apiRequest(`/api/tournaments/${tournamentUid}/go-offline`, {
    method: 'POST',
    body: JSON.stringify({ device_id: deviceId }),
  });
  await markOffline(tournamentUid);
}

/** Bring a tournament back online with full reconciliation. */
export async function goOnline(tournamentUid: string): Promise<Tournament> {
  // Suppress the go-online self-echo (offline_mode=false) over SSE until local
  // offline state is cleared below — see goingOnlineUids / lostOfflineLock.
  goingOnlineUids.add(tournamentUid);
  try {
    const deviceId = getDeviceId();
    const tournament = await getTournament(tournamentUid);
    if (!tournament) throw new Error('Tournament not found locally');

    const offlinePlayers = await getOfflinePlayers(tournamentUid);

    // Gather offline sanctions
    const sanctionUids = await getOfflineSanctionUids(tournamentUid);
    const offlineSanctions: Sanction[] = [];
    for (const uid of sanctionUids) {
      const s = await getSanction(uid);
      if (s) offlineSanctions.push(s);
    }

    // Gather offline decks
    const deckUids = await getOfflineDeckUids(tournamentUid);
    const offlineDecks: DeckObject[] = [];
    for (const uid of deckUids) {
      const d = await getDeck(uid);
      if (d) offlineDecks.push(d);
    }

    let result: Tournament;
    let summary: { players_matched: number; accounts_created: number; decks_synced: number; sanctions_synced: number } | null = null;
    try {
      const resp = await apiRequest<{
        tournament: Tournament;
        summary: { players_matched: number; accounts_created: number; decks_synced: number; sanctions_synced: number };
      }>(
        `/api/tournaments/${tournamentUid}/go-online`,
        {
          method: 'POST',
          body: JSON.stringify({
            device_id: deviceId,
            tournament,
            offline_players: offlinePlayers,
            offline_sanctions: offlineSanctions,
            offline_decks: offlineDecks,
          }),
        },
        // handleGoOnline's catch toasts (incl. the localized 410 lock-lost
        // message) and covers network errors — suppress apiRequest's duplicate.
        { suppressErrorToast: true },
      );
      result = resp.tournament;
      summary = resp.summary;
    } catch (e) {
      // The offline session ended under this device — 410 (an IC force-unlocked
      // it, or it was already brought online) or 409 (another device force-took
      // over the lock). Either way this device's offline snapshot can't be
      // synced: drop the orphaned local state and surface the loss (the lock-lost
      // warning's "unlocked or taken over" covers both); SSE/snapshot then
      // delivers the authoritative state. Without clearing on 409 the device
      // wedges as offline, relying solely on the takeover's SSE frame landing.
      // Reclaiming, if wanted, is a deliberate separate force-takeover — not a
      // silent clobber of the other device from this sync path.
      if (e instanceof ApiError && (e.status === 410 || e.status === 409)) {
        await clearOfflineState(tournamentUid);
        // Irreversible data loss: persist until dismissed, never auto-fade.
        showToast({ type: 'error', message: m.offline_lock_lost_warning(), duration: 0 });
        throw new OfflineLockLostError(m.offline_lock_lost_warning());
      }
      throw e;
    }

    // Clean up temp user stubs (server created real users with uuid7 UIDs)
    for (const p of offlinePlayers) {
      await deleteUser(p.temp_uid);
    }

    // Update local state with server-reconciled version
    await saveTournament(result);
    await clearOfflineState(tournamentUid);

    // Outcome summary: closes the loop the go-offline modal opened — every
    // created account is a real coopted VEKN member.
    if (summary) {
      showToast({
        type: 'success',
        message: m.offline_go_online_summary({
          matched: String(summary.players_matched),
          created: String(summary.accounts_created),
          decks: String(summary.decks_synced),
        }),
        duration: 10000,
      });
    }

    return result;
  } finally {
    goingOnlineUids.delete(tournamentUid);
  }
}

/** Force-takeover: claim offline lock from another device. */
export async function forceTakeover(tournamentUid: string): Promise<void> {
  const deviceId = getDeviceId();
  await apiRequest(`/api/tournaments/${tournamentUid}/force-takeover`, {
    method: 'POST',
    body: JSON.stringify({ device_id: deviceId }),
  });
  await markOffline(tournamentUid);
}

/**
 * IC-only emergency unlock: clears a wedged offline lock WITHOUT syncing the
 * holding device's offline changes (potential data loss — last resort). The
 * server broadcasts the unlocked tournament over SSE, which reconciles IDB.
 */
export async function forceUnlock(tournamentUid: string): Promise<void> {
  // handleForceUnlock's catch toasts on failure (and covers network errors) —
  // suppress apiRequest's duplicate.
  await apiRequest(
    `/api/tournaments/${tournamentUid}/force-unlock`,
    { method: 'POST' },
    { suppressErrorToast: true },
  );
}

/** Add an offline player to the registry and create a local user stub. */
export async function addOfflinePlayer(
  tournamentUid: string,
  player: OfflinePlayer,
): Promise<void> {
  // Save to offline players registry
  await dbAddOfflinePlayer(tournamentUid, player);

  // Create a minimal user stub in IndexedDB so player name displays work
  await saveUser({
    uid: player.temp_uid,
    modified: new Date().toISOString(),
    name: player.name,
    country: null,
    vekn_id: player.vekn_id || null,
    roles: [],
  });
}

/** Opportunistic sync: push tournament snapshot to server as backup. */
export async function syncOffline(tournamentUid: string): Promise<void> {
  if (!navigator.onLine) return;
  if (!isOffline(tournamentUid)) return;

  const deviceId = getDeviceId();
  const tournament = await getTournament(tournamentUid);
  if (!tournament) return;

  try {
    const result = await apiRequest<{ synced_at: string }>(
      `/api/tournaments/${tournamentUid}/sync-offline`,
      {
        method: 'POST',
        body: JSON.stringify({ device_id: deviceId, tournament }),
      },
      // Opportunistic backup: failures must stay silent (the catch below is the
      // contract) — notably the 404 an offline-CREATED tournament gets until
      // go-online inserts it server-side.
      { suppressErrorToast: true },
    );
    await setMetadata(`offline_last_sync:${tournamentUid}`, result.synced_at);
    const newTimes = new Map(lastSyncTimes);
    newTimes.set(tournamentUid, result.synced_at);
    lastSyncTimes = newTimes;
  } catch {
    // Silent failure — opportunistic sync
  }
}

/** Schedule an opportunistic sync (debounced). Call after each offline action. */
export function scheduleSyncOffline(tournamentUid: string): void {
  const existing = syncTimers.get(tournamentUid);
  if (existing) clearTimeout(existing);

  syncTimers.set(
    tournamentUid,
    setTimeout(() => {
      syncTimers.delete(tournamentUid);
      syncOffline(tournamentUid);
    }, SYNC_DEBOUNCE_MS),
  );
}
