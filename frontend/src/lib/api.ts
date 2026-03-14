/**
 * API client for backend communication.
 */

import type { User, Sanction, SanctionLevel, SanctionCategory, SanctionSubcategory, Tournament, DeckObject, League } from '$lib/types';
import { getAllUsers, getTournament, saveTournament, saveLeague, getSanctionsForTournament, getSanctionsForUser, getDecksByTournament, saveDeck, deleteDeck } from './db';
import { processTournamentEvent, buildActorContext, type DeckOp, type TournamentEvent } from './engine';
import { showToast } from '$lib/stores/toast.svelte';
import { getAccessToken, getAuthState } from '$lib/stores/auth.svelte';
import { isOffline, scheduleSyncOffline } from '$lib/stores/offline.svelte';
import { addOfflineDeckUid } from '$lib/db';

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

/**
 * API error class with message extraction.
 */
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public detail?: string
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

/**
 * Make an authenticated API request.
 */
export async function apiRequest<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getAccessToken();
  const headers: Record<string, string> = {
    ...((options.headers as Record<string, string>) || {}),
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  if (options.body && typeof options.body === 'string') {
    headers['Content-Type'] = 'application/json';
  }

  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    let detail: string | undefined;
    try {
      const data = await response.json();
      detail = data.detail || data.message;
    } catch {
      // Ignore JSON parse errors
    }
    const message = detail || `Request failed: ${response.statusText}`;
    showToast({ type: 'error', message });
    throw new ApiError(message, response.status, detail);
  }

  if (response.status === 204 || response.headers.get('content-length') === '0') {
    return undefined as T;
  }
  return response.json();
}

/**
 * Check if the app is online.
 */
export function isOnline(): boolean {
  return navigator.onLine;
}

/**
 * Fetch users - always use IndexedDB for offline-first approach.
 */
export async function fetchUsers(): Promise<User[]> {
  return getAllUsers();
}

export async function createUser(
  name: string,
  country: string,
  city?: string | null,
  nickname?: string | null,
  email?: string | null,
  roles?: string[],
  city_geoname_id?: number | null,
): Promise<User> {
  if (!isOnline()) {
    throw new Error('Cannot create users while offline. Please connect to the internet.');
  }

  const params = new URLSearchParams();
  params.append('name', name);
  params.append('country', country);
  if (city) params.append('city', city);
  if (city_geoname_id != null) params.append('city_geoname_id', String(city_geoname_id));
  if (nickname) params.append('nickname', nickname);
  if (email) params.append('email', email);
  if (roles !== undefined) {
    roles.forEach(role => params.append('roles', role));
  }

  return apiRequest<User>(`/api/users/?${params}`, { method: 'POST' });
}

export async function updateUser(
  uid: string,
  name?: string,
  country?: string,
  vekn_id?: string | null,
  city?: string | null,
  nickname?: string | null,
  roles?: string[],
  city_geoname_id?: number | null,
): Promise<User> {
  if (!isOnline()) {
    throw new Error('Cannot update users while offline. Please connect to the internet.');
  }

  const params = new URLSearchParams();
  if (name) params.append('name', name);
  if (country) params.append('country', country);
  if (vekn_id !== undefined) params.append('vekn_id', vekn_id || '');
  if (city !== undefined) params.append('city', city || '');
  if (city_geoname_id !== undefined) params.append('city_geoname_id', city_geoname_id != null ? String(city_geoname_id) : '');
  if (nickname !== undefined) params.append('nickname', nickname || '');
  if (roles !== undefined) {
    if (roles.length === 0) {
      // Send empty string to explicitly clear all roles
      params.append('roles', '');
    } else {
      roles.forEach(role => params.append('roles', role));
    }
  }

  return apiRequest<User>(`/api/users/${uid}?${params}`, { method: 'PUT' });
}

// VEKN ID Management API

export interface VeknClaimResponse {
  user: User;
  message: string;
  access_token: string;
  refresh_token: string;
  expires_in: number;
}

export interface VeknSponsorResponse {
  user: User;
  vekn_id: string;
  message: string;
}

export interface VeknLinkResponse {
  user: User;
  displaced_user?: User;
  message: string;
}

export interface VeknMessageResponse {
  message: string;
}

export interface VeknAbandonResponse {
  message: string;
  user: User;
  access_token: string;
  refresh_token: string;
  expires_in: number;
}

/**
 * Claim an unclaimed VEKN ID for the current user.
 */
export async function claimVeknId(vekn_id: string): Promise<VeknClaimResponse> {
  if (!isOnline()) {
    throw new Error('Cannot claim VEKN ID while offline.');
  }
  return apiRequest<VeknClaimResponse>('/vekn/claim', {
    method: 'POST',
    body: JSON.stringify({ vekn_id }),
  });
}

/**
 * Abandon the current user's VEKN ID.
 */
export async function abandonVeknId(): Promise<VeknAbandonResponse> {
  if (!isOnline()) {
    throw new Error('Cannot abandon VEKN ID while offline.');
  }
  return apiRequest<VeknAbandonResponse>('/vekn/abandon', {
    method: 'POST',
  });
}

/**
 * Sponsor a new VEKN member (allocates new sequential VEKN ID).
 */
export async function sponsorVeknMember(user_uid: string): Promise<VeknSponsorResponse> {
  if (!isOnline()) {
    throw new Error('Cannot sponsor member while offline.');
  }
  return apiRequest<VeknSponsorResponse>('/vekn/sponsor', {
    method: 'POST',
    body: JSON.stringify({ user_uid }),
  });
}

/**
 * Link a VEKN ID to a user (may displace current holder).
 */
export async function linkVeknId(vekn_id: string, user_uid: string): Promise<VeknLinkResponse> {
  if (!isOnline()) {
    throw new Error('Cannot link VEKN ID while offline.');
  }
  return apiRequest<VeknLinkResponse>('/vekn/link', {
    method: 'POST',
    body: JSON.stringify({ vekn_id, user_uid }),
  });
}

/**
 * Force-abandon a user's VEKN ID (for NC/Prince/IC).
 */
export async function forceAbandonVeknId(user_uid: string): Promise<VeknMessageResponse> {
  if (!isOnline()) {
    throw new Error('Cannot force-abandon VEKN ID while offline.');
  }
  return apiRequest<VeknMessageResponse>('/vekn/force-abandon', {
    method: 'POST',
    body: JSON.stringify({ user_uid }),
  });
}

/**
 * Merge two user accounts (for NC/Prince/IC).
 */
export async function mergeUsers(keep_uid: string, delete_uid: string): Promise<{ user: User; message: string }> {
  if (!isOnline()) {
    throw new Error('Cannot merge users while offline.');
  }
  return apiRequest<{ user: User; message: string }>('/admin/users/merge', {
    method: 'POST',
    body: JSON.stringify({ keep_uid, delete_uid }),
  });
}

// Sanctions API

export interface CreateSanctionData {
  user_uid: string;
  level: SanctionLevel;
  category: SanctionCategory;
  subcategory?: SanctionSubcategory | null;
  round_number?: number | null;
  description: string;
  expires_at?: string | null;  // ISO datetime string
  tournament_uid?: string | null;
}

/**
 * Create a new sanction (IC/Ethics only for SUSPENSION/PROBATION).
 */
export async function createSanction(data: CreateSanctionData): Promise<Sanction> {
  if (!isOnline()) {
    throw new Error('Cannot create sanction while offline.');
  }
  return apiRequest<Sanction>('/sanctions/', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

/**
 * Lift a sanction (sets lifted_at and lifted_by_uid).
 */
export async function liftSanction(uid: string): Promise<Sanction> {
  if (!isOnline()) {
    throw new Error('Cannot lift sanction while offline.');
  }
  return apiRequest<Sanction>(`/sanctions/${uid}`, {
    method: 'PUT',
    body: JSON.stringify({ lifted: true }),
  });
}

export interface UpdateSanctionData {
  level?: SanctionLevel;
  category?: SanctionCategory;
  subcategory?: SanctionSubcategory | null;
  round_number?: number | null;
  description?: string;
  expires_at?: string | null;  // YYYY-MM-DD date string
  lifted?: boolean;
}

/**
 * Update a sanction (level, category, description, expiry, or lift it).
 */
export async function updateSanction(uid: string, data: UpdateSanctionData): Promise<Sanction> {
  if (!isOnline()) {
    throw new Error('Cannot update sanction while offline.');
  }
  return apiRequest<Sanction>(`/sanctions/${uid}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

/**
 * Soft delete a sanction.
 */
export async function deleteSanctionApi(uid: string): Promise<{ message: string }> {
  if (!isOnline()) {
    throw new Error('Cannot delete sanction while offline.');
  }
  return apiRequest<{ message: string }>(`/sanctions/${uid}`, {
    method: 'DELETE',
  });
}

// Avatar API

/**
 * Upload user avatar.
 * @param userUid - The user's UID
 * @param blob - The image blob (should be webp, max 1MB)
 */
export async function uploadAvatar(userUid: string, blob: Blob): Promise<{ success: boolean }> {
  if (!isOnline()) {
    throw new Error('Cannot upload avatar while offline.');
  }

  const token = getAccessToken();
  const formData = new FormData();
  formData.append('file', blob, 'avatar.webp');

  const response = await fetch(`${API_URL}/api/users/${userUid}/avatar`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: formData,
  });

  if (!response.ok) {
    let detail: string | undefined;
    try {
      const data = await response.json();
      detail = data.detail || data.message;
    } catch {
      // Ignore
    }
    const message = detail || `Failed to upload avatar: ${response.statusText}`;
    showToast({ type: 'error', message });
    throw new ApiError(message, response.status, detail);
  }

  showToast({ type: 'success', message: 'Avatar updated' });
  return response.json();
}

// Archon Import API

export interface ArchonImportResult {
  success: boolean;
  errors: string[];
  warnings: string[];
  players_matched: number;
  rounds_imported: number;
  has_finals: boolean;
}

export async function importArchonFile(tournamentUid: string, file: File): Promise<ArchonImportResult> {
  if (!isOnline()) {
    throw new Error('Cannot import while offline.');
  }

  const token = getAccessToken();
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(`${API_URL}/api/tournaments/${tournamentUid}/archon-import`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: formData,
  });

  const data = await response.json();
  if (!response.ok && !data.errors) {
    const message = data.detail || `Import failed: ${response.statusText}`;
    showToast({ type: 'error', message });
    throw new ApiError(message, response.status, data.detail);
  }
  return data;
}

// Tournament API

export interface CreateTournamentData {
  name: string;
  format?: string;
  rank?: string;
  online?: boolean;
  start?: string | null;
  finish?: string | null;
  timezone?: string;
  country?: string | null;
  venue?: string;
  venue_url?: string;
  address?: string;
  map_url?: string;
  description?: string;
  max_rounds?: number;
  standings_mode?: string;
  decklists_mode?: string;
  proxies?: boolean;
  multideck?: boolean;
  decklist_required?: boolean;
  table_rooms?: { name: string; count: number }[];
  league_uid?: string | null;
  round_time?: number;
  finals_time?: number;
  time_extension_policy?: string;
}

export async function createTournament(data: CreateTournamentData): Promise<Tournament> {
  if (!isOnline()) {
    throw new Error('Cannot create tournament while offline. Use createTournamentOffline().');
  }
  return apiRequest<Tournament>('/api/tournaments/', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

/** Create a tournament locally when offline. Saved to IndexedDB, reconciled on go-online. */
export async function createTournamentOffline(data: CreateTournamentData): Promise<Tournament> {
  const { markOffline } = await import('$lib/stores/offline.svelte');
  const { getDeviceId } = await import('./db');
  const { createTournamentWithEngine } = await import('./engine');
  const user = getAuthState().user;
  const uid = crypto.randomUUID();
  const now = new Date().toISOString();

  const config = {
    uid,
    now,
    ...data,
    timezone: data.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone,
    country: data.country || user?.country || null,
  };

  const actor = {
    uid: user?.uid || '',
    roles: user?.roles || [],
    is_organizer: true,
    can_organize_league_uids: [],
  };

  const result = await createTournamentWithEngine(config, actor);
  const tournament: Tournament = {
    ...(result as unknown as Tournament),
    // Offline-only fields (not part of engine output)
    offline_mode: true,
    offline_device_id: getDeviceId(),
    offline_user_uid: user?.uid || '',
    offline_since: now,
  };

  await saveTournament(tournament);
  await markOffline(uid);

  return tournament;
}

export async function deleteTournamentApi(uid: string): Promise<{ message: string }> {
  if (!isOnline()) {
    throw new Error('Cannot delete tournament while offline.');
  }
  return apiRequest<{ message: string }>(`/api/tournaments/${uid}`, {
    method: 'DELETE',
  });
}

/**
 * Per-tournament action queue to serialize server POSTs.
 * Prevents concurrent requests from racing on the same tournament.
 */
const actionQueues = new Map<string, Promise<void>>();

function enqueueServerAction(uid: string, fn: () => Promise<void>): void {
  const prev = actionQueues.get(uid) ?? Promise.resolve();
  const next = prev.then(fn, fn); // Run fn even if previous failed
  actionQueues.set(uid, next);
  next.finally(() => {
    if (actionQueues.get(uid) === next) {
      actionQueues.delete(uid);
    }
  });
}

/**
 * Pre-check: block barred players (suspension, league-wide DQ) before WASM optimistic path.
 * Mirrors backend _check_player_barred() logic.
 */
async function checkPlayerBarred(playerUid: string, tournament: Tournament): Promise<void> {
  const sanctions = await getSanctionsForUser(playerUid);
  const now = new Date();
  for (const s of sanctions) {
    if (s.deleted_at || s.lifted_at) continue;
    if (s.level === 'suspension' && (!s.expires_at || new Date(s.expires_at) > now)) {
      throw new Error('Player is suspended and cannot participate');
    }
  }
  if (tournament.league_uid) {
    for (const s of sanctions) {
      if (s.deleted_at || s.lifted_at) continue;
      if (s.level === 'disqualification' && s.tournament_uid) {
        const dqTournament = await getTournament(s.tournament_uid);
        if (dqTournament && dqTournament.league_uid === tournament.league_uid) {
          throw new Error('Player is disqualified from a league tournament and cannot participate');
        }
      }
    }
  }
}

export async function tournamentAction(uid: string, action: string, data?: Record<string, unknown>): Promise<Tournament> {
  const event = { type: action as import('$lib/engine').TournamentEventType, ...data };

  // Try optimistic update via WASM engine
  const current = await getTournament(uid);
  if (current) {
    try {
      // Pre-check: block barred players before WASM optimistic path
      if (action === 'CheckIn' && data?.player_uid) {
        await checkPlayerBarred(data.player_uid as string, current);
      } else if ((action === 'Register' || action === 'AddPlayer') && data?.user_uid) {
        await checkPlayerBarred(data.user_uid as string, current);
      }
      const actor = await buildActorContext(getAuthState().user ?? null, current, action);
      // Combine tournament-scoped sanctions with user-level suspension/DQ
      // sanctions for all tournament players (needed for CheckInAll etc.)
      const sanctions = await getSanctionsForTournament(uid);
      const seenUids = new Set(sanctions.map(s => s.uid));
      const playerUids = new Set((current.players ?? []).map(p => p.user_uid));
      for (const puid of playerUids) {
        if (!puid) continue;
        for (const s of await getSanctionsForUser(puid)) {
          if (seenUids.has(s.uid) || s.deleted_at || s.lifted_at) continue;
          if (s.level === 'suspension' || s.level === 'disqualification') {
            sanctions.push(s);
            seenUids.add(s.uid);
          }
        }
      }
      const decks = await getDecksByTournament(uid);
      const result = await processTournamentEvent(current, event, actor, sanctions, decks);
      await saveTournament(result.tournament);

      // Handle deck side-effects in IDB
      const affectedDeckUids = await applyDeckOps(result.deckOps, uid, decks);

      // If tournament is in offline mode, track deck UIDs and skip server POST
      if (isOffline(uid)) {
        for (const deckUid of affectedDeckUids) {
          await addOfflineDeckUid(uid, deckUid);
        }
        scheduleSyncOffline(uid);
        return result.tournament;
      }

      // For StartRound: forward WASM-computed seating so the server uses
      // the same tables (seating computation is non-deterministic).
      let serverEvent: TournamentEvent = event;
      if (action === 'StartRound' && result.tournament.rounds &&
          result.tournament.rounds.length > (current.rounds?.length ?? 0)) {
        const newRound = result.tournament.rounds[result.tournament.rounds.length - 1]!;
        serverEvent = { ...event, seating: newRound.map(t => t.seating.map(s => s.player_uid)) };
      }

      // Queue server POST (serialized per tournament, prevents concurrent races)
      enqueueServerAction(uid, async () => {
        try {
          await apiRequest<Tournament>(`/api/tournaments/${uid}/action`, {
            method: 'POST',
            body: JSON.stringify(serverEvent),
          });
        } catch (e) {
          console.error('Server rejected action, SSE will correct:', e);
        }
      });

      return result.tournament;
    } catch {
      // WASM engine failed (unknown action, etc.) — fall through to server-only
    }
  }

  // Fallback: server-only
  if (!isOnline()) {
    throw new Error('Cannot perform tournament action while offline.');
  }
  return apiRequest<Tournament>(`/api/tournaments/${uid}/action`, {
    method: 'POST',
    body: JSON.stringify(event),
  });
}

/**
 * Apply deck operations from engine result to IndexedDB.
 * In online mode, SSE will deliver authoritative state and overwrite.
 * Returns UIDs of affected decks (for offline tracking).
 */
async function applyDeckOps(deckOps: DeckOp[], tournamentUid: string, existingDecks: DeckObject[]): Promise<string[]> {
  const affectedUids: string[] = [];
  for (const op of deckOps) {
    if (op.op === 'upsert' && op.deck && op.player_uid) {
      const existing = existingDecks.find(
        d => d.user_uid === op.player_uid && d.round === (op.deck!.round ?? null)
      );
      const deckObj: DeckObject = {
        uid: existing?.uid || crypto.randomUUID(),
        modified: new Date().toISOString(),
        tournament_uid: tournamentUid,
        user_uid: op.player_uid,
        round: op.deck.round ?? null,
        name: op.deck.name || '',
        author: op.deck.author || '',
        comments: op.deck.comments || '',
        cards: op.deck.cards || {},
        public: op.deck.public || false,
      };
      await saveDeck(deckObj);
      affectedUids.push(deckObj.uid);
    } else if (op.op === 'delete' && op.player_uid) {
      for (const d of existingDecks) {
        if (d.user_uid === op.player_uid) {
          await deleteDeck(d.uid);
        }
      }
    } else if (op.op === 'set_public' && op.deck_uid) {
      const target = existingDecks.find(d => d.uid === op.deck_uid);
      if (target) {
        target.public = op.public ?? false;
        target.modified = new Date().toISOString();
        await saveDeck(target);
        affectedUids.push(target.uid);
      }
    }
  }
  return affectedUids;
}

/**
 * Self check-in via QR code (server-only, no optimistic path).
 */
export async function qrCheckin(tournamentUid: string, code: string): Promise<Tournament> {
  if (!isOnline()) {
    throw new Error('Cannot check in while offline.');
  }
  return apiRequest<Tournament>(`/api/tournaments/${tournamentUid}/qr-checkin`, {
    method: 'POST',
    body: JSON.stringify({ code }),
  });
}

export async function setTableScore(
  tournamentUid: string,
  round: number,
  table: number,
  scores: Array<{ player_uid: string; vp: number }>
): Promise<Tournament> {
  return tournamentAction(tournamentUid, 'SetScore', { round, table, scores });
}

/**
 * Delete user avatar.
 */
// League API

export interface CreateLeagueData {
  name: string;
  kind?: string;
  standings_mode?: string;
  format?: string | null;
  country?: string | null;
  start?: string | null;
  finish?: string | null;
  description?: string;
  parent_uid?: string | null;
}

export async function createLeague(data: CreateLeagueData): Promise<League> {
  if (!isOnline()) {
    throw new Error('Cannot create league while offline.');
  }
  const created = await apiRequest<League>('/api/leagues/', {
    method: 'POST',
    body: JSON.stringify(data),
  });
  await saveLeague(created);
  return created;
}

export async function updateLeague(uid: string, data: Partial<CreateLeagueData>): Promise<League> {
  if (!isOnline()) {
    throw new Error('Cannot update league while offline.');
  }
  const updated = await apiRequest<League>(`/api/leagues/${uid}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
  await saveLeague(updated);
  return updated;
}

export async function deleteLeagueApi(uid: string): Promise<void> {
  if (!isOnline()) {
    throw new Error('Cannot delete league while offline.');
  }
  await apiRequest<void>(`/api/leagues/${uid}`, {
    method: 'DELETE',
  });
}

export async function addLeagueOrganizer(uid: string, userUid: string): Promise<League> {
  return apiRequest<League>(`/api/leagues/${uid}/organizers`, {
    method: 'POST',
    body: JSON.stringify({ user_uid: userUid }),
  });
}

export async function removeLeagueOrganizer(uid: string, organizerUid: string): Promise<League> {
  return apiRequest<League>(`/api/leagues/${uid}/organizers/${organizerUid}`, {
    method: 'DELETE',
  });
}

export async function addTournamentOrganizer(uid: string, userUid: string): Promise<Tournament> {
  return apiRequest<Tournament>(`/api/tournaments/${uid}/organizers`, {
    method: 'POST',
    body: JSON.stringify({ user_uid: userUid }),
  });
}

export async function removeTournamentOrganizer(uid: string, organizerUid: string): Promise<Tournament> {
  return apiRequest<Tournament>(`/api/tournaments/${uid}/organizers/${organizerUid}`, {
    method: 'DELETE',
  });
}

// Timer API

export async function timerStart(uid: string): Promise<void> {
  await apiRequest(`/api/tournaments/${uid}/timer/start`, { method: 'POST' });
}

export async function timerPause(uid: string): Promise<void> {
  await apiRequest(`/api/tournaments/${uid}/timer/pause`, { method: 'POST' });
}

export async function timerReset(uid: string): Promise<void> {
  await apiRequest(`/api/tournaments/${uid}/timer/reset`, { method: 'POST' });
}

export async function timerAddTime(uid: string, table: string, seconds: number): Promise<void> {
  await apiRequest(`/api/tournaments/${uid}/timer/add-time`, {
    method: 'POST',
    body: JSON.stringify({ table, seconds }),
  });
}

export async function timerClockStop(uid: string, table: string): Promise<void> {
  await apiRequest(`/api/tournaments/${uid}/timer/clock-stop`, {
    method: 'POST',
    body: JSON.stringify({ table }),
  });
}

export async function timerClockResume(uid: string, table: string): Promise<void> {
  await apiRequest(`/api/tournaments/${uid}/timer/clock-resume`, {
    method: 'POST',
    body: JSON.stringify({ table }),
  });
}

// Judge call API

export async function callJudge(uid: string, table: number): Promise<void> {
  await apiRequest<void>(`/api/tournaments/${uid}/call-judge`, {
    method: 'POST',
    body: JSON.stringify({ table }),
  });
}

export async function deleteAvatar(userUid: string): Promise<{ success: boolean }> {
  if (!isOnline()) {
    throw new Error('Cannot delete avatar while offline.');
  }

  const result = await apiRequest<{ success: boolean }>(`/api/users/${userUid}/avatar`, {
    method: 'DELETE',
  });

  showToast({ type: 'success', message: 'Avatar removed' });
  return result;
}
