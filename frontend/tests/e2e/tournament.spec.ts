import { test, expect, type Page } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';
import { loginAsOrganizer, getE2EState } from './helpers/auth';
import { waitForSync } from './helpers/wait';

/** The action bar's primary CTA — exact match avoids the sticky strip's
 *  duplicate "<action> — <state>" button once the bar scrolls off screen. */
function cta(page: Page, name: string) {
  return page.getByRole('button', { name, exact: true });
}

/** Resolve when the server acknowledges a specific tournament action. */
function actionResponse(page: Page, action: string) {
  return page.waitForResponse(
    (r) => r.url().includes('/action') && r.request().method() === 'POST'
      && (r.request().postData() ?? '').includes(action),
  );
}

/** Score a table via the UI: give the first seat all VPs (a valid oust order)
 *  and wait for the Finished badge. */
async function sweepTable(page: Page, heading: string, vp: number) {
  const card = page
    .locator('div.bg-surface-muted\\/50')
    .filter({ has: page.getByRole('heading', { name: heading, exact: true }) });
  // Prelim tables fold their scores behind "Manage"; the finals table shows
  // them directly. Expand only when the trigger is present.
  const enter = card.getByRole('button', { name: 'Manage' });
  if (await enter.count()) await enter.click();
  // First seat gets all VPs (a sweep is a valid oust order); VP is a button
  // group (VpInput), so this clicks a button, not a <select>.
  await card
    .locator('[role="group"]')
    .first()
    .getByRole('button', { name: String(vp), exact: true })
    .click();
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
  // The upload form defaults to the URL tab; switch to "Paste Deck" for text import.
  await scope.getByRole('button', { name: 'Paste Deck' }).click();
  await scope.getByPlaceholder('Deck name (optional)').fill(name);
  await scope.getByPlaceholder('Paste your deck list here...').fill(DECK_TEXT);
  await scope.getByRole('button', { name: 'Upload Deck' }).click();
  // Upload registered: contents stay hidden pre-round-1, replace is offered
  await expect(scope.getByRole('button', { name: 'Replace' })).toBeVisible({ timeout: 5_000 });
}

test.describe('Tournament lifecycle', () => {
  test.setTimeout(45_000);

  test('create, run rounds, toss, finals, and rank the winner', async ({ page }) => {
    const state = getE2EState();

    await page.goto('/tournaments');
    await loginAsOrganizer(page);
    // Navigate to pick up auth state (SSE reconnects with full-level access)
    await page.goto('/tournaments');
    await waitForSync(page);

    await page.getByText('+ New Tournament').click();
    await expect(page).toHaveURL(/\/tournaments\/new/);

    await page.locator('#name').fill('E2E Test Tournament');
    await page.locator('#start').fill('2099-01-01T10:00');
    await page.locator('#country').selectOption('US');
    await page.getByRole('button', { name: 'Create Tournament' }).click();
    // First optimistic mutation of the run: WASM/IndexedDB cold-start can push
    // the redirect past the 2s warm-path budget under CI load, so allow more.
    await expect(page).toHaveURL(/\/tournaments\/[a-f0-9-]+/, { timeout: 10_000 });

    await expect(page.locator('h1')).toContainText('E2E Test Tournament');
    await expect(page.getByText('Planned').first()).toBeVisible();

    await cta(page, 'Open Registration').click();
    await expect(page.getByRole('button', { name: /Start Check-in/ })).toBeVisible({ timeout: 2_000 });

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

    // exact: true — a substring match also hits a player row whose uuid7 ends in
    // "8" ("…a48 Registered" contains "8 registered" case-insensitively).
    await expect(page.getByText('8 registered', { exact: true })).toBeVisible({ timeout: 2_000 });

    await cta(page, 'Start Check-in').click();
    // Bulk check-in lives in the toolbar's "More" overflow (per-player rows have
    // their own "More" too) — scope to the overflow trigger, the only one with
    // aria-haspopup, to avoid a strict-mode match.
    await page.getByRole('button', { name: 'More' }).and(page.locator('[aria-haspopup="true"]')).click();
    await expect(page.getByRole('button', { name: 'Check All In' })).toBeVisible({ timeout: 2_000 });
    await page.getByRole('button', { name: 'Check All In' }).click();
    await expect(
      cta(page, 'Start Round 1'),
    ).toBeVisible({ timeout: 2_000 });

    // The Players tab renders mobile + desktop variants; scope to the
    // visible desktop table for the upload form.
    const playersDesktop = page
      .locator('div.hidden.sm\\:block')
      .filter({ has: page.locator('table') });
    await page
      .locator('tr')
      .filter({ hasText: state.player_names[0]! })
      .getByTitle('View')
      .click();
    await uploadDeck(playersDesktop, 'E2E Deck v1');
    await playersDesktop.getByRole('button', { name: 'Replace' }).click();
    await uploadDeck(playersDesktop, 'E2E Deck v2');

    for (const round of [1, 2]) {
      // Wait for the server POST so seating is committed before scoring
      const started = actionResponse(page, 'StartRound');
      await cta(page, `Start Round ${round}`).click();
      await started;
      await expect(page.getByText('Playing').first()).toBeVisible({ timeout: 2_000 });

      if (round === 1) {
        // Deck contents are hidden from the organizer until round 1 starts —
        // now the replaced deck's name is revealed on the Players tab
        await page.getByRole('button', { name: 'Players' }).click();
        await page
          .locator('tr')
          .filter({ hasText: state.player_names[0]! })
          .getByTitle('View')
          .click();
        await expect(playersDesktop.getByText('E2E Deck v2')).toBeVisible({ timeout: 5_000 });
      }

      await page.getByRole('button', { name: 'Rounds' }).click();

      if (round === 1) {
        const table1 = page
          .locator('div.bg-surface-muted\\/50')
          .filter({ has: page.getByRole('heading', { name: 'Table 1', exact: true }) });
        const seatRows = table1.locator('.divide-y > div');

        const movedPlayer = (await seatRows.first().locator('span').first().innerText()).trim();
        await seatRows.first().getByTitle('Unseat player').click();
        await expect(seatRows).toHaveCount(3, { timeout: 2_000 });
        await table1.getByRole('button', { name: 'Seat a player' }).click();
        await table1.getByRole('button', { name: movedPlayer }).click();
        await expect(seatRows).toHaveCount(4, { timeout: 2_000 });
        await expect(seatRows.last()).toContainText(movedPlayer);

        // The indicator dot renders from IDB, so its appearance proves the
        // sanction came back over SSE (POST /sanctions is not optimistic).
        await seatRows.first().getByTitle('Sanction').click();
        await page.locator('#ts-description').fill('E2E caution: slow play');
        await page.getByRole('button', { name: 'Issue Sanction' }).click();
        await expect(seatRows.first().getByTitle('Caution (R1)')).toBeVisible({ timeout: 5_000 });
      }

      await sweepTable(page, 'Table 1', 4);
      await sweepTable(page, 'Table 2', 4);

      await cta(page, 'End Round').click();
      await expect(page.getByText(`Round ${round} complete`)).toBeVisible({ timeout: 5_000 });
    }

    await expect(page.getByText(/Resolve top 5 ties/)).toBeVisible({ timeout: 2_000 });
    await page.getByRole('button', { name: 'Players' }).click();
    await page.getByRole('button', { name: 'Random Toss' }).click();
    await expect(page.getByText(/start finals/)).toBeVisible({ timeout: 2_000 });

    // StartFinals auto-switches to the Finals tab.
    await cta(page, 'Start Finals').click();
    await sweepTable(page, 'Finals Table', 5);

    const finished = actionResponse(page, 'FinishFinals');
    await cta(page, 'Finish Finals').click();
    await finished; // server-side finish triggers the ratings recompute + SSE
    await expect(page.getByText('Finished').first()).toBeVisible({ timeout: 2_000 });
    await expect(page.getByText('Tournament complete.')).toBeVisible({ timeout: 2_000 });

    // A final that was played must stay on screen once the tournament is finished:
    // finals qualification answers whether one can *start*, never whether to show one.
    await page.getByRole('button', { name: 'Finals' }).click();
    await expect(page.getByRole('heading', { name: 'Finals Table', exact: true }))
      .toBeVisible({ timeout: 5_000 });

    const winnerBanner = page.locator('.banner-highlight').filter({ hasText: 'Winner' });
    await expect(winnerBanner).toBeVisible({ timeout: 2_000 });
    // Banner shows "Name (vekn_id)" — strip the id to match plain names
    const winnerName = (await winnerBanner.locator('div').nth(1).innerText())
      .replace(/\s*\(\d+\)\s*$/, '')
      .trim();
    expect(state.player_names).toContain(winnerName);

    await page.goto('/rankings');
    await waitForSync(page);
    await expect(page.locator('tbody').getByText(winnerName)).toBeVisible({ timeout: 10_000 });
  });
});
