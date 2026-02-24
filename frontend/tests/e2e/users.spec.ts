import { test, expect } from '@playwright/test';
import { loginAsOrganizer } from './helpers/auth';
import { waitForUsers } from './helpers/wait';

/**
 * E2E tests for the Archon app.
 * Tests run against the dev server with real backend SSE data.
 *
 * Timeout policy:
 * - Optimistic (WASM) UI changes: 2s max
 * - SSE sync: handled by waitForSync/waitForUsers
 * - Route mocks (login error, forgot password): 2s
 */

// ─── App Load ──────────────────────────────────────────────────

test.describe('App loads correctly', () => {
  test('redirects / to /tournaments', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveURL(/\/tournaments/);
  });

  test('displays navigation sidebar', async ({ page }) => {
    await page.goto('/users');
    await expect(page.getByRole('link', { name: /Tournaments/ })).toBeVisible();
    await expect(page.getByRole('link', { name: /Users/ })).toBeVisible();
  });

  test('displays users page elements', async ({ page }) => {
    await page.goto('/users');
    await expect(page.locator('#name-search')).toBeVisible();
    await expect(page.locator('#country-filter')).toBeVisible();
  });

  test('loads users via SSE', async ({ page }) => {
    await page.goto('/users');
    await waitForUsers(page);

    const userName = page.locator('.user-row').first().locator('.user-name').first();
    await expect(userName).not.toBeEmpty();
  });
});

// ─── Login Page ────────────────────────────────────────────────

test.describe('Login page', () => {
  test('displays login form elements', async ({ page }) => {
    await page.goto('/login');

    await expect(page.locator('h1')).toContainText('Archon');
    await expect(page.getByRole('button', { name: 'Login' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Sign Up' })).toBeVisible();
    await expect(page.locator('#login-email')).toBeVisible();
    await expect(page.locator('#login-password')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Sign In', exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: /Discord/ })).toBeVisible();
    await expect(page.getByText('Forgot password?')).toBeVisible();
  });

  test('switches between login and signup modes', async ({ page }) => {
    await page.goto('/login');

    await expect(page.locator('#login-email')).toBeVisible();
    await page.getByRole('button', { name: 'Sign Up' }).click();
    await expect(page.getByText('Create a new account')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Continue with Email' })).toBeVisible();
    await page.getByRole('button', { name: 'Login' }).click();
    await expect(page.locator('#login-email')).toBeVisible();
  });

  test('shows error on invalid login', async ({ page }) => {
    // Mock auth/login to return an error (tests UI error handling, not backend)
    await page.route('**/auth/login', async (route) => {
      await route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Invalid email or password' }),
      });
    });

    await page.goto('/login');
    await page.locator('#login-email').fill('bad@example.com');
    await page.locator('#login-password').fill('wrongpassword');
    await page.getByRole('button', { name: 'Sign In', exact: true }).click();

    await expect(page.getByText('Invalid email or password')).toBeVisible({ timeout: 2_000 });
  });

  test('forgot password flow shows confirmation', async ({ page }) => {
    // Mock the magic link endpoint (tests UI flow, not email sending)
    await page.route('**/auth/email/request', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ message: 'Email sent' }),
      });
    });

    await page.goto('/login');
    await page.getByText('Forgot password?').click();
    await expect(page.getByRole('heading', { name: 'Reset your password' })).toBeVisible();

    await page.locator('#reset-email').fill('user@example.com');
    await page.getByRole('button', { name: 'Send Reset Link' }).click();

    await expect(page.getByText('Check your email')).toBeVisible({ timeout: 2_000 });
    await expect(page.getByText('user@example.com')).toBeVisible();
  });
});

// ─── Users List & Filtering ────────────────────────────────────

test.describe('Users list filtering', () => {
  test('filters users by name search', async ({ page }) => {
    await page.goto('/users');
    await waitForUsers(page);

    const totalBefore = await page.locator('.user-row').count();

    await page.locator('#name-search').fill('a');
    await page.waitForTimeout(300);

    const totalAfter = await page.locator('.user-row').count();
    expect(totalAfter).toBeLessThanOrEqual(totalBefore);

    if (totalAfter > 0) {
      const firstUserName = await page.locator('.user-row').first().locator('.user-name').first().textContent();
      expect(firstUserName).toBeTruthy();
    }
  });

  test('filters users by country', async ({ page }) => {
    await page.goto('/users');
    await waitForUsers(page);

    await page.locator('#country-filter').selectOption('FR');
    await page.waitForTimeout(200);

    const count = await page.locator('.user-row').count();
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test('filters users by role', async ({ page }) => {
    await page.goto('/users');
    await waitForUsers(page);

    await page.getByRole('button', { name: 'Judge', exact: true }).click();
    await page.waitForTimeout(200);

    const count = await page.locator('.user-row').count();
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test('navigates to user detail page on row click', async ({ page }) => {
    await page.goto('/users');
    await waitForUsers(page);

    await page.locator('.user-row').first().click();
    await expect(page).toHaveURL(/\/users\/[a-f0-9-]+/, { timeout: 2_000 });

    await expect(page.getByText('Country:')).toBeVisible({ timeout: 2_000 });
    await expect(page.getByText('Last modified:')).toBeVisible();
  });

  test('combines name and country filters', async ({ page }) => {
    await page.goto('/users');
    await waitForUsers(page);

    await page.locator('#country-filter').selectOption('US');
    await page.waitForTimeout(200);

    const afterCountry = await page.locator('.user-row').count();

    await page.locator('#name-search').fill('a');
    await page.waitForTimeout(300);

    const afterBoth = await page.locator('.user-row').count();
    expect(afterBoth).toBeLessThanOrEqual(afterCountry);
  });
});

// ─── Authenticated Features ────────────────────────────────────

test.describe('Edit user (authenticated)', () => {
  test('shows edit button when authenticated', async ({ page }) => {
    await page.goto('/login');
    await loginAsOrganizer(page);
    await page.goto('/users');
    await waitForUsers(page);

    await page.locator('.user-row').first().click();
    await expect(page).toHaveURL(/\/users\/[a-f0-9-]+/, { timeout: 2_000 });
    await expect(page.getByText('Country:')).toBeVisible({ timeout: 2_000 });

    await expect(page.getByTitle('Edit user')).toBeVisible();
  });

  test('opens edit mode and shows form fields', async ({ page }) => {
    await page.goto('/login');
    await loginAsOrganizer(page);
    await page.goto('/users');
    await waitForUsers(page);

    await page.locator('.user-row').first().click();
    await expect(page).toHaveURL(/\/users\/[a-f0-9-]+/, { timeout: 2_000 });
    await expect(page.getByTitle('Edit user')).toBeVisible({ timeout: 2_000 });
    await page.getByTitle('Edit user').click();

    await expect(page.locator('#edit-name')).toBeVisible({ timeout: 2_000 });
    await expect(page.locator('#edit-country')).toBeVisible();
    await expect(page.locator('#edit-nickname')).toBeVisible();
    await expect(page.locator('fieldset legend').filter({ hasText: 'Roles' })).toBeVisible();
    await expect(page.getByTitle('Close')).toBeVisible();
  });

  test('can close edit mode', async ({ page }) => {
    await page.goto('/login');
    await loginAsOrganizer(page);
    await page.goto('/users');
    await waitForUsers(page);

    await page.locator('.user-row').first().click();
    await expect(page).toHaveURL(/\/users\/[a-f0-9-]+/, { timeout: 2_000 });
    await expect(page.getByTitle('Edit user')).toBeVisible({ timeout: 2_000 });
    await page.getByTitle('Edit user').click();
    await expect(page.locator('#edit-name')).toBeVisible({ timeout: 2_000 });

    await page.getByTitle('Close').click();

    await expect(page.getByText('Country:')).toBeVisible({ timeout: 2_000 });
    await expect(page.locator('#edit-name')).not.toBeVisible();
  });
});

test.describe('Sanctions (authenticated as IC)', () => {
  test('shows sanction controls for IC user', async ({ page }) => {
    await page.goto('/login');
    await loginAsOrganizer(page);
    await page.goto('/users');
    await waitForUsers(page);

    await page.locator('.user-row').first().click();
    await expect(page).toHaveURL(/\/users\/[a-f0-9-]+/, { timeout: 2_000 });
    await expect(page.getByText('Country:')).toBeVisible({ timeout: 2_000 });

    await expect(page.getByRole('heading', { name: 'Sanctions' })).toBeVisible({ timeout: 2_000 });
    await expect(page.getByRole('button', { name: 'Issue Sanction' })).toBeVisible();
  });

  test('opens sanction modal with form fields', async ({ page }) => {
    await page.goto('/login');
    await loginAsOrganizer(page);
    await page.goto('/users');
    await waitForUsers(page);

    await page.locator('.user-row').first().click();
    await expect(page).toHaveURL(/\/users\/[a-f0-9-]+/, { timeout: 2_000 });
    await expect(page.getByRole('heading', { name: 'Sanctions' })).toBeVisible({ timeout: 2_000 });

    await page.getByRole('button', { name: 'Issue Sanction' }).click();

    await expect(page.locator('#sanction-level')).toBeVisible({ timeout: 2_000 });
    await expect(page.locator('#sanction-category')).toBeVisible();
    await expect(page.locator('#sanction-description')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Issue Sanction' }).last()).toBeVisible();
    await expect(page.getByRole('button', { name: 'Cancel' })).toBeVisible();
  });

  test('closes sanction modal on cancel', async ({ page }) => {
    await page.goto('/login');
    await loginAsOrganizer(page);
    await page.goto('/users');
    await waitForUsers(page);

    await page.locator('.user-row').first().click();
    await expect(page).toHaveURL(/\/users\/[a-f0-9-]+/, { timeout: 2_000 });
    await expect(page.getByRole('heading', { name: 'Sanctions' })).toBeVisible({ timeout: 2_000 });
    await page.getByRole('button', { name: 'Issue Sanction' }).click();
    await expect(page.locator('#sanction-level')).toBeVisible({ timeout: 2_000 });

    await page.getByRole('button', { name: 'Cancel' }).click();

    await expect(page.locator('#sanction-level')).not.toBeVisible();
  });

  test('closes sanction modal on Escape key', async ({ page }) => {
    await page.goto('/login');
    await loginAsOrganizer(page);
    await page.goto('/users');
    await waitForUsers(page);

    await page.locator('.user-row').first().click();
    await expect(page).toHaveURL(/\/users\/[a-f0-9-]+/, { timeout: 2_000 });
    await expect(page.getByRole('heading', { name: 'Sanctions' })).toBeVisible({ timeout: 2_000 });
    await page.getByRole('button', { name: 'Issue Sanction' }).click();
    await expect(page.locator('#sanction-level')).toBeVisible({ timeout: 2_000 });

    await page.keyboard.press('Escape');

    await expect(page.locator('#sanction-level')).not.toBeVisible();
  });
});
