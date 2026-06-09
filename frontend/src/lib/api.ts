/**
 * API client for backend communication.
 */

import type { User, Sanction, SanctionLevel, SanctionCategory, SanctionSubcategory, Tournament, League } from '$lib/types';
import { getAllUsers, saveTournament, saveLeague } from './db';
import { showToast } from '$lib/stores/toast.svelte';
import { getAccessToken, getAuthState } from '$lib/stores/auth.svelte';
import * as m from './paraglide/messages.js';

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
  options: RequestInit = {},
  // apiRequest is the single toast authority for its own failures: it auto-toasts
  // offline, transport (network), AND HTTP error responses. Callers that surface
  // the error themselves (inline message or their own catch toast) pass this to
  // avoid a duplicate toast.
  { suppressErrorToast = false }: { suppressErrorToast?: boolean } = {}
): Promise<T> {
  // Offline guard: every apiRequest is a mutation (reads are offline-first from
  // IndexedDB), so there's no point attempting the fetch. Toast + throw an
  // ApiError (status 0 = never left the device) so empty-catch callers aren't
  // silent and inline callers can still distinguish it.
  if (!isOnline()) {
    const message = m.error_action_requires_online();
    if (!suppressErrorToast) showToast({ type: 'error', message });
    throw new ApiError(message, 0);
  }

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

  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...options,
      headers,
    });
  } catch (e) {
    // fetch() rejects with a TypeError on a transport failure (dropped mid-flight,
    // DNS, CORS, server down). This never reached the !response.ok block below, so
    // it used to escape untoasted and get swallowed by empty catches — toast it.
    if (!suppressErrorToast) showToast({ type: 'error', message: m.error_network_unreachable() });
    throw e instanceof Error ? e : new Error(m.error_network_unreachable());
  }

  if (!response.ok) {
    let detail: string | undefined;
    try {
      const data = await response.json();
      detail = data.detail || data.message;
    } catch {
      // Ignore JSON parse errors
    }
    const message = detail || `Request failed: ${response.statusText}`;
    if (!suppressErrorToast) showToast({ type: 'error', message });
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
 * Guard an online-only action: toasts + throws a localized error when offline.
 * Toasts so the many empty-catch callers (sanctions, VEKN, avatar — which relied
 * on apiRequest's toast but threw here, before it) aren't silent offline. Callers
 * that render the error themselves pass `suppressErrorToast`.
 */
export function requireOnline({ suppressErrorToast = false }: { suppressErrorToast?: boolean } = {}): void {
  if (isOnline()) return;
  const message = m.error_action_requires_online();
  if (!suppressErrorToast) showToast({ type: 'error', message });
  throw new ApiError(message, 0);
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
  // Pass { suppressErrorToast: true } from callers that render the error inline.
  opts?: { suppressErrorToast?: boolean },
): Promise<User> {
  requireOnline(opts);

  const body: Record<string, unknown> = { name, country };
  if (city) body.city = city;
  if (city_geoname_id != null) body.city_geoname_id = city_geoname_id;
  if (nickname) body.nickname = nickname;
  if (email) body.email = email;
  if (roles !== undefined) body.roles = roles;

  return apiRequest<User>('/api/users/', { method: 'POST', body: JSON.stringify(body) }, opts);
}

export async function updateUser(
  uid: string,
  name?: string,
  country?: string,
  city?: string | null,
  nickname?: string | null,
  roles?: string[],
  city_geoname_id?: number | null,
  // Pass { suppressErrorToast: true } from callers that render the error inline.
  opts?: { suppressErrorToast?: boolean },
): Promise<User> {
  requireOnline(opts);

  // Omit a field to leave it unchanged; '' clears a string, [] clears roles.
  const body: Record<string, unknown> = {};
  if (name) body.name = name;
  if (country) body.country = country;
  if (city !== undefined) body.city = city ?? '';
  if (city_geoname_id != null) body.city_geoname_id = city_geoname_id;
  if (nickname !== undefined) body.nickname = nickname ?? '';
  if (roles !== undefined) body.roles = roles;

  return apiRequest<User>(`/api/users/${uid}`, { method: 'PUT', body: JSON.stringify(body) }, opts);
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
  requireOnline();
  return apiRequest<VeknClaimResponse>('/vekn/claim', {
    method: 'POST',
    body: JSON.stringify({ vekn_id }),
  });
}

/**
 * Abandon the current user's VEKN ID.
 */
export async function abandonVeknId(): Promise<VeknAbandonResponse> {
  requireOnline();
  return apiRequest<VeknAbandonResponse>('/vekn/abandon', {
    method: 'POST',
  });
}

/**
 * Sponsor a new VEKN member (allocates new sequential VEKN ID).
 */
export async function sponsorVeknMember(user_uid: string): Promise<VeknSponsorResponse> {
  requireOnline();
  return apiRequest<VeknSponsorResponse>('/vekn/sponsor', {
    method: 'POST',
    body: JSON.stringify({ user_uid }),
  });
}

/**
 * Link a VEKN ID to a user (may displace current holder).
 */
export async function linkVeknId(vekn_id: string, user_uid: string): Promise<VeknLinkResponse> {
  requireOnline();
  return apiRequest<VeknLinkResponse>('/vekn/link', {
    method: 'POST',
    body: JSON.stringify({ vekn_id, user_uid }),
  });
}

/**
 * Force-abandon a user's VEKN ID (for NC/Prince/IC).
 */
export async function forceAbandonVeknId(user_uid: string): Promise<VeknMessageResponse> {
  requireOnline();
  return apiRequest<VeknMessageResponse>('/vekn/force-abandon', {
    method: 'POST',
    body: JSON.stringify({ user_uid }),
  });
}

/**
 * Merge two user accounts (for NC/Prince/IC).
 */
export async function mergeUsers(keep_uid: string, delete_uid: string): Promise<{ user: User; message: string }> {
  requireOnline();
  return apiRequest<{ user: User; message: string }>('/admin/users/merge', {
    method: 'POST',
    body: JSON.stringify({ keep_uid, delete_uid }),
  });
}

/** Result of an IC manual-sync trigger: a status plus a free-form stats map. */
export interface AdminSyncResult {
  status: string;
  stats: Record<string, unknown>;
}

/** IC-only: trigger a VEKN member sync now (also runs on a 6h schedule). */
export async function syncVeknMembers(): Promise<AdminSyncResult> {
  requireOnline({ suppressErrorToast: true });
  // Errors surface inline in ConfirmActionModal — suppress the duplicate toast.
  return apiRequest<AdminSyncResult>('/admin/sync-vekn', { method: 'POST' }, { suppressErrorToast: true });
}

/** IC-only: trigger a VEKN tournament sync now (also runs on a 6h schedule). */
export async function syncVeknTournaments(): Promise<AdminSyncResult> {
  requireOnline({ suppressErrorToast: true });
  return apiRequest<AdminSyncResult>('/admin/sync-vekn-tournaments', { method: 'POST' }, { suppressErrorToast: true });
}

/** IC-only: trigger a TWDA decklist import now (also runs on a 24h schedule). */
export async function syncTwdaDecks(): Promise<AdminSyncResult> {
  requireOnline({ suppressErrorToast: true });
  return apiRequest<AdminSyncResult>('/admin/sync-twda-decks', { method: 'POST' }, { suppressErrorToast: true });
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
  requireOnline();
  return apiRequest<Sanction>('/sanctions/', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

/**
 * Lift a sanction (sets lifted_at and lifted_by_uid).
 */
export async function liftSanction(uid: string): Promise<Sanction> {
  requireOnline();
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
  requireOnline();
  return apiRequest<Sanction>(`/sanctions/${uid}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

/**
 * Soft delete a sanction.
 */
export async function deleteSanctionApi(uid: string): Promise<{ message: string }> {
  requireOnline();
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
  requireOnline();

  // apiRequest passes FormData through untouched (no JSON content-type) and
  // handles auth + error extraction; the browser sets the multipart boundary.
  const formData = new FormData();
  formData.append('file', blob, 'avatar.webp');

  const result = await apiRequest<{ success: boolean }>(
    `/api/users/${userUid}/avatar`,
    { method: 'POST', body: formData }
  );
  showToast({ type: 'success', message: m.profile_avatar_updated() });
  return result;
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
  requireOnline();

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
}

export async function createTournament(data: CreateTournamentData, opts?: { suppressErrorToast?: boolean }): Promise<Tournament> {
  requireOnline(opts);
  return apiRequest<Tournament>('/api/tournaments/', {
    method: 'POST',
    body: JSON.stringify(data),
  }, opts);
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

export async function deleteTournamentApi(uid: string, opts?: { suppressErrorToast?: boolean }): Promise<{ message: string }> {
  requireOnline(opts);
  const result = await apiRequest<{ message: string }>(`/api/tournaments/${uid}`, {
    method: 'DELETE',
  }, opts);
  // Optimistic IDB delete so UI updates immediately instead of waiting for SSE
  const { deleteTournament } = await import('./db');
  await deleteTournament(uid);
  return result;
}

/**
 * Self check-in via QR code (server-only, no optimistic path).
 */
export async function qrCheckin(tournamentUid: string, code: string): Promise<Tournament> {
  requireOnline();
  return apiRequest<Tournament>(`/api/tournaments/${tournamentUid}/qr-checkin`, {
    method: 'POST',
    body: JSON.stringify({ code }),
  });
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

export async function createLeague(data: CreateLeagueData, opts?: { suppressErrorToast?: boolean }): Promise<League> {
  requireOnline(opts);
  const created = await apiRequest<League>('/api/leagues/', {
    method: 'POST',
    body: JSON.stringify(data),
  }, opts);
  await saveLeague(created);
  return created;
}

export async function updateLeague(uid: string, data: Partial<CreateLeagueData>, opts?: { suppressErrorToast?: boolean }): Promise<League> {
  requireOnline(opts);
  const updated = await apiRequest<League>(`/api/leagues/${uid}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  }, opts);
  await saveLeague(updated);
  return updated;
}

export async function deleteLeagueApi(uid: string, opts?: { suppressErrorToast?: boolean }): Promise<void> {
  requireOnline(opts);
  await apiRequest<void>(`/api/leagues/${uid}`, {
    method: 'DELETE',
  }, opts);
  // Optimistic IDB delete so UI updates immediately instead of waiting for SSE
  const { deleteLeague } = await import('./db');
  await deleteLeague(uid);
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

// Judge call API

export async function callJudge(uid: string, table: number): Promise<void> {
  await apiRequest<void>(`/api/tournaments/${uid}/call-judge`, {
    method: 'POST',
    body: JSON.stringify({ table }),
  });
}

export async function deleteAvatar(userUid: string): Promise<{ success: boolean }> {
  requireOnline();

  const result = await apiRequest<{ success: boolean }>(`/api/users/${userUid}/avatar`, {
    method: 'DELETE',
  });

  showToast({ type: 'success', message: m.profile_avatar_removed() });
  return result;
}
