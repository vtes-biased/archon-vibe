import { test, expect } from '@playwright/test';
import { setupAuthBeforeNavigation } from './helpers/auth';
import { waitForSync } from './helpers/wait';

/**
 * League lifecycle: an IC creates a league through the form and it shows up
 * on the detail page and in the list. Reads come from IndexedDB
 * (offline-first); creation is a real API call.
 */
test.describe('League lifecycle', () => {
  test('create a league, see it on detail and list pages', async ({ page }) => {
    await setupAuthBeforeNavigation(page);
    await page.goto('/leagues/new');
    await waitForSync(page);

    // The form only renders for IC/NC roles (auth state loads async)
    await expect(page.locator('#name')).toBeVisible({ timeout: 5_000 });
    await page.locator('#name').fill('E2E Test League');
    await page.locator('#start').fill('2026-01-01');
    await page.getByRole('button', { name: 'Create League' }).click();

    // createLeague is a real API call; redirect happens on success
    await expect(page).toHaveURL(/\/leagues\/[a-f0-9-]+/, { timeout: 5_000 });
    await expect(page.locator('h1')).toContainText('E2E Test League');
    await expect(page.getByText('No tournaments in this league yet.')).toBeVisible();
    await expect(page.getByText('Standings will appear when tournaments finish.')).toBeVisible();

    // List page shows it (no finish date → active, the default filter).
    // Match by role: the name also appears in a CSS-hidden responsive variant.
    await page.goto('/leagues');
    await waitForSync(page);
    await expect(
      page.getByRole('link', { name: /E2E Test League/ }).first(),
    ).toBeVisible({ timeout: 5_000 });
  });
});
