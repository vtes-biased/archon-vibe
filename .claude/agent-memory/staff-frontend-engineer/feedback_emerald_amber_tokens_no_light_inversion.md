---
name: button-component-light-mode-token-trap
description: Stock Tailwind emerald/amber/etc tokens are NOT in app.css @theme or html.light — they don't follow the light-mode scale inversion, unlike the .btn-*/badge-* CSS classes
metadata:
  type: feedback
---

Stock Tailwind color tokens (`emerald`, `amber`, `red`, `slate`, etc.) have **no `--color-*` entry** in app.css `@theme` or under `html.light`. Only `crimson/bone/dusk/ash/mist` are scale-inverted. So `bg-emerald-700` / `bg-amber-700` resolve to the *same* fixed sRGB value in both themes and never pick up light-mode contrast adjustments.

The legacy `.btn-emerald/.btn-amber/.btn-red` and `.badge-*` CSS classes DO hand-roll separate light-mode values (app.css ~262–273): light mode deliberately *darkens* the button bg (emerald-700 #047857 → emerald-800 #065f46; amber-700 #b45309 → amber-800 #92400e) so white text clears 4.5:1 on the near-white `dusk-950 #FFFFFF` surface. White on amber-700 #b45309 is ~3.4:1 — fails AA; on #92400e it passes.

**Why:** when building components with non-crimson semantic colors (the shared `<Button>` warning/primary variants), using bare `bg-emerald-700`/`bg-amber-700` silently regresses light-mode contrast vs the `btn-*` classes it replaces. Amber-on-white is the contrast cliff.

**How to apply:** for any non-crimson colored surface that must work in both themes, either (a) reuse the existing `.btn-*`/`.badge-*`/`.banner-*` CSS classes (they nail both modes incl. disabled), or (b) supply light/dark values explicitly via `dark:` prefixes — but first confirm how `dark:` is wired in this Tailwind v4 setup (it must key off `html:not(.light)`, since light is a class strategy, not `prefers-color-scheme`). Crimson/ash/dusk/bone/mist need no special handling — they're already inverted. See [[shared-button-component]].
