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

// Call after page.goto(): localStorage needs a page context.
export async function loginAsOrganizer(page: Page) {
  await expect(
    page.locator('[data-sync-state="synced"]').first(),
  ).toBeVisible({ timeout: 8_000 });

  const state = getE2EState();
  await page.evaluate(
    ({ access, refresh }) => {
      localStorage.setItem('archon_access_token', access);
      localStorage.setItem('archon_refresh_token', refresh);

      // Clear lastSyncTimestamp so the next load fetches a fresh full-level
      // snapshot rather than a catch-up from the stale public-level timestamp.
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

// Call before the first page.goto(): the tokens must exist when page scripts
// run, or the first sync lands without full-level data.
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
