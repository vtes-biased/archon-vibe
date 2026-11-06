# SvelteKit 3 with adapter-static 4

Doc-impact: `wiki/architecture.md` (frontend stack), `wiki/testing.md` (frontend
step), `wiki/design.md` (list view state names `replaceState`); `wiki/hazards.md`
if the asset-path or stale-chunk behaviour changes.

## Peers (checked 2026-11-06)

Kit 3.1.1 wants vite ^8.0.12, svelte ^5.57.1, vite-plugin-svelte ^7, typescript
^6 (optional), node >=22.17 — all met. adapter-static 4 needs kit ^3. TypeScript
stays on 6: TS 7 is deferred in `wiki/dev.md`, and kit 3 itself peers ^6 only.

## Migration inventory

From the official "Migrating to SvelteKit 3" guide, against this tree:

- **`svelte.config.js` is no longer read.** Its options move into `sveltekit({...})`
  in `vite.config.ts`: the adapter (`pages`/`assets` = `build`, `fallback:
  '200.html'`, `strict`), `prerender.handleHttpError` / `handleUnseenRoutes`,
  `paths.relative: true` (its comment carries a Vite 8 trap: `false` doubles the
  preload path into a 404), `vitePreprocess()`, and the aliases.
- **Aliases** `$lib`, `$components`, `$engine`: the guide replaces `$lib` with
  `#lib` plus module extensions. Whether custom `$`-aliases survive in kit 3 is
  unconfirmed — check before rewriting.
- **`$lib` imports**: ~900 lines in 144 files. Check for an official codemod
  (`npx sv migrate`) before hand-rewriting; a fan-out goes to the `mass-edit` agent.
- **Shallow routing**: 8 `pushState`/`replaceState` call sites from
  `$app/navigation` become `goto(url, { shallow: true, replace?, state })`.
- **Not exposed**: no `$app/paths` imports (`base`/`assets`/`resolveRoute`
  removal), no server hooks (readonly `event.request`).

## Traps

- The deploy keeps one previous build's chunks (`dist.prev`) and
  `reloadOnStaleChunk` stands down for route nodes because kit's version check
  recovers them (`wiki/hazards.md`). Re-verify both against kit 3's navigation.
- Paraglide's SvelteKit examples now import hook types from `@sveltejs/kit/hooks`;
  we have no hooks, but land Paraglide 3 first so its line is not entangled.
