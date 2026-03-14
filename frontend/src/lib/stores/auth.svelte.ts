/**
 * Auth store for managing authentication state.
 *
 * Uses Svelte 5 runes for reactive state management.
 * Persists tokens in localStorage and handles automatic refresh.
 */

const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
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

/**
 * Refresh the access token using the refresh token.
 */
async function refreshTokens(): Promise<boolean> {
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
      setAuthState({ isLoading: false, error: data.detail || "Registration failed" });
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

    setAuthState({ isLoading: false, error: "Failed to fetch user data" });
    return false;
  } catch (e) {
    setAuthState({
      isLoading: false,
      error: e instanceof Error ? e.message : "Registration failed",
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
      setAuthState({ isLoading: false, error: data.detail || "Login failed" });
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

    setAuthState({ isLoading: false, error: "Failed to fetch user data" });
    return false;
  } catch (e) {
    setAuthState({
      isLoading: false,
      error: e instanceof Error ? e.message : "Login failed",
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
  contact_discord?: string;
  contact_phone?: string;
  phone_is_whatsapp?: boolean;
  community_links?: { type: string; url: string; label: string }[];
}

/**
 * Update the current user's profile.
 */
export async function updateProfile(data: ProfileUpdate): Promise<boolean> {
  const token = getAccessToken();
  if (!token) {
    setAuthState({ error: "Not authenticated" });
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
        setAuthState({ error: "Session expired" });
        return false;
      }
      return updateProfile(data);
    }

    if (!response.ok) {
      const errorData = await response.json();
      setAuthState({ error: errorData.detail || "Update failed" });
      return false;
    }

    const result: MeResponse = await response.json();
    setAuthState({ user: result.user, authMethods: result.auth_methods, error: null });
    return true;
  } catch (e) {
    setAuthState({
      error: e instanceof Error ? e.message : "Update failed",
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
      setAuthState({ isLoading: false, error: data.detail || "Failed to send email" });
      return false;
    }

    setAuthState({ isLoading: false, error: null });
    return true;
  } catch (e) {
    setAuthState({
      isLoading: false,
      error: e instanceof Error ? e.message : "Failed to send email",
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
      error: e instanceof Error ? e.message : "Verification failed",
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
      setAuthState({ isLoading: false, error: data.detail || "Failed to set password" });
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

    setAuthState({ isLoading: false, error: "Failed to fetch user data" });
    return false;
  } catch (e) {
    setAuthState({
      isLoading: false,
      error: e instanceof Error ? e.message : "Failed to set password",
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
