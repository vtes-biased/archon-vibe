# Design

The pinned visual direction. The gothic VTES system below *is* the brief — the
`frontend-design` skill contributes craft process and a quality floor, but its
"pick a bespoke palette, take an aesthetic risk" guidance does not apply to
surfaces inside the app; the skill defers to a pinned brief by its own rule. A
genuinely new standalone surface with no precedent here — a landing or onboarding
page — earns the skill's full process, after which the durable decisions fold back
into this page. **Consistency with this system beats novelty.**

## Palette

VTES / Vampire: the Masquerade inspired: gothic horror, pale and muted, dark mode
primary.

`@theme` is not colour-only — it is the general Tailwind v4 design-token registry,
and also holds the layout tokens for safe-area insets and the nav footprint (see
*Mobile first*).

Colour is expressed as **role tokens** in four families — `surface` (backgrounds),
`ink` (text), `line` (borders) and `accent` (crimson). Each token is defined
**once** in `app.css` `@theme` via CSS `light-dark(LIGHT, DARK)`, so its value
follows the element's `color-scheme` automatically. There is **no** per-shade
`html.light` override block and **no** numeric scale to hand-invert — that was the
old two-sources-of-truth bug. Use them as ordinary Tailwind utilities, opacity
modifiers included.

| Token | Light | Dark | Role |
|---|---|---|---|
| `surface` | `#F5F0E6` | `#2A2520` | page background |
| `surface-card` | `#FFFFFF` | `#1C1A1E` | cards, panels |
| `surface-muted` | `#E8E6E4` | `#3D3A37` | subtle row / overlay |
| `surface-hover` | `#D4D0CC` | `#4A4642` | interactive hover |
| `surface-active` | `#B8B2AC` | `#5A5550` | solid neutral control |
| `ink-strong` | `#5E5444` | `#FAF8F4` | headings, emphasis |
| `ink-bright` | `#4A4642` | `#D4D0CC` | bright body, labels |
| `ink` | `#5A5550` | `#B8B2AC` | default body text |
| `ink-muted` | `#6B6560` | `#9A938C` | secondary text |
| `ink-faint` | `#7D756E` | `#7D756E` | tertiary / disabled |
| `line` | `#D4D0CC` | `#4A4642` | default border, divider |
| `line-strong` | `#B8B2AC` | `#5A5550` | stronger border |
| `accent` | `#A40F2D` | `#DC143C` | brand crimson — fills, borders, rings, large display headings |
| `accent-strong` | `#880C26` | `#A40F2D` | CTA button solid |
| `accent-strong-hover` | `#960D29` | `#C41235` | CTA hover |
| `accent-soft` | `#FCE4E8` | `#6E0A1F` | accent tint background |
| `accent-soft-border` | `#F9CCD4` | `#880C26` | accent tint border |
| `link` | `#DC143C` | `#EC6B84` | links, accent text |
| `link-soft` | `#C41235` | `#F4A3B3` | light accent text on tint |
| `info` | `#1e40af` | `#60a5fa` | status — azure; info / positive |
| `warn` | `#6b21a8` | `#c084fc` | status — amethyst; pending / warning |
| `highlight` | `#86198f` | `#e879f9` | status — fuchsia; mid severity |
| `select` | `#1e40af` | `#60a5fa` | selection affordance — azure; a **purpose** token, not a status meaning |
| `select-border` | `#bfdbfe` | `#1e3a8a` | select border |
| `select-soft` | `#eff6ff` | `#1e3a8a` | select tint, always with opacity |

`accent` as body-size **text** is only ~3.5:1 on cards — AA for large text only.
Use `link` for body-size accent text. `ink-faint` is a single grey for both themes
and does not clear the 4.5:1 body floor: keep it to de-emphasised and disabled
text.

**Adding a colour**: one `--color-<role>: light-dark(LIGHT, DARK)` line in
`@theme`, AA verified in both themes. **Never** reintroduce a numeric ramp or an
`html.light` override block.

**Theme toggle**: system / light / dark, stored in `localStorage.theme` and applied
before first paint by an inline script in `app.html` to prevent a flash. The light
theme does one thing: `html.light { color-scheme: light }`.

### Semantic classes

Standard Tailwind status colours are **off-palette**. The app uses a tight
gothic-jewel set: **blue (azure), amethyst (purple), fuchsia (magenta), crimson,
slate**. **No green, amber, teal, cyan, lime, yellow, orange, indigo or rose.**
Violet is reserved for destructive `btn-danger`. All combinations are WCAG-AA in
both themes, and each class is defined once with `light-dark()`.

| Layer | Classes | Hue mapping |
|---|---|---|
| **Status** — meaning | `badge-*`, `banner-*`, `toast-*`, `status-*`, `btn-success`/`-pending`, `dot-*`, `text-info`/`text-warn`/`text-highlight` | success and info = azure · pending and warn = amethyst · danger and error = crimson · highlight = fuchsia |
| **Categorical** — identity | `badge-blue`/`-amethyst`/`-fuchsia`/`-crimson`/`-slate` | arbitrary distinct tags; the hue is just a label |

Raw stock Tailwind colour utilities do not adapt to the theme — use role utilities
or these semantic classes, never `bg-emerald-*`-style tints.

When to use what: **status text tokens** for inline status text and standalone
icons where a badge would be too heavy; **status classes** for component-level
status; **selection tokens** for the seating tap-to-swap affordance only, never for
status; **categorical classes** for identity tags. `banner-*` is for info and
warning boxes and **never on a chip** — a bordered `banner-warn` span reads as a
shrunken alert box next to real badges; use a status badge.

### Badges

`Badge.svelte` owns every chip. Never hand-roll the utility string. It takes a
**kind**, which is a grammar the reader can triage on, plus a **tone**:

| Kind | Means | Looks like |
|---|---|---|
| `status` | carries meaning — tournament state, sanction severity, sync warnings | the coloured one; keep it rare per row |
| `identity` | names the thing — format, rank, role, league kind | quiet neutral, unless the hue *is* the label as with roles |
| `link` | goes somewhere | taller (32px), hover fade |
| `control` | does something | taller (32px), bordered, pressable |

The height difference is the affordance, not just the touch target: an inert label
never grows. **One row carries one meaning-bearing colour** — if everything is
coloured the eye has nothing to triage on. Tone lookups live beside their data and
return tone names, never classes, so a chip cannot drift back into raw utilities.

### Colourblind-safe severity

Every severity or status tier is a fixed colour token **plus** a shape-distinct
lucide icon **plus** a text label. Colour is reinforcement, never the sole signal.

| Tier | Token | Icon |
|---|---|---|
| Blocking | `text-link` (crimson) | `OctagonX` |
| Strong | `text-highlight` (fuchsia) | `TriangleAlert` |
| Soft | `text-warn` (amethyst) | `Info` |

The connection indicator likewise uses a distinct icon per state: `Wifi` online,
a spinning `RefreshCw` syncing (with `motion-reduce:animate-none`), `WifiOff`
offline.

### Buttons

All action buttons go through `Button.svelte`, which owns colour, size and the
disabled and loading states, so call sites pass intent rather than classes.

| Variant | Colour | Intent |
|---|---|---|
| `primary` | crimson | **every** affirmative action — lifecycle CTAs and form/auth submits alike |
| `danger` | **violet** | destructive: delete, drop, force-takeover, cancel round, finish tournament |
| `secondary` | neutral solid | neutral secondary action, bulk utilities, the More overflow trigger |
| `ghost` | neutral outline | tertiary, de-emphasised |

**One primary CTA per surface.** Crimson is the single positive colour, so a screen
shows one filled crimson button and collapses the rest into an overflow menu. A
legitimate second lifecycle choice — Start Round versus Start Finals — drops to
`secondary`, never a second `primary`.

**Danger is violet, never red.** Red and crimson are the same hue family and
collapse together even under colourblindness, so destructive actions get their own
hue. Meaning must not rest on hue alone: pair `danger` with an icon and a verb.

Props: `size`, `block`, `loading` (spinner, `aria-busy`, auto-disables),
`disabled`; extra layout classes via `class`. Focus comes from the global
`:focus-visible` ring — never add a bespoke outline.

**Do not** route through `Button`: icon-only buttons, toggles, tabs, segmented
controls, dropdown and menu options, row- or card-wrapping buttons, `<a>`-styled
links, or Discord brand-fill buttons.

Disabled states: `Button` owns its own. Form inputs use `disabled:opacity-50`,
icon-only and small raw buttons `disabled:opacity-40`.
`button:disabled { cursor: not-allowed }` is global — never add it inline. Cursor
affordance is global too, so a missing per-button `cursor-pointer` is not a defect.

## Typography

Hierarchy is carried by **weight contrast**, not just size — the venue is a phone
in low light or bright sun on a dark theme, where thin strokes are fatiguing.

| Role | Size | Weight | Colour |
|---|---|---|---|
| Display / wordmark | `text-4xl` | `font-light` | `text-accent` — the **only** sanctioned `font-light`, and only at `text-4xl`+ |
| Page title `h1` | `text-3xl` (`text-2xl` on tight cards) | `font-semibold` | `text-accent`, or `text-ink-strong` on a coloured surface |
| Section `h2` | `text-xl` | `font-medium` | `text-ink-strong` / `text-link` |
| Subsection `h3` | `text-lg` / `text-sm` | `font-medium`–`font-semibold` | `text-ink-strong` |
| Eyebrow / label | `text-sm` | `font-medium uppercase tracking-wide` | `text-ink-muted` |
| Body | `text-base` / `text-sm` | `font-normal` | `text-ink` |
| Secondary / meta | `text-sm` / `text-xs` | `font-normal` | `text-ink-muted` |

Never `font-light` below `text-4xl`. Page titles are `font-semibold` so they
outrank the `font-medium` heads beneath them by weight as well as size. For
`text-sm`/`text-xs` headings use `text-ink-strong` or `text-link`, never
`text-accent`.

Custom fonts "Ankha VTES" and "VTES Clans" are served from `/fonts/`.

## Mobile first

Design for touch first, then enhance for desktop.

- **44×44px minimum touch targets.** This is the recurring gap — re-check small
  icon buttons, steppers, unseat and sanction controls, VP selects, and tab
  toggles.
- **Safe areas.** `app.html` sets `viewport-fit=cover`, and `@theme` defines
  `--spacing-safe-t/-l/-r` from `env(safe-area-inset-*)`, always live.
  `--spacing-safe-b` is **0 by default** and becomes the real inset only inside
  `@media (display-mode: standalone)`: in an iOS Safari tab the bottom toolbar
  already occupies that space, and the inset flips as the toolbar collapses on
  scroll, so honouring it there would make the bottom nav change height mid-scroll.
  The contract is that **every viewport-edge-anchored surface absorbs its own
  inset** through the generated utilities — `pt-safe-t`, `pb-safe-b`, `pr-safe-r`,
  `pl-safe-l`. `--spacing-navbar` is the mobile bottom nav's **total** footprint,
  its touch row plus `--spacing-safe-b` under the same standalone gate, so anything
  stacking above the nav derives its offset from it (`h-navbar`, `bottom-navbar`)
  and never a hard-coded `bottom-14`. `--spacing-rail` is the desktop equivalent,
  rail width plus the left inset.
- **`sticky` carries its own inset.** `sticky top-*` / `bottom-*` resolve against
  the **scrollport**, not the shell's padding box, so a sticky header parks under
  the status bar and a sticky footer parks behind the bottom nav unless it adds the
  inset itself — `top-[calc(1rem+var(--spacing-safe-t))]`,
  `bottom-[calc(1rem+var(--spacing-navbar))]`.
- **Modal heights use `dvh`, never `vh`.** On iOS `vh` is the *large* viewport, so
  a `90vh` sheet outgrows the visible area while the toolbar shows. Vertically
  centred panels cap at **`85dvh`**: that puts the top edge at `7.5dvh`, the
  smallest margin that still clears `safe-area-inset-top` on a Dynamic Island
  phone. `90dvh` clips the panel header under the status bar.
- **Full height inside the shell is `.min-h-shell`, not `min-h-screen`.** The
  shell's content box is `dvh` minus the top inset and the nav, so a `100vh` child
  overflows it and centres its content low.
- **No hover-only interactions**; always a tap equivalent.
- **Tap-to-swap** in the seating editor: tap a player, then tap a seat — same table
  reorders, cross-table swaps, an open seat moves. **No drag-and-drop anywhere in
  the app.**
- **Global focus ring**: a crimson `:focus-visible` outline in `@layer base`. Form
  inputs may opt out with `focus:outline-none` **only** if they provide their own
  visible crimson indicator.
- **Navigation**: bottom nav or hamburger, not top-heavy headers.
- **Forms**: large inputs, no complex multi-column layouts on mobile.
- **Containers**: full width on mobile, max-width on larger screens.
- **Tables must reflow to cards** on mobile — the player table is the canonical
  case — or signal a horizontal-scroll affordance.
- Tab content padding scales (`p-3 sm:p-6`); don't use desktop padding on mobile.

Material-adjacent basics: clean card layouts with subtle shadows, crisp
typography, a 4px spacing grid, 4–8px rounded corners.

## Patterns

**Auto-save** — no explicit save buttons; changes save on input with clear feedback.
No Cancel affordance on an auto-save form: the exit action is Close or Done, and a
pending debounce is **flushed** on close, never dropped. Only genuinely
irreversible or externally visible actions gate behind a confirm step.

**List view state** — filters belong to the list, not the component instance, in
three layers:

- **URL query string** is canonical: every filter and the page number mirrored with
  `replaceState`, so Back restores the exact view and a filtered list is shareable.
  Read `window.location`, never the page store — shallow routing leaves the store
  behind.
- **Nav-menu memory** — a bare link back into a list resolves, on click, to the
  view it was left in. sessionStorage, 30-minute inactivity window, so a new or
  stale tab starts clean. The page number and free-text query are deliberately
  dropped: those are a position and an intent, not a view preference.
- **localStorage** only for true display preferences outliving the tab — the
  agenda/all toggle, the theme.

Because a restored filter can hide data, **every list's empty state must
distinguish "nothing matches these filters" from "nothing here yet"** and offer a
one-click Clear filters.

**Modals** — `fixed inset-0 z-50` with backdrop blur, `role="dialog"`,
`aria-modal`, `aria-labelledby`, Escape handling and a focus-on-mount action.
Always `stopPropagation` on the backdrop, the content container and any form
inside: without it, clicking a text input inside a modal can trigger parent
handlers like collapsing the expanded list item behind it.

**Capture modal state at open time** — snapshot the item into local state when
opening from a list, so SSE sync updates cannot change the modal's data mid-edit.

Prefer a dedicated edit modal over inline action buttons for an object with several
actions: more room for fields, a cleaner list, actions grouped, and easier to
show or hide by object state.

**Scope form options by context** — sanctions opened from the user list offer only
the VEKN-wide levels, while the tournament view offers the event-level ones.

**Never render a figure we can't compute correctly** — the rule and its two
corollaries are [dogmas](dogmas.md#product). Practically: if the client lacks an
input the server-side computation uses — the viewer can't see sanctions, the row
isn't in scope, the engine binding isn't loaded — render an em dash and, where it
helps, say why.

**Player display privacy** — offline events show the real name and VEKN ID;
online events show the nickname, with the abbreviated real name and VEKN ID in
parentheses. `seatDisplay`/`seatDisplayParts` in `tournament-utils.ts` own the
rule.

**Create and edit share sections, not initial state** — a form used for both
(TournamentFields' `mode` prop) keeps the same sections but differs in what starts
expanded: creation opens what must be filled, editing opens nothing.

**Country display** — flag then name in body text (`🇫🇷 France`), name then flag in
`<select>` options (`France 🇫🇷`) so browser type-ahead works.

**Markdown** — never `line-clamp-N` over rendered markdown HTML; derive a
plain-text excerpt from the source for a folded preview.

Shared helpers live in `tournament-utils.ts`; don't re-duplicate score helpers per
file.

## Console surfaces

The organizer console is a workbench, not a brochure. A proposed console feature
checks against three rules before adding anything:

1. **State owns the surface.** What is present, expanded and prominent is a
   function of tournament state; pre-event reference material and setup
   affordances leave the working surface during play. Placement follows:
   state-dependent, time-critical actions live in the action bar,
   state-independent ones in Tools.
2. **One button budget per surface.** A surface shows the actions of the current
   moment; everything rarer is exactly one tap deep in Tools — demoted, by
   preference, to *deleted* (another path already does the job), an *icon*
   (frequent and self-evident), or the *menu* (rare).
3. **Say it once.** A fact appears in exactly one place, at its shortest, through
   one notice component; rule citations belong in help.

The boundary rule: actions that operate on what you are looking at stay on that
surface as icons; actions that operate on the tournament go in Tools.

**No "Advanced" section.** It names a frequency, not a topic, and becomes a
dumping ground; every config field lives in the section its subject belongs to.

Two components enforce the console grammar: `FoldableSection` is the one shell
every config section uses, and `InlineNotice` is the one shape for a notice —
two tones, chosen by what the reader must *do*, not by severity theatre.

### The redesign pass

**Planned, unscheduled**: a pass bringing the console back to the three rules,
and/or a simple mode for organizers who run small events and need none of the
apparatus. The console drifted because each feature was added where it was first
needed, as an inline labelled button — Raffle, promo recording, Archon import,
Share Image, Print standings. None was wrong alone; the sum is a surface where
reference material and tools outweigh the work, worst on a phone in the Finished
state, where six inline buttons bury a single line of content. Rule 2 is therefore
a policy for *future* features, not only a cleanup backlog.

The direction, from a phone review of a finished 8-player event (2026-08-07/08):
the working surface starts inside the first viewport, the action bar sits **above**
the tabs so its guidance line is visible on every tab, reference material leaves
the masthead from check-in on, and everything rarer than the current moment sits
one tap deep in a Tools sheet opened from the masthead — grouped and ordered
**like the event runs** (set up · at the door · wrap up), because an event's
chronology is fixed and muscle memory holds. The grouping axis is the moment you
reach for a thing, not the subsystem it belongs to: promo distribution is
end-of-event, CSV import is setup and has nothing to do with VEKN.

Decisions already taken, not to be re-litigated:

- **Share Image is deleted, not moved** — `backend/src/og.py` server-renders a
  per-tournament `og:image` from the banner, so pasting the link already yields a
  cover. The banner therefore matters *more* after the pass, and needs a real home.
- **Go Offline stays in the masthead button row** (owner, 2026-08-08: "always
  accessible and obvious") — state-dependent and time-critical, and the masthead is
  the one surface present on every tab.
- **Tab labels show the active one only.** A text-shrinking fix is fragile across
  five locales, where the overflow is worse than English suggests.
- **No Start Finals CTA in an empty Finals tab.** Finishing without a final is
  legitimate ([rules §3.1.6](domain/tournament-rules.md)), so a CTA there would
  frame finals as the expected path.
- **The description drops out of the organizer view only** — organizers wrote it,
  players still need it.

Rejected, with the reason that killed each: **per-tab status counts** and **a
masthead reporting live round state**, both because the action bar's guidance line
already says it and rule 3 forbids the second voice; **a flat Tools dropdown**,
the hamburger trap where finding anything means reading all of it; and **Tools in
the tab row**, since it opens a sheet rather than swapping a panel and would spend
the width the redesign just recovered.
