---
name: crimson-is-brand-not-primary-cta
description: Design call — crimson is brand/chrome, NOT the primary action-button fill; emerald=primary(go), btn-red=danger; don't collapse the green/amber/red lifecycle ramp into one red
metadata:
  type: feedback
---

In the gothic VTES app, the recurring instinct "brand color (crimson) = primary CTA fill" is **wrong**, and I recommended against it when the owner asked "what does design think?" about reworking the button palette.

**Rule:** crimson stays **brand + system chrome only** (wordmark, global :focus-visible ring, active nav, selection, glow). It is NOT the primary action-button fill. The action-button vocabulary is a green→amber→red **severity/lifecycle ramp**:
- `primary` (forward/confirm) = **emerald** — Start Round, Register, Check-in, Create, Save, Approve, Sign in/up, Upload. (Currently called `primary` in [[project_shared_button_component]]'s variant map.)
- `warning` (caution, reversible) = **amber** — Close Reg, Finish Round, Go Offline, Check-out.
- `danger` (destructive, hard-undo) = **btn-red** `#b91c1c`/`#991b1b` (a hardware-store red, distinct from crimson's pinker `#A40F2D`) — NOT crimson. `btn-red` already exists in app.css with both-theme handling and was unused.

**Why:**
1. Green=go is a strong pre-attentive affordance and the tournament lifecycle (go/caution/stop) is real semantics, not decoration — flattening it into one crimson destroys forward-action scanning for a TO mid-round.
2. Brand colors read as brand because they're *rationed*; making crimson the default fill on every form destroys its gothic identity.
3. Red-vs-red is the WORST colourblind case (cf. #225). If crimson were both primary AND danger, Save and Delete would be the same saturated red — the two most consequential buttons indistinguishable under CVD. Keep a hue gap (green vs red) + back it with icon+text. Don't spend your hardest color pair on Save-vs-Delete. Don't use orange for danger — it collides with amber.

**How to apply:** When asked to make crimson the primary button, push back with the above. For any palette/variant rework: crimson→chrome only, emerald→primary, btn-red→danger (icon-forward), amber→warning. The palette rethink belongs in ticket #232 (semantic role tokens + WCAG-AA-both-themes audit), NOT bundled into the button migration — ship the component with colors preserved first, recolor centrally later (one VARIANT-map swap). Tag the ~150 call-sites by *intent* (danger vs brand vs primary), not current color, so #232 is a pure central recolor.

**#232 token cleanup:** emerald + amber are stock Tailwind tokens with bespoke `html.light` overrides (see [[feedback_emerald_amber_tokens_no_light_inversion]]) — #232 should move them into the `@theme`/CSS-var system so they invert by rule like crimson/ash.
