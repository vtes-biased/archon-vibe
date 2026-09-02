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

**Tailwind's `dark:` variant does not track the theme** and must not be used. It
keys on `prefers-color-scheme`, so a theme the user picked against their OS leaves
every `dark:` utility on the wrong side — most visibly `dark:prose-invert`, which
renders dark body text on a dark card and is invisible to anyone whose OS already
agrees with their theme. Rendered markdown takes **`doc-prose`** instead, which
maps the `--tw-prose-*` variables onto the role tokens and so follows
`color-scheme` like everything else. `just dark-variant` holds the ban
([dev](dev.md#lint-gates)).

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

Azure carries two jobs: status meaning above, and the `create` button variant
([Buttons](#buttons)), which reuses `btn-success` for its fill. The two never meet
on one control — status azure labels a fact (a Paid chip, an info banner), `create`
names an action.

Raw stock Tailwind colour utilities do not adapt to the theme — use role utilities
or these semantic classes, never `bg-emerald-*`-style tints.

#### The beta green

Green has exactly one sanctioned use: the **beta environment mark** — the app icon
`#00C853` on the standard `#2A2520` ground, and the `BETA` chip beside the rail
logo (`badge-beta`, `light-dark(#05603a, #6ee7b7)` on `light-dark(#ecfdf5, rgb(5 96
58 / 0.6))`). Reserving it is what makes it safe: green never appears in
production, so it can never be read as a status colour, and a design review run on
beta sees the true palette everywhere except that one deliberately foreign mark.
Recolouring the app's own accent tokens on beta was rejected for the opposite
reason — it would make beta useless for reviewing design.

When to use what: **status text tokens** for inline status text and standalone
icons where a badge would be too heavy; **status classes** for component-level
status; **selection tokens** for the seating tap-to-swap affordance only, never for
status; **categorical classes** for identity tags. `banner-*` is for info and
warning boxes and **never on a chip** — a bordered `banner-warn` span reads as a
shrunken alert box next to real badges; use a status badge.

### Beta identity

A user with both environments installed must never confuse them: results recorded
on beta never reach VEKN, and the mistake surfaces long after the event. The two
deployments are one release artifact, so the environment is resolved at runtime
from the hostname ([dev](dev.md#environment-identity)) and every identity surface
reads it — home-screen icon and name (`Archon Beta`, the name the mail and WebAuthn
configuration already use), push notification icon, the rail mark with its `BETA`
chip, and the link-preview card on the paths that have a crawler stub. A link to a
route with no stub still previews from `app.html`'s static tags, which name
production on both hosts. Below `sm` there is no rail: the home-screen icon and
name are the whole signal, which is why they carry it rather than an in-app banner.

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
| `primary` | crimson | every affirmative action except creation — lifecycle CTAs and form/auth submits alike |
| `create` | **azure** | starting a new top-level item from a list surface, and nothing else |
| `danger` | **violet** | destructive: delete, drop, force-takeover, cancel round, finish tournament |
| `secondary` | neutral solid | neutral secondary action, bulk utilities, the More overflow trigger |
| `ghost` | neutral outline | tertiary, de-emphasised |

**One primary CTA per surface.** Crimson is the single positive colour, so a screen
shows one filled crimson button and collapses the rest into an overflow menu. A
legitimate second lifecycle choice — Start Round versus Start Finals — drops to
`secondary`, never a second `primary`.

**`create` spends its own budget, not the primary one.** A list surface shows at
most one azure create button, and it does not count against the crimson primary —
`/tournaments` legitimately carries a blue New Tournament in its header and a
crimson calendar-feed CTA in agenda view. The six create buttons are the tournament
and league headers, the community add-link, the member list, and the promo catalog
header and its gallery empty state.

**The boundary is top-level and list-shaped.** `create` opens a *new item of the
list you are looking at*; it never dresses a form submit, a row-level add, a nested
add-to-this-thing, or a state the button can toggle into — a blue button reading
Cancel is the leak this rule exists to prevent. Everything else affirmative stays
`primary`.

**A create opens a modal, unless it has a page's worth of fields and earns a
route.** Nothing expands inline: an inline form is what pushes the button into a
toggle and gives that leak somewhere to start. Tournament and league creation take
`/tournaments/new` and `/leagues/new` on field count alone; the community link, the
promo entry and the member each open a dialog.

**Danger is violet, never red.** Red and crimson are the same hue family and
collapse together even under colourblindness, so destructive actions get their own
hue. Meaning must not rest on hue alone: pair `danger` with an icon and a verb.

Props: `size`, `block`, `loading` (spinner, `aria-busy`, auto-disables),
`disabled`, `href` (renders an `<a>`, which takes neither state); extra layout
classes via `class`. Focus comes from the global `:focus-visible` ring — never add
a bespoke outline.

**Do not** route through `Button`: icon-only buttons, toggles, tabs, segmented
controls, dropdown and menu options, row- or card-wrapping buttons, text links, or
Discord brand-fill buttons. A *button-shaped* link is not an exception — pass
`href` and `Button` renders an `<a>` with the same classes, keeping cmd- and
middle-click, which `onclick={goto}` would lose.

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
- **Navigation**: bottom nav or hamburger, not top-heavy headers. Below `sm` the
  six destinations are icon-only — labels truncate to ambiguity in `es`/`pt`, so
  the name lives in `aria-label` and `title` — and each icon must be
  shape-distinct from the other five at 24px: `/tournaments` `Trophy`, `/leagues`
  `FlagTriangleRight`, `/rankings` `ListOrdered`, `/users` `Users`, `/help`
  `BookOpen`, `/profile` `CircleUser`. Each is picked by what the other five
  already own: the award cluster is `Trophy`'s, so rankings takes the numbered
  ladder its labels name outright (*Classifiche*, *Clasificaciones*); the calendar
  family is the row date glyph on both lists and `Shield` is the judge mark, so
  leagues takes the pennant clubs exchange (*gagliardetto*, *banderín*) rather
  than a season; and `User` beside community's `Users` is one shape at that size,
  so profile takes the circled bust. `/tournaments`, `/leagues` and `/profile`
  repeat their nav icon in their own empty state.
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

**Unactionable match** — a member the organizer cannot add is listed disabled with
its reason, never filtered out of the results: an empty dropdown reads as "no such
member" and invites minting the duplicate only an IC can merge back. Holds for the
add-player search and the create-and-register dedup review, and the reason wins
over any other block on the same row — already registered, then suspended. Where
the list is capped, addable rows rank ahead of blocked ones before the cap, and a
"no match" branch tests for an addable match rather than an empty list: a blocked
row must never displace one the organizer can act on, nor stand in for it.

**The first viewport shows the work.** A list surface reaches its first rows
without scrolling on a 393×852 phone: the search field and the view toggle stay in
the open, every select folds behind a single control naming how many filters are
active, and what is left above the rows is the header and that row. This is the
console's own first-viewport rule ([the redesign pass](#the-redesign-pass))
generalized — apparatus is what moves, never the content it filters. The public
tournament masthead still owes it.

**List view state** — filters belong to the list, not the component instance, in
three layers:

- **URL query string** is canonical: every filter, the segmented-toggle tab and the
  page number mirrored with `replaceState`, so Back restores the exact view and a
  filtered list is shareable. Read `window.location`, never the page store —
  shallow routing leaves the store behind. **A filter whose control only some
  viewers can see is excluded**: a shared link would hand everyone else a filter
  they can neither see nor clear. On `/users` that is the officials-only sponsor
  and no-VEKN toggles — the sanction toggles render for every signed-in viewer and
  so are mirrored. An arrival pointer is not a filter and is neither mirrored nor
  remembered (`/users?sponsor`).
- **Nav-menu memory** — a bare link back into a list resolves, on click, to the
  view it was left in. sessionStorage, 30-minute inactivity window, so a new or
  stale tab starts clean. The page number and free-text query are deliberately
  dropped: those are a position and an intent, not a view preference.
- **localStorage** only for true display preferences outliving the tab — the
  agenda/all toggle, the theme.

Because a restored filter can hide data, **every list's empty state must
distinguish "nothing matches these filters" from "nothing here yet"** and offer a
one-click Clear filters.

**Tabs come in two idioms and they are not interchangeable.** A **segmented pill
toggle** filters the page under it — a few short labels, no icons, every label
always visible (`/rankings`, `/users`). A **tab strip** swaps the panel beneath a
subject that stays put: `TabStrip.svelte` owns it and no surface hand-rolls it —
icon always, the label spelled out on the **active tab only** below `sm`,
`aria-label` the full label at every width, `aria-current="page"` on the active
one, and the row scrolls rather than wraps. The active-only label is what makes
three or four tabs survive five locales at 360px; a text-shrinking fix is fragile
there, where the overflow is worse than English suggests. The strip carries the
tournament console, the member profile and the public member page.

**One fold grammar.** `FoldableSection` is the app's single disclosure shell —
muted box, chevron right closed and down open, the whole header a 44px target, a
150ms slide — and a **section** that folds uses it, inside the console and out. It
takes a `header` snippet for a count or a total, an `ontoggle` for a parent that
owns the state (an exclusive accordion, a body that loads on first open), and a
`disabled` for a body that cannot be fetched. It takes no styling props: a fold
that wants its own box is a fold that has drifted. A chevron points **right closed
and down open** everywhere — a rotating one is not an alternative and has no
exception. `just fold-grammar` ([dev](dev.md#lint-gates)) holds both halves.

Six surfaces fold outside the shell, for a structural reason and not a visual
preference:

- **A list row folds in place** — the whole row is the target and the chevron
  trails a multi-part summary of the row's own subject, which a titled section
  would have to throw away: `PlayersTab`'s player card, `PlayerDecksSection`'s
  visible decks, and `CommunityCountryCard`. `RoundsTab`'s round and table headers
  fold this way too because their rows carry sibling action buttons, which cannot
  nest inside the shell's own button.
- **`ToolsSheet`** — the sheet's grammar is full-bleed menu rows, and a boxed
  section inside it breaks the rhythm the sheet is scanned by.
- **`FoldableDescription`** — closed, it renders the excerpt instead of hiding the
  body, so it is a preview rather than a disclosure.

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

**Table labels** — a table is named by the sign the player walks to: `Main Hall 3`
under a configured room, the room name alone when it holds a single table, and a
localized `Table N` when no room covers the index. The engine's `tableLabel` is the
only implementation; the seating grid, player view, printed seating sheet,
judge-call banner and both Web Push bodies each render it with their own localized
fallback.

**Create and edit share sections, not initial state** — a form used for both
(TournamentFields' `mode` prop) keeps the same sections but differs in what starts
expanded: creation opens what must be filled, editing opens nothing.

**A wizard fronts a form, it never replaces one.** Tournament creation asks four
archetype questions and then reveals the ordinary create form prefilled, rather
than collecting the fields itself: one submit path, one set of validations, one set
of field labels. The count is fixed at four whichever branch is taken, so it never
moves under the reader; single-choice steps advance on tap, steps carrying several
controls end in Next; and an organizer who already knows what they want skips
straight to the form, bookmarkable at `?form`. A wizard writing into the values
bypasses the field handlers that enforce their invariants, so the prefill owes them
itself — online clears proxies, dropping open rounds clears self-organized.

**Guidance names the real label, and only once.** The closing panel covers what the
app cannot automate — the Discord bot, co-organizers, table rooms, the CSV import,
offline mode, decklists, QR self-check-in, payment at the door, parallel rounds,
latecomers — and interpolates every control it names from that control's own
message key, the rule the [help mockups](i18n.md#guide-mockups) already run on. It
stays silent where the form beneath it speaks: the open-rounds warning and the
self-organized description belong to the fields.

**Country display** — flag then name in body text (`🇫🇷 France`), name then flag in
`<select>` options (`France 🇫🇷`) so browser type-ahead works.

**Markdown** — never `line-clamp-N` over rendered markdown HTML; derive a
plain-text excerpt from the source for a folded preview.

**Downloads are produced on the device.** The organizer's event copy renders from
local data and is handed over as a Blob — a plain navigation to a download
endpoint carries no `Authorization` header, so an authenticated one answers 401 to
every click. The account data export is the exception, because its payload is
genuinely server-side; it passes the token in the query string. A *small*
server-side file (the sealed NDA) is instead fetched with the auth header and
handed over as a Blob — query-token auth stays confined to the one snapshot
endpoint that already speaks it.

Shared helpers live in `tournament-utils.ts`; don't re-duplicate score helpers per
file.

## Member profile

Two surfaces show one member: `/profile`, the owner's own, and `/users/[uid]`, the
public one. A top player's record — four rating categories, wins, decklists — runs
about 950px on a phone with the account stack another screen behind it, so both are
tabbed.

**Identity stays above the strip.** Avatar, name, nickname, VEKN ID, country, city
and roles are the page's subject, not tab content. Below it:

| Surface | Tabs |
|---|---|
| `/profile` | Profile · Play record · Account |
| `/users/[uid]` | Profile · Play record |

- **Profile** — contact details and community links; on the public page also the
  sponsor note and whatever VEKN, NDA and sanction controls the viewer's access
  grants.
- **Play record** — ratings, then the wins and the decklists. The
  undocumented-decklist nudge sits between them on `/profile` only: it is
  actionable by the player alone and reads as a reproach on anyone else's page.
- **Account** — linked accounts, authorized apps, the member's own playtest NDA
  records with a re-download of each sealed file, settings, developer,
  administration, data. The NDA block renders only when a record exists.

Two constraints the structure has to keep. An **OAuth return lands on Account**:
the Discord and GitHub link confirmations render inside that tab and are invisible
anywhere else. And the **undocumented-decklist nudge sits beside the wins it
names**, never below the decklists — tabs already put it one gesture deep, which is
this structure's accepted cost. The count and the wins behind it stay together for
the same reason [tournaments](tournaments.md) states: the number is auditable
rather than asserted.

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

`InlineNotice` is the one shape for a notice — two tones, chosen by what the
reader must *do*, not by severity theatre. Config sections fold through the
app-wide [fold grammar](#patterns).

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
- **No Start Finals CTA in an empty Finals tab.** Finishing without a final is
  legitimate ([rules §3.1.6](domain/tournament-rules.md)), so a CTA there would
  frame finals as the expected path.
- **Finished spends its primary on promo reporting**, the one state whose button
  budget was empty. The CTA deep-links into the Tools promos panel rather than
  moving the form out of it: `ReportPromos` carries no state gate and raffled
  promos feed the report from check-in on
  ([tournaments](tournaments.md#engine-event-catalog)), so Tools stays the
  any-state path while the bar names the moment.
- **The description drops out of the organizer view only** — organizers wrote it,
  players still need it.

Rejected, with the reason that killed each: **per-tab status counts** and **a
masthead reporting live round state**, both because the action bar's guidance line
already says it and rule 3 forbids the second voice; **a flat Tools dropdown**,
the hamburger trap where finding anything means reading all of it; and **Tools in
the tab row**, since it opens a sheet rather than swapping a panel and would spend
the width the redesign just recovered.
