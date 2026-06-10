import { test, expect, type Page } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';
import { loginAsOrganizer, getE2EState } from './helpers/auth';
import { waitForSync } from './helpers/wait';

/**
 * Full nominal tournament arc, all through the real UI (no API shortcuts):
 * create → register 8 players → check-in → 2 rounds scored via the VP
 * dropdowns → random toss (sweep scoring guarantees ties at the finals
 * cutoff) → finals → winner banner → rating points visible on /rankings.
 *
 * Mutations are optimistic (WASM) but server POSTs are serialized per
 * tournament, so chaining UI steps is ordering-safe; we only await the
 * server response where the next step depends on a server-side effect.
 */

/** Resolve when the server acknowledges a specific tournament action. */
function actionResponse(page: Page, action: string) {
  return page.waitForResponse(
    (r) => r.url().includes('/action') && r.request().method() === 'POST'
      && (r.request().postData() ?? '').includes(action),
  );
}

/**
 * Score a table through the UI: give the first seat all VPs (a sweep is a
 * valid oust order) and wait for the table badge to flip to Finished.
 */
async function sweepTable(page: Page, heading: string, vp: number) {
  const card = page
    .locator('div.bg-ash-900\\/50')
    .filter({ has: page.getByRole('heading', { name: heading, exact: true }) });
  await card.locator('select').first().selectOption(String(vp));
  await expect(card.getByText('Finished', { exact: true })).toBeVisible({ timeout: 5_000 });
}

// A real tournament-legal deck (Fifth Edition Tremere preconstructed) in the
// classic text export format — crypt tails, section headers, accented names.
const DECK_TEXT = fs.readFileSync(
  path.join(path.dirname(fileURLToPath(import.meta.url)), 'fixtures', 'tremere-precon.txt'),
  'utf-8',
);

/** Paste a decklist in the (visible, desktop) upload form and submit. */
async function uploadDeck(scope: ReturnType<Page['locator']>, name: string) {
  await scope.getByPlaceholder('Deck name (optional)').fill(name);
  await scope.getByPlaceholder('Paste your deck list here...').fill(DECK_TEXT);
  await scope.getByRole('button', { name: 'Upload Deck' }).click();
  // Upload registered: contents stay hidden pre-round-1, replace is offered
  await expect(scope.getByRole('button', { name: 'Replace deck' })).toBeVisible({ timeout: 5_000 });
}

test.describe('Tournament lifecycle', () => {
  test.setTimeout(45_000);

  test('create, run rounds, toss, finals, and rank the winner', async ({ page }) => {
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
    await page.locator('#start').fill('2099-01-01T10:00');
    await page.locator('#country').selectOption('US');
    await page.getByRole('button', { name: 'Create Tournament' }).click();
    await expect(page).toHaveURL(/\/tournaments\/[a-f0-9-]+/, { timeout: 2_000 });

    await expect(page.locator('h1')).toContainText('E2E Test Tournament');
    await expect(page.getByText('Planned').first()).toBeVisible();

    // ── Step 3: Open Registration (optimistic) ──
    await page.getByRole('button', { name: 'Open Registration' }).click();
    await expect(page.getByRole('button', { name: /Start Check-in/ })).toBeVisible({ timeout: 2_000 });

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
    await page.getByRole('button', { name: 'Start Check-in' }).click();
    await expect(page.getByRole('button', { name: 'Check All In' })).toBeVisible({ timeout: 2_000 });
    await page.getByRole('button', { name: 'Check All In' }).click();
    await expect(
      page.getByRole('button', { name: 'Start Round 1' }),
    ).toBeVisible({ timeout: 2_000 });

    // ── Step 5b: Organizer enters a player's decklist, then replaces it ──
    // The Players tab renders mobile + desktop variants; scope to the
    // visible desktop table for the upload form.
    const playersDesktop = page
      .locator('div.hidden.sm\\:block')
      .filter({ has: page.locator('table') });
    await page
      .locator('tr')
      .filter({ hasText: state.player_names[0]! })
      .getByTitle('View deck')
      .click();
    await uploadDeck(playersDesktop, 'E2E Deck v1');
    await playersDesktop.getByRole('button', { name: 'Replace deck' }).click();
    await uploadDeck(playersDesktop, 'E2E Deck v2');

    // ── Steps 6-7: Rounds 1 and 2, scored through the Rounds tab UI ──
    for (const round of [1, 2]) {
      // Wait for the server POST so seating is committed before scoring
      const started = actionResponse(page, 'StartRound');
      await page.getByRole('button', { name: `Start Round ${round}` }).click();
      await started;
      await expect(page.getByText('Playing').first()).toBeVisible({ timeout: 2_000 });

      if (round === 1) {
        // Deck contents are hidden from the organizer until round 1 starts —
        // now the replaced deck's name is revealed on the Players tab
        await page.getByRole('button', { name: 'Players' }).click();
        await page
          .locator('tr')
          .filter({ hasText: state.player_names[0]! })
          .getByTitle('View deck')
          .click();
        await expect(playersDesktop.getByText('E2E Deck v2')).toBeVisible({ timeout: 5_000 });
      }

      await page.getByRole('button', { name: 'Rounds' }).click();

      if (round === 1) {
        const table1 = page
          .locator('div.bg-ash-900\\/50')
          .filter({ has: page.getByRole('heading', { name: 'Table 1', exact: true }) });
        const seatRows = table1.locator('.divide-y > div');

        // ── Seating modification: unseat the first seat, re-seat them last ──
        const movedPlayer = (await seatRows.first().locator('span').first().innerText()).trim();
        await seatRows.first().getByTitle('Unseat player').click();
        await expect(seatRows).toHaveCount(3, { timeout: 2_000 });
        await table1.getByRole('button', { name: 'Seat a player' }).click();
        await table1.getByRole('button', { name: movedPlayer }).click();
        await expect(seatRows).toHaveCount(4, { timeout: 2_000 });
        await expect(seatRows.last()).toContainText(movedPlayer);

        // ── In-event sanction: caution the (new) first seat ──
        // The indicator dot renders from IDB, so its appearance proves the
        // sanction came back over SSE (POST /sanctions is not optimistic).
        await seatRows.first().getByTitle('Issue Tournament Sanction').click();
        await page.locator('#ts-description').fill('E2E caution: slow play');
        await page.getByRole('button', { name: 'Issue Sanction' }).click();
        await expect(seatRows.first().getByTitle('Caution (R1)')).toBeVisible({ timeout: 5_000 });
      }

      await sweepTable(page, 'Table 1', 4);
      await sweepTable(page, 'Table 2', 4);

      await page.getByRole('button', { name: 'End Round' }).click();
      await expect(page.getByText(`Round ${round} complete`)).toBeVisible({ timeout: 5_000 });
    }

    // ── Step 8: Random toss resolves the guaranteed cutoff ties ──
    await expect(page.getByText(/Resolve top 5 ties/)).toBeVisible({ timeout: 2_000 });
    await page.getByRole('button', { name: 'Players' }).click();
    await page.getByRole('button', { name: 'Random Toss' }).click();
    await expect(page.getByText(/start finals/)).toBeVisible({ timeout: 2_000 });

    // ── Step 9: Finals (StartFinals auto-switches to the Finals tab) ──
    await page.getByRole('button', { name: 'Start Finals' }).click();
    await sweepTable(page, 'Finals Table', 5);

    const finished = actionResponse(page, 'FinishFinals');
    await page.getByRole('button', { name: 'Finish Finals' }).click();
    await finished; // server-side finish triggers the ratings recompute + SSE
    await expect(page.getByText('Finished').first()).toBeVisible({ timeout: 2_000 });
    await expect(page.getByText('Tournament complete.')).toBeVisible({ timeout: 2_000 });

    // ── Step 10: Winner banner on Overview ──
    await page.getByRole('button', { name: 'Overview' }).click();
    const winnerBanner = page.locator('.banner-emerald').filter({ hasText: 'Winner' });
    await expect(winnerBanner).toBeVisible({ timeout: 2_000 });
    // Banner shows "Name (vekn_id)" — strip the id to match plain names
    const winnerName = (await winnerBanner.locator('div').nth(1).innerText())
      .replace(/\s*\(\d+\)\s*$/, '')
      .trim();
    expect(state.player_names).toContain(winnerName);

    // ── Step 11: Rating points landed — winner appears on /rankings ──
    await page.goto('/rankings');
    await waitForSync(page);
    await expect(page.locator('tbody').getByText(winnerName)).toBeVisible({ timeout: 10_000 });
  });
});
