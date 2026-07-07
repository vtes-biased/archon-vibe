# Frontend Design Guidelines

## This doc vs. the `frontend-design` skill

This file is the project's **pinned visual direction** — the gothic VTES system below *is* the brief. The `frontend-design` skill (auto-invoked on UI work) contributes craft process and a quality floor; the two compose:

- **Existing surfaces & new features inside the app** → this doc wins. The skill's *craft* still applies: intentional type scale + weight hierarchy, structure that encodes meaning (don't decorate), motion restraint, copy as design material, and its quality floor — responsive, visible keyboard focus, `prefers-reduced-motion` honored. Its "pick a bespoke palette / take an aesthetic risk" guidance does **not** — stay on the token scale and patterns here. The skill defers by its own rule: a pinned brief always wins.
- **Genuinely new standalone surfaces** with no precedent here (e.g. a landing / onboarding page) → run the skill's full brainstorm → critique → build process, then fold durable decisions back into this doc.

When in doubt, consistency with this system beats novelty.

## Color Palette

VTES / Vampire: the Masquerade inspired. Gothic horror, pale and muted, with dark mode as primary.

Colour is expressed as **role tokens** in four families — `surface` (backgrounds), `ink` (text), `line` (borders), `accent` (crimson). Each token is defined **once** in `app.css` `@theme` via CSS `light-dark(LIGHT, DARK)`, so its value follows the element's `color-scheme` automatically — there is **no** per-shade `html.light` override block and **no** numeric scale to hand-invert. Use them as ordinary Tailwind utilities (`bg-surface-card`, `text-ink-muted`, `border-line`, `text-link`), opacity modifiers included (`bg-surface-hover/50`).

| Token | Utility e.g. | Light | Dark | Role |
|-------|--------------|-------|------|------|
| `surface` | `bg-surface` | `#F5F0E6` | `#2A2520` | Page background |
| `surface-card` | `bg-surface-card` | `#FFFFFF` | `#1C1A1E` | Cards / panels |
| `surface-muted` | `bg-surface-muted` | `#E8E6E4` | `#3D3A37` | Subtle row / overlay bg |
| `surface-hover` | `bg-surface-hover` | `#D4D0CC` | `#4A4642` | Interactive hover |
| `surface-active` | `bg-surface-active` | `#B8B2AC` | `#5A5550` | Solid neutral control |
| `ink-strong` | `text-ink-strong` | `#5E5444` | `#FAF8F4` | Headings / emphasis |
| `ink-bright` | `text-ink-bright` | `#4A4642` | `#D4D0CC` | Bright body / labels |
| `ink` | `text-ink` | `#5A5550` | `#B8B2AC` | Default body text |
| `ink-muted` | `text-ink-muted` | `#6B6560` | `#9A938C` | Secondary text |
| `ink-faint` | `text-ink-faint` | `#7D756E` | `#7D756E` | Tertiary / disabled |
| `line` | `border-line` | `#D4D0CC` | `#4A4642` | Default border / divider |
| `line-strong` | `border-line-strong` | `#B8B2AC` | `#5A5550` | Stronger border |
| `accent` | `bg/border/ring-accent` | `#A40F2D` | `#DC143C` | Brand crimson — fills / borders / rings / large display headings. For body-size accent text use `link` (`accent` is ~3.5:1 on cards — AA-ok for large text only). |
| `accent-strong` | `bg-accent-strong` | `#880C26` | `#A40F2D` | CTA button solid |
| `accent-strong-hover` | `hover:bg-accent-strong-hover` | `#960D29` | `#C41235` | CTA hover |
| `accent-soft` | `bg-accent-soft/20` | `#FCE4E8` | `#6E0A1F` | Accent tint background |
| `accent-soft-border` | `border-accent-soft-border` | `#F9CCD4` | `#880C26` | Accent tint border |
| `link` | `text-link` | `#DC143C` | `#EC6B84` | Links / accent text |
| `link-soft` | `text-link-soft` | `#C41235` | `#F4A3B3` | Light accent text on tint |
| `info` | `text-info` | `#1e40af` | `#60a5fa` | Status text/icon — azure; info / positive (✓, online). Shares hex with `select` today but has a distinct role (may diverge). |
| `warn` | `text-warn` | `#6b21a8` | `#c084fc` | Status text/icon — amethyst; pending / warning (matches `.dot-pending`) |
| `highlight` | `text-highlight` | `#86198f` | `#e879f9` | Status text/icon — fuchsia; highlight / mid severity (matches `.dot-highlight`) |
| `select` | `text-select` / `ring-select` | `#1e40af` | `#60a5fa` | Selection affordance — azure; tap-to-swap seating (moving banner, seat ring). Purpose token, NOT a status meaning. |
| `select-border` | `border-select-border` | `#bfdbfe` | `#1e3a8a` | Select border |
| `select-soft` | `bg-select-soft/40` | `#eff6ff` | `#1e3a8a` | Select tint bg (always use with opacity) |

**Adding a colour:** add one `--color-<role>: light-dark(LIGHT, DARK)` line in `@theme` and verify AA in both themes. Never reintroduce a numeric ramp (`*-400`/`*-900`) or an `html.light` override block. Known exception: `ink-faint` (tertiary/disabled) is a single grey for both themes and does not clear the 4.5:1 body floor — keep it to de-emphasised/disabled text, not primary content.

Role badges use distinct colors but remain muted/dusty to fit the gothic aesthetic.

### Semantic Color Classes

Standard Tailwind status colors (green/amber/teal/…) are **off-palette** — the app uses a tight gothic-jewel set instead. Coloured UI elements use the semantic classes in `app.css`, each defined **once** with CSS `light-dark(LIGHT, DARK)` (the theme value is picked from `color-scheme`; **no** parallel `html.light` block — that was the old two-sources-of-truth bug).

**Hues:** blue (azure) · amethyst (purple) · fuchsia (magenta) · crimson · slate (neutral). **No green/amber/teal/cyan/lime/yellow/orange/indigo/rose.** Violet is reserved for destructive `btn-danger` only. All combos are WCAG-AA in both themes.

Two layers share these hues:

| Layer | Classes | Hue mapping |
|-------|---------|-------------|
| **Status** (meaning) | `badge-success`/`-pending`/`-danger`/`-info`/`-highlight` · `banner-info`/`-warn`/`-error`/`-highlight` · `toast-success`/`-warn` · `status-offline`/`-update` · `btn-success`/`-pending` · `dot-pending`/`-highlight`/`-danger` · `text-info`/`text-warn`/`text-highlight` | success/info = azure · pending/warn = amethyst · danger/error = crimson · highlight = fuchsia |
| **Categorical** (identity) | `badge-blue`/`-amethyst`/`-fuchsia`/`-crimson`/`-slate` | arbitrary distinct tags (roles, link platforms) — pick by family, the hue is just a label |

**Colourblind-safe severity/status rule:** every severity/status tier = fixed colour token + fixed shape-distinct lucide icon + text label. Colour is reinforcement, never the sole signal. The ordinal severity scale for seating issues:

| Tier | Token | Icon | Used by |
|------|-------|------|---------|
| Blocking (rule level 0) | `text-link` (crimson) | `OctagonX` | Hard seating violations |
| Strong (levels 1–4) | `text-highlight` (fuchsia) | `TriangleAlert` | Soft seating warnings |
| Soft (levels ≥5) | `text-warn` (amethyst) | `Info` | Seating suggestions |

This mirrors `.dot-danger`→`.dot-highlight`→`.dot-pending` (crimson→fuchsia→amethyst). The connection indicator likewise uses a distinct icon per state: `Wifi` (`text-info`, online), `RefreshCw` spin (`text-warn`, syncing, with `motion-reduce:animate-none`), `WifiOff` (`text-link`, offline).

**Selection hue (azure):** `select`/`select-border`/`select-soft` tokens are a **purpose** family, not a status meaning — they cover the tap-to-swap seating affordance (the moving-player banner, selected-seat ring, swap-target ring, "move here"/seat-assign chips). Azure is also used by `badge-info`/`status-update`/`text-info` (info-status meaning); same hue, distinct role/token names, deliberately separate.

**When to use what:**
- **Status text/icon tokens** (`text-info`, `text-warn`, `text-highlight`) — inline status text and standalone icons where a `.badge-*` on a bare span would be too heavy. Always pair with a shape-distinct icon + text label (see colourblind rule above).
- **Status classes** (`badge-*`, `banner-*`, `dot-*`, etc.) — component-level status (pills, banners, indicator dots). Pair with an icon + text; colour is reinforcement, never the sole signal.
- **Selection tokens** (`text-select`, `border-select-border`, `bg-select-soft`) — seating tap-to-swap affordance only. Never use for status.
- **Categorical classes** (`badge-blue` etc.) — identity tags where the hue is arbitrary.
- `btn-*` — solid status chips only (paid/pending filter chips, help-guide mockups). **Action buttons go through `<Button>`** (below), which uses `bg-crimson-*` / `btn-danger`.
- `banner-*` — info/warning boxes (add `border rounded-lg p-3` etc.).
- Accent role tokens (`bg-accent*`, `text-link*`, `border-accent`, `ring-accent`) — crimson, theme-switched via `light-dark()`; use directly.

**Adding a semantic colour:** add one `light-dark(LIGHT, DARK)` rule in `app.css` and verify AA in both themes. Do **not** reintroduce green/amber or a parallel `html.light` override block.

### Buttons — use `<Button>`

All action buttons go through `$lib/components/Button.svelte`. It owns colour, size, and the disabled/loading states, so call-sites pass intent, not classes.

| Variant | Colour | Intent |
|---------|--------|--------|
| `primary` | crimson | **Every** affirmative action — lifecycle CTAs (Start Round, Close Registration, Finish Round/Finals) *and* form/auth submits (Sign in, Create, Upload, Save, Approve) |
| `danger` | **violet** (`btn-danger`) | Destructive (Delete, Drop, Force-takeover, Cancel round, Finish tournament). Always pair with an icon + verb. |
| `secondary` | neutral ash (solid) | Neutral secondary action; bulk utilities; the **More** overflow trigger |
| `ghost` | neutral ash (outline) | Tertiary / de-emphasised (Reopen tournament, Go-offline trigger) |

- **One primary CTA per surface.** Crimson is the single positive colour, so a screen should show one filled crimson button; collapse the rest into an overflow (`ActionMenu.svelte`). A legitimate second lifecycle choice (e.g. Start Round vs Start Finals) drops to `secondary`, never a second `primary`.
- **Danger is violet, never red.** Red and crimson are the same hue family and collapse together — even under colourblindness — so destructive actions get their own hue. Meaning must not rest on hue alone: pair `danger` with an icon (`TriangleAlert`/`Trash2`) + a verb.
- `primary`/`secondary`/`ghost` use the `accent`/`surface`/`ink`/`line` role tokens (each carries both themes via `light-dark()`). `danger` uses `btn-danger`, its own `light-dark()` class (violet is off-palette).
- Props: `size` (`sm`/`md`/`lg`), `block` (full width), `loading` (spinner + `aria-busy`, auto-disables), `disabled`; extra layout classes (`flex-1`, margins) via `class`. Focus comes from the global `:focus-visible` ring — never add a bespoke outline.
- **Do not** route through `<Button>`: icon-only buttons, toggles/tabs/segmented controls, dropdown/menu options (e.g. the items inside `ActionMenu`), row/card-wrapping buttons, `<a>`-styled links, or Discord brand-fill buttons — leave those as raw elements.

**Palette history:** the crimson-primary system replaced the earlier scheme (emerald `primary`, crimson `brand`/`danger`, amber `warning`): `primary` → crimson, `danger` → violet `btn-danger`, `warning`/emerald dropped from `<Button>` (`btn-success`/`btn-pending` remain only for status chips + help-guide mockups). **#232 (shipped):** the semantic component classes were recoloured to the gothic-jewel set (green/amber out; blue/amethyst/fuchsia/crimson/slate in) and migrated to `light-dark()` — no parallel `html.light` block — with WCAG-AA verified in both themes; raw inline green/amber tints swept to the palette. **#247 (shipped):** the numeric-scale → role-token migration completed — every `bg-dusk-950`/`text-ash-400`-style utility moved to the `surface`/`ink`/`line`/`accent` role tokens across ~80 files, the `html.light` scale-inversion block was deleted, and the last off-palette inline alert boxes (purple/sky/blue) became `banner-*` (see *Color Palette*). **#225/#248 (shipped):** severity and connection indicators made colourblind-safe (icon+shape+text alongside colour); `info`/`warn`/`highlight` status TEXT tokens and the `select`/`select-border`/`select-soft` purpose-token family added (azure formalised as the tap-to-swap selection affordance, distinct from `badge-info`/`text-info` at the same hue); inline purple/blue/sky tints in the seating/rounds/player flow and the two help-guide-mirrored components (`JudgeCallBanner`, `TimerDisplay`) migrated to semantic tokens. Follow-up #252 finishes the inline-tint sweep across ~12 remaining files.

### Disabled States

Action buttons use `<Button>`, which owns its disabled + loading states — never hand-roll them. For the remaining non-`<Button>` cases:

| Element | Disabled style |
|---------|---------------|
| `<Button>` | Built-in — pass `disabled` / `loading` |
| Form inputs (text, select, textarea) | `disabled:opacity-50` |
| Icon-only / small raw buttons | `disabled:opacity-40` |

`button:disabled { cursor: not-allowed }` is global in `app.css` — never add `disabled:cursor-not-allowed` inline.

### Light Theme — Role Tokens

Every colour role is a single `--color-<role>: light-dark(LIGHT, DARK)` entry in `@theme` (see *Color Palette* above). `light-dark()` resolves from the element's `color-scheme`, so the only thing the light theme does is flip it: `html.light { color-scheme: light }`. No per-shade override block, no numeric scale-inversion to keep in sync — both theme values live at the token's definition.

**Semantic component classes** (`badge-*`, `banner-*`, `btn-*`, `toast-*`, `status-*`, `dot-*`) follow the same `light-dark()` pattern with their own (often jewel-tinted) values.

**Adding new colors**: add one `light-dark()` rule — a role token in `@theme` or a semantic component class — and verify AA in both themes. Do not add a numeric ramp or an `html.light` override block.

**Theme toggle**: Users can cycle system / light / dark via the toggle in the sidebar (desktop) or bottom nav (mobile). Preference is stored in `localStorage.theme` and applied before first paint via an inline script in `app.html` to prevent FOUC.

**Store**: `$lib/stores/theme.svelte.ts` — `cycleTheme()`, `getTheme()`, `initTheme()`.

## Typography

Hierarchy is carried by **weight contrast**, not just size — the venue is a phone in
low light or bright sun on a dark theme, where thin strokes are fatiguing. Titles are
**semibold**; the lightest weight is reserved for **large display only** (the `text-4xl`
"Archon" wordmark). A semibold `text-3xl` title sits clearly above a `font-medium` section
head; a thin one did not (size said "title", weight said "caption").

| Role | Size | Weight | Colour |
|------|------|--------|--------|
| Display / wordmark | `text-4xl` | `font-light` | `text-accent` — the **only** sanctioned `font-light`; ≥`text-4xl` only |
| Page title (`h1`) | `text-3xl` (`text-2xl` on tight cards) | `font-semibold` | `text-accent` (or `text-ink-strong` on a coloured surface) |
| Section (`h2`) | `text-xl` | `font-medium` | `text-ink-strong` / `text-link` |
| Subsection (`h3`) | `text-lg` / `text-sm` | `font-medium`–`font-semibold` | `text-ink-strong` |
| Eyebrow / label | `text-sm` | `font-medium uppercase tracking-wide` | `text-ink-muted` |
| Body | `text-base` / `text-sm` | `font-normal` | `text-ink` |
| Secondary / meta | `text-sm` / `text-xs` | `font-normal` | `text-ink-muted` |

**Rules:**
- Never `font-light` below `text-4xl` (display only). Page titles are `font-semibold`, so
  they outrank the `font-medium` heads beneath them by weight as well as size.
- `text-accent` (crimson) as **text** is AA only at large sizes (`text-xl`+). The ladder
  uses it for the display wordmark and `text-3xl` titles only; for `text-sm`/`text-xs`
  headings use `text-ink-strong`, or `text-link` (`#EC6B84` dark) for accent text — never
  `text-accent`.

## Country Display

Show country flag emoji with country name. Use `getCountryFlag(isoCode)` from `lib/geonames.ts`.

- **Display text**: Flag before name: `🇫🇷 France`
- **In `<select>` options**: Name before flag: `France 🇫🇷` (enables browser type-ahead)

## Material Design

- Clean card-based layouts with subtle shadows
- Crisp typography, good contrast
- Consistent spacing (4px grid)
- Rounded corners (4-8px)

## Auto-Save Pattern

**No explicit save buttons.** Changes save/sync immediately on input.

- Provide clear feedback (loading states, success indicators)
- No "Cancel" affordance on auto-save forms — changes persist as they're made, so the exit action is Close/Done, and a pending debounce is **flushed** on close (never dropped)
- Exception: genuinely irreversible or externally-visible actions gate behind an explicit confirm step; for everything else prefer clean reversibility over confirmation (no confirmation bloat)

## Mobile First

Design for touch devices first, then enhance for desktop.

- **Touch targets**: Minimum 44x44px
- **No hover-only interactions**: Always have tap/click equivalent
- **Tap-to-swap**: seating editor uses tap-a-player then tap-a-seat (same table = reorder, cross-table = swap, open seat = move); no drag-and-drop anywhere in the app
- **Focus ring**: A global `:focus-visible` crimson outline (2px, `--color-crimson-500`) is defined in `@layer base` in `app.css` — do not add bespoke outlines to buttons, links, or nav items. Form inputs may opt out with `focus:outline-none` only if they provide their own visible crimson focus indicator (border or ring).
- **Navigation**: Bottom nav or hamburger, not top-heavy headers
- **Forms**: Large inputs, avoid complex multi-column layouts on mobile
- **Containers**: Full-width on mobile, max-width on larger screens

## Modals

### Click Propagation

Modals must prevent click events from bubbling to parent elements. Always add `stopPropagation` to:
- Modal overlay (backdrop)
- Modal content container
- Forms inside the modal

```svelte
<div class="fixed inset-0 ..." onclick={(e) => e.stopPropagation()}>
  <div class="modal-content" onclick={(e) => e.stopPropagation()}>
    <form onclick={(e) => e.stopPropagation()}>
```

Without this, clicking inside a modal (e.g., on a text input) can trigger parent handlers like collapsing an expanded list item.

### Edit Modals vs Inline Actions

For objects with multiple actions (edit fields + lift + delete), prefer a dedicated edit modal over inline action buttons. Benefits:
- More space for editable fields
- Cleaner list UI (single edit button per item)
- Actions grouped logically in one place
- Easier to show/hide actions based on object state

### Captured State

When opening a modal from a list item, capture the item's data at open time:

```typescript
let editingItem = $state<Item | null>(null);

function openModal(item: Item) {
  editingItem = item;  // Capture snapshot
  showModal = true;
}
```

This prevents SSE sync updates from changing the modal's data mid-edit.

## Context-Specific Options

Scope form options by context. Example: sanctions from user list only allow PROBATION/SUSPENSION (global sanctions), while tournament view will allow all types (CAUTION, WARNING, DQ, etc.).
