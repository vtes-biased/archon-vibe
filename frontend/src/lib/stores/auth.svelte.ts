/**
 * Auth store for managing authentication state.
 *
 * Uses Svelte 5 runes for reactive state management.
 * Persists tokens in localStorage and handles automatic refresh.
 */

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";
import type { User } from "$lib/types";

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
      await refreshTokens();
    }
  }, refreshIn);
}

/**
 * Store tokens in localStorage.
 */
function storeTokens(tokens: TokenResponse) {
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
    authState = {
      user: result.user,
      authMethods: result.auth_methods,
      isAuthenticated: true,
      isLoading: false,
      error: null,
    };
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
      clearTokens();
      authState = { user: null, authMethods: [], isAuthenticated: false, isLoading: false, error: null };
      return false;
    }

    const tokens: TokenResponse = await response.json();
    storeTokens(tokens);
    return true;
  } catch {
    clearTokens();
    authState = { user: null, authMethods: [], isAuthenticated: false, isLoading: false, error: null };
    return false;
  }
}

/**
 * Fetch the current user from the API.
 */
async function fetchCurrentUser(): Promise<MeResponse | null> {
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
  authState = { ...authState, isLoading: true };

  const token = getAccessToken();
  if (!token) {
    authState = { user: null, authMethods: [], isAuthenticated: false, isLoading: false, error: null };
    return;
  }

  // Check if token is expired
  const payload = parseJwt(token);
  if (payload && payload.exp * 1000 < Date.now()) {
    // Token expired, try to refresh
    const refreshed = await refreshTokens();
    if (!refreshed) {
      authState = { user: null, authMethods: [], isAuthenticated: false, isLoading: false, error: null };
      return;
    }
  }

  // Fetch user data
  const result = await fetchCurrentUser();
  if (result) {
    authState = { user: result.user, authMethods: result.auth_methods, isAuthenticated: true, isLoading: false, error: null };

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
    clearTokens();
    authState = { user: null, authMethods: [], isAuthenticated: false, isLoading: false, error: null };
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
  authState = { ...authState, isLoading: true, error: null };

  try {
    const response = await fetch(`${API_BASE}/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password, name }),
    });

    if (!response.ok) {
      const data = await response.json();
      authState = {
        ...authState,
        isLoading: false,
        error: data.detail || "Registration failed",
      };
      return false;
    }

    const tokens: TokenResponse = await response.json();
    storeTokens(tokens);

    // Fetch user data
    const result = await fetchCurrentUser();
    if (result) {
      authState = { user: result.user, authMethods: result.auth_methods, isAuthenticated: true, isLoading: false, error: null };
      return true;
    }

    authState = { ...authState, isLoading: false, error: "Failed to fetch user data" };
    return false;
  } catch (e) {
    authState = {
      ...authState,
      isLoading: false,
      error: e instanceof Error ? e.message : "Registration failed",
    };
    return false;
  }
}

/**
 * Login with email and password.
 */
export async function login(email: string, password: string): Promise<boolean> {
  authState = { ...authState, isLoading: true, error: null };

  try {
    const response = await fetch(`${API_BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });

    if (!response.ok) {
      const data = await response.json();
      authState = {
        ...authState,
        isLoading: false,
        error: data.detail || "Login failed",
      };
      return false;
    }

    const tokens: TokenResponse = await response.json();
    storeTokens(tokens);

    // Fetch user data
    const result = await fetchCurrentUser();
    if (result) {
      authState = { user: result.user, authMethods: result.auth_methods, isAuthenticated: true, isLoading: false, error: null };
      return true;
    }

    authState = { ...authState, isLoading: false, error: "Failed to fetch user data" };
    return false;
  } catch (e) {
    authState = {
      ...authState,
      isLoading: false,
      error: e instanceof Error ? e.message : "Login failed",
    };
    return false;
  }
}

/**
 * Logout the current user.
 */
export function logout(): void {
  clearTokens();
  authState = { user: null, authMethods: [], isAuthenticated: false, isLoading: false, error: null };
}

/**
 * Profile update payload.
 */
export interface ProfileUpdate {
  name?: string;
  nickname?: string;
  country?: string;
  city?: string;
  contact_email?: string;
  contact_phone?: string;
}

/**
 * Update the current user's profile.
 */
export async function updateProfile(data: ProfileUpdate): Promise<boolean> {
  const token = getAccessToken();
  if (!token) {
    authState = { ...authState, error: "Not authenticated" };
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
        authState = { ...authState, error: "Session expired" };
        return false;
      }
      return updateProfile(data);
    }

    if (!response.ok) {
      const errorData = await response.json();
      authState = { ...authState, error: errorData.detail || "Update failed" };
      return false;
    }

    const result: MeResponse = await response.json();
    authState = { ...authState, user: result.user, authMethods: result.auth_methods, error: null };
    return true;
  } catch (e) {
    authState = {
      ...authState,
      error: e instanceof Error ? e.message : "Update failed",
    };
    return false;
  }
}

/**
 * Clear any auth error.
 */
export function clearError(): void {
  authState = { ...authState, error: null };
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
 * Check if WebAuthn/Passkeys are supported in this browser.
 */
export function isPasskeySupported(): boolean {
  return (
    typeof window !== "undefined" &&
    window.PublicKeyCredential !== undefined &&
    typeof window.PublicKeyCredential === "function"
  );
}

/**
 * Register a passkey for the current authenticated user.
 * User must already be logged in.
 */
export async function registerPasskey(): Promise<boolean> {
  if (!authState.isAuthenticated) {
    authState = { ...authState, error: "Must be logged in to register passkey" };
    return false;
  }

  if (!isPasskeySupported()) {
    authState = { ...authState, error: "Passkeys not supported in this browser" };
    return false;
  }

  const token = getAccessToken();
  if (!token) {
    authState = { ...authState, error: "No access token" };
    return false;
  }

  try {
    // Get registration options from server
    const optionsResponse = await fetch(`${API_BASE}/auth/passkey/register/options`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    });

    if (!optionsResponse.ok) {
      const data = await optionsResponse.json();
      authState = { ...authState, error: data.detail || "Failed to get passkey options" };
      return false;
    }

    const options = await optionsResponse.json();

    // Convert base64url to ArrayBuffer for WebAuthn API
    options.challenge = base64urlToBuffer(options.challenge);
    options.user.id = base64urlToBuffer(options.user.id);
    if (options.excludeCredentials) {
      options.excludeCredentials = options.excludeCredentials.map(
        (cred: { id: string; type: string }) => ({
          ...cred,
          id: base64urlToBuffer(cred.id),
        })
      );
    }

    // Create credential
    const credential = (await navigator.credentials.create({
      publicKey: options,
    })) as PublicKeyCredential | null;

    if (!credential) {
      authState = { ...authState, error: "Passkey creation cancelled" };
      return false;
    }

    // Send credential to server for verification
    const attestationResponse = credential.response as AuthenticatorAttestationResponse;
    const credentialData = {
      id: credential.id,
      rawId: bufferToBase64url(credential.rawId),
      type: credential.type,
      response: {
        clientDataJSON: bufferToBase64url(attestationResponse.clientDataJSON),
        attestationObject: bufferToBase64url(attestationResponse.attestationObject),
      },
    };

    const verifyResponse = await fetch(`${API_BASE}/auth/passkey/register/verify`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ credential: credentialData }),
    });

    if (!verifyResponse.ok) {
      const data = await verifyResponse.json();
      authState = { ...authState, error: data.detail || "Passkey registration failed" };
      return false;
    }

    return true;
  } catch (e) {
    authState = {
      ...authState,
      error: e instanceof Error ? e.message : "Passkey registration failed",
    };
    return false;
  }
}

/**
 * Create a new account with a passkey.
 */
export async function createAccountWithPasskey(): Promise<boolean> {
  if (!isPasskeySupported()) {
    authState = { ...authState, error: "Passkeys not supported in this browser" };
    return false;
  }

  authState = { ...authState, isLoading: true, error: null };

  try {
    // Get registration options from server
    const optionsResponse = await fetch(`${API_BASE}/auth/passkey/create/options`, {
      method: "POST",
    });

    if (!optionsResponse.ok) {
      const data = await optionsResponse.json();
      authState = {
        ...authState,
        isLoading: false,
        error: data.detail || "Failed to get passkey options",
      };
      return false;
    }

    const options = await optionsResponse.json();

    // Convert base64url to ArrayBuffer for WebAuthn API
    options.challenge = base64urlToBuffer(options.challenge);
    options.user.id = base64urlToBuffer(options.user.id);

    // Create credential
    const credential = (await navigator.credentials.create({
      publicKey: options,
    })) as PublicKeyCredential | null;

    if (!credential) {
      authState = { ...authState, isLoading: false, error: "Passkey creation cancelled" };
      return false;
    }

    // Send credential to server for verification
    const attestationResponse = credential.response as AuthenticatorAttestationResponse;
    const credentialData = {
      id: credential.id,
      rawId: bufferToBase64url(credential.rawId),
      type: credential.type,
      response: {
        clientDataJSON: bufferToBase64url(attestationResponse.clientDataJSON),
        attestationObject: bufferToBase64url(attestationResponse.attestationObject),
      },
    };

    const verifyResponse = await fetch(`${API_BASE}/auth/passkey/create/verify`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ credential: credentialData }),
    });

    if (!verifyResponse.ok) {
      const data = await verifyResponse.json();
      authState = {
        ...authState,
        isLoading: false,
        error: data.detail || "Account creation failed",
      };
      return false;
    }

    const tokens: TokenResponse = await verifyResponse.json();
    storeTokens(tokens);

    // Fetch user data
    const result = await fetchCurrentUser();
    if (result) {
      authState = { user: result.user, authMethods: result.auth_methods, isAuthenticated: true, isLoading: false, error: null };
      return true;
    }

    authState = { ...authState, isLoading: false, error: "Failed to fetch user data" };
    return false;
  } catch (e) {
    authState = {
      ...authState,
      isLoading: false,
      error: e instanceof Error ? e.message : "Account creation failed",
    };
    return false;
  }
}

/**
 * Check if conditional UI (passkey autofill) is supported.
 */
export async function isConditionalUISupported(): Promise<boolean> {
  if (!isPasskeySupported()) return false;
  try {
    return await PublicKeyCredential.isConditionalMediationAvailable?.() ?? false;
  } catch {
    return false;
  }
}

// Track if conditional UI is active to prevent duplicate calls
let conditionalUIAbortController: AbortController | null = null;

/**
 * Start conditional UI (passkey autofill). Call this on page load.
 * When user selects a passkey from autofill, it authenticates automatically.
 * Returns a cleanup function to abort the conditional UI.
 */
export async function startConditionalUI(
  onSuccess: () => void
): Promise<(() => void) | null> {
  if (!(await isConditionalUISupported())) {
    return null;
  }

  // Abort any existing conditional UI
  conditionalUIAbortController?.abort();
  conditionalUIAbortController = new AbortController();

  try {
    // Get authentication options from server
    const optionsResponse = await fetch(`${API_BASE}/auth/passkey/login/options`, {
      method: "POST",
    });

    if (!optionsResponse.ok) {
      return null;
    }

    const options = await optionsResponse.json();

    // Convert base64url to ArrayBuffer for WebAuthn API
    options.challenge = base64urlToBuffer(options.challenge);
    if (options.allowCredentials) {
      options.allowCredentials = options.allowCredentials.map(
        (cred: { id: string; type: string }) => ({
          ...cred,
          id: base64urlToBuffer(cred.id),
        })
      );
    }

    // Start conditional UI - this waits for user to select from autofill
    const credential = (await navigator.credentials.get({
      publicKey: options,
      mediation: "conditional",
      signal: conditionalUIAbortController.signal,
    })) as PublicKeyCredential | null;

    if (!credential) {
      return null;
    }

    // User selected a passkey - authenticate
    authState = { ...authState, isLoading: true, error: null };

    const assertionResponse = credential.response as AuthenticatorAssertionResponse;
    const credentialData = {
      id: credential.id,
      rawId: bufferToBase64url(credential.rawId),
      type: credential.type,
      response: {
        clientDataJSON: bufferToBase64url(assertionResponse.clientDataJSON),
        authenticatorData: bufferToBase64url(assertionResponse.authenticatorData),
        signature: bufferToBase64url(assertionResponse.signature),
        userHandle: assertionResponse.userHandle
          ? bufferToBase64url(assertionResponse.userHandle)
          : null,
      },
    };

    const verifyResponse = await fetch(`${API_BASE}/auth/passkey/login/verify`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ credential: credentialData }),
    });

    if (!verifyResponse.ok) {
      const data = await verifyResponse.json();
      authState = {
        ...authState,
        isLoading: false,
        error: data.detail || "Passkey login failed",
      };
      return null;
    }

    const tokens: TokenResponse = await verifyResponse.json();
    storeTokens(tokens);

    const result = await fetchCurrentUser();
    if (result) {
      authState = { user: result.user, authMethods: result.auth_methods, isAuthenticated: true, isLoading: false, error: null };
      onSuccess();
    } else {
      authState = { ...authState, isLoading: false, error: "Failed to fetch user data" };
    }

    return null;
  } catch {
    // Aborted or failed - that's fine, user can click button instead
    return null;
  }
}

/**
 * Stop conditional UI if it's running.
 */
export function stopConditionalUI(): void {
  conditionalUIAbortController?.abort();
  conditionalUIAbortController = null;
}

/**
 * Login with a passkey (explicit login, shows browser dialog).
 */
export async function loginWithPasskey(): Promise<boolean> {
  if (!isPasskeySupported()) {
    authState = { ...authState, error: "Passkeys not supported in this browser" };
    return false;
  }

  authState = { ...authState, isLoading: true, error: null };

  try {
    // Get authentication options from server
    const optionsResponse = await fetch(`${API_BASE}/auth/passkey/login/options`, {
      method: "POST",
    });

    if (!optionsResponse.ok) {
      const data = await optionsResponse.json();
      authState = {
        ...authState,
        isLoading: false,
        error: data.detail || "Failed to get passkey options",
      };
      return false;
    }

    const options = await optionsResponse.json();

    // Convert base64url to ArrayBuffer for WebAuthn API
    options.challenge = base64urlToBuffer(options.challenge);
    if (options.allowCredentials) {
      options.allowCredentials = options.allowCredentials.map(
        (cred: { id: string; type: string }) => ({
          ...cred,
          id: base64urlToBuffer(cred.id),
        })
      );
    }

    // Get credential
    const credential = (await navigator.credentials.get({
      publicKey: options,
    })) as PublicKeyCredential | null;

    if (!credential) {
      authState = { ...authState, isLoading: false, error: null };
      return false;
    }

    // Send credential to server for verification
    const assertionResponse = credential.response as AuthenticatorAssertionResponse;
    const credentialData = {
      id: credential.id,
      rawId: bufferToBase64url(credential.rawId),
      type: credential.type,
      response: {
        clientDataJSON: bufferToBase64url(assertionResponse.clientDataJSON),
        authenticatorData: bufferToBase64url(assertionResponse.authenticatorData),
        signature: bufferToBase64url(assertionResponse.signature),
        userHandle: assertionResponse.userHandle
          ? bufferToBase64url(assertionResponse.userHandle)
          : null,
      },
    };

    const verifyResponse = await fetch(`${API_BASE}/auth/passkey/login/verify`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ credential: credentialData }),
    });

    if (!verifyResponse.ok) {
      const data = await verifyResponse.json();
      authState = {
        ...authState,
        isLoading: false,
        error: data.detail || "Passkey login failed",
      };
      return false;
    }

    const tokens: TokenResponse = await verifyResponse.json();
    storeTokens(tokens);

    // Fetch user data
    const result = await fetchCurrentUser();
    if (result) {
      authState = { user: result.user, authMethods: result.auth_methods, isAuthenticated: true, isLoading: false, error: null };
      return true;
    }

    authState = { ...authState, isLoading: false, error: "Failed to fetch user data" };
    return false;
  } catch {
    authState = { ...authState, isLoading: false, error: null };
    return false;
  }
}

/**
 * Request a magic link email for signup or password reset.
 * @param email User's email address
 * @param purpose "signup" for new accounts, "reset" for password reset
 */
export async function requestMagicLink(
  email: string,
  purpose: "signup" | "reset" = "signup"
): Promise<boolean> {
  authState = { ...authState, isLoading: true, error: null };

  try {
    const response = await fetch(`${API_BASE}/auth/email/request`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, purpose }),
    });

    if (!response.ok) {
      const data = await response.json();
      authState = {
        ...authState,
        isLoading: false,
        error: data.detail || "Failed to send email",
      };
      return false;
    }

    authState = { ...authState, isLoading: false, error: null };
    return true;
  } catch (e) {
    authState = {
      ...authState,
      isLoading: false,
      error: e instanceof Error ? e.message : "Failed to send email",
    };
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
  authState = { ...authState, isLoading: true, error: null };

  try {
    const response = await fetch(`${API_BASE}/auth/email/verify`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    });

    if (!response.ok) {
      const data = await response.json();
      authState = {
        ...authState,
        isLoading: false,
        error: data.detail || "Invalid or expired link",
      };
      return null;
    }

    const data = await response.json();
    authState = { ...authState, isLoading: false, error: null };

    return {
      setPasswordToken: data.set_password_token,
      email: data.email,
      purpose: data.purpose,
    };
  } catch (e) {
    authState = {
      ...authState,
      isLoading: false,
      error: e instanceof Error ? e.message : "Verification failed",
    };
    return null;
  }
}

/**
 * Set password after magic link verification.
 * Creates user/auth if signup, updates password if reset.
 * Returns true on success and logs in the user.
 */
export async function setPassword(token: string, password: string): Promise<boolean> {
  authState = { ...authState, isLoading: true, error: null };

  try {
    const response = await fetch(`${API_BASE}/auth/email/set-password`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token, password }),
    });

    if (!response.ok) {
      const data = await response.json();
      authState = {
        ...authState,
        isLoading: false,
        error: data.detail || "Failed to set password",
      };
      return false;
    }

    const tokens: TokenResponse = await response.json();
    storeTokens(tokens);

    // Fetch user data
    const result = await fetchCurrentUser();
    if (result) {
      authState = {
        user: result.user,
        authMethods: result.auth_methods,
        isAuthenticated: true,
        isLoading: false,
        error: null,
      };
      return true;
    }

    authState = { ...authState, isLoading: false, error: "Failed to fetch user data" };
    return false;
  } catch (e) {
    authState = {
      ...authState,
      isLoading: false,
      error: e instanceof Error ? e.message : "Failed to set password",
    };
    return false;
  }
}

// Helper functions for base64url encoding/decoding
function base64urlToBuffer(base64url: string): ArrayBuffer {
  const padding = "=".repeat((4 - (base64url.length % 4)) % 4);
  const base64 = base64url.replace(/-/g, "+").replace(/_/g, "/") + padding;
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes.buffer;
}

function bufferToBase64url(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i]!);
  }
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=/g, "");
}
