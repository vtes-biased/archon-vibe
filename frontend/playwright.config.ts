import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright configuration for E2E tests.
 * 
 * Environment variables:
 * - BASE_URL: Override the frontend URL (default: http://localhost:5173)
 * - CI: Set in CI environments for stricter behavior
 * 
 * See https://playwright.dev/docs/test-configuration.
 */

const baseURL = process.env.BASE_URL || 'http://localhost:5173';

export default defineConfig({
  testDir: './tests/e2e',
  outputDir: '../test-results',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 1,
  workers: process.env.CI ? 2 : 4,
  reporter: [['html', { outputFolder: '../playwright-report', open: 'never' }]],
  timeout: 15_000,

  globalSetup: './tests/e2e/global-setup.ts',
  globalTeardown: './tests/e2e/global-teardown.ts',

  use: {
    baseURL,
    locale: 'en-US',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  /* Run dev server before starting tests (skipped if BASE_URL is set externally) */
  webServer: process.env.BASE_URL ? undefined : {
    command: 'npm run dev',
    url: 'http://localhost:5173',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});

