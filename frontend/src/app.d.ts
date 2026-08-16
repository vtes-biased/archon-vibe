declare global {
  // Injected by vite `define` (see vite.config.ts) — the build-time app version.
  const __APP_VERSION__: string;

  namespace App {}
}

export {};
