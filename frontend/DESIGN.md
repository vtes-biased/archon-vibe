# Frontend Design Guidelines

## This doc vs. the `frontend-design` skill

This file is the project's **pinned visual direction** — the gothic VTES system below *is* the brief. The `frontend-design` skill (auto-invoked on UI work) contributes craft process and a quality floor; the two compose:

- **Existing surfaces & new features inside the app** → this doc wins. The skill's *craft* still applies: intentional type scale + weight hierarchy, structure that encodes meaning (don't decorate), motion restraint, copy as design material, and its quality floor — responsive, visible keyboard focus, `prefers-reduced-motion` honored. Its "pick a bespoke palette / take an aesthetic risk" guidance does **not** — stay on the token scale and patterns here. The skill defers by its own rule: a pinned brief always wins.
- **Genuinely new standalone surfaces** with no precedent here (e.g. a landing / onboarding page) → run the skill's full brainstorm → critique → build process, then fold durable decisions back into this doc.

When in doubt, consistency with this system beats novelty.

## Color Palette

VTES / Vampire: the Masquerade inspired. Gothic horror, pale and muted, with dark mode as primary.

| Name      | Light Mode        | Dark Mode         | Usage                        |
|-----------|-------------------|-------------------|------------------------------|
| `crimson` | `#8B0000`         | `#DC143C`         | Primary accent, CTAs         |
| `bone`    | `#F5F0E6`         | `#2A2520`         | Backgrounds                  |
| `dusk`    | `#E8E0D5`         | `#1C1A1E`         | Cards, surfaces              |
| `ash`     | `#6B6560`         | `#A09890`         | Text, borders                |
| `mist`    | `#9B9590`         | `#605850`         | Muted text, disabled states  |

Role badges use distinct colors but remain muted/dusty to fit the gothic aesthetic.

### Semantic Color Classes

Standard Tailwind status colors (green/amber/teal/…) are **off-palette** — the app uses a tight gothic-jewel set instead. Coloured UI elements use the semantic classes in `app.css`, each defined **once** with CSS `light-dark(LIGHT, DARK)` (the theme value is picked from `color-scheme`; **no** parallel `html.light` block — that was the old two-sources-of-truth bug).

**Hues:** blue (azure) · amethyst (purple) · fuchsia (magenta) · crimson · slate (neutral). **No green/amber/teal/cyan/lime/yellow/orange/indigo/rose.** Violet is reserved for destructive `btn-danger` only. All combos are WCAG-AA in both themes.

Two layers share these hues:

| Layer | Classes | Hue mapping |
|-------|---------|-------------|
| **Status** (meaning) | `badge-success`/`-pending`/`-danger`/`-info`/`-highlight` · `banner-info`/`-warn`/`-error`/`-highlight` · `toast-success`/`-warn` · `status-offline`/`-update` · `btn-success`/`-pending` · `dot-pending`/`-highlight`/`-danger` | success/info = blue · pending/warn = amethyst · danger/error = crimson · highlight = fuchsia |
| **Categorical** (identity) | `badge-blue`/`-amethyst`/`-fuchsia`/`-crimson`/`-slate` | arbitrary distinct tags (roles, link platforms) — pick by family, the hue is just a label |

**When to use what:**
- **Status classes** — anything carrying good/bad/attention *meaning*. Pair with an icon + text; colour is reinforcement, never the sole signal (see #225).
- **Categorical classes** (`badge-blue` etc.) — identity tags where the hue is arbitrary.
- `btn-*` — solid status chips only (paid/pending filter chips, help-guide mockups). **Action buttons go through `<Button>`** (below), which uses `bg-crimson-*` / `btn-danger`.
- `banner-*` — info/warning boxes (add `border rounded-lg p-3` etc.).
- Crimson palette classes (`bg-crimson-*`, `text-crimson-*`) — handled by scale inversion, use directly.

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
- `primary`/`secondary`/`ghost` use crimson/ash, which are scale-inverted (adapt to light mode automatically). `danger` uses `btn-danger`, defined with `light-dark()` (violet has no scale inversion).
- Props: `size` (`sm`/`md`/`lg`), `block` (full width), `loading` (spinner + `aria-busy`, auto-disables), `disabled`; extra layout classes (`flex-1`, margins) via `class`. Focus comes from the global `:focus-visible` ring — never add a bespoke outline.
- **Do not** route through `<Button>`: icon-only buttons, toggles/tabs/segmented controls, dropdown/menu options (e.g. the items inside `ActionMenu`), row/card-wrapping buttons, `<a>`-styled links, or Discord brand-fill buttons — leave those as raw elements.

**Palette history:** the crimson-primary system replaced the earlier scheme (emerald `primary`, crimson `brand`/`danger`, amber `warning`): `primary` → crimson, `danger` → violet `btn-danger`, `warning`/emerald dropped from `<Button>` (`btn-success`/`btn-pending` remain only for status chips + help-guide mockups). **#232 (mostly shipped):** the semantic component classes were recoloured to the gothic-jewel set (green/amber out; blue/amethyst/fuchsia/crimson/slate in) and migrated to `light-dark()` — no parallel `html.light` block — with WCAG-AA verified in both themes; raw inline green/amber tints swept to the palette. **Still deferred:** the full numeric-scale token migration (`bg-dusk-950`/`text-ash-400` → `surface`/`text`/`accent`/`border` role tokens across ~80 files); the crimson/bone/dusk/ash scale inversion keeps working until then.

### Disabled States

Action buttons use `<Button>`, which owns its disabled + loading states — never hand-roll them. For the remaining non-`<Button>` cases:

| Element | Disabled style |
|---------|---------------|
| `<Button>` | Built-in — pass `disabled` / `loading` |
| Form inputs (text, select, textarea) | `disabled:opacity-50` |
| Icon-only / small raw buttons | `disabled:opacity-40` |

`button:disabled { cursor: not-allowed }` is global in `app.css` — never add `disabled:cursor-not-allowed` inline.

### Light Theme — Scale Inversion

The crimson/bone/dusk/ash/mist **numeric scales** are theme-switched via **CSS variable overrides** under `html.light` in `app.css` — *scale inversion*: dark shade numbers (900/950) are reassigned to light color values and vice versa, so existing Tailwind classes (`bg-dusk-950`, `text-ash-300`, etc.) resolve to light-mode colors with zero component changes.

**Exception — semantic component classes** (`badge-*`, `banner-*`, `btn-*`, `toast-*`, `status-*`, `dot-*`) do **not** use inversion; each is a single `light-dark()` rule (see *Semantic Color Classes* above).

**Adding new colors**: a new `@theme` scale shade needs its inverted value under `html.light`; a new semantic component class needs a `light-dark()` rule instead.

**Theme toggle**: Users can cycle system / light / dark via the toggle in the sidebar (desktop) or bottom nav (mobile). Preference is stored in `localStorage.theme` and applied before first paint via an inline script in `app.html` to prevent FOUC.

**Store**: `$lib/stores/theme.svelte.ts` — `cycleTheme()`, `getTheme()`, `initTheme()`.

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
- Always allow undo/cancel/revert
- Exception: destructive or batch actions may require confirmation

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
