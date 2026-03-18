/**
 * Playwright global teardown: clean up state file.
 *
 * DB cleanup is not needed — docker compose down -v destroys the volume.
 * For local runs, use: uv run python backend/scripts/seed_e2e.py --cleanup
 */
import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const STATE_FILE = path.join(__dirname, '.e2e-state.json');

async function globalTeardown() {
  try {
    fs.unlinkSync(STATE_FILE);
  } catch {
    // Ignore if not present
  }
}

export default globalTeardown;
