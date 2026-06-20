---
name: crimson-is-brand-not-primary-cta
description: RESOLVED (2026-06-20) — owner picked crimson=primary CTA, danger=NOT red (use purple/amethyst), drop the amber warning tier. Verified danger-hue contrast + CVD math here. Prior green-primary recommendation kept below for reasoning only.
metadata:
  type: feedback
---

**STATUS (2026-06-20): DECIDED by owner.** The "open"/"prior" sections below are superseded — kept only for the reasoning that still informs the design. The owner's resolved direction:
1. **Crimson IS the primary CTA** (gothic identity; #DC143C dark / #8B0000 light). This merges the old `brand` + `primary` into one crimson variant — `brand` (40+ sites: Sign in/Create/Upload/Save/Approve) and forward-`warning` sites all converge on one crimson `primary`. It's a 2-into-1 merge, not a rename.
2. **Danger must NOT be red.** Red↔crimson are the same hue family → collapse. Use **purple/amethyst** (blue-channel-bearing hue restores CVD separation).
3. **Drop the `warning`/amber tier entirely.** Sparse palette: crimson=the one go CTA, ash=all secondary/ghost, amethyst=danger. Emerald dropped too.

**Why shape-not-hue (prior plan) was WRONG and a distinct hue works — the metric correction:** WCAG *luminance* contrast between two equally-dark saturated fills is always ~1.1–1.3 (that's lightness, not hue) — so "amethyst vs crimson = 1.1 luminance" does NOT mean they look alike. The right metric is **perceptual hue distance ΔE\*ab + the same simulated under each CVD type** (>~11 = clearly different; <~5 = confusable). Amethyst clears it everywhere; that's why danger can stay a confident SOLID fill, no outline workaround needed.

**Verified danger-hue facts (crimson primary fill anchor = crimson-700 #A40F2D dark, hue 24°; white text):**
- **Amethyst (RECOMMENDED danger):** dark `#6D28D9` / hover `#7C3AED` / light `#5B21B6`. White text 7.10 dark / 8.98 light ✅AA. ΔE vs crimson = 103 normal / **91 prot / 108 deut / 86 trit** — huge separation under all CVD. Muted dusty royal = best gothic fit.
- Fuchsia `#A21CAF` (alt): white text 6.32; ΔE 74/70/75/45 — safe but hotter/neon, hover dips to 4.71 (no AA headroom).
- Violet-indigo `#5B21B6`: great text contrast but only 1.92 vs dusk-950 bg → button shape goes faint on near-black. Avoid as danger fill.
- **PINK/ROSE REJECTED** (owner asked): rose `#BE185D` is hue 5° = same red family as crimson → ΔE only 23 normal and **collapses to 12.7 under tritanopia** (reads as crimson). The blue channel is what buys CVD separation; rose has none. Confirmed bad.
- Solid fill (not outline) for danger; **keep icon+verb (#225)** — colour is never the sole signal even when CVD-safe.

**`app.css` mechanics (post-#247):** the old `crimson-*`/`ash-*` numeric scales and the `html.light` scale-inversion block are **gone**. The palette is now semantic role tokens (`accent-strong`, `ink-muted`, etc.) via `light-dark()` in `@theme`. `.btn-danger` uses amethyst (`#6D28D9` dark / `#5B21B6` light) as a semantic CSS class with its own `light-dark()` declaration — no manual `html.light` override needed.
**AS SHIPPED (#228):** only the `brand`/`warning` variant keys were removed from `<Button>`. `btn-emerald`/`btn-amber` were KEPT in app.css — still used *raw* by help-guide mockups, the paid/pending filter chips (status colour, legit), and 2 list-page `<a>` CTAs; the mockup drift is tracked in #245. `btn-red` left defined-but-unused. `.btn-danger` (#6D28D9 dark / #5B21B6 light) added in both theme blocks. Folding `brand`→`primary` was a real 27-site call-site sweep.

**Re-homing the 13 live `variant="warning"` sites when amber drops (validated against code):** forward state actions (Close Reg, Finish Round ×2, Finish Finals) + in-modal confirms (Archon overwrite, override-save ×2, add offline player, Raffle Draw) → `primary`. Mode-switches gated by ConfirmActionModal (Go Offline, Force Takeover) + Timer Pause → `secondary` (caution carried by the modal, not button hue). **Call Judge** (PlayerView, made prominent in commit 751ffb6) was amber for *loudness* not as a forward CTA — fold to crimson `primary` full-width (loud enough); resist adding a 5th `attention` variant.

**Final variant map (tight, 4):** primary=crimson-700 (the one go CTA), secondary=ash-800, ghost=ash outline, danger=`btn-danger` amethyst+icon+verb.

**DESIGN.md drift:** lines 54–64 still document the OLD #232 plan which now contradicts this in two places ("crimson reverts to chrome only" and "danger moves to a distinct red") — both reversed. Update the table + "Planned palette (#232…)" paragraph in the same pass.

---

(PRIOR recommendation, pre-reopen — kept for the reasoning, which still informs the crimson-primary design above:)

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

**#247 token cleanup (DONE):** the numeric `crimson/bone/dusk/ash/mist` scales and the `html.light` scale-inversion block were replaced by semantic role tokens (`surface*`/`ink*`/`line*`/`accent*`/`link*`) in `app.css @theme`, all via `light-dark()`. See `frontend/DESIGN.md` Color Palette. (See also [[button-component-light-mode-token-trap]].)
