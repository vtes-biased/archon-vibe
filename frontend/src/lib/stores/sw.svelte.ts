/**
 * Service worker registration and update management.
 */
import { dev } from '$app/environment';
import { getOfflineTournamentUids } from '$lib/stores/offline.svelte';

let updateAvailable = $state(false);
let waitingWorker: ServiceWorker | null = null;

// Guards the auto-apply path against a reload loop: if the new worker somehow never
// becomes the controller, we'd otherwise reload on every boot forever.
const AUTO_APPLIED_KEY = 'sw_auto_applied';

export function getUpdateAvailable(): boolean {
  return updateAvailable;
}

export function applyUpdate(): void {
  if (waitingWorker) {
    waitingWorker.postMessage({ type: 'SKIP_WAITING' });
    // Reload once the new SW takes over
    navigator.serviceWorker.addEventListener('controllerchange', () => {
      window.location.reload();
    });
  }
}

/**
 * A worker left `waiting` from a previous visit is applied immediately rather than
 * parked behind the update banner. The bundle in that waiting worker may be the only
 * one that can read the current server's snapshot format, and a client running stale
 * JS can't tell a format it doesn't understand from a broken server — it just retries
 * forever with an empty IndexedDB after a resync. Taking the update at boot, when the
 * user has no work in flight, closes that window.
 *
 * Deliberately NOT applied while a tournament is locked offline: the same invariant
 * the banner already respects (+layout hides it when `hasOfflineLocked`). Never reload
 * out from under an organizer mid-event; they take the update when they go online.
 */
function autoApplyOnBoot(registration: ServiceWorkerRegistration): boolean {
  if (!registration.waiting) return false;
  if (getOfflineTournamentUids().size > 0) return false;
  if (sessionStorage.getItem(AUTO_APPLIED_KEY)) return false;
  sessionStorage.setItem(AUTO_APPLIED_KEY, '1');
  waitingWorker = registration.waiting;
  applyUpdate();
  return true;
}

export function initServiceWorker(): void {
  if (!('serviceWorker' in navigator)) return;

  navigator.serviceWorker
    .register('/service-worker.js', { type: dev ? 'module' : 'classic' })
    .then((registration) => {
      // Detect waiting worker from previous visit
      if (registration.waiting) {
        if (autoApplyOnBoot(registration)) return;
        waitingWorker = registration.waiting;
        updateAvailable = true;
      }

      // Detect new updates
      registration.addEventListener('updatefound', () => {
        const installing = registration.installing;
        if (!installing) return;

        installing.addEventListener('statechange', () => {
          if (installing.state === 'installed' && navigator.serviceWorker.controller) {
            // New SW installed while old one is still active = update available
            waitingWorker = installing;
            updateAvailable = true;
          }
        });
      });

      // Check for updates periodically (every hour)
      setInterval(() => {
        registration.update();
      }, 60 * 60 * 1000);
    })
    .catch((err) => {
      console.error('Service worker registration failed:', err);
    });
}
