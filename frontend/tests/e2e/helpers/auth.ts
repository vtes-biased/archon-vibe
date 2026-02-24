/**
 * Auth helpers for E2E tests — uses real tokens from global setup.
 */
import { expect } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';
import type { Page } from '@playwright/test';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const STATE_FILE = path.join(__dirname, '..', '.e2e-state.json');

export interface E2EState {
  organizer_uid: string;
  organizer_email: string;
  organizer_password: string;
  player_uids: string[];
  player_names: string[];
  access_token: string;
  refresh_token: string;
}

let _cached: E2EState | null = null;

export function getE2EState(): E2EState {
  if (!_cached) {
    _cached = JSON.parse(fs.readFileSync(STATE_FILE, 'utf-8'));
  }
  return _cached!;
}

/**
 * Set real auth tokens in localStorage so the app recognizes the organizer.
 * Must be called after page.goto() (needs a page context for localStorage).
 *
 * Also clears lastSyncTimestamp from IDB so the next page load fetches a
 * fresh snapshot at the full access level (not the stale public-level data).
 */
export async function loginAsOrganizer(page: Page) {
  // Wait for anonymous sync to complete (green dot = IDB stores created + data loaded)
  await expect(
    page.locator('.bg-emerald-500').first(),
  ).toBeVisible({ timeout: 8_000 });

  const state = getE2EState();
  await page.evaluate(
    ({ access, refresh }) => {
      localStorage.setItem('archon_access_token', access);
      localStorage.setItem('archon_refresh_token', refresh);

      // Clear lastSyncTimestamp so the next page load fetches a fresh
      // full-level snapshot instead of doing a catch-up from the old
      // public-level timestamp (which would miss the level change).
      const req = indexedDB.open('archon-db');
      req.onsuccess = () => {
        const db = req.result;
        const tx = db.transaction('metadata', 'readwrite');
        tx.objectStore('metadata').delete('last_sync_timestamp');
        tx.oncomplete = () => db.close();
      };
    },
    { access: state.access_token, refresh: state.refresh_token },
  );
}

/**
 * Register auth tokens via addInitScript so they are available BEFORE
 * page scripts run. This ensures the first sync uses full-level data.
 *
 * Must be called BEFORE the first page.goto(). The sync will fetch the
 * full-level snapshot (~7MB) which takes longer but includes all users.
 *
 * Required for tests that need full-level IDB data (e.g., tournament
 * player search that relies on all users being in IDB).
 */
export async function setupAuthBeforeNavigation(page: Page) {
  const state = getE2EState();
  await page.addInitScript(
    ({ access, refresh }) => {
      localStorage.setItem('archon_access_token', access);
      localStorage.setItem('archon_refresh_token', refresh);
    },
    { access: state.access_token, refresh: state.refresh_token },
  );
}
