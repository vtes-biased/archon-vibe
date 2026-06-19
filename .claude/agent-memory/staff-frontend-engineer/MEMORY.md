# Staff Frontend Engineer — Project Memory

## Project: Archon (VTES Tournament Management PWA)

### Stack & Dependencies
- Svelte 5 (runes: $state, $derived, $effect, $props), SvelteKit with adapter-static (SPA, static export)
- TailwindCSS v4 (via @tailwindcss/vite), @tailwindcss/typography; custom colors in `app.css` `@theme` block
- TypeScript ~5.9, Vite 6
- idb (IndexedDB wrapper), lucide-svelte (tree-shaken SVG icons — chosen over @iconify because runtime icon fetching breaks offline), marked + dompurify (markdown)
- WASM engine (Rust) for all business logic (scoring, permissions, validation)
- Paraglide JS for i18n (en/fr/es/pt/it), messages in `frontend/messages/{locale}.json`, used as `m.key_name()`

### Design System (authoritative: `frontend/DESIGN.md`)
- Dark-first gothic palette: crimson, bone, dusk, ash, mist. Custom fonts "Ankha VTES" / "VTES Clans" served from `/fonts/`.
- Mobile-first; **44px minimum touch targets**; auto-save pattern (no explicit save buttons).
- Country display: flag + name. Consistent form styling: `bg-dusk-950 border-ash-600/700 rounded-lg`.
- Tab content padding should scale (`p-3 sm:p-6`) — don't use desktop padding on mobile.

### Architecture Patterns
- Offline-first: **reads come from IndexedDB only**; mutations via API; SSE for sync. Never add an API GET for display data.
- `syncManager`: connect/addEventListener pattern. `+layout.svelte` owns connect/disconnect; components only listen.
- `displayContext`: centralized filter state for UserList. Toast: `stores/toast.svelte` + `Toast.svelte`.
- `buildActorContext` is async (loads leagues from IndexedDB) and feeds WASM permission checks; WASM authz wrappers must **fail closed** on a null/cold engine.

### Component Structure & Splitting
- `/routes/+layout.svelte`: desktop side nav (~80px) + mobile bottom nav + status bar.
- Tournament detail is split into tab components (OverviewTab, PlayersTab, RoundsTab, FinalsTab, ConfigTab, DecksTab); state ownership stays in the parent `[uid]/+page.svelte`.
- User.svelte: multi-mode (view/edit/create), debounced auto-save in edit mode.
- **Split rule:** when a page file exceeds ~1000 lines, extract logical sections into child components (props down, state stays in parent). The tournament `[uid]/+page.svelte` and `profile/+page.svelte` are the recurring offenders — watch them.

### Recurring Patterns / Standards
- All UI strings go through Paraglide (`m.key_name()`) — no hardcoded English. Translate raw enum states (tournament/player/table state) rather than rendering the enum value.
- Mobile tables must reflow to a card layout (the player table is the canonical case) and signal horizontal-scroll affordance when they don't.
- Every `<button>` needs `cursor: pointer` (it's not the default in this app's reset). Touch targets ≥44px — re-check small icon buttons (+/- steppers, unseat/sanction, VP selects).
- Modals: `fixed inset-0 z-50` + backdrop-blur, `role="dialog"` + `aria-modal` + `aria-labelledby`, Escape handling, `focusOnMount` action, stopPropagation, captured state.
- Shared utils live in `tournament-utils.ts` (e.g. `getStateBadgeClass`, score helpers) — don't re-duplicate `computeGwLocal`/`computeTpLocal`/`vpOptions` per file.
- English copy must pluralize (`{count} round(s)`) — the flat-string i18n setup has no built-in plural rules, so handle count-dependent strings deliberately.

### Gotchas
- [No line-clamp on markdown](feedback_no_lineclamp_on_markdown.md) — never `line-clamp-N` over `{@html renderMarkdown(...)}`; derive a plain-text excerpt from source for folded previews.
- Focus-ring floor: global `:focus-visible` crimson ring; opt out only with a self-provided crimson indicator — see DESIGN.md (Mobile First).
- [Stock Tailwind color tokens skip light inversion](feedback_emerald_amber_tokens_no_light_inversion.md) — `bg-emerald/amber-*` don't follow `html.light`; only the `.btn-*`/`.badge-*` CSS classes hand-roll light contrast.

### Components
- [Shared <Button> component](project_shared_button_component.md) — app-wide action button (variant primary|secondary|warning|ghost|danger); don't migrate icon-only/stepper/list buttons to it.
