import type { User, Sanction, SanctionLevel, SanctionCategory, SanctionSubcategory, Tournament, League, Promo, PromoKind, PromoLedgerEntry, PromoLedgerKind, TournamentRank } from '$lib/types';
import { saveTournament, saveLeague } from './db';
import { showToast } from '$lib/stores/toast.svelte';
import { authorizedFetch, ensureSyncToken, getAuthState } from '$lib/stores/auth.svelte';
import { errorCodeToMessage } from './error-codes';
import * as m from './paraglide/messages.js';

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

/** `code`/`params` carry the engine's structured rejection when the 400 body has them —
 * `toUserMessage` maps the code to a localized message. */
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public detail?: string,
    public code?: string,
    public params?: Record<string, string>
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
  // apiRequest is the single toast authority for its own failures: it auto-toasts offline, transport,
  // and HTTP errors. Callers that surface the error themselves pass this to avoid a duplicate toast.
  { suppressErrorToast = false }: { suppressErrorToast?: boolean } = {}
): Promise<T> {
  // Offline guard: an apiRequest is a mutation or a server-only proxy read (ordinary reads are
  // offline-first from IndexedDB), so there's no point attempting the fetch. Toast + throw
  // (status 0 = never left the device) so callers can distinguish it.
  if (!isOnline()) {
    const message = m.error_action_requires_online();
    if (!suppressErrorToast) showToast({ type: 'error', message });
    throw new ApiError(message, 0);
  }

  const headers: Record<string, string> = {
    ...((options.headers as Record<string, string>) || {}),
  };

  if (options.body && typeof options.body === 'string') {
    headers['Content-Type'] = 'application/json';
  }

  let response: Response;
  try {
    // authorizedFetch attaches the bearer and retries once on 401 after a single-flighted refresh —
    // the backstop for laptop-wake/suspended-tab mutations whose proactive refresh timer died with the tab.
    response = await authorizedFetch(`${API_URL}${path}`, {
      ...options,
      headers,
    });
  } catch (e) {
    // fetch() rejects with a TypeError on a transport failure (dropped mid-flight, DNS, CORS, server
    // down). This never reaches the !response.ok block below, so it used to escape untoasted — toast it.
    if (!suppressErrorToast) showToast({ type: 'error', message: m.error_network_unreachable() });
    throw e instanceof Error ? e : new Error(m.error_network_unreachable());
  }

  if (!response.ok) {
    let detail: string | undefined;
    let code: string | undefined;
    let params: Record<string, string> | undefined;
    try {
      const data = await response.json();
      detail = data.detail || data.message;
      // Engine rejection bodies carry top-level code+params next to detail
      if (typeof data.code === 'string') {
        code = data.code;
        params = data.params ?? {};
      }
    } catch {
    }
    const localized = code ? errorCodeToMessage(code, params) : undefined;
    const message = localized || detail || `Request failed: ${response.statusText}`;
    if (!suppressErrorToast) showToast({ type: 'error', message });
    throw new ApiError(message, response.status, detail, code, params);
  }

  if (response.status === 204 || response.headers.get('content-length') === '0') {
    return undefined as T;
  }
  return response.json();
}

export function isOnline(): boolean {
  return navigator.onLine;
}

/** Toasts + throws when offline. Toasts so the many empty-catch callers (sanctions, VEKN, avatar)
 * aren't silent offline. Callers that render the error themselves pass `suppressErrorToast`. */
export function requireOnline({ suppressErrorToast = false }: { suppressErrorToast?: boolean } = {}): void {
  if (isOnline()) return;
  const message = m.error_action_requires_online();
  if (!suppressErrorToast) showToast({ type: 'error', message });
  throw new ApiError(message, 0);
}

/** Per-env VAPID public key (applicationServerKey) the browser subscribes with. */
export async function getVapidPublicKey(): Promise<string> {
  const { key } = await apiRequest<{ key: string }>('/api/push/vapid-key', {}, { suppressErrorToast: true });
  return key;
}

/** Registers (upserts) the browser's push subscription. Locale is stored per-subscription so
 * notification bodies render in this device's language (a user may have a FR phone and an EN laptop). */
export async function registerPushSubscription(
  sub: PushSubscriptionJSON,
  locale: string
): Promise<void> {
  await apiRequest<void>(
    '/api/push/subscribe',
    { method: 'POST', body: JSON.stringify({ ...sub, locale }) },
    { suppressErrorToast: true }
  );
}

export async function deletePushSubscription(endpoint: string): Promise<void> {
  await apiRequest<void>(
    '/api/push/unsubscribe',
    { method: 'POST', body: JSON.stringify({ endpoint }) },
    { suppressErrorToast: true }
  );
}

export interface FeedbackSubmission {
  category: 'bug' | 'feature' | 'question';
  title: string;
  description: string;
  app_version: string;
  route: string;
  locale: string;
  user_agent: string;
}

/** File in-app feedback as a GitHub issue (online-only). The modal renders its own
 *  success/error state, so callers suppress the apiRequest toast. */
export async function submitFeedback(
  data: FeedbackSubmission,
  opts?: { suppressErrorToast?: boolean }
): Promise<{ issue_url: string; issue_number: number }> {
  return apiRequest<{ issue_url: string; issue_number: number }>(
    '/api/feedback/',
    { method: 'POST', body: JSON.stringify(data) },
    opts
  );
}

export async function createUser(
  name: string,
  country: string,
  city?: string | null,
  nickname?: string | null,
  email?: string | null,
  roles?: string[],
  city_geoname_id?: number | null,
  opts?: { suppressErrorToast?: boolean },
): Promise<User> {
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
  opts?: { suppressErrorToast?: boolean },
): Promise<User> {
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

/** Mark or clear a member's deceased status (IC or same-country NC). */
export async function setMemberDeceased(uid: string, deceased: boolean): Promise<User> {
  return apiRequest<User>(
    `/api/users/${uid}/deceased`,
    { method: 'PATCH', body: JSON.stringify({ deceased }) },
  );
}

/** Soft-delete a VEKN-less member (IC only). Returns the soft-deleted user. */
export async function deleteMember(uid: string): Promise<User> {
  return apiRequest<User>(`/api/users/${uid}`, { method: 'DELETE' });
}

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

export async function claimVeknId(vekn_id: string): Promise<VeknClaimResponse> {
  return apiRequest<VeknClaimResponse>('/vekn/claim', {
    method: 'POST',
    body: JSON.stringify({ vekn_id }),
  });
}

export async function abandonVeknId(): Promise<VeknAbandonResponse> {
  return apiRequest<VeknAbandonResponse>('/vekn/abandon', {
    method: 'POST',
  });
}

/** Allocates a new sequential VEKN ID. */
export async function sponsorVeknMember(user_uid: string): Promise<VeknSponsorResponse> {
  return apiRequest<VeknSponsorResponse>('/vekn/sponsor', {
    method: 'POST',
    body: JSON.stringify({ user_uid }),
  });
}

/** May displace the current holder of that VEKN ID. */
export async function linkVeknId(vekn_id: string, user_uid: string): Promise<VeknLinkResponse> {
  return apiRequest<VeknLinkResponse>('/vekn/link', {
    method: 'POST',
    body: JSON.stringify({ vekn_id, user_uid }),
  });
}

/** Gated by the `manage_vekn` capability. */
export async function forceAbandonVeknId(user_uid: string): Promise<VeknMessageResponse> {
  return apiRequest<VeknMessageResponse>('/vekn/force-abandon', {
    method: 'POST',
    body: JSON.stringify({ user_uid }),
  });
}

/** IC only. Unions both accounts' roles rather than picking one side. */
export async function mergeUsers(keep_uid: string, delete_uid: string): Promise<{ user: User; message: string }> {
  return apiRequest<{ user: User; message: string }>('/admin/users/merge', {
    method: 'POST',
    body: JSON.stringify({ keep_uid, delete_uid }),
  });
}

export interface AdminSyncResult {
  /** "started" / "already_running" for background-dispatched syncs. */
  status: string;
  /** Only present for synchronous ops; the VEKN/TWDA syncs run in the background. */
  stats?: Record<string, unknown>;
}

/** IC-only: dispatch a VEKN member sync in the background (also runs on a 6h schedule). */
export async function syncVeknMembers(): Promise<AdminSyncResult> {
  // Errors surface inline in ConfirmActionModal — suppress the duplicate toast.
  return apiRequest<AdminSyncResult>('/admin/sync-vekn', { method: 'POST' }, { suppressErrorToast: true });
}

/** IC-only: dispatch a VEKN tournament sync in the background (also runs on a 6h schedule). */
export async function syncVeknTournaments(): Promise<AdminSyncResult> {
  return apiRequest<AdminSyncResult>('/admin/sync-vekn-tournaments', { method: 'POST' }, { suppressErrorToast: true });
}

/** IC-only: dispatch a TWDA decklist import in the background (also runs on a 24h schedule). */
export async function syncTwdaDecks(): Promise<AdminSyncResult> {
  return apiRequest<AdminSyncResult>('/admin/sync-twda-decks', { method: 'POST' }, { suppressErrorToast: true });
}

export interface VeknJobStatus {
  last_success_at?: string;
  last_error_at?: string;
  last_error?: string;
  last_status?: 'ok' | 'error';
  last_detail?: Record<string, unknown>;
}
export interface VeknStatusResponse {
  jobs: Record<string, VeknJobStatus>;
}

/** In-process server state, not a synced object type — a justified GET (like the sync triggers
 * above, it can't come from IndexedDB). */
export async function getVeknStatus(): Promise<VeknStatusResponse> {
  return apiRequest<VeknStatusResponse>('/admin/vekn-status', { method: 'GET' }, { suppressErrorToast: true });
}

/** A browser download can't carry an Authorization header, so the token rides the query string —
 * same as the SSE/snapshot fetch. */
export async function downloadDataExport(): Promise<void> {
  // Thrown, not toasted: the caller (confirm modal) renders the failure in place with a retry. Offline,
  // the navigation would otherwise land on the browser's error page, replacing the SPA.
  if (!isOnline()) throw new Error(m.error_action_requires_online());
  const t = await ensureSyncToken();
  if (t.kind !== 'token') throw new Error(m.auth_error_session_expired());
  // Content-Disposition makes this a download, not a navigation — the SPA stays put.
  window.location.href = `${API_URL}/snapshot?download=1&token=${encodeURIComponent(t.token)}`;
}

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

/** IC/Ethics only for SUSPENSION/PROBATION. */
export async function createSanction(data: CreateSanctionData): Promise<Sanction> {
  return apiRequest<Sanction>('/sanctions/', {
    method: 'POST',
    body: JSON.stringify(data),
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

export async function updateSanction(uid: string, data: UpdateSanctionData): Promise<Sanction> {
  return apiRequest<Sanction>(`/sanctions/${uid}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function deleteSanctionApi(uid: string): Promise<{ message: string }> {
  return apiRequest<{ message: string }>(`/sanctions/${uid}`, {
    method: 'DELETE',
  });
}

/** Blob should be webp, max 1MB. */
export async function uploadAvatar(userUid: string, blob: Blob): Promise<{ success: boolean }> {
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

  const formData = new FormData();
  formData.append('file', file);

  const response = await authorizedFetch(`${API_URL}/api/tournaments/${tournamentUid}/archon-import`, {
    method: 'POST',
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
  registration_url?: string;
  description?: string;
  max_rounds?: number;
  open_rounds?: boolean;
  self_organized_rounds?: boolean;
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
  let result: { message: string };
  try {
    result = await apiRequest<{ message: string }>(`/api/tournaments/${uid}`, {
      method: 'DELETE',
    }, opts);
  } catch (e) {
    // 404 = the server never knew this tournament (created offline, not yet pushed at go-online) —
    // the local delete below IS the deletion.
    if (!(e instanceof ApiError && e.status === 404)) throw e;
    result = { message: 'Tournament deleted' };
  }
  // Optimistic IDB delete so UI updates immediately instead of waiting for SSE.
  const { deleteTournament } = await import('./db');
  await deleteTournament(uid);
  // Drop any offline lock/metadata (no-op for ordinary online tournaments)
  const { clearOfflineState } = await import('$lib/stores/offline.svelte');
  await clearOfflineState(uid);
  return result;
}

/** Register a tournament with the VEKN calendar on demand (organizer action). */
export async function syncTournamentVekn(uid: string, opts?: { suppressErrorToast?: boolean }): Promise<Tournament> {
  return apiRequest<Tournament>(`/api/tournaments/${uid}/push-vekn`, {
    method: 'POST',
  }, opts);
}

/** Server-only, no optimistic path. */
export async function qrCheckin(tournamentUid: string, code: string): Promise<Tournament> {
  return apiRequest<Tournament>(`/api/tournaments/${tournamentUid}/qr-checkin`, {
    method: 'POST',
    body: JSON.stringify({ code }),
  });
}

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
  open_to_country_princes?: boolean;
}

export async function createLeague(data: CreateLeagueData, opts?: { suppressErrorToast?: boolean }): Promise<League> {
  const created = await apiRequest<League>('/api/leagues/', {
    method: 'POST',
    body: JSON.stringify(data),
  }, opts);
  await saveLeague(created);
  return created;
}

export async function updateLeague(uid: string, data: Partial<CreateLeagueData>, opts?: { suppressErrorToast?: boolean }): Promise<League> {
  const updated = await apiRequest<League>(`/api/leagues/${uid}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  }, opts);
  await saveLeague(updated);
  return updated;
}

export async function deleteLeagueApi(uid: string, opts?: { suppressErrorToast?: boolean }): Promise<void> {
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

export async function postAnnouncement(uid: string, body: string): Promise<void> {
  await apiRequest(`/api/tournaments/${uid}/announce`, {
    method: 'POST',
    body: JSON.stringify({ body }),
  });
}

export async function deleteAnnouncement(uid: string, announcementId: string): Promise<void> {
  await apiRequest(`/api/tournaments/${uid}/announce/${announcementId}`, { method: 'DELETE' });
}

export async function callJudge(uid: string, table: number): Promise<void> {
  await apiRequest<void>(`/api/tournaments/${uid}/call-judge`, {
    method: 'POST',
    body: JSON.stringify({ table }),
  });
}

/** The new versioned banner_path arrives via SSE — no need to return it here. Blob should be the
 * cropped 1.91:1 image, webp, max 1MB. */
export async function uploadTournamentBanner(
  tournamentUid: string,
  blob: Blob
): Promise<{ success: boolean }> {
  const formData = new FormData();
  formData.append('file', blob, 'banner.webp');

  const result = await apiRequest<{ success: boolean }>(
    `/api/tournaments/${tournamentUid}/banner`,
    { method: 'POST', body: formData }
  );
  showToast({ type: 'success', message: m.tournament_banner_updated() });
  return result;
}

export async function deleteTournamentBanner(
  tournamentUid: string
): Promise<{ success: boolean }> {
  const result = await apiRequest<{ success: boolean }>(
    `/api/tournaments/${tournamentUid}/banner`,
    { method: 'DELETE' }
  );
  showToast({ type: 'success', message: m.tournament_banner_removed() });
  return result;
}

// Promos: catalog is IC-only; the ledger read below is the app's one sanctioned online-only carve-out.

export interface PromoPayload {
  name?: string;
  kind?: PromoKind;
  description?: string;
  release_date?: string | null;
  active?: boolean;
  allowed_ranks?: TournamentRank[];
  league_uids?: string[];
}

export async function createPromo(payload: PromoPayload): Promise<Promo> {
  return apiRequest<Promo>('/api/promos/', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function updatePromo(uid: string, payload: PromoPayload): Promise<Promo> {
  return apiRequest<Promo>(`/api/promos/${uid}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

/** 409 = referenced by reports/raffles/ledger — retire (active=false) instead. */
export async function deletePromoCatalogEntry(uid: string): Promise<void> {
  await apiRequest<void>(`/api/promos/${uid}`, { method: 'DELETE' }, { suppressErrorToast: true });
}

export async function uploadPromoImage(uid: string, file: File | Blob): Promise<{ success: boolean }> {
  const formData = new FormData();
  formData.append('file', file, 'promo.webp');
  return apiRequest<{ success: boolean }>(`/api/promos/${uid}/image`, {
    method: 'POST',
    body: formData,
  });
}

export async function deletePromoImage(uid: string): Promise<void> {
  await apiRequest<void>(`/api/promos/${uid}/image`, { method: 'DELETE' });
}

export interface LedgerEntryPayload {
  kind: PromoLedgerKind;
  lines: { promo_uid: string; qty: number }[];
  to_uid?: string; // assignments only
  from_uid?: string; // IC only; defaults to the actor
  note?: string;
  happened_at?: string;
}

export async function createPromoLedgerEntries(payload: LedgerEntryPayload): Promise<PromoLedgerEntry[]> {
  return apiRequest<PromoLedgerEntry[]>('/api/promos/ledger', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

/** Whole role-scoped ledger (officials: all rows; others: involved rows) — the app's one sanctioned
 * online-only-read carve-out. */
export async function getPromoLedger(): Promise<PromoLedgerEntry[]> {
  return apiRequest<PromoLedgerEntry[]>('/api/promos/ledger', { method: 'GET' });
}

export interface NdaRecord {
  uid: string;
  user_uid: string;
  status: 'pending' | 'signed' | 'uploaded';
  document_version: number | null;
  document_sha256: string | null;
  signer_name: string | null;
  signer_email: string | null;
  requested_by: string;
  created_at: string;
  signed_at: string | null;
  content_type: string | null;
}

export interface NdaStatus {
  records: NdaRecord[];
  pending: NdaRecord | null;
  has_nda: boolean;
  document_version: number;
}

/** PTC/IC for any member; members for themselves. Online-only read — NDA records
 * are never synced or projected. */
export async function getNdaStatus(
  userUid: string,
  opts?: { suppressErrorToast?: boolean }
): Promise<NdaStatus> {
  return apiRequest<NdaStatus>(`/api/users/${userUid}/nda`, { method: 'GET' }, opts);
}

export async function requestNdaSignature(userUid: string): Promise<void> {
  await apiRequest<void>(`/api/users/${userUid}/nda/request`, { method: 'POST' });
}

export async function getNdaDocument(
  userUid: string
): Promise<{ text: string; version: number; sha256: string }> {
  return apiRequest(`/api/users/${userUid}/nda/document`, { method: 'GET' });
}

export async function signNda(
  userUid: string,
  data: { name: string; email: string; address: string; phone: string }
): Promise<{ success: boolean; record_uid: string }> {
  return apiRequest(`/api/users/${userUid}/nda/sign`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function uploadNdaScan(userUid: string, file: File): Promise<void> {
  const formData = new FormData();
  formData.append('file', file, file.name);
  await apiRequest<void>(`/api/users/${userUid}/nda/upload`, {
    method: 'POST',
    body: formData,
  });
}

/** Small PII evidence file: fetched with the auth header and handed over as a
 * Blob, unlike the query-token data export (see design.md, downloads). */
export async function downloadNdaPdf(userUid: string, recordUid: string): Promise<void> {
  requireOnline();
  const response = await authorizedFetch(
    `${API_URL}/api/users/${userUid}/nda/${recordUid}/pdf`
  );
  if (!response.ok) {
    showToast({ type: 'error', message: m.nda_download_failed() });
    throw new ApiError(m.nda_download_failed(), response.status);
  }
  const blob = await response.blob();
  const ext = (response.headers.get('Content-Type') ?? 'application/pdf')
    .split('/')
    .pop()!
    .replace('jpeg', 'jpg');
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `bcp-playtest-nda.${ext}`;
  a.click();
  URL.revokeObjectURL(url);
}
