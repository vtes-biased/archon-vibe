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
import { apiRequest } from '$lib/api';

// Reactive set of offline tournament UIDs
let offlineTournamentUids = $state<Set<string>>(new Set());

// Last sync timestamps per tournament
let lastSyncTimes = $state<Map<string, string>>(new Map());

// Debounce timer per tournament for opportunistic sync
const syncTimers = new Map<string, ReturnType<typeof setTimeout>>();
const SYNC_DEBOUNCE_MS = 30_000;

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

  const result = await apiRequest<Tournament>(`/api/tournaments/${tournamentUid}/go-online`, {
    method: 'POST',
    body: JSON.stringify({
      device_id: deviceId,
      tournament,
      offline_players: offlinePlayers,
      offline_sanctions: offlineSanctions,
      offline_decks: offlineDecks,
    }),
  });

  // Clean up temp user stubs (server created real users with uuid7 UIDs)
  for (const p of offlinePlayers) {
    await deleteUser(p.temp_uid);
  }

  // Update local state with server-reconciled version
  await saveTournament(result);
  await clearOfflineState(tournamentUid);

  return result;
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
