import { test, expect, type Page } from '@playwright/test';

// The dev-server e2e never loads the BUILT artifact, so prod-only asset-pipeline
// breakage (chunks/WASM that fail to resolve → dead app) ships green. This loads
// the build the way prod serves it and asserts it boots.
//
// '/' is prerendered (relative asset paths); the deep route is served by the
// 200.html SPA fallback (absolute paths) — the combination an asset-path
// regression breaks but the dev server hides.
const ROUTES = ['/', '/tournaments/0190aaaa-bbbb-7ccc-8ddd-eeeeeeeeeeee'];

// With no backend the app's API/SSE calls 503; those are the only legitimate
// console errors. Anything else (a 404 chunk, module-MIME mismatch, WASM init
// failure) is a build break.
const BENIGN_CONSOLE = [/status of 503/i, /snapshot fetch failed/i, /SSE connection error/i];

async function collect(page: Page) {
  const assetResponses: Array<{ status: number; path: string }> = [];
  const wasmResponses: Array<{ status: number; path: string }> = [];
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];

  page.on('console', (m) => m.type() === 'error' && consoleErrors.push(m.text()));
  page.on('pageerror', (e) => pageErrors.push(String(e)));
  page.on('response', (r) => {
    const path = new URL(r.url()).pathname;
    if (path.startsWith('/_app/')) assetResponses.push({ status: r.status(), path });
    if (path.endsWith('.wasm')) wasmResponses.push({ status: r.status(), path });
  });

  return { assetResponses, wasmResponses, consoleErrors, pageErrors };
}

for (const route of ROUTES) {
  test(`built app boots on ${route}`, async ({ page }) => {
    const { assetResponses, wasmResponses, consoleErrors, pageErrors } = await collect(page);

    await page.goto(route, { waitUntil: 'load' });
    // Wait for the engine's WASM fetch before asserting; tolerate timeout, since
    // its absence is itself a failure the assertions below catch.
    await page.waitForResponse((r) => r.url().endsWith('.wasm'), { timeout: 20_000 }).catch(() => {});
    await page.waitForLoadState('networkidle').catch(() => {});

    const brokenAssets = assetResponses.filter((r) => r.status >= 400);
    expect(brokenAssets, `4xx/5xx on built assets: ${JSON.stringify(brokenAssets)}`).toEqual([]);

    expect(wasmResponses.length, 'no .wasm requested — engine never initialised').toBeGreaterThan(0);
    expect(wasmResponses.every((r) => r.status === 200), `WASM not 200: ${JSON.stringify(wasmResponses)}`).toBe(true);

    const mountedChildren = await page.locator('body > div').first().evaluate((el) => el.childElementCount);
    expect(mountedChildren, 'app shell rendered no content').toBeGreaterThan(0);

    expect(pageErrors, `uncaught page errors: ${JSON.stringify(pageErrors)}`).toEqual([]);
    const unexpected = consoleErrors.filter((e) => !BENIGN_CONSOLE.some((re) => re.test(e)));
    expect(unexpected, `unexpected console errors: ${JSON.stringify(unexpected)}`).toEqual([]);
  });
}
