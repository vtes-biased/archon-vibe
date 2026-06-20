---
name: role-token-palette
description: The #247 migration replaced numeric Tailwind scales with light-dark() role tokens (surface/ink/line/accent); naming traps and consolidations to remember
metadata:
  type: project
---

#247 (shipped, on `main`) migrated the whole frontend off numeric color scales (`crimson/bone/dusk/ash/mist-NNN`) to ~17 **role tokens** defined once in `app.css` `@theme` via CSS `light-dark(LIGHT, DARK)`. The old `html.light` scale-inversion block is gone. Families: `surface` (bg), `ink` (text), `line` (border), `accent` (crimson). Authoritative table is in `frontend/DESIGN.md` § Color Palette.

**Why:** kill the dual-maintenance numeric ramp + parallel `html.light` override block; one token now carries both theme values.

**How to apply (the traps that survive the migration):**
- **`text-accent` ≠ accent text at body size.** `accent` dark `#DC143C` on cards is only ~3.46 (fails AA for normal text; OK for large `text-3xl+` headings/fills/borders/rings). For body/small accent **text** use `text-link` (dark `#EC6B84`, ~5.x — passes). The DESIGN.md wording "strong accent text" is misleading; several small links still use `text-accent` (User.svelte, CommunityTab.svelte, ProfileView.svelte, +layout mobile-nav active label) — these are pre-existing (faithful map from `text-crimson-500`), not regressions, but flag them.
- **`ink-faint`** is the low-contrast floor (~2.5–3.8 depending on surface) — only for genuinely tertiary/disabled text, never required reading.
- **Deliberate consolidation, NOT value-preserving:** the warm `dusk` surfaces were folded into cool `ash` neutrals — `bg-dusk-900`→`surface-muted`, `bg-dusk-800`→`surface-hover`. Visible shift (warm→cool) esp. in light-mode form fields (near-white→grey). Intended; codified in DESIGN.md.
- **`ink-strong`** absorbed bone-100/200/300 emphasis tiers — benign (all near-white in dark; all darken in light, gaining contrast). The ExampleBox header two-tone was restored manually after the merge collapsed it.
- Adding a color = one `--color-<role>: light-dark(LIGHT,DARK)` line + verify AA both themes. Never reintroduce a numeric ramp or `html.light` override block.

Related: [[feedback_crimson_is_brand_not_primary_cta]], [[feedback_emerald_amber_tokens_no_light_inversion]], [[project_shared_button_component]].
