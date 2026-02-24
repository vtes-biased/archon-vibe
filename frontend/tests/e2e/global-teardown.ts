/**
 * Playwright global teardown: clean up test data.
 */
import { execSync } from 'child_process';
import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const STATE_FILE = path.join(__dirname, '.e2e-state.json');
const BACKEND_DIR = path.join(__dirname, '..', '..', '..', 'backend');
const SETUP_SCRIPT = path.join(__dirname, '..', '..', 'tests', 'e2e', 'setup_e2e.py');

async function globalTeardown() {
  try {
    execSync(`uv run python3 ${SETUP_SCRIPT} --cleanup`, {
      cwd: BACKEND_DIR,
      stdio: ['pipe', 'pipe', 'pipe'],
    });
  } catch (e) {
    console.error('E2E cleanup failed:', e);
  }

  // Remove state file
  try {
    fs.unlinkSync(STATE_FILE);
  } catch {
    // Ignore if not present
  }
}

export default globalTeardown;
