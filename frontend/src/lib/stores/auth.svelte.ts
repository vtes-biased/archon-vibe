/**
 * Auth store for managing authentication state.
 *
 * Uses Svelte 5 runes for reactive state management.
 * Persists tokens in localStorage and handles automatic refresh.
 */

const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
import * as m from '$lib/paraglide/messages.js';
import { toUserMessage } from '$lib/errors';
import type { User } from "$lib/types";
import { syncManager } from "$lib/sync";

const ACCESS_TOKEN_KEY = "archon_access_token";
const REFRESH_TOKEN_KEY = "archon_refresh_token";
const REFRESH_THRESHOLD_MS = 60 * 1000; // Refresh 1 minute before expiry

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

// Reactive auth state
let authState = $state<AuthState>({
  user: null,
  authMethods: [],
  isAuthenticated: false,
  isLoading: true,
  error: null,
});

// Timer for auto-refresh
let refreshTimer: ReturnType<typeof setTimeout> | null = null;

// Guard so the cross-tab storage listener is registered only once.
let crossTabSyncRegistered = false;

/**
 * Update auth state with partial values.
 */
export function setAuthState(updates: Partial<AuthState>) {
  authState = { ...authState, ...updates };
}

/**
 * Parse JWT token to extract expiry time.
 */
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

/**
 * Schedule automatic token refresh before expiry.
 */
function scheduleRefresh(expiresIn: number) {
  if (refreshTimer) {
    clearTimeout(refreshTimer);
  }

  // Refresh 1 minute before expiry (or immediately if less than 1 minute left)
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

/**
 * Store tokens in localStorage. Exported for passkey module.
 */
export function storeTokens(tokens: TokenResponse) {
  localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access_token);
  localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token);
  scheduleRefresh(tokens.expires_in);
}

/**
 * Clear tokens from localStorage.
 */
function clearTokens() {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
  if (refreshTimer) {
    clearTimeout(refreshTimer);
    refreshTimer = null;
  }
}

/**
 * Get the current access token.
 */
export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}

/**
 * React to auth changes made in *other* same-origin tabs.
 *
 * Tokens live in shared localStorage, so a login/logout/claim in one tab changes
 * the effective access level for every tab — but only the tab that made the
 * change knows. A tab that doesn't notice keeps its old-level SSE writing into
 * the *shared* IndexedDB, clobbering the other tab's data and silently dropping
 * it to a lower-access view. Here we converge this tab to the new
 * auth level so all same-origin tabs stay at one level and write identical
 * projections.
 *
 * The handler never writes to localStorage (the other tab already did), so it
 * can't trigger a storage-event cascade. Same-user token rotation (an auto
 * refresh in another tab) only re-arms our refresh timer — the access level is
 * unchanged, so the cached data is still valid and no resync is needed.
 */
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

/**
 * Register the cross-tab auth listener once (client-side only).
 */
function registerCrossTabAuthSync(): void {
  if (crossTabSyncRegistered || typeof window === "undefined") return;
  crossTabSyncRegistered = true;
  window.addEventListener("storage", (event) => {
    // storage fires only on the *other* tabs; key === null is localStorage.clear().
    if (event.key !== null && event.key !== ACCESS_TOKEN_KEY) return;
    void handleCrossTabAuthChange();
  });
}

/**
 * Store tokens from OAuth callback and initialize auth state.
 */
export async function storeTokensFromCallback(
  accessToken: string,
  refreshToken: string
): Promise<void> {
  localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
  localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);

  // Parse token to get expiry and schedule refresh
  const payload = parseJwt(accessToken);
  if (payload) {
    const expiresIn = payload.exp - Math.floor(Date.now() / 1000);
    scheduleRefresh(expiresIn);
  }

  // Fetch user data to complete auth state
  const result = await fetchCurrentUser();
  if (result) {
    setAuthState({
      user: result.user,
      authMethods: result.auth_methods,
      isAuthenticated: true,
      isLoading: false,
      error: null,
    });
    // Reconnect SSE with new token to get proper data level
    syncManager.refresh();
  }
}

// Single-flight: concurrent refreshers must share one POST, else a replayed
// rotated-out refresh token trips the backend's reuse-detection.
let refreshInFlight: Promise<boolean> | null = null;

/**
 * Refresh the access token. On failure the side effect distinguishes the cases:
 * a rejected refresh token clears tokens + resets auth state; a transient error
 * keeps them. Callers tell them apart via getAccessToken() afterwards.
 */
export async function refreshTokens(): Promise<boolean> {
  if (refreshInFlight) return refreshInFlight;
  refreshInFlight = doRefreshTokens();
  try {
    return await refreshInFlight;
  } finally {
    refreshInFlight = null;
  }
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
      // Server explicitly rejected the token — clear auth state
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

/**
 * Outcome of resolving a token before opening an SSE/snapshot connection:
 *  - token      authed; refreshed on demand if it was near expiry
 *  - anonymous  no session — connect at public level
 *  - downgrade  refresh token dead → caller must resync (clear-then-refill),
 *               never a since-overlay that mixes member + public rows
 *  - retry      transient refresh failure → back off, don't connect stale
 */
export type SyncToken =
  | { kind: "token"; token: string }
  | { kind: "anonymous" }
  | { kind: "downgrade" }
  | { kind: "retry" };

/**
 * Refresh on demand so we never open a connection with a stale access token (the
 * proactive timer dies under tab-suspend/device-sleep).
 */
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

/**
 * Fetch the current user from the API. Exported for passkey module.
 */
export async function fetchCurrentUser(): Promise<MeResponse | null> {
  const token = getAccessToken();
  if (!token) return null;

  try {
    const response = await fetch(`${API_BASE}/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
    });

    if (response.status === 401) {
      // Token expired, try to refresh
      const refreshed = await refreshTokens();
      if (!refreshed) return null;

      // Retry with new token
      const newToken = getAccessToken();
      if (!newToken) return null;

      const retryResponse = await fetch(`${API_BASE}/auth/me`, {
        headers: { Authorization: `Bearer ${newToken}` },
      });

      if (!retryResponse.ok) return null;

      return await retryResponse.json();
    }

    if (!response.ok) return null;

    return await response.json();
  } catch {
    return null;
  }
}

/**
 * Initialize auth state from stored tokens.
 * Call this on app startup.
 */
export async function initAuth(): Promise<void> {
  setAuthState({ isLoading: true });
  registerCrossTabAuthSync();

  const token = getAccessToken();
  if (!token) {
    setAuthState({ user: null, authMethods: [], isAuthenticated: false, isLoading: false, error: null });
    return;
  }

  // Check if token is expired
  const payload = parseJwt(token);
  if (payload && payload.exp * 1000 < Date.now()) {
    // Token expired, try to refresh
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

  // Fetch user data
  const result = await fetchCurrentUser();
  if (result) {
    setAuthState({ user: result.user, authMethods: result.auth_methods, isAuthenticated: true, isLoading: false, error: null });

    // Schedule refresh based on current token
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

/**
 * Register a new user.
 */
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

    // Fetch user data
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

/**
 * Login with email and password.
 */
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

    // Fetch user data
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

/**
 * Logout the current user.
 */
export async function logout(): Promise<void> {
  clearTokens();
  await syncManager.reset();
  setAuthState({ user: null, authMethods: [], isAuthenticated: false, isLoading: false, error: null });
}

/**
 * Profile update payload.
 */
export interface ProfileUpdate {
  name?: string;
  nickname?: string;
  country?: string;
  city?: string;
  city_geoname_id?: number | null;
  contact_email?: string;
  contact_phone?: string;
  phone_is_whatsapp?: boolean;
  community_links?: { type: string; url: string; label: string; languages: string[] }[];
}

/**
 * Update the current user's profile.
 */
export async function updateProfile(data: ProfileUpdate): Promise<boolean> {
  const token = getAccessToken();
  if (!token) {
    setAuthState({ error: m.auth_error_not_authenticated() });
    return false;
  }

  try {
    const response = await fetch(`${API_BASE}/auth/me`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(data),
    });

    if (response.status === 401) {
      const refreshed = await refreshTokens();
      if (!refreshed) {
        setAuthState({ error: m.auth_error_session_expired() });
        return false;
      }
      return updateProfile(data);
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

/**
 * Clear any auth error.
 */
export function clearError(): void {
  setAuthState({ error: null });
}

/**
 * Get the current auth state (reactive).
 */
export function getAuthState(): AuthState {
  return authState;
}

/**
 * Check if the current user has a specific role.
 */
export function hasRole(role: string): boolean {
  return authState.user?.roles.includes(role as User["roles"][number]) ?? false;
}

/**
 * Check if the current user has any of the specified roles.
 */
export function hasAnyRole(...roles: string[]): boolean {
  if (!authState.user) return false;
  return roles.some((role) =>
    authState.user!.roles.includes(role as User["roles"][number])
  );
}

/**
 * Request a magic link email for signup or password reset.
 * @param email User's email address
 * @param purpose "signup" for new accounts, "reset" for password reset
 */
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

/**
 * Response from verifying a magic link.
 */
export interface VerifyMagicLinkResult {
  setPasswordToken: string;
  email: string;
  purpose: "signup" | "reset";
}

/**
 * Verify a magic link token.
 * Returns a set-password token that allows the user to set their password.
 * Does NOT log in directly - user must set password first.
 */
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

/**
 * Set password after magic link verification.
 * Creates user/auth if signup, updates password if reset.
 * Returns true on success and logs in the user.
 */
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

    // Fetch user data
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

/**
 * Generate or regenerate a calendar subscription token.
 * Returns { calendar_token, calendar_url } on success, null on failure.
 */
export async function generateCalendarToken(): Promise<{ calendar_token: string; calendar_url: string } | null> {
  const token = getAccessToken();
  if (!token) return null;

  try {
    const response = await fetch(`${API_BASE}/auth/me/calendar-token`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    });

    if (response.status === 401) {
      const refreshed = await refreshTokens();
      if (!refreshed) return null;
      return generateCalendarToken();
    }

    if (!response.ok) return null;

    const data = await response.json();
    // Update local auth state with new token
    if (authState.user) {
      setAuthState({ user: { ...authState.user, calendar_token: data.calendar_token } });
    }
    return data;
  } catch {
    return null;
  }
}
