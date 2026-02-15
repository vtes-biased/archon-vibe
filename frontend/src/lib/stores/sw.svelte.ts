/**
 * Service worker registration and update management.
 */
import { dev } from '$app/environment';

let updateAvailable = $state(false);
let waitingWorker: ServiceWorker | null = null;

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

export function initServiceWorker(): void {
  if (!('serviceWorker' in navigator)) return;

  navigator.serviceWorker
    .register('/service-worker.js', { type: dev ? 'module' : 'classic' })
    .then((registration) => {
      // Detect waiting worker from previous visit
      if (registration.waiting) {
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
