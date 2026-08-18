import { defineConfig, devices } from '@playwright/test';

// Separate from the e2e config: the smoke needs no backend, seed or login — it
// serves the static `build/` artifact and asserts the pipeline boots.
const PORT = 4173;

export default defineConfig({
  testDir: './tests/smoke',
  outputDir: '../test-results/smoke',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 0, // a build break is deterministic; a retry would only mask flake
  reporter: [['list']],
  timeout: 60_000,

  use: {
    baseURL: `http://localhost:${PORT}`,
    trace: 'on-first-retry',
  },

  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],

  webServer: {
    command: `node tests/smoke/serve-build.mjs build`,
    url: `http://localhost:${PORT}`,
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});
