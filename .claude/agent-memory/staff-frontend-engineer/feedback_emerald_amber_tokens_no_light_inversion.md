---
name: button-component-light-mode-token-trap
description: Stock Tailwind tokens (blue/purple/violet/red/emerald/amber/etc) are NOT in app.css @theme or html.light — they don't follow light-mode scale inversion, unlike the semantic .badge-*/.btn-*/.banner-* classes (which now use light-dark())
metadata:
  type: feedback
---

Stock Tailwind color tokens (`blue`, `purple`, `violet`, `red`, `emerald`, `amber`, `slate`, etc.) have **no `--color-*` entry** in app.css `@theme` or under `html.light`. Only `crimson/bone/dusk/ash/mist` are scale-inverted. So `bg-blue-900/30`, `text-purple-400`, `text-red-200` resolve to the *same* fixed sRGB value in both themes and never pick up light-mode contrast adjustments. On a light surface (`dusk-950` inverts to `#FFFFFF`), dark-tuned tints fail AA: `text-blue-400`/`text-purple-400` on white ~2:1; `text-red-200` on `bg-red-900/30` over white ~1.1:1 (effectively invisible).

The semantic CSS classes — `.badge-success/-info/-blue/-pending/-amethyst/-danger/-crimson/-highlight/-fuchsia/-slate`, `.btn-success/-pending/-danger`, `.banner-info/-warn/-error/-highlight`, `.toast-success/-warn`, `.status-*`, `.dot-*` — DO handle both themes, but as of #232 (the gothic recolor) they do it via a single **`light-dark(LIGHT, DARK)`** declaration per class, NOT the old parallel `html.light {}` override block (that block is gone). `light-dark()` keys off `color-scheme`, which app.css sets to `light` on `html.light` and `dark` on `:root`. All semantic combos were verified WCAG AA 6.3–10:1 in both themes.

**Renames done in #232:** `badge-emerald→-success`, `badge-amber→-pending`, `banner-emerald/-blue/-red→-highlight/-info/-error`, `banner-amber→-warn`, `toast-emerald/amber→-success/warn`, `btn-emerald/amber→-success/pending`, `btn-red` removed. New gothic-jewel meaning layer: success/info=blue, pending/warn=amethyst(purple), danger/error=crimson, highlight=fuchsia. `btn-danger` stays violet (danger-button-only).

**Why:** the AA-verified figure only covers elements routed through the semantic classes. Raw inline tints (`text-blue-400`, `bg-purple-900/30`, `bg-red-900/30 text-red-200`) bypass that audit and silently break in light mode. The #232 recolor swept success→blue and warn→purple across many raw inline sites but left ~40+ raw `blue-*`/`purple-*` tints and 6 stray `red-*` error boxes un-converted — those don't invert. `red` is also off-palette (same hue family as crimson, different token) and should be `crimson-*` or `banner-error`.

**How to apply:** for any colored surface that must work in both themes, reuse a semantic class (`.badge-*`/`.btn-*`/`.banner-*`/`.toast-*`/`.dot-*`) rather than raw stock tints. When auditing a "recolor to palette" change, grep for raw `(bg|text|border|ring)-(blue|purple|violet|red|emerald|amber|...)-[0-9]` — a clean off-palette sweep of *converted* sites does NOT mean the raw-tint layer is theme-safe. Crimson/ash/dusk/bone/mist need no special handling — already inverted. Meaning must never rest on hue alone (#225): the raw status dots/icons here are OK because each has an adjacent text label or state/icon. See [[shared-button-component]], [[crimson-is-brand-not-primary-cta]].
