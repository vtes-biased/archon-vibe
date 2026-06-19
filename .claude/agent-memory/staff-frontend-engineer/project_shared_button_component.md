---
name: shared-button-component
description: The app-wide <Button> component (variant/size/block/loading/disabled) replacing btn-*/inline-crimson/ghost buttons — its variant set and the light-mode token trap
metadata:
  type: project
---

A single shared action-button component lives at `frontend/src/lib/components/Button.svelte`, replacing three legacy patterns: the `.btn-emerald/.btn-amber/.btn-red` semantic CSS classes (app.css ~217–229), inline `bg-crimson-*`, and border ghost buttons. ConfirmActionModal.svelte was the first consumer.

Variant set is fixed: `primary|secondary|warning|ghost|danger` (warning = the legacy amber action colour, kept deliberately — do not rename or drop it). Sizes: sm=text-xs, md=text-sm, lg=text-sm+font-medium. Props: variant/size/block/loading/disabled/type + `class` passthrough + `...rest`.

**Why:** owner mass-migrated ~130–150 action-button call-sites to it in one pass; the API was blessed before fan-out so it's expensive to change now.

**How to apply:** route new action buttons through `<Button>`, not `btn-*`/inline-crimson. Do NOT migrate icon-only/stepper/toggle/list-row buttons to it — those are a separate control class (DESIGN.md tier-3 `disabled:opacity-40`, 44px square targets) and `<Button>`'s rectangular sized padding shrinks them below 44px. See [[button-component-light-mode-token-trap]].
