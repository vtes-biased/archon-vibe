# i18n Architecture Plan

## Decision: Paraglide JS
- Compile-time i18n via Vite plugin (not runtime store-based)
- Tree-shakeable: only active locale messages included in bundle
- Typed message functions: `m.greeting({ name })` with compile-time checks
- Zero runtime dependency (generated code is plain JS)
- Compatible with adapter-static SPA mode

## Why Not svelte-i18n
- Runtime overhead (loads all translations into memory)
- No type safety on keys or interpolation params
- Store-based reactivity adds overhead to every string render

## Offline-First Compatibility
- Translations are static build assets, not data
- Bundled into JS output, cached by service worker automatically
- No IndexedDB involvement, no SSE sync impact
- Locale preference in localStorage (synchronous, offline-safe)
- NO URL-based locale routing (SPA with static adapter, would break routing)

## File Structure
```
frontend/
  project.inlang/settings.json
  messages/{en,fr,pt,es,it}.json
  src/lib/paraglide/  (generated, may be gitignored)
```

## Key Naming: Flat with Underscore Namespaces
- `nav_tournaments`, `login_sign_in`, `tournament_state_planned`
- Flat (not nested JSON) for simplicity and translator agent compatibility

## Rust Engine Error Migration
- ~50+ English error strings in tournament.rs, deck.rs, permissions.rs
- Phase 5: migrate to structured error codes with params
- Example: `{ code: "tournament.need_min_players", params: { min: 4 } }`
- Frontend maps error codes to translated messages

## VTES Terminology Rules
- Card names, clan names, discipline names, set names: always English
- Game mechanic terms (VP, GW, Oust, etc.): translate per official rulebook
- VEKN organizational roles (Prince, NC, IC): keep English (proper nouns)
- Tournament ranks (National Championship): translate

## Migration Phases
0. Infrastructure setup (Paraglide, config, locale picker)
1. Layout + navigation + login page
2. Page-by-page extraction (tournaments list, profile, rankings, users)
3. Tournament detail tabs (one tab per PR)
4. Error messages and toasts (api.ts, toast messages)
5. Rust engine error codes (deferred)

## Vite Config
- Add `paraglideVitePlugin` before sveltekit() in plugins
- Strategy: `['cookie', 'baseLocale']` (no 'url')
- Add `paths.relative: false` to svelte.config.js

## Component Usage Pattern
```svelte
<script lang="ts">
  import * as m from '$lib/paraglide/messages';
</script>
<span>{m.status_offline()}</span>
```
