/**
 * Passkey (WebAuthn) authentication functions.
 *
 * Extracted from auth store — handles passkey registration, login,
 * and conditional UI (autofill) via the WebAuthn API.
 */

import { getAccessToken, getAuthState, setAuthState, storeTokens, fetchCurrentUser } from './auth.svelte';

const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

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
  const authState = getAuthState();
  if (!authState.isAuthenticated) {
    setAuthState({ error: "Must be logged in to register passkey" });
    return false;
  }

  if (!isPasskeySupported()) {
    setAuthState({ error: "Passkeys not supported in this browser" });
    return false;
  }

  const token = getAccessToken();
  if (!token) {
    setAuthState({ error: "No access token" });
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
      setAuthState({ error: data.detail || "Failed to get passkey options" });
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
      setAuthState({ error: "Passkey creation cancelled" });
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
      setAuthState({ error: data.detail || "Passkey registration failed" });
      return false;
    }

    return true;
  } catch (e) {
    setAuthState({
      error: e instanceof Error ? e.message : "Passkey registration failed",
    });
    return false;
  }
}

/**
 * Create a new account with a passkey.
 */
export async function createAccountWithPasskey(): Promise<boolean> {
  if (!isPasskeySupported()) {
    setAuthState({ error: "Passkeys not supported in this browser" });
    return false;
  }

  setAuthState({ isLoading: true, error: null });

  try {
    // Get registration options from server
    const optionsResponse = await fetch(`${API_BASE}/auth/passkey/create/options`, {
      method: "POST",
    });

    if (!optionsResponse.ok) {
      const data = await optionsResponse.json();
      setAuthState({ isLoading: false, error: data.detail || "Failed to get passkey options" });
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
      setAuthState({ isLoading: false, error: "Passkey creation cancelled" });
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
      setAuthState({ isLoading: false, error: data.detail || "Account creation failed" });
      return false;
    }

    const tokens = await verifyResponse.json();
    storeTokens(tokens);

    // Fetch user data
    const result = await fetchCurrentUser();
    if (result) {
      setAuthState({ user: result.user, authMethods: result.auth_methods, isAuthenticated: true, isLoading: false, error: null });
      return true;
    }

    setAuthState({ isLoading: false, error: "Failed to fetch user data" });
    return false;
  } catch (e) {
    setAuthState({
      isLoading: false,
      error: e instanceof Error ? e.message : "Account creation failed",
    });
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
    setAuthState({ isLoading: true, error: null });

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
      setAuthState({ isLoading: false, error: data.detail || "Passkey login failed" });
      return null;
    }

    const tokens = await verifyResponse.json();
    storeTokens(tokens);

    const result = await fetchCurrentUser();
    if (result) {
      setAuthState({ user: result.user, authMethods: result.auth_methods, isAuthenticated: true, isLoading: false, error: null });
      onSuccess();
    } else {
      setAuthState({ isLoading: false, error: "Failed to fetch user data" });
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
    setAuthState({ error: "Passkeys not supported in this browser" });
    return false;
  }

  setAuthState({ isLoading: true, error: null });

  try {
    // Get authentication options from server
    const optionsResponse = await fetch(`${API_BASE}/auth/passkey/login/options`, {
      method: "POST",
    });

    if (!optionsResponse.ok) {
      const data = await optionsResponse.json();
      setAuthState({ isLoading: false, error: data.detail || "Failed to get passkey options" });
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
      setAuthState({ isLoading: false, error: null });
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
      setAuthState({ isLoading: false, error: data.detail || "Passkey login failed" });
      return false;
    }

    const tokens = await verifyResponse.json();
    storeTokens(tokens);

    // Fetch user data
    const result = await fetchCurrentUser();
    if (result) {
      setAuthState({ user: result.user, authMethods: result.auth_methods, isAuthenticated: true, isLoading: false, error: null });
      return true;
    }

    setAuthState({ isLoading: false, error: "Failed to fetch user data" });
    return false;
  } catch {
    setAuthState({ isLoading: false, error: null });
    return false;
  }
}
