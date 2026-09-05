const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
import * as m from '$lib/paraglide/messages.js';
import { toUserMessage } from '$lib/errors';
import type { User } from "$lib/types";
import { syncManager } from "$lib/sync";
import { forgetViews } from "$lib/last-view";

const ACCESS_TOKEN_KEY = "archon_access_token";
const REFRESH_TOKEN_KEY = "archon_refresh_token";
const REFRESH_THRESHOLD_MS = 60 * 1000;

interface AuthMethod {
  type: string;
  identifier: string;
  verified: boolean;
}

interface AuthState {
  user: User | null;
  authMethods: AuthMethod[];
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;
}

interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

interface MeResponse {
  user: User;
  auth_methods: { type: string; identifier: string; verified: boolean }[];
}

let authState = $state<AuthState>({
  user: null,
  authMethods: [],
  isAuthenticated: false,
  isLoading: true,
  error: null,
});

let refreshTimer: ReturnType<typeof setTimeout> | null = null;

let crossTabSyncRegistered = false;
let ownUserSyncRegistered = false;

export function setAuthState(updates: Partial<AuthState>) {
  authState = { ...authState, ...updates };
}

function parseJwt(token: string): { exp: number; sub: string } | null {
  try {
    const base64Url = token.split(".")[1];
    if (!base64Url) return null;
    const base64 = base64Url.replace(/-/g, "+").replace(/_/g, "/");
    const jsonPayload = decodeURIComponent(
      atob(base64)
        .split("")
        .map((c) => "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2))
        .join("")
    );
    return JSON.parse(jsonPayload);
  } catch {
    return null;
  }
}

function scheduleRefresh(expiresIn: number) {
  if (refreshTimer) {
    clearTimeout(refreshTimer);
  }

  const refreshIn = Math.max(0, expiresIn * 1000 - REFRESH_THRESHOLD_MS);

  refreshTimer = setTimeout(async () => {
    const refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);
    if (refreshToken) {
      const success = await refreshTokens();
      if (!success && localStorage.getItem(REFRESH_TOKEN_KEY)) {
        // Network error — server may be restarting. Retry in 5 seconds.
        scheduleRefresh(5);
      }
    }
  }, refreshIn);
}

/** Exported for the passkey module. */
export function storeTokens(tokens: TokenResponse) {
  localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access_token);
  localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token);
  scheduleRefresh(tokens.expires_in);
}

function clearTokens() {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
  if (refreshTimer) {
    clearTimeout(refreshTimer);
    refreshTimer = null;
  }
}

export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}

/** Tokens live in shared localStorage, so a login/logout/claim in another tab changes this tab's
 * effective access level; if unnoticed, this tab's old-level SSE clobbers the shared IndexedDB with a lower-access projection. Converges this tab to match. */
async function handleCrossTabAuthChange(): Promise<void> {
  const token = getAccessToken();

  // Logout in another tab → drop to anonymous and resync the public view.
  if (!token) {
    if (!authState.isAuthenticated) return;
    if (refreshTimer) {
      clearTimeout(refreshTimer);
      refreshTimer = null;
    }
    setAuthState({ user: null, authMethods: [], isAuthenticated: false, isLoading: false, error: null });
    await syncManager.refresh();
    return;
  }

  // Same user, rotated token (another tab refreshed): keep our timer in sync but
  // leave the cache alone — the access level hasn't changed.
  const payload = parseJwt(token);
  if (payload && authState.user && payload.sub === authState.user.uid) {
    scheduleRefresh(payload.exp - Math.floor(Date.now() / 1000));
    return;
  }

  // Login / claim / user switch in another tab → adopt it and resync at the new
  // access level.
  if (payload) scheduleRefresh(payload.exp - Math.floor(Date.now() / 1000));
  const result = await fetchCurrentUser();
  if (result) {
    setAuthState({ user: result.user, authMethods: result.auth_methods, isAuthenticated: true, isLoading: false, error: null });
    await syncManager.refresh();
  }
}

function registerOwnUserSync(): void {
  if (ownUserSyncRegistered) return;
  ownUserSyncRegistered = true;
  syncManager.addEventListener((event) => {
    if (event.type !== "user") return;
    const synced = event.data as User | undefined;
    const current = authState.user;
    if (!synced || !current || synced.uid !== current.uid) return;
    if (synced.modified === current.modified) return;
    setAuthState({ user: { ...synced, calendar_token: current.calendar_token } });
  });
}

function registerCrossTabAuthSync(): void {
  if (crossTabSyncRegistered || typeof window === "undefined") return;
  crossTabSyncRegistered = true;
  window.addEventListener("storage", (event) => {
    // storage fires only on the *other* tabs; key === null is localStorage.clear().
    if (event.key !== null && event.key !== ACCESS_TOKEN_KEY) return;
    void handleCrossTabAuthChange();
  });
}

export async function storeTokensFromCallback(
  accessToken: string,
  refreshToken: string
): Promise<void> {
  localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
  localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);

  const payload = parseJwt(accessToken);
  if (payload) {
    const expiresIn = payload.exp - Math.floor(Date.now() / 1000);
    scheduleRefresh(expiresIn);
  }

  const result = await fetchCurrentUser();
  if (result) {
    setAuthState({
      user: result.user,
      authMethods: result.auth_methods,
      isAuthenticated: true,
      isLoading: false,
      error: null,
    });
    syncManager.refresh();
  }
}

// Single-flight: concurrent refreshers must share one POST, else a replayed
// rotated-out refresh token trips the backend's reuse-detection.
let refreshInFlight: Promise<boolean> | null = null;

/** On failure the side effect distinguishes the cases: a rejected refresh token clears tokens + resets
 * auth state; a transient error keeps them. Callers tell them apart via getAccessToken() afterwards. */
export async function refreshTokens(): Promise<boolean> {
  if (refreshInFlight) return refreshInFlight;
  refreshInFlight = doRefreshTokens();
  try {
    return await refreshInFlight;
  } finally {
    refreshInFlight = null;
  }
}

/** On a 401, does one single-flighted refresh (dedup'd via refreshTokens) and one retry with the new
 * token. Never loops: if the endpoint keeps 401ing after a successful refresh, that 401 is returned. */
export async function authorizedFetch(input: string, init: RequestInit = {}): Promise<Response> {
  const doFetch = () => {
    const token = getAccessToken();
    const headers = new Headers(init.headers);
    if (token) headers.set("Authorization", `Bearer ${token}`);
    return fetch(input, { ...init, headers });
  };
  const response = await doFetch();
  if (response.status !== 401) return response;
  const refreshed = await refreshTokens();
  if (!refreshed || !getAccessToken()) return response;
  return doFetch();
}

async function doRefreshTokens(): Promise<boolean> {
  const refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);
  if (!refreshToken) {
    return false;
  }

  try {
    const response = await fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });

    if (!response.ok) {
      clearTokens();
      setAuthState({ user: null, authMethods: [], isAuthenticated: false, isLoading: false, error: null });
      return false;
    }

    const tokens: TokenResponse = await response.json();
    storeTokens(tokens);
    return true;
  } catch {
    // Network error (server unreachable) — keep tokens for retry later.
    // Don't clear auth state; the server may just be restarting.
    return false;
  }
}

/** `downgrade`: refresh token dead → caller must resync via clear-then-refill, never a since-overlay
 * that mixes member + public rows. `retry`: transient failure → back off, don't connect stale. */
export type SyncToken =
  | { kind: "token"; token: string }
  | { kind: "anonymous" }
  | { kind: "downgrade" }
  | { kind: "retry" };

// Refresh on demand: the proactive timer dies under tab-suspend and device-sleep,
// so a connection would otherwise open on a stale access token.
export async function ensureSyncToken(): Promise<SyncToken> {
  const token = getAccessToken();
  if (!token) return { kind: "anonymous" };

  const payload = parseJwt(token);
  if (payload && payload.exp * 1000 - Date.now() > REFRESH_THRESHOLD_MS) {
    return { kind: "token", token };
  }

  const refreshed = await refreshTokens();
  if (refreshed) {
    const fresh = getAccessToken();
    return fresh ? { kind: "token", token: fresh } : { kind: "downgrade" };
  }
  // Cleared tokens ⇒ refresh token rejected (downgrade); kept ⇒ transient.
  return getAccessToken() ? { kind: "retry" } : { kind: "downgrade" };
}

/** Exported for the passkey module. */
export async function fetchCurrentUser(): Promise<MeResponse | null> {
  if (!getAccessToken()) return null;

  try {
    const response = await authorizedFetch(`${API_BASE}/auth/me`);
    if (!response.ok) return null;
    return await response.json();
  } catch {
    return null;
  }
}

export async function initAuth(): Promise<void> {
  setAuthState({ isLoading: true });
  registerCrossTabAuthSync();
  registerOwnUserSync();

  const token = getAccessToken();
  if (!token) {
    setAuthState({ user: null, authMethods: [], isAuthenticated: false, isLoading: false, error: null });
    return;
  }

  const payload = parseJwt(token);
  if (payload && payload.exp * 1000 < Date.now()) {
    const refreshed = await refreshTokens();
    if (!refreshed) {
      // If we still have a refresh token, the server may be temporarily down.
      // Keep tokens and show as not authenticated for now — next app load will retry.
      const hasRefresh = localStorage.getItem(REFRESH_TOKEN_KEY);
      if (!hasRefresh) {
        clearTokens();
      }
      setAuthState({ user: null, authMethods: [], isAuthenticated: false, isLoading: false, error: null });
      return;
    }
  }

  const result = await fetchCurrentUser();
  if (result) {
    setAuthState({ user: result.user, authMethods: result.auth_methods, isAuthenticated: true, isLoading: false, error: null });

    const currentToken = getAccessToken();
    if (currentToken) {
      const currentPayload = parseJwt(currentToken);
      if (currentPayload) {
        const expiresIn = currentPayload.exp - Math.floor(Date.now() / 1000);
        scheduleRefresh(expiresIn);
      }
    }
  } else {
    // fetchCurrentUser returns null on both auth failure and network error.
    // Only clear tokens if the refresh token is also gone (definitively rejected).
    const hasRefresh = localStorage.getItem(REFRESH_TOKEN_KEY);
    if (!hasRefresh) {
      clearTokens();
    }
    setAuthState({ user: null, authMethods: [], isAuthenticated: false, isLoading: false, error: null });
  }
}

export async function register(
  email: string,
  password: string,
  name: string
): Promise<boolean> {
  setAuthState({ isLoading: true, error: null });

  try {
    const response = await fetch(`${API_BASE}/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password, name }),
    });

    if (!response.ok) {
      const data = await response.json();
      setAuthState({ isLoading: false, error: data.detail || m.auth_error_registration() });
      return false;
    }

    const tokens: TokenResponse = await response.json();
    storeTokens(tokens);

    const result = await fetchCurrentUser();
    if (result) {
      setAuthState({ user: result.user, authMethods: result.auth_methods, isAuthenticated: true, isLoading: false, error: null });
      syncManager.refresh();
      return true;
    }

    setAuthState({ isLoading: false, error: m.auth_error_fetch_user() });
    return false;
  } catch (e) {
    setAuthState({
      isLoading: false,
      error: toUserMessage(e, m.auth_error_registration()),
    });
    return false;
  }
}

export async function login(email: string, password: string): Promise<boolean> {
  setAuthState({ isLoading: true, error: null });

  try {
    const response = await fetch(`${API_BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });

    if (!response.ok) {
      const data = await response.json();
      setAuthState({ isLoading: false, error: data.detail || m.auth_error_login() });
      return false;
    }

    const tokens: TokenResponse = await response.json();
    storeTokens(tokens);

    const result = await fetchCurrentUser();
    if (result) {
      setAuthState({ user: result.user, authMethods: result.auth_methods, isAuthenticated: true, isLoading: false, error: null });
      syncManager.refresh();
      return true;
    }

    setAuthState({ isLoading: false, error: m.auth_error_fetch_user() });
    return false;
  } catch (e) {
    setAuthState({
      isLoading: false,
      error: toUserMessage(e, m.auth_error_login()),
    });
    return false;
  }
}

export async function logout(): Promise<void> {
  clearTokens();
  // Remembered list views can hold filters an anonymous viewer has no control for (state=finished
  // is authenticated-only), so they would filter unaccountably.
  forgetViews();
  await syncManager.reset();
  setAuthState({ user: null, authMethods: [], isAuthenticated: false, isLoading: false, error: null });
  // An anonymous tab still streams the public view. Without this the tab is left deaf with no
  // retry pending — the one absorbing state the reconnect loop otherwise has none of.
  void syncManager.connect();
}

export interface ProfileUpdate {
  name?: string;
  nickname?: string;
  country?: string;
  city?: string;
  city_geoname_id?: number | null;
  contact_email?: string;
  contact_phone?: string;
  phone_is_whatsapp?: boolean;
  community_links?: {
    type: string;
    url: string;
    label: string;
    languages?: string[];
    country?: string | null;
    state?: string;
  }[];
}

export async function updateProfile(data: ProfileUpdate): Promise<boolean> {
  if (!getAccessToken()) {
    setAuthState({ error: m.auth_error_not_authenticated() });
    return false;
  }

  try {
    const response = await authorizedFetch(`${API_BASE}/auth/me`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });

    if (response.status === 401) {
      setAuthState({ error: m.auth_error_session_expired() });
      return false;
    }

    if (!response.ok) {
      const errorData = await response.json();
      setAuthState({ error: errorData.detail || m.auth_error_update() });
      return false;
    }

    const result: MeResponse = await response.json();
    setAuthState({ user: result.user, authMethods: result.auth_methods, error: null });
    return true;
  } catch (e) {
    setAuthState({
      error: toUserMessage(e, m.auth_error_update()),
    });
    return false;
  }
}

export function getAuthState(): AuthState {
  return authState;
}

export async function requestMagicLink(
  email: string,
  purpose: "signup" | "reset" = "signup",
  includeAuth = false,
): Promise<boolean> {
  setAuthState({ isLoading: true, error: null });

  try {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (includeAuth) {
      const token = getAccessToken();
      if (token) headers["Authorization"] = `Bearer ${token}`;
    }
    const response = await fetch(`${API_BASE}/auth/email/request`, {
      method: "POST",
      headers,
      body: JSON.stringify({ email, purpose }),
    });

    if (!response.ok) {
      const data = await response.json();
      setAuthState({ isLoading: false, error: data.detail || m.auth_error_send_email() });
      return false;
    }

    setAuthState({ isLoading: false, error: null });
    return true;
  } catch (e) {
    setAuthState({
      isLoading: false,
      error: toUserMessage(e, m.auth_error_send_email()),
    });
    return false;
  }
}

export interface VerifyMagicLinkResult {
  setPasswordToken: string;
  email: string;
  purpose: "signup" | "reset";
}

/** Does NOT log in directly — the caller must call setPassword first. */
export async function verifyMagicLink(
  token: string
): Promise<VerifyMagicLinkResult | null> {
  setAuthState({ isLoading: true, error: null });

  try {
    const response = await fetch(`${API_BASE}/auth/email/verify`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    });

    if (!response.ok) {
      const data = await response.json();
      setAuthState({ isLoading: false, error: data.detail || "Invalid or expired link" });
      return null;
    }

    const data = await response.json();
    setAuthState({ isLoading: false, error: null });

    return {
      setPasswordToken: data.set_password_token,
      email: data.email,
      purpose: data.purpose,
    };
  } catch (e) {
    setAuthState({
      isLoading: false,
      error: toUserMessage(e, m.auth_error_verification()),
    });
    return null;
  }
}

export async function setPassword(token: string, password: string): Promise<boolean> {
  setAuthState({ isLoading: true, error: null });

  try {
    const response = await fetch(`${API_BASE}/auth/email/set-password`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token, password }),
    });

    if (!response.ok) {
      const data = await response.json();
      setAuthState({ isLoading: false, error: data.detail || m.auth_error_set_password() });
      return false;
    }

    const tokens: TokenResponse = await response.json();
    storeTokens(tokens);

    const result = await fetchCurrentUser();
    if (result) {
      setAuthState({
        user: result.user,
        authMethods: result.auth_methods,
        isAuthenticated: true,
        isLoading: false,
        error: null,
      });
      syncManager.refresh();
      return true;
    }

    setAuthState({ isLoading: false, error: m.auth_error_fetch_user() });
    return false;
  } catch (e) {
    setAuthState({
      isLoading: false,
      error: toUserMessage(e, m.auth_error_set_password()),
    });
    return false;
  }
}

/** Returns the failure message, or null on success. Writes no shared auth state:
 * the profile page unmounts its whole panel on `isLoading`, taking the form with it. */
export async function changePassword(password: string): Promise<string | null> {
  try {
    const response = await authorizedFetch(`${API_BASE}/auth/me/password`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password }),
    });

    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      return data.detail || m.auth_error_set_password();
    }

    return null;
  } catch (e) {
    return toUserMessage(e, m.auth_error_set_password());
  }
}

export async function generateCalendarToken(): Promise<{ calendar_token: string; calendar_url: string } | null> {
  if (!getAccessToken()) return null;

  try {
    const response = await authorizedFetch(`${API_BASE}/auth/me/calendar-token`, {
      method: "POST",
    });

    if (!response.ok) return null;

    const data = await response.json();
    if (authState.user) {
      setAuthState({ user: { ...authState.user, calendar_token: data.calendar_token } });
    }
    return data;
  } catch {
    return null;
  }
}
