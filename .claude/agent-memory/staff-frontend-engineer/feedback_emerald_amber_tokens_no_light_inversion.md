---
name: button-component-light-mode-token-trap
description: Stock Tailwind tokens (blue/purple/violet/red/emerald/amber/etc) are NOT in app.css @theme — they don't follow light-dark() theming, unlike the semantic role tokens (surface*/ink*/line*/accent*/link*) and .badge-*/.btn-*/.banner-* classes
metadata:
  type: feedback
---

**As of #247 (semantic role token migration):** the old numeric scales `crimson/bone/dusk/ash/mist` and the `html.light` scale-inversion override block are **gone**. The design system is now ~17 role tokens defined once via CSS `light-dark(LIGHT, DARK)` in `app.css @theme`: families `surface*`, `ink*` (text), `line*` (borders), `accent*`/`link*` (crimson). Use `bg-surface-card`, `text-ink-muted`, `border-line`, `text-link`, etc. See `frontend/DESIGN.md` Color Palette for the full table.

Stock Tailwind color tokens (`blue`, `purple`, `violet`, `red`, `emerald`, `amber`, `slate`, etc.) have **no `--color-*` entry** in `app.css @theme`. So `bg-blue-900/30`, `text-purple-400`, `text-red-200` resolve to the *same* fixed sRGB value in both themes and never pick up light-mode adjustments. On a light surface, dark-tuned tints fail AA: `text-blue-400`/`text-purple-400` on white ~2:1; `text-red-200` on `bg-red-900/30` over white ~1.1:1 (effectively invisible).

The semantic CSS classes — `.badge-success/-info/-blue/-pending/-amethyst/-danger/-crimson/-highlight/-fuchsia/-slate`, `.btn-success/-pending/-danger`, `.banner-info/-warn/-error/-highlight`, `.toast-success/-warn`, `.status-*`, `.dot-*` — DO handle both themes via `light-dark(LIGHT, DARK)` declarations. `light-dark()` keys off `color-scheme`, which `app.css` sets to `light` on `html.light` and `dark` on `:root`. All semantic combos were verified WCAG AA 6.3–10:1 in both themes.

**Renames done in #232:** `badge-emerald→-success`, `badge-amber→-pending`, `banner-emerald/-blue/-red→-highlight/-info/-error`, `banner-amber→-warn`, `toast-emerald/amber→-success/warn`, `btn-emerald/amber→-success/pending`, `btn-red` removed. New gothic-jewel meaning layer: success/info=blue, pending/warn=amethyst(purple), danger/error=crimson, highlight=fuchsia. `btn-danger` stays violet (danger-button-only).

**Why:** the AA-verified figure only covers elements routed through the semantic role tokens or semantic classes. Raw inline tints (`text-blue-400`, `bg-purple-900/30`, `bg-red-900/30 text-red-200`) bypass that audit and silently break in light mode. `red` is off-palette (same hue family as crimson, different token) and should be `crimson-*` or `banner-error`.

**How to apply:** for any colored surface that must work in both themes, use a role utility (`bg-surface-*`, `text-ink-*`, `border-line-*`, `text-accent-*`) or a semantic class (`.badge-*`/`.btn-*`/`.banner-*`/`.toast-*`/`.dot-*`) rather than raw stock or old numeric-scale tints. When auditing a "recolor to palette" change, grep for raw `(bg|text|border|ring)-(blue|purple|violet|red|emerald|amber|...)-[0-9]` — those don't adapt to theme. **Still-unswept after #247** (alert-box backgrounds were converted, but inline text accents were not): `text-purple-400`/`text-blue-400` in `RoundsTab.svelte`, `PlayerView.svelte`, `OrganizerGuide.svelte` — obvious next sweep target. Meaning must never rest on hue alone (#225): raw status dots/icons are OK when they have an adjacent text label or state/icon. See [[shared-button-component]], [[crimson-is-brand-not-primary-cta]].
