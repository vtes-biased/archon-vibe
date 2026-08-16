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

let offlineTournamentUids = $state<Set<string>>(new Set());

let lastSyncTimes = $state<Map<string, string>>(new Map());

const syncTimers = new Map<string, ReturnType<typeof setTimeout>>();
const SYNC_DEBOUNCE_MS = 30_000;

// Tournaments this device is actively bringing back online: any SSE lock-state frame is ignored until
// the go-online HTTP response resolves (see lostOfflineLock), collapsing a concurrent unlock/takeover into one warning.
const goingOnlineUids = new Set<string>();

export async function initOfflineState(): Promise<void> {
  const entries = await getMetadataByPrefix('offline_tournament:');
  const uids = new Set<string>();
  for (const [key] of entries) {
    uids.add(key.replace('offline_tournament:', ''));
  }
  offlineTournamentUids = uids;

  const syncEntries = await getMetadataByPrefix('offline_last_sync:');
  const times = new Map<string, string>();
  for (const [key, value] of syncEntries) {
    times.set(key.replace('offline_last_sync:', ''), value);
  }
  lastSyncTimes = times;
}

export function isOffline(tournamentUid: string): boolean {
  return offlineTournamentUids.has(tournamentUid);
}

export function getOfflineTournamentUids(): Set<string> {
  return offlineTournamentUids;
}

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

  const timer = syncTimers.get(tournamentUid);
  if (timer) {
    clearTimeout(timer);
    syncTimers.delete(tournamentUid);
  }
}

/** True if this device's offline lock was lost — the authoritative row now shows offline_mode=false
 * or a different offline_device_id (force-unlock or takeover already happened server-side). */
export function lostOfflineLock(t: {
  uid: string;
  offline_mode?: boolean;
  offline_device_id?: string;
}): boolean {
  if (!isOffline(t.uid)) return false;
  // A go-online we initiated is in flight: its HTTP response decides the lock outcome, so ignore every
  // SSE lock-state frame here until then — acting on them would double-report the transition.
  if (goingOnlineUids.has(t.uid)) return false;
  return t.offline_mode !== true || t.offline_device_id !== getDeviceId();
}

/** Drops the now-orphaned local offline state and warns the holder its unsynced changes are gone.
 * Called from the SSE/snapshot path once the authoritative (unlocked) tournament reaches the device. */
export async function handleOfflineLockLost(tournamentUid: string): Promise<void> {
  await clearOfflineState(tournamentUid);
  // Irreversible data loss: persist until dismissed, never auto-fade.
  showToast({ type: 'error', message: m.offline_lock_lost_warning(), duration: 0 });
}

/** The offline lock was lost during go-online; the loss toast is already shown. */
export class OfflineLockLostError extends Error {}

export async function goOffline(tournamentUid: string): Promise<void> {
  const deviceId = getDeviceId();
  await apiRequest(`/api/tournaments/${tournamentUid}/go-offline`, {
    method: 'POST',
    body: JSON.stringify({ device_id: deviceId }),
  });
  await markOffline(tournamentUid);
}

export async function goOnline(tournamentUid: string): Promise<Tournament> {
  // Suppress the go-online self-echo (offline_mode=false) over SSE until local
  // offline state is cleared below — see goingOnlineUids / lostOfflineLock.
  goingOnlineUids.add(tournamentUid);
  try {
    const deviceId = getDeviceId();
    const tournament = await getTournament(tournamentUid);
    if (!tournament) throw new Error('Tournament not found locally');

    const offlinePlayers = await getOfflinePlayers(tournamentUid);

    const sanctionUids = await getOfflineSanctionUids(tournamentUid);
    const offlineSanctions: Sanction[] = [];
    for (const uid of sanctionUids) {
      const s = await getSanction(uid);
      if (s) offlineSanctions.push(s);
    }

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
        // handleGoOnline's catch toasts (incl. the localized 410 lock-lost message) and covers network
        // errors — suppress apiRequest's duplicate.
        { suppressErrorToast: true },
      );
      result = resp.tournament;
      summary = resp.summary;
    } catch (e) {
      // 410 (force-unlocked or already online) or 409 (another device took the lock): this device's
      // snapshot can't sync — clear orphaned state; reclaiming after 409 is a deliberate separate force-takeover, never a silent clobber.
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

export async function forceTakeover(tournamentUid: string): Promise<void> {
  const deviceId = getDeviceId();
  await apiRequest(`/api/tournaments/${tournamentUid}/force-takeover`, {
    method: 'POST',
    body: JSON.stringify({ device_id: deviceId }),
  });
  await markOffline(tournamentUid);
}

/** IC-only emergency unlock: clears a wedged offline lock WITHOUT syncing the holding device's offline
 * changes (potential data loss — last resort). The server broadcasts the unlock over SSE, which reconciles IDB. */
export async function forceUnlock(tournamentUid: string): Promise<void> {
  // handleForceUnlock's catch toasts on failure (and covers network errors) —
  // suppress apiRequest's duplicate.
  await apiRequest(
    `/api/tournaments/${tournamentUid}/force-unlock`,
    { method: 'POST' },
    { suppressErrorToast: true },
  );
}

export async function addOfflinePlayer(
  tournamentUid: string,
  player: OfflinePlayer,
): Promise<void> {
  await dbAddOfflinePlayer(tournamentUid, player);

  // Minimal user stub in IndexedDB so player name displays work
  await saveUser({
    uid: player.temp_uid,
    modified: new Date().toISOString(),
    name: player.name,
    country: null,
    vekn_id: player.vekn_id || null,
    roles: [],
  });
}

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
      // Opportunistic backup: failures must stay silent (the catch below is the contract) — notably
      // the 404 an offline-CREATED tournament gets until go-online inserts it server-side.
      { suppressErrorToast: true },
    );
    await setMetadata(`offline_last_sync:${tournamentUid}`, result.synced_at);
    const newTimes = new Map(lastSyncTimes);
    newTimes.set(tournamentUid, result.synced_at);
    lastSyncTimes = newTimes;
  } catch {
  }
}

/** Call after each offline action. */
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
