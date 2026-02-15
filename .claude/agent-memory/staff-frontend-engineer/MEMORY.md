# Staff Frontend Engineer - Project Memory

## Project: Archon (VTES Tournament Management PWA)

### Stack & Dependencies
- Svelte 5 (runes: $state, $derived, $effect, $props), SvelteKit with adapter-static
- TailwindCSS v4 (via @tailwindcss/vite), @tailwindcss/typography
- TypeScript ~5.9.3, Vite 6
- idb (IndexedDB wrapper), @iconify/svelte (icons), marked + dompurify (markdown)
- WASM engine (Rust) for business logic (scoring, permissions, validation)
- Paraglide JS for i18n (en, fr, es, pt, it), messages in frontend/messages/{locale}.json

### Design System (see frontend/DESIGN.md)
- Dark-first gothic palette: crimson, bone, dusk, ash, mist
- Custom colors defined in app.css @theme block
- Custom fonts: "Ankha VTES", "VTES Clans" (served from /fonts/)
- Auto-save pattern (no explicit save buttons), mobile-first, 44px touch targets
- Modal pattern: stopPropagation, captured state, focusOnMount action

### Architecture Patterns
- Offline-first: reads from IndexedDB, mutations via API, SSE for sync
- syncManager: connect/addEventListener pattern used in layouts and pages
- displayContext: centralized filter state for UserList
- Toast system: stores/toast.svelte + Toast.svelte component

### Component Structure
- `/routes/+layout.svelte`: Side nav (desktop, 80px wide), bottom nav (mobile), status bar
- `/lib/components/`: Shared components (User, UserList, SanctionsManager, TournamentFields, etc.)
- Tournament detail: split into tab components (OverviewTab, PlayersTab, RoundsTab, FinalsTab, ConfigTab, DecksTab)
- User.svelte: multi-mode (view/edit/create), auto-save with debounce in edit mode

### Key File Sizes (watch for splitting)
- tournaments/[uid]/+page.svelte: 928 lines (near 1000-line limit)
- profile/+page.svelte: 719 lines (growing -- has 3 modals inline)
- UserList.svelte: 667 lines
- User.svelte: 601 lines
- RoundsTab.svelte: 569 lines
- SanctionsManager.svelte: 498 lines

### Known Patterns
- `getStateBadgeClass()` extracted to tournament-utils.ts (was duplicated)
- Country display: flag + name, select uses name + flag (per DESIGN.md)
- Consistent form styling: bg-dusk-950 border-ash-600/700 rounded-lg
- Role filter toggles: pill buttons with getRoleClasses()
- All modals use fixed inset-0 z-50 backdrop-blur pattern
- i18n: all UI strings extracted to Paraglide messages (m.key_name())

### i18n Gaps (found 2026-02-15)
- leagues/[uid]/+page.svelte: hardcoded English everywhere (not using Paraglide)
- Tournament states displayed as raw enum values without translation

### Accessibility Notes
- Modals have role="dialog", aria-modal, aria-labelledby, Escape key handling
- focusOnMount action used on modal dialogs
- UserList rows have role="button" tabindex="0" with Enter key handling
- Select elements use labels, ids are present on most inputs
- LocaleSwitcher has aria-label

### Mobile Touch Target Concerns
- DeckDisplay +/- edit buttons: w-5 h-5 (20px, well below 44px minimum)
- League detail edit/delete buttons: py-1.5 (approx 32px, below 44px)
