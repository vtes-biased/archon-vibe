// Reactive navigator.onLine — one shared listener instead of per-page copies.
// Distinct from stores/offline.svelte.ts (tournament offline-mode device lock).
let online = $state(typeof navigator !== "undefined" ? navigator.onLine : true);

if (typeof window !== "undefined") {
  window.addEventListener("online", () => (online = true));
  window.addEventListener("offline", () => (online = false));
}

export function isBrowserOnline(): boolean {
  return online;
}
