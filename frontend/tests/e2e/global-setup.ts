/**
 * Playwright global setup: seed test data, login organizer, store state.
 */
import { execSync } from 'child_process';
import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const STATE_FILE = path.join(__dirname, '.e2e-state.json');
const API_URL = process.env.VITE_API_URL || 'http://localhost:8000';
const BACKEND_DIR = path.join(__dirname, '..', '..', '..', 'backend');
const SETUP_SCRIPT = path.join(__dirname, '..', '..', 'tests', 'e2e', 'setup_e2e.py');

const BASE_URL = process.env.BASE_URL || 'http://localhost:5173';

async function globalSetup() {
  // 1. Health-check backend
  for (let i = 0; i < 10; i++) {
    try {
      const res = await fetch(`${API_URL}/health`);
      if (res.ok) break;
    } catch {
      if (i === 9) throw new Error(`Backend not reachable at ${API_URL}`);
      await new Promise(r => setTimeout(r, 1000));
    }
  }

  // 2. Clean up any leftover test data first
  try {
    execSync(`uv run python3 ${SETUP_SCRIPT} --cleanup`, {
      cwd: BACKEND_DIR,
      stdio: ['pipe', 'pipe', 'pipe'],
    });
  } catch {
    // Ignore cleanup errors on first run
  }

  // 3. Seed test data
  const seedOutput = execSync(`uv run python3 ${SETUP_SCRIPT}`, {
    cwd: BACKEND_DIR,
    encoding: 'utf-8',
    stdio: ['pipe', 'pipe', 'pipe'],
  });
  const seedData = JSON.parse(seedOutput.trim());

  // 4. Login organizer via real /auth/login
  const loginRes = await fetch(`${API_URL}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      email: seedData.organizer_email,
      password: seedData.organizer_password,
    }),
  });
  if (!loginRes.ok) {
    throw new Error(`Login failed: ${loginRes.status} ${await loginRes.text()}`);
  }
  const tokens = await loginRes.json();

  // 5. Store state for tests
  const state = {
    ...seedData,
    access_token: tokens.access_token,
    refresh_token: tokens.refresh_token,
  };
  fs.writeFileSync(STATE_FILE, JSON.stringify(state, null, 2));

  // 6. Warm up Vite dev server — visit the app so Vite pre-compiles all
  //    JS bundles before parallel test workers hit it simultaneously.
  const { chromium } = await import('@playwright/test');
  const browser = await chromium.launch();
  const page = await browser.newPage();
  try {
    await page.goto(BASE_URL, { timeout: 30_000 });
    // Wait for the app to fully render (layout + sync indicator)
    await page.waitForSelector('.bg-emerald-500, .bg-amber-500', { timeout: 15_000 });
  } catch {
    // Non-fatal: tests may still pass with slightly slower first load
  }
  await browser.close();
}

export default globalSetup;
