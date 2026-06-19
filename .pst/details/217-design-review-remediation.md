# 217 — Production design-review remediation

Epic tracking the pre-production UX / accessibility / visual-system review of the
mobile-first PWA. The ticket map + sequencing are below; the **full source review is
folded in verbatim at the bottom** of this file (its root `archon-design-review.md`
was removed once captured here, so this detail file is the single source of truth).

## Framing
- ~90% of users are players → player flow leads.
- In-venue context: a phone, one hand, poor light, time pressure, five languages.
- Severity reflects **launch risk** for that context, not abstract polish.

## Priority mapping (review level → pst tag)
| Review | Meaning | pst tag |
|---|---|---|
| **P0** | Blockers — fix before launch | **p1** |
| **P1** | High — fix in the launch window | **p2** |
| **P2** | Polish — fast-follow | **p3** |

## Launch sequencing (#39)
The review frames the **p1 set (#218–#222)** as "land before the #39 phase-1 cutover."
Recorded here as `relates:#39`, **not** a hard `depends` — #39 is the one active
thread and gating it is the owner's call. Revisit when scheduling the cutover.

## Children
### p1 — review P0 · launch blockers
| # | Finding | Primary file |
|---|---|---|
| 218 | Enlarge player VP-report control (tiny `<select>` → ≥44px stepper, hero control) | `tournaments/[uid]/PlayerView.svelte` |
| 219 | Hoist "your table + seat" to top of player view when Playing | `tournaments/[uid]/PlayerView.svelte` |
| 220 | Global `:focus-visible` ring (WCAG 2.4.7) | `app.css`, `+layout.svelte` |
| 221 | Seating editor tap/keyboard alternative to drag (DESIGN.md requires it) | `lib/components/SeatingSortable.svelte` |
| 222 | Fixed status/update banners cover content → normal-flow layout | `+layout.svelte` |

### p2 — review P1 · launch window
| # | Finding | Primary file |
|---|---|---|
| 223 | "Call Judge" emergency action → prominent ≥44px control | `tournaments/[uid]/PlayerView.svelte` |
| 224 | "Upload a valid deck" → inline actionable CTA + validation errors | `tournaments/[uid]/PlayerView.svelte` |
| 225 | Colourblind-safe severity + connection (icon/shape + text) | `SeatingSortable.svelte`, `+layout.svelte` |
| 226 | Bottom-nav label size 10px → 11–12px; verify longest locale | `+layout.svelte` |
| 227 | Single `<Button variant>` component (collapses 3-tier disabled rule) | `app.css` + tournament views |
| 228 | Reduce action-bar density → 1 primary CTA + "More" overflow | `tournaments/[uid]/+page.svelte` |
| 229 | Strengthen offline ownership / data-loss model + first-run explainer | `tournaments/[uid]/+page.svelte`, `TournamentModals.svelte` |

### p3 — review P2 · polish / fast-follow
| # | Finding | Primary file |
|---|---|---|
| 230 | Legend/tooltips for GW / VP / TP | `tournaments/[uid]/PlayerView.svelte` + standings |
| 231 | Number seats, mark player's row, loosen spacing | `tournaments/[uid]/PlayerView.svelte` |
| 232 | AA contrast audit both themes + semantic-token migration | `app.css` |
| 233 | Tighten type scale + weight hierarchy | `app.css` |
| 234 | Non-QR check-in fallback + camera-error path | `PlayerView.svelte`, `QrCheckinScanner.svelte` |
| 235 | Degraded-mode states: toast → durable banner | `+layout.svelte` |

## Cross-cutting notes
- **i18n x5** on implementation for any child adding user-facing strings: 221, 224,
  229, 230, 234 (and any new labels in 223/225/226).
- **Agent workflow**: route each child's implementation through `staff-frontend-engineer`
  (UX/mobile) and `i18n-translator` (strings); `documentalist` for `frontend/DESIGN.md`
  where a finding contradicts the documented rule (e.g. 221 non-drag alternative, 227
  three-tier disabled states).
- **Natural batches** (land together if picked up): 227+228 (Button component then
  action-bar density consume it); 219+231 (player table/seat card + seat numbering);
  225 severity icons reuse for any new status iconography.

---

## Source review (verbatim — from the removed root `archon-design-review.md`)

# Archon — Production Design Review

**Design Review · Pre-production**

UX & visual design review for the VTES tournament organizer, ahead of the production launch.

| | |
|---|---|
| **Scope** | Mobile-first PWA · offline & online |
| **Surfaces reviewed** | Player flow · organizer console · auth · lists |
| **Status** | Beta → production |

---

## How to read this

The build is feature-rich and the engineering is solid — the issues below are about **readiness for real players in a real venue**: a phone, one hand, poor light, time pressure, five languages. Findings are grouped by audience, then prioritised. Because **~90% of users are players**, the player experience leads.

| Priority | Count | Meaning |
|---|---|---|
| **P0** | 5 | Blockers — fix before launch |
| **P1** | 7 | High — fix in the launch window |
| **P2** | 6 | Polish — fast-follow |

---

## What's already strong

- ✓ Coherent gothic theme with a real token scale and disciplined dark-first design.
- ✓ Thoughtful state machine surfaced as a step indicator + plain-language guidance.
- ✓ Genuinely offline-first, with degraded-state messaging the team clearly thought about.
- ✓ Five-language i18n wired through, with auto-save and no-save-button discipline.
- ✓ Spinner-flash delays and "capture state on modal open" show real UX care.
- ✓ Confirmations on destructive actions; QR check-in as a fast-path for crowds.

---

## 01 · Player experience — the 90%

### P0 — The one thing every player does (report VP) is a tiny dropdown
**Touch target · core task**

Score reporting uses a `text-xs` native `<select>` at roughly 24px tall — about half the 44px minimum the project's own guidelines mandate. Seat rows sit at `py-1.5` (~6px), so four-to-five score controls are stacked in a cramped column. This is the single most-repeated player interaction, done with one thumb at a table.

**Fix:** Replace the dropdown with a large VP stepper or segmented control (0 / 0.5 / 1 …), full-width rows, ≥44px hit areas, clear "saving / saved" feedback. This is the player view's hero control — give it room.

*Seen in `PlayerView.svelte`*

### P0 — "Which table am I at?" is buried below status, score and standings
**Information hierarchy**

During play, the thing a player urgently needs — their table and seat — renders *after* the status line, current score, cutoff card and the full standings table. On a phone that's a scroll past several blocks at exactly the moment a round is being called.

**Fix:** When state is Playing, hoist "Your table + seat position" to the top of the player view as the primary card; push standings, cutoff and history below it. Seat order matters in VTES (predator/prey) — show the player where they sit at a glance.

*Seen in `PlayerView.svelte`*

### P1 — "Call Judge" — an emergency action — is the smallest control on the table
**Affordance**

It renders as a `text-xs` ghost button with a 12px icon, tucked next to the table-state badge. When a player needs a judge, they're often flustered — this should be impossible to miss, not the tiniest tap target on screen.

**Fix:** Give it a clear, full-width or prominently sized button within the table card, ≥44px, with an unmistakable label. Keep the 30s cooldown feedback but make the resting state confident.

*Seen in `PlayerView.svelte`*

### P1 — "Upload a valid deck" is a passive warning, not a way to fix it
**Actionability**

When a decklist is required, the player sees amber warning text where the check-in button would be — but no upload control beside it. They have to find the deck section elsewhere on the page, fix it, and come back. At the door, that's friction at the worst moment.

**Fix:** Make the warning actionable: an inline "Upload deck" button right there, and surface the specific validation errors so the player knows what's wrong.

*Seen in `PlayerView.svelte`*

### P2 — Score jargon ("0GW 1.5VP 12TP") is unexplained for casual players
**Comprehension**

Standings and table rows pack three abbreviations together with no legend. Veterans read it instantly; a first-time attendee does not. Since most users are players and many are newcomers, the shorthand quietly excludes them.

**Fix:** Add a one-tap legend or tooltips (Game Wins / Victory Points / Tournament Points), and spell terms out at least once per screen. Lean on progressive disclosure rather than dense abbreviation.

### P2 — Seat rows are cramped and seat order isn't labelled
**Density · clarity**

Tables list players in seating order, but nothing labels seats 1–5 or marks the player's own seat, predator and prey — information that matters in VTES. Combined with the tight row spacing, the table is hard to parse at a glance.

**Fix:** Number the seats, highlight the current player's row, and loosen vertical spacing. Optionally label predator/prey relative to "you".

---

## 02 · Accessibility & touch — everyone

### P0 — No app-wide visible focus state
**Keyboard / a11y**

Buttons, tabs and nav items carry `hover:` styling but no `focus-visible` ring. A few controls (e.g. the login consent box) opt in individually, but it isn't systematic. Keyboard, switch-access and screen-magnifier users can't tell where they are — a WCAG 2.4.7 failure that also blocks accessibility compliance many venues/orgs require.

**Fix:** Add one global `:focus-visible` ring (the crimson ring already implied by the design language) on all interactive elements, and run a keyboard-only pass of the core flows.

*Seen across `app.css`, `+layout.svelte` & tournament views*

### P1 — Meaning carried by colour alone (not colourblind-safe)
**Colour vision**

Seating issue severity is encoded as crimson / amber / sky with an identical alert icon for all three — and amber-vs-crimson is exactly the red/green confusion axis (~8% of men). The connection indicator is a 12px dot that's only distinguishable by colour (amber / emerald / crimson).

**Fix:** Differentiate by shape/icon and text, not colour only. The issue text is already present — pair each severity with a distinct icon; give the connection dot a label or icon state.

*Seen in `SeatingSortable.svelte`, `+layout.svelte`*

### P1 — 10px truncated labels in the mobile bottom nav
**Legibility · i18n**

The primary mobile nav has six items with `text-[10px]` truncated labels. 10px is below a comfortable minimum, and FR / ES / PT-BR / IT words are longer than the English — they'll truncate to ambiguity in the very languages you ship.

**Fix:** Bump to ~11–12px, verify each label in the longest locale, and consider dropping to five primary destinations so labels breathe.

*Seen in `+layout.svelte`*

---

## 03 · Visual system & consistency

### P1 — Three competing button patterns and hand-rolled disabled states
**Consistency · maintenance**

Actions appear as semantic classes (`.btn-emerald` / `.btn-amber`), as inline `bg-crimson-700`, and as `border` ghost buttons — often in the same toolbar. DESIGN.md already documents *three different disabled-state tiers* to keep them in line, which is a tell that the abstraction is missing.

**Fix:** Introduce one `<Button variant=…>` with primary / secondary / ghost / danger variants and built-in disabled + loading states. The three-tier disabled rule then collapses into one.

*Seen in `app.css` & throughout the tournament views*

### P2 — Light mode by "scale inversion" is brittle
**Theming · contrast**

Light theme is built by reassigning shade numbers (900 → light, 50 → dark). It's clever and zero-touch for components, but the crimson scale already needs an admitted "not a pure inversion" hand-tuning, every new colour must be manually inverted or it breaks, and the semantic badge/btn/banner classes maintain a parallel light-mode block. That's two sources of truth drifting apart, with contrast bugs as the failure mode.

**Fix:** For launch: audit every badge / button / banner combination for WCAG AA in *both* themes. Longer term, migrate to semantic role tokens (surface / text / accent / border) so each theme defines roles once instead of inverting a numeric ramp.

*Seen in `app.css`*

### P2 — Thin headings and weak hierarchy hurt legibility in venues
**Typography**

Page titles and the wordmark use `font-light`; most body text is a single size of mid-grey `ash-400`. Thin weight on a dark theme, read in low light or bright sun at a game store, is fatiguing — and the flat hierarchy makes scanning harder.

**Fix:** Establish a small type scale with real weight contrast (e.g. semibold titles, regular body), and reserve the lightest weight for large display sizes only.

---

## 04 · Organizer workflow — under time pressure

### P0 — Seating editor is drag-only — no fallback, keyboard-inert
**Interaction · a11y**

Moving players between tables is the highest-stakes organizer action, and it's only possible by drag-and-drop (with a touch polyfill + manual auto-scroll — a notoriously fragile combination on mobile). DESIGN.md explicitly requires a non-drag alternative; there isn't one. The handle is `tabindex=0` but has no key handler, so it's focusable yet does nothing for keyboard users.

**Fix:** Add a tap-based alternative: tap a player → "Move to table N / swap with…" menu. It serves keyboard users, fixes the touch-fragility risk, and satisfies the project's own design rule. Keep drag as an enhancement.

*Seen in `SeatingSortable.svelte`*

### P1 — The action bar offers up to ~7 buttons with weak primary/secondary hierarchy
**Cognitive load**

In the Waiting state alone an organizer sees Start Round, Start Finals, Check All In, Mark All Paid, Reset Check-in, QR, plus a Finish / Reopen danger row — differentiated mostly by colour. Under time pressure with players waiting, that's a lot to scan to find "the next thing".

**Fix:** One unmistakable primary CTA per state; collapse secondary actions into a "More" overflow; keep danger actions separated (they already are) but give them a clearer destructive treatment than a faint text link.

*Seen in `tournaments/[uid]/+page.svelte`*

### P2 — Player self-check-in is QR-only
**Robustness**

The player's self-serve check-in path depends on scanning the organizer's QR code. If the camera permission fails, the room is dark, or the code isn't being displayed, the player has no in-app fallback (the organizer can still check them in manually, so it's not a hard block — but it's a single point of failure at the busiest moment).

**Fix:** Offer a tap-to-check-in fallback (or a short code entry) alongside the scanner, and a clear camera-permission error with the manual path.

*Seen in `PlayerView.svelte`, `QrCheckinScanner.svelte`*

---

## 05 · Offline, status & trust

### P0 — Status & update banners are fixed overlays that cover content
**Layout**

Offline and "update available" banners are `position:fixed` at the top, stacked with a manual `top-10` nudge, while page content reserves no space for them. On the surfaces that matter most when offline, the banner can sit on top of the page header — the exact moment the user most needs both.

**Fix:** Put the status region in normal flow (or offset the main content by the banner height) so banners push content down instead of covering it, and handle the multi-banner stack with layout rather than hard-coded offsets.

*Seen in `+layout.svelte`*

### P1 — Offline ownership & data-loss risk is under-communicated
**Mental model · data loss**

The app's most distinctive feature — single-device offline ownership, with force-takeover that can discard another device's unsaved data — is conveyed through amber/grey banners, confirm modals, and a 12px sidebar dot. For something with genuine data-loss consequences, the status model is easy to misread, and there's no first-run explanation of how going offline works.

**Fix:** Give offline a prominent, persistent status treatment (which device owns the event, when it last synced) and a short one-time explainer. Make force-takeover's data-loss wording unambiguous and require deliberate confirmation.

*Seen in `tournaments/[uid]/+page.svelte`, `TournamentModals.svelte`*

### P2 — A critical engine failure is surfaced as a toast
**Feedback durability**

A WASM engine load failure disables permission checks, optimistic writes and standings — a genuinely degraded app — yet it's shown as a (persistent) toast competing for the same space as transient confirmations. It's good that it's surfaced at all; the channel just doesn't match the severity.

**Fix:** Promote degraded-mode states to a durable banner that explains what's limited and how to recover, separate from the transient toast stack.

*Seen in `+layout.svelte`*

---

## Prioritised punch list

### P0 — Block the launch
1. Enlarge the player VP-report control to ≥44px (core task).
2. Hoist "your table + seat" to the top of the player view during play.
3. Add a global visible `:focus-visible` state.
4. Give the seating editor a tap/keyboard alternative to drag.
5. Stop fixed status banners from covering page content.

### P1 — Fix in the launch window
1. Promote "Call Judge" to a prominent, large control.
2. Make "upload a valid deck" an inline, actionable CTA.
3. Make severity & connection status colourblind-safe (icon + text).
4. Raise bottom-nav label size; verify in the longest locale.
5. Standardise a single Button component with variants.
6. Reduce action-bar density to one primary CTA + overflow.
7. Strengthen the offline ownership / data-loss model.

### P2 — Polish · fast-follow
1. Add a legend/tooltips for GW / VP / TP.
2. Number seats, mark the player's row, loosen spacing.
3. Audit AA contrast in both themes; plan semantic-token migration.
4. Tighten the type scale and weight hierarchy.
5. Add a non-QR check-in fallback + camera-error path.
6. Move degraded-mode states from toast to a durable banner.

---

*Scope note: this is a heuristic review from the source — UX, accessibility and visual-system level, not a line-by-line audit or a substitute for usability testing with real players and organizers. Severity reflects launch risk for the mobile, in-venue context. Findings reference the SvelteKit frontend as reviewed.*
