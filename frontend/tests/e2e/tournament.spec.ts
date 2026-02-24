import { test, expect, type Page } from '@playwright/test';
import { loginAsOrganizer, getE2EState } from './helpers/auth';
import { waitForSync } from './helpers/wait';

const API_URL = process.env.VITE_API_URL || 'http://localhost:8000';

/**
 * Score all tables via API, then end the round via API.
 * Reads seating from IDB (WASM optimistic update — deterministic since
 * StartRound now forwards computed seating to the server).
 */
async function scoreAndEndRound(page: Page, tournamentUid: string, roundIndex: number) {
  await page.evaluate(
    async ({ uid, round, apiUrl }) => {
      const token = localStorage.getItem('archon_access_token');

      // Read round tables from IDB (written by WASM optimistic update)
      const db = await new Promise<IDBDatabase>((resolve, reject) => {
        const req = indexedDB.open('archon-db');
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error);
      });
      let tables: any;
      for (let attempt = 0; attempt < 20; attempt++) {
        const tournament = await new Promise<any>((resolve, reject) => {
          const tx = db.transaction('tournaments', 'readonly');
          const req = tx.objectStore('tournaments').get(uid);
          req.onsuccess = () => resolve(req.result);
          req.onerror = () => reject(req.error);
        });
        if (tournament?.rounds?.[round]) {
          tables = tournament.rounds[round];
          break;
        }
        await new Promise((r) => setTimeout(r, 500));
      }
      db.close();
      if (!tables) throw new Error(`Round ${round} not found in IDB after 10s polling`);

      // Score all tables — first player gets all VPs (valid oust-order)
      for (let t = 0; t < tables.length; t++) {
        const table = tables[t];
        const scores = table.seating.map((s: any, i: number) => ({
          player_uid: s.player_uid,
          vp: i === 0 ? table.seating.length : 0,
        }));
        const res = await fetch(`${apiUrl}/api/tournaments/${uid}/action`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ type: 'SetScore', round, table: t, scores }),
        });
        if (!res.ok) {
          const body = await res.text();
          throw new Error(`SetScore table ${t} failed: ${res.status} ${body}`);
        }
      }

      // Finish the round via API
      const endRes = await fetch(`${apiUrl}/api/tournaments/${uid}/action`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ type: 'FinishRound' }),
      });
      if (!endRes.ok) {
        const body = await endRes.text();
        throw new Error(`FinishRound failed: ${endRes.status} ${body}`);
      }
    },
    { uid: tournamentUid, round: roundIndex, apiUrl: API_URL },
  );
}

test.describe('Tournament lifecycle', () => {
  test.setTimeout(30_000);

  test('create, run rounds, and finish tournament', async ({ page }) => {
    const state = getE2EState();

    // ── Setup: navigate, wait for sync, then set auth tokens ──
    await page.goto('/tournaments');
    await loginAsOrganizer(page);
    // Navigate to pick up auth state (SSE reconnects with full-level access)
    await page.goto('/tournaments');
    await waitForSync(page);

    // ── Step 1: Navigate to new tournament page ──
    await page.getByText('+ New Tournament').click();
    await expect(page).toHaveURL(/\/tournaments\/new/);

    // ── Step 2: Create tournament (optimistic: redirect is instant) ──
    await page.locator('#name').fill('E2E Test Tournament');
    await page.locator('#country').selectOption('US');
    await page.getByRole('button', { name: 'Create Tournament' }).click();
    await expect(page).toHaveURL(/\/tournaments\/[a-f0-9-]+/, { timeout: 2_000 });
    const tournamentUid = page.url().split('/tournaments/')[1]!;

    await expect(page.locator('h1')).toContainText('E2E Test Tournament');
    await expect(page.getByText('Planned').first()).toBeVisible();

    // ── Step 3: Open Registration (optimistic) ──
    await page.getByRole('button', { name: 'Open Registration' }).click();
    await expect(page.getByRole('button', { name: /Close Registration/ })).toBeVisible({ timeout: 2_000 });

    // ── Step 4: Add Players via VEKN ID search ──
    await page.getByRole('button', { name: 'Players' }).click();

    for (let i = 0; i < 8; i++) {
      const name = state.player_names[i]!;
      const veknId = `999${String(i + 10).padStart(4, '0')}`;
      const searchInput = page.locator('#player-search-input');
      await searchInput.fill(veknId);
      await expect(
        page.locator('button').filter({ hasText: name }),
      ).toBeVisible({ timeout: 2_000 });
      await page.locator('button').filter({ hasText: name }).click();
      await expect(searchInput).toHaveValue('');
    }

    await expect(page.getByText('8 registered')).toBeVisible({ timeout: 2_000 });

    // ── Step 5: Close Registration & Check In All (optimistic) ──
    await page.getByRole('button', { name: 'Close Registration' }).click();
    await expect(page.getByRole('button', { name: 'Check All In' })).toBeVisible({ timeout: 2_000 });
    await page.getByRole('button', { name: 'Check All In' }).click();
    await expect(
      page.getByRole('button', { name: 'Start Round 1' }),
    ).toBeVisible({ timeout: 2_000 });

    // ── Step 6: Round 1 (optimistic: tables appear instantly) ──
    // Wait for the server POST so seating is committed before we score via API
    const sr1Promise = page.waitForResponse(
      (r) => r.url().includes('/action') && r.request().method() === 'POST'
        && (r.request().postData() ?? '').includes('StartRound'),
    );
    await page.getByRole('button', { name: 'Start Round 1' }).click();
    await sr1Promise;
    await expect(page.getByText('Playing').first()).toBeVisible({ timeout: 2_000 });

    await page.getByRole('button', { name: 'Rounds' }).click();
    await expect(page.getByText('Table 1')).toBeVisible({ timeout: 2_000 });
    await expect(page.getByText('Table 2')).toBeVisible();

    // Score round 1 via API and end it
    await scoreAndEndRound(page, tournamentUid, 0);

    await expect(
      page.getByRole('button', { name: 'Start Round 2' }),
    ).toBeVisible({ timeout: 5_000 });

    // ── Step 7: Round 2 ──
    const sr2Promise = page.waitForResponse(
      (r) => r.url().includes('/action') && r.request().method() === 'POST'
        && (r.request().postData() ?? '').includes('StartRound'),
    );
    await page.getByRole('button', { name: 'Start Round 2' }).click();
    await sr2Promise;
    await expect(page.getByText('Playing').first()).toBeVisible({ timeout: 2_000 });

    // Score round 2 via API and end it
    await scoreAndEndRound(page, tournamentUid, 1);

    await expect(
      page.getByRole('button', { name: 'Start Round 3' }),
    ).toBeVisible({ timeout: 5_000 });

    // ── Step 8: Finish Tournament (optimistic) ──
    await page.getByRole('button', { name: 'Finish Tournament' }).click();
    await expect(page.getByText('Finished').first()).toBeVisible({ timeout: 2_000 });
    await expect(page.getByText('Tournament complete.')).toBeVisible({ timeout: 2_000 });
  });
});
