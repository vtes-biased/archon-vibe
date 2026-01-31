/**
 * API client for backend communication.
 */

import type { User, Sanction, SanctionLevel, SanctionCategory, Tournament, TournamentConfig } from '$lib/types';
import { getAllUsers, getTournament, saveTournament, logChange } from './db';
import { processTournamentEvent, buildActorContext } from './engine';
import { showToast } from '$lib/stores/toast.svelte';
import { getAccessToken, getAuthState } from '$lib/stores/auth.svelte';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

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

export async function fetchUser(uid: string): Promise<User> {
  const response = await fetch(`${API_URL}/api/users/${uid}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch user: ${response.statusText}`);
  }
  return response.json();
}

export async function createUser(
  name: string,
  country: string,
  city?: string | null,
  nickname?: string | null,
  email?: string | null,
  roles?: string[]
): Promise<User> {
  if (!isOnline()) {
    throw new Error('Cannot create users while offline. Please connect to the internet.');
  }

  const params = new URLSearchParams();
  params.append('name', name);
  params.append('country', country);
  if (city) params.append('city', city);
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
  roles?: string[]
): Promise<User> {
  if (!isOnline()) {
    throw new Error('Cannot update users while offline. Please connect to the internet.');
  }

  const params = new URLSearchParams();
  if (name) params.append('name', name);
  if (country) params.append('country', country);
  if (vekn_id !== undefined) params.append('vekn_id', vekn_id || '');
  if (city !== undefined) params.append('city', city || '');
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

/**
 * Get all sanctions for a user (from server, not IndexedDB).
 */
export async function getUserSanctionsApi(userUid: string, includeDeleted = false): Promise<Sanction[]> {
  const params = includeDeleted ? '?include_deleted=true' : '';
  return apiRequest<Sanction[]>(`/sanctions/user/${userUid}${params}`);
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

// Tournament API

export async function fetchTournament(uid: string): Promise<Tournament> {
  return apiRequest<Tournament>(`/api/tournaments/${uid}`);
}

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
}

export async function createTournament(data: CreateTournamentData): Promise<Tournament> {
  if (!isOnline()) {
    throw new Error('Cannot create tournament while offline.');
  }
  return apiRequest<Tournament>('/api/tournaments/', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updateTournament(uid: string, data: Partial<CreateTournamentData>): Promise<Tournament> {
  if (!isOnline()) {
    throw new Error('Cannot update tournament while offline.');
  }
  return apiRequest<Tournament>(`/api/tournaments/${uid}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function deleteTournamentApi(uid: string): Promise<{ message: string }> {
  if (!isOnline()) {
    throw new Error('Cannot delete tournament while offline.');
  }
  return apiRequest<{ message: string }>(`/api/tournaments/${uid}`, {
    method: 'DELETE',
  });
}

export async function tournamentAction(uid: string, action: string, data?: Record<string, unknown>): Promise<Tournament> {
  // Try optimistic update via WASM engine
  const current = await getTournament(uid);
  if (current) {
    try {
      const event = { type: action, ...data };
      const actor = buildActorContext(getAuthState().user ?? null, current);
      const updated = await processTournamentEvent(current, event, actor);
      await saveTournament(updated);
      await logChange('tournaments', 'update', uid, { event });

      // Send to server async — SSE will correct if divergence
      apiRequest<Tournament>(`/api/tournaments/${uid}/${action}`, {
        method: 'POST',
        body: data ? JSON.stringify(data) : undefined,
      }).catch(e => {
        console.error('Server rejected action, SSE will correct:', e);
      });

      return updated;
    } catch {
      // WASM engine failed (unknown action, etc.) — fall through to server-only
    }
  }

  // Fallback: server-only
  if (!isOnline()) {
    throw new Error('Cannot perform tournament action while offline.');
  }
  return apiRequest<Tournament>(`/api/tournaments/${uid}/${action}`, {
    method: 'POST',
    body: data ? JSON.stringify(data) : undefined,
  });
}

export async function setTableScore(
  tournamentUid: string,
  round: number,
  table: number,
  scores: Array<{ player_uid: string; vp: number }>
): Promise<Tournament> {
  if (!isOnline()) {
    throw new Error('Cannot set scores while offline.');
  }
  return apiRequest<Tournament>(
    `/api/tournaments/${tournamentUid}/rounds/${round}/tables/${table}/score`,
    {
      method: 'PUT',
      body: JSON.stringify({ scores }),
    }
  );
}

/**
 * Delete user avatar.
 */
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
