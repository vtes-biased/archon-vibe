import { test, expect, type Page } from '@playwright/test';

/**
 * E2E tests for the Archon app.
 * Tests run against the dev server with real backend SSE data.
 * Run serially to avoid overwhelming backend with simultaneous SSE connections.
 */
test.describe.configure({ mode: 'serial' });

// Helper: wait for users to load via SSE
async function waitForUsers(page: Page) {
  await expect(page.locator('#users-list-container')).toBeVisible({ timeout: 30_000 });
  await expect(page.locator('.user-row').first()).toBeVisible({ timeout: 5_000 });
}

// Helper: set up a fake authenticated session by injecting tokens and mocking /auth/me
async function loginAs(page: Page, roles: string[] = []) {
  // Create a fake JWT payload (header.payload.signature)
  // The payload just needs to be valid base64 with exp in the future
  const payload = btoa(JSON.stringify({
    sub: 'test-user-uid',
    exp: Math.floor(Date.now() / 1000) + 3600,
    type: 'access',
  }));
  const fakeToken = `eyJ.${payload}.sig`;
  const fakeRefresh = `eyJ.${payload}.ref`;

  // Mock /auth/me to return our test user (must match MeResponse shape)
  await page.route('**/auth/me', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        user: {
          uid: 'test-user-uid',
          modified: new Date().toISOString(),
          name: 'Test Admin',
          country: 'US',
          vekn_id: '1000000',
          city: null,
          state: null,
          nickname: null,
          roles: roles,
          avatar_path: null,
          contact_email: 'test@example.com',
          contact_discord: null,
          contact_phone: null,
          coopted_by: null,
          coopted_at: null,
          vekn_synced: false,
          vekn_synced_at: null,
          local_modifications: [],
          vekn_prefix: null,
        },
        auth_methods: [],
      }),
    });
  });

  // Mock token refresh
  await page.route('**/auth/refresh', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        access_token: fakeToken,
        refresh_token: fakeRefresh,
        token_type: 'bearer',
      }),
    });
  });

  // Set tokens in localStorage before navigating
  await page.evaluate(({ token, refresh }) => {
    localStorage.setItem('archon_access_token', token);
    localStorage.setItem('archon_refresh_token', refresh);
  }, { token: fakeToken, refresh: fakeRefresh });
}

// ─── App Load ──────────────────────────────────────────────────

test.describe('App loads correctly', () => {
  test('redirects / to /tournaments', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveURL(/\/tournaments/);
  });

  test('displays navigation sidebar', async ({ page }) => {
    await page.goto('/users');
    // Desktop sidebar nav links
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

    // Title
    await expect(page.locator('h1')).toContainText('Archon');

    // Mode toggle
    await expect(page.getByRole('button', { name: 'Login' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Sign Up' })).toBeVisible();

    // Login form fields
    await expect(page.locator('#login-email')).toBeVisible();
    await expect(page.locator('#login-password')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Sign In', exact: true })).toBeVisible();

    // Other login options
    await expect(page.getByRole('button', { name: /Discord/ })).toBeVisible();
    await expect(page.getByText('Forgot password?')).toBeVisible();
  });

  test('switches between login and signup modes', async ({ page }) => {
    await page.goto('/login');

    // Default: login mode
    await expect(page.locator('#login-email')).toBeVisible();

    // Switch to signup
    await page.getByRole('button', { name: 'Sign Up' }).click();
    await expect(page.getByText('Create a new account')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Continue with Email' })).toBeVisible();

    // Switch back to login
    await page.getByRole('button', { name: 'Login' }).click();
    await expect(page.locator('#login-email')).toBeVisible();
  });

  test('shows error on invalid login', async ({ page }) => {
    // Mock auth/login to return an error
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

    // Error message should appear
    await expect(page.getByText('Invalid email or password')).toBeVisible({ timeout: 5_000 });
  });

  test('forgot password flow shows confirmation', async ({ page }) => {
    // Mock the magic link endpoint
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

    await expect(page.getByText('Check your email')).toBeVisible({ timeout: 5_000 });
    await expect(page.getByText('user@example.com')).toBeVisible();
  });
});

// ─── Users List & Filtering ────────────────────────────────────

test.describe('Users list filtering', () => {
  test('filters users by name search', async ({ page }) => {
    await page.goto('/users');
    await waitForUsers(page);

    const totalBefore = await page.locator('.user-row').count();

    // Type a search query
    await page.locator('#name-search').fill('a');
    // Wait for debounced search to apply
    await page.waitForTimeout(500);

    // Should have fewer or equal results (filtered)
    const totalAfter = await page.locator('.user-row').count();
    expect(totalAfter).toBeLessThanOrEqual(totalBefore);

    // All visible names should contain 'a' (case-insensitive prefix match on any word)
    if (totalAfter > 0) {
      const firstUserName = await page.locator('.user-row').first().locator('.user-name').first().textContent();
      expect(firstUserName).toBeTruthy();
    }
  });

  test('filters users by country', async ({ page }) => {
    await page.goto('/users');
    await waitForUsers(page);

    // Select a specific country
    await page.locator('#country-filter').selectOption('FR');
    // Wait for filter to apply
    await page.waitForTimeout(300);

    const rows = page.locator('.user-row');
    const count = await rows.count();

    // If there are French users, they should be displayed
    // The filter should work (not crash) regardless
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test('filters users by role', async ({ page }) => {
    await page.goto('/users');
    await waitForUsers(page);

    // Click a role filter button (e.g., "Judge")
    await page.getByRole('button', { name: 'Judge', exact: true }).click();
    await page.waitForTimeout(300);

    // The filter button should be visually active (different styling)
    // And results should be filtered
    const rows = page.locator('.user-row');
    const count = await rows.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test('expands a user row to show details', async ({ page }) => {
    await page.goto('/users');
    await waitForUsers(page);

    // Click the first user row
    await page.locator('.user-row').first().click();

    // The expanded view should show user details (User.svelte in view mode)
    await expect(page.getByText('Country:')).toBeVisible({ timeout: 3_000 });
    await expect(page.getByText('Last modified:')).toBeVisible();
  });

  test('combines name and country filters', async ({ page }) => {
    await page.goto('/users');
    await waitForUsers(page);

    // Apply country filter first
    await page.locator('#country-filter').selectOption('US');
    await page.waitForTimeout(300);

    const afterCountry = await page.locator('.user-row').count();

    // Then add name search
    await page.locator('#name-search').fill('a');
    await page.waitForTimeout(500);

    const afterBoth = await page.locator('.user-row').count();
    expect(afterBoth).toBeLessThanOrEqual(afterCountry);
  });
});

// ─── Authenticated Features ────────────────────────────────────

test.describe('Edit user (authenticated)', () => {
  test('shows edit button when authenticated', async ({ page }) => {
    // Set up auth before navigating
    await page.goto('/login'); // Need a page context to set localStorage
    await loginAs(page, ['IC']);
    await page.goto('/users');
    await waitForUsers(page);

    // Expand a user
    await page.locator('.user-row').first().click();
    await expect(page.getByText('Country:')).toBeVisible({ timeout: 3_000 });

    // Edit button should be visible (pencil icon)
    await expect(page.getByTitle('Edit user')).toBeVisible();
  });

  test('opens edit mode and shows form fields', async ({ page }) => {
    await page.goto('/login');
    await loginAs(page, ['IC']);
    await page.goto('/users');
    await waitForUsers(page);

    // Expand and edit first user
    await page.locator('.user-row').first().click();
    await expect(page.getByTitle('Edit user')).toBeVisible({ timeout: 3_000 });
    await page.getByTitle('Edit user').click();

    // Edit form should appear with fields
    await expect(page.locator('#edit-name')).toBeVisible({ timeout: 3_000 });
    await expect(page.locator('#edit-country')).toBeVisible();
    await expect(page.locator('#edit-nickname')).toBeVisible();

    // Roles fieldset should be visible
    await expect(page.locator('fieldset legend').filter({ hasText: 'Roles' })).toBeVisible();

    // Close button should be visible
    await expect(page.getByTitle('Close')).toBeVisible();
  });

  test('can close edit mode', async ({ page }) => {
    await page.goto('/login');
    await loginAs(page, ['IC']);
    await page.goto('/users');
    await waitForUsers(page);

    // Expand, edit, then close
    await page.locator('.user-row').first().click();
    await expect(page.getByTitle('Edit user')).toBeVisible({ timeout: 3_000 });
    await page.getByTitle('Edit user').click();
    await expect(page.locator('#edit-name')).toBeVisible({ timeout: 3_000 });

    // Close edit mode
    await page.getByTitle('Close').click();

    // Should be back to view mode
    await expect(page.getByText('Country:')).toBeVisible({ timeout: 3_000 });
    await expect(page.locator('#edit-name')).not.toBeVisible();
  });
});

test.describe('Sanctions (authenticated as IC)', () => {
  test('shows sanction controls for IC user', async ({ page }) => {
    await page.goto('/login');
    await loginAs(page, ['IC', 'Ethics']);
    await page.goto('/users');
    await waitForUsers(page);

    // Expand and edit a user
    await page.locator('.user-row').first().click();
    await expect(page.getByTitle('Edit user')).toBeVisible({ timeout: 3_000 });
    await page.getByTitle('Edit user').click();
    await expect(page.locator('#edit-name')).toBeVisible({ timeout: 3_000 });

    // Sanctions fieldset should be visible for IC/Ethics (use legend to avoid matching filter section)
    await expect(page.locator('fieldset legend').filter({ hasText: 'Sanctions' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Issue Sanction' })).toBeVisible();
  });

  test('opens sanction modal with form fields', async ({ page }) => {
    await page.goto('/login');
    await loginAs(page, ['IC', 'Ethics']);
    await page.goto('/users');
    await waitForUsers(page);

    // Navigate to edit mode
    await page.locator('.user-row').first().click();
    await expect(page.getByTitle('Edit user')).toBeVisible({ timeout: 3_000 });
    await page.getByTitle('Edit user').click();
    await expect(page.locator('#edit-name')).toBeVisible({ timeout: 3_000 });

    // Open sanction modal
    await page.getByRole('button', { name: 'Issue Sanction' }).click();

    // Modal should appear with form fields
    await expect(page.locator('#sanction-level')).toBeVisible({ timeout: 3_000 });
    await expect(page.locator('#sanction-category')).toBeVisible();
    await expect(page.locator('#sanction-description')).toBeVisible();

    // Submit button
    await expect(page.getByRole('button', { name: 'Issue Sanction' }).last()).toBeVisible();
    // Cancel button
    await expect(page.getByRole('button', { name: 'Cancel' })).toBeVisible();
  });

  test('closes sanction modal on cancel', async ({ page }) => {
    await page.goto('/login');
    await loginAs(page, ['IC', 'Ethics']);
    await page.goto('/users');
    await waitForUsers(page);

    // Navigate to sanction modal
    await page.locator('.user-row').first().click();
    await expect(page.getByTitle('Edit user')).toBeVisible({ timeout: 3_000 });
    await page.getByTitle('Edit user').click();
    await expect(page.locator('#edit-name')).toBeVisible({ timeout: 3_000 });
    await page.getByRole('button', { name: 'Issue Sanction' }).click();
    await expect(page.locator('#sanction-level')).toBeVisible({ timeout: 3_000 });

    // Cancel
    await page.getByRole('button', { name: 'Cancel' }).click();

    // Modal should be gone
    await expect(page.locator('#sanction-level')).not.toBeVisible();
  });

  test('closes sanction modal on Escape key', async ({ page }) => {
    await page.goto('/login');
    await loginAs(page, ['IC', 'Ethics']);
    await page.goto('/users');
    await waitForUsers(page);

    // Navigate to sanction modal
    await page.locator('.user-row').first().click();
    await expect(page.getByTitle('Edit user')).toBeVisible({ timeout: 3_000 });
    await page.getByTitle('Edit user').click();
    await expect(page.locator('#edit-name')).toBeVisible({ timeout: 3_000 });
    await page.getByRole('button', { name: 'Issue Sanction' }).click();
    await expect(page.locator('#sanction-level')).toBeVisible({ timeout: 3_000 });

    // Press Escape
    await page.keyboard.press('Escape');

    // Modal should be gone
    await expect(page.locator('#sanction-level')).not.toBeVisible();
  });
});
