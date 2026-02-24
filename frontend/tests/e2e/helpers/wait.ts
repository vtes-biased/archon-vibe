/**
 * Sync wait helpers for E2E tests.
 *
 * The test DB only contains ~10 mock users (VEKN sync disabled for E2E),
 * so the SSE sync should complete in well under 5s.
 */
import { expect, type Page } from '@playwright/test';

const DEFAULT_SYNC_TIMEOUT = 8_000;

/**
 * Wait for SSE sync to complete (emerald dot in sidebar).
 */
export async function waitForSync(page: Page, timeout = DEFAULT_SYNC_TIMEOUT) {
  await expect(
    page.locator('.bg-emerald-500').first(),
  ).toBeVisible({ timeout });
}

/**
 * Wait for users to load in the users list.
 */
export async function waitForUsers(page: Page) {
  await waitForSync(page);
  await expect(
    page.locator('.user-row').first(),
  ).toBeVisible({ timeout: 3_000 });
}
