---
name: project-focus-ring-floor
description: App-wide :focus-visible crimson ring is the keyboard-focus floor in @layer base; components opt out only with a self-provided crimson indicator
metadata:
  type: project
---

A global keyboard-focus ring lives in `@layer base` in `frontend/src/app.css`: `:focus-visible { outline: 2px solid var(--color-crimson-500); outline-offset: 2px; }`, plus a `.sr-only.peer:focus-visible + div` rule that projects the ring onto toggle tracks (the checkbox is `sr-only`/1px). It is the WCAG 2.4.7 floor (pst #220).

**Why:** No app-wide visible keyboard focus existed — only hover styling. Venues require a11y compliance. Placed in `@layer base` so Tailwind utilities (a later layer) override it per-control.

**How to apply:**
- Do NOT add bespoke `focus`/`focus-visible` outlines to buttons, links, or nav items — the floor covers them. (The former inline opt-out on the login consent checkbox was dropped — the floor now covers it.)
- A component may use `focus:outline-none` ONLY if it provides its own visible crimson focus indicator (a `focus:ring-*` or `focus:border-*` on the same element). This opt-out contract is pinned in `frontend/DESIGN.md` (Mobile First § Focus ring). All ~14 `focus:outline-none` sites currently honor it — when reviewing new form inputs, verify the pair.
- Ring contrast holds on every surface because `outline-offset: 2px` inserts a page-background gap (ring-vs-bg, not ring-vs-element) — so even the active crimson nav item and crimson CTAs pass. Preserve the offset if anyone touches this.
- Craft layer (applied): a soft crimson `box-shadow` glow sits under the hard outline — `0 0 8px color-mix(in srgb, var(--color-crimson-500) 45%, transparent)`. Deriving it via `color-mix` off crimson-500 means it auto-follows the [[scale-inversion]] (no `html.light` override needed). Hard outline kept underneath for 1.4.11; the glow may be clipped by an `overflow:hidden` ancestor — harmless.

Related: [[feedback_no_lineclamp_on_markdown]] (other DESIGN.md-anchored standards).
