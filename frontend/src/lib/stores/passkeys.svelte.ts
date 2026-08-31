import * as m from '$lib/paraglide/messages.js';
import { toUserMessage } from '$lib/errors';
import { authorizedFetch, getAuthState, setAuthState, storeTokens, fetchCurrentUser } from './auth.svelte';

const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

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

export function isPasskeySupported(): boolean {
  return (
    typeof window !== "undefined" &&
    window.PublicKeyCredential !== undefined &&
    typeof window.PublicKeyCredential === "function"
  );
}

export async function registerPasskey(): Promise<boolean> {
  const authState = getAuthState();
  if (!authState.isAuthenticated) {
    setAuthState({ error: m.passkey_error_must_login() });
    return false;
  }

  if (!isPasskeySupported()) {
    setAuthState({ error: m.passkey_error_not_supported() });
    return false;
  }

  try {
    const optionsResponse = await authorizedFetch(`${API_BASE}/auth/passkey/register/options`, {
      method: "POST",
    });

    if (!optionsResponse.ok) {
      const data = await optionsResponse.json();
      setAuthState({ error: data.detail || m.passkey_error_options() });
      return false;
    }

    const options = await optionsResponse.json();

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

    const credential = (await navigator.credentials.create({
      publicKey: options,
    })) as PublicKeyCredential | null;

    if (!credential) {
      setAuthState({ error: m.passkey_error_cancelled() });
      return false;
    }

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

    const verifyResponse = await authorizedFetch(`${API_BASE}/auth/passkey/register/verify`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ credential: credentialData }),
    });

    if (!verifyResponse.ok) {
      const data = await verifyResponse.json();
      setAuthState({ error: data.detail || m.passkey_error_registration() });
      return false;
    }

    return true;
  } catch (e) {
    setAuthState({
      error: toUserMessage(e, m.passkey_error_registration()),
    });
    return false;
  }
}

export async function createAccountWithPasskey(): Promise<boolean> {
  if (!isPasskeySupported()) {
    setAuthState({ error: m.passkey_error_not_supported() });
    return false;
  }

  setAuthState({ isLoading: true, error: null });

  try {
    const optionsResponse = await fetch(`${API_BASE}/auth/passkey/create/options`, {
      method: "POST",
    });

    if (!optionsResponse.ok) {
      const data = await optionsResponse.json();
      setAuthState({ isLoading: false, error: data.detail || m.passkey_error_options() });
      return false;
    }

    const options = await optionsResponse.json();

    options.challenge = base64urlToBuffer(options.challenge);
    options.user.id = base64urlToBuffer(options.user.id);

    const credential = (await navigator.credentials.create({
      publicKey: options,
    })) as PublicKeyCredential | null;

    if (!credential) {
      setAuthState({ isLoading: false, error: m.passkey_error_cancelled() });
      return false;
    }

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
      setAuthState({ isLoading: false, error: data.detail || m.passkey_error_account_creation() });
      return false;
    }

    const tokens = await verifyResponse.json();
    storeTokens(tokens);

    const result = await fetchCurrentUser();
    if (result) {
      setAuthState({ user: result.user, authMethods: result.auth_methods, isAuthenticated: true, isLoading: false, error: null });
      return true;
    }

    setAuthState({ isLoading: false, error: m.auth_error_fetch_user() });
    return false;
  } catch (e) {
    setAuthState({
      isLoading: false,
      error: toUserMessage(e, m.passkey_error_account_creation()),
    });
    return false;
  }
}

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

export async function startConditionalUI(
  onSuccess: () => void
): Promise<(() => void) | null> {
  if (!(await isConditionalUISupported())) {
    return null;
  }

  conditionalUIAbortController?.abort();
  conditionalUIAbortController = new AbortController();

  try {
    const optionsResponse = await fetch(`${API_BASE}/auth/passkey/login/options`, {
      method: "POST",
    });

    if (!optionsResponse.ok) {
      return null;
    }

    const options = await optionsResponse.json();

    options.challenge = base64urlToBuffer(options.challenge);
    if (options.allowCredentials) {
      options.allowCredentials = options.allowCredentials.map(
        (cred: { id: string; type: string }) => ({
          ...cred,
          id: base64urlToBuffer(cred.id),
        })
      );
    }

    const credential = (await navigator.credentials.get({
      publicKey: options,
      mediation: "conditional",
      signal: conditionalUIAbortController.signal,
    })) as PublicKeyCredential | null;

    if (!credential) {
      return null;
    }

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
      setAuthState({ isLoading: false, error: data.detail || m.passkey_error_login() });
      return null;
    }

    const tokens = await verifyResponse.json();
    storeTokens(tokens);

    const result = await fetchCurrentUser();
    if (result) {
      setAuthState({ user: result.user, authMethods: result.auth_methods, isAuthenticated: true, isLoading: false, error: null });
      onSuccess();
    } else {
      setAuthState({ isLoading: false, error: m.auth_error_fetch_user() });
    }

    return null;
  } catch {
    // Aborted or failed - that's fine, user can click button instead
    return null;
  }
}

export function stopConditionalUI(): void {
  conditionalUIAbortController?.abort();
  conditionalUIAbortController = null;
}

export async function loginWithPasskey(): Promise<boolean> {
  if (!isPasskeySupported()) {
    setAuthState({ error: m.passkey_error_not_supported() });
    return false;
  }

  setAuthState({ isLoading: true, error: null });

  try {
    const optionsResponse = await fetch(`${API_BASE}/auth/passkey/login/options`, {
      method: "POST",
    });

    if (!optionsResponse.ok) {
      const data = await optionsResponse.json();
      setAuthState({ isLoading: false, error: data.detail || m.passkey_error_options() });
      return false;
    }

    const options = await optionsResponse.json();

    options.challenge = base64urlToBuffer(options.challenge);
    if (options.allowCredentials) {
      options.allowCredentials = options.allowCredentials.map(
        (cred: { id: string; type: string }) => ({
          ...cred,
          id: base64urlToBuffer(cred.id),
        })
      );
    }

    const credential = (await navigator.credentials.get({
      publicKey: options,
    })) as PublicKeyCredential | null;

    if (!credential) {
      setAuthState({ isLoading: false, error: null });
      return false;
    }

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
      setAuthState({ isLoading: false, error: data.detail || m.passkey_error_login() });
      return false;
    }

    const tokens = await verifyResponse.json();
    storeTokens(tokens);

    const result = await fetchCurrentUser();
    if (result) {
      setAuthState({ user: result.user, authMethods: result.auth_methods, isAuthenticated: true, isLoading: false, error: null });
      return true;
    }

    setAuthState({ isLoading: false, error: m.auth_error_fetch_user() });
    return false;
  } catch {
    setAuthState({ isLoading: false, error: null });
    return false;
  }
}
