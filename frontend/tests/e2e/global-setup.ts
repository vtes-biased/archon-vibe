/**
 * Playwright global setup: read seed data from shared volume, login organizer, store state.
 *
 * In Docker: populate-db writes seed JSON to E2E_SEED_FILE (/shared/e2e-seed.json).
 * Locally:   run `uv run python backend/scripts/seed_e2e.py` from repo root first.
 */
import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const STATE_FILE = path.join(__dirname, '.e2e-state.json');
const API_URL = process.env.VITE_API_URL || 'http://localhost:8000';
const BASE_URL = process.env.BASE_URL || 'http://localhost:5173';

// In Docker, populate-db writes seed data to this file via a shared volume.
// Locally, run the seed script with --output to produce it.
const SEED_FILE = process.env.E2E_SEED_FILE
  || path.join(__dirname, '..', '..', '..', 'e2e-seed.json');

async function globalSetup() {
  // 1. Health-check backend
  for (let i = 0; i < 10; i++) {
    try {
      const res = await fetch(`${API_URL}/`);
      if (res.ok) break;
    } catch {
      if (i === 9) throw new Error(`Backend not reachable at ${API_URL}`);
      await new Promise(r => setTimeout(r, 1000));
    }
  }

  // 2. Read seed data (written by populate-db container or manual script run)
  if (!fs.existsSync(SEED_FILE)) {
    throw new Error(
      `Seed file not found at ${SEED_FILE}. ` +
      'In Docker, ensure populate-db ran successfully. ' +
      'Locally, run: uv run python backend/scripts/seed_e2e.py --output e2e-seed.json'
    );
  }
  const seedData = JSON.parse(fs.readFileSync(SEED_FILE, 'utf-8'));

  // 3. Login organizer via real /auth/login
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

  // 4. Store state for tests
  const state = {
    ...seedData,
    access_token: tokens.access_token,
    refresh_token: tokens.refresh_token,
  };
  fs.writeFileSync(STATE_FILE, JSON.stringify(state, null, 2));

  // 5. Warm up Vite dev server — visit the app so Vite pre-compiles all
  //    JS bundles before parallel test workers hit it simultaneously.
  const { chromium } = await import('@playwright/test');
  const browser = await chromium.launch();
  const page = await browser.newPage();
  try {
    await page.goto(BASE_URL, { timeout: 30_000 });
    await page.waitForSelector('.bg-emerald-500, .bg-amber-500', { timeout: 15_000 });
  } catch {
    // Non-fatal: tests may still pass with slightly slower first load
  }
  await browser.close();
}

export default globalSetup;
