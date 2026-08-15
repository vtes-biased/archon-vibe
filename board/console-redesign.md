> Elaborated context for a line in `BOARD.md`. Deleted with the line.
> `#N` below is a **retired tracker number**, not a GitHub issue and not a live
> pointer — the surrounding prose carries the fact. A real GitHub issue is
> written `gh-N`.

# Tournament organizer console redesign

Source: 7 phone screenshots of "Alicante por la tarde" (Finished, 8 players, iOS Safari,
new.archon.vekn.net) reviewed with the owner on 2026-08-07/08, plus a read of
`frontend/src/routes/tournaments/[uid]/`.

## The direction

**The console is a workbench, not a brochure.** Every child derives from three rules. When a new
console feature is proposed, check it against these before adding a button.

1. **State owns the surface.** What is *present*, *expanded* and *prominent* is a function of
   tournament state. Reference material (description, date, location, organizers) and setup
   affordances (banner upload, promo recording) are pre-event concerns and must not occupy the
   working surface during play. The rule applies one level down, inside a row: the player card's
   paid/deck controls are the work at the door desk and noise during round 3. It also decides
   *placement*: state-dependent and time-critical actions belong in the action bar (Go offline),
   state-independent ones belong in Tools (Delete).

2. **One button budget per surface.** A surface shows the actions of the current moment and
   nothing else. Everything rarer is exactly one tap deep in Tools. Three demotions, in order of
   preference:
   - **delete** if another path already does the job (Share Image → link sharing; Download
     Report (Text) → Copy results; Record promo cards → the Tools entry it merely scrolls to),
   - **icon** if frequent and self-evident (Print standings),
   - **menu** if rare (Reopen, Raffle, Delete).

   The ActionBar already states this rule in its own source comment (`ActionBar.svelte:160`).
   The Finished state ignores it and renders six inline buttons. Most of this work is making the
   console keep a promise it already made.

3. **Say it once.** A fact appears in exactly one place, at its shortest, through one notice
   component. "Unranked" as a badge *and* a boxed paragraph *and* a rules citation is one fact at
   three weights. Rule citations belong in help. This rule also killed a proposal of our own —
   see *Rejected* below.

### Why the console drifted

Each feature was added where it was first needed, as an inline labelled button: Raffle, promo
recording, Archon import, Share Image, Print standings. None was wrong alone; the sum is a
console where reference material and tools outweigh the work. Rule 2 is therefore also a policy
for *future* features, not just a cleanup pass.

## Target composition (organizer view, phone)

```
[ back ]
[ masthead — full pre-event · title + badges only from check-in on ]
[                              Share ·  Go Offline ·  Tools ]
[ ACTION BAR — state rail · guidance · ONE primary CTA · secondaries ]  ← above the tabs
[ ⌾ Players    ⚔    🏆                                              ]  ← active label only
[ tab content — starts within the first viewport ]
...
[ sticky: state label + primary CTA ]                                  ← follows you down
```

Player card, collapsed (two lines):

```
#3  José Más Cruz                                   [Finished]
    #1002913 · 1GW 2.5VP 88TP · 0 RP
```

Tap to expand → paid toggle, deck state, More. One expanded at a time. During Registration and
pre-first-round Waiting, cards render in **door mode** with those controls inline instead.

## The Tools sheet (#574)

One entry point in the **masthead**, not the tab row — so the tab row gains no new resident and
stays purely tabs. Grouped and **ordered like the event runs**; the order is fixed because an
event's chronology is fixed, so muscle memory holds, and the group matching the current state is
the one already expanded.

```
Set up        Details · Organizers · Table rooms · Banner
              Import players (CSV) · Add to the VEKN calendar
              Import a finished event (.xlsx)
At the door   Check-in QR code
Wrap up       Promo distribution · Raffle · Copy results
              Report results to VEKN · Reopen tournament
              Delete tournament
```

**The grouping axis is the moment you reach for it, not the subsystem it belongs to.** Promo
distribution is end-of-event, not setup. CSV import is setup and has nothing to do with VEKN.
Import takes `.xlsx` (legacy Archon desktop) while export emits JSON from
`/api/tournaments/{uid}/report` — they do not round-trip, so grouping by file format actively
misleads.

Listing Config's four accordions as direct entries is the point: today each is three
interactions deep (tab → scroll → unfold), which is *why* the "Record promo cards" button and
the header "add co-organizer" chip exist. Listing sections directly dissolves that class of
shortcut instead of relocating it.

**Boundary rule for future features:** actions that operate on what you are looking at stay on
that surface as icons (Print standings); actions that operate on the tournament go in Tools.

**Carve-outs that stay visible:** Share (frequent, and the only distribution path once Share
Image is deleted) and the VEKN sync **status** badges (status is information, not an action — the
*Report results to VEKN* action moves into Tools, the pending/stale badges stay in the masthead
where they act as a call to action).

## Copy is design material

- `Sync to VEKN` does two different jobs depending on state → split into **Add to the VEKN
  calendar** (before) and **Report results to VEKN** (after).
- `Download Report (JSON)` / `(Text)` are named after serialisations. Text is deleted; JSON means
  a portable copy of the event and should say so.
- The Unranked box explains at length what its own badge already says.

## Findings by screenshot

| # | Finding | Child |
|---|---------|-------|
| 1 | First viewport contains nothing actionable: back link, "Add banner" dropzone (on a *Finished* event), title wrapped to 2 lines, 3 rows of badges, info card | #565 |
| 1 | Share + "Go Offline" squeeze the title into wrapping; "Go Offline" wraps itself | #565 |
| 1 | Organizers render as 4 lines of crimson links, competing with the accent-crimson title | #565 |
| 2, 4 | Five stacked control rows (~400px) before the first player | #568 |
| 2, 4 | Player card ~190px; solid blue **Paid** button is the loudest element, outranking the result | #569 |
| 2, 3 | Bottom nav renders mid-screen while scrolling | #573 |
| 3, 5, 6, 7 | ActionBar renders *inside* the tab panel — same ~700px block on all four tabs | #564 |
| 3, 5, 6, 7 | Tab row overflows: "Config" clips to "Confi"/"Cor", no scroll affordance | #566 |
| 3, 5, 6, 7 | Announcement composer permanently expanded above the console | #570 |
| 3, 5, 6 | Two notices (Unranked, TWDA) styled two different ways for the same class of info | #567 |
| 5, 6 | Finished panel: 6 inline buttons; on Finals it buries the single line of content | #567 |
| 6 | "Start finals from the Overview tab" — the Overview tab no longer exists | #571 |
| 7 | "More" dropdown overflows the right edge and shifts the page horizontally | #572 |

## Decisions taken

- **Description dropped in organizer view only.** Organizers wrote it; players still need it.
- **Share Image deleted, not moved.** `backend/src/og.py` server-renders a per-tournament
  `og:image` from the banner, so pasting the link already yields a proper cover. Consequence: the
  banner matters *more* after this change, hence a real home in Tools → Set up.
- **Go Offline stays in the masthead button row,** beside Share and Tools — not in Tools, and not
  moved into the action bar either (owner, 2026-08-08: "always accessible and obvious"). It is
  state-dependent and time-critical, and the masthead is the one surface present on every tab.
- **Tab labels: active only.** The width problem is worse in es/pt/fr/it than the English
  screenshots show, so a text-shrinking fix would be fragile across five locales.
- **No Start Finals CTA in the empty Finals tab.** Finishing without a final is legitimate
  (rules 3.1.6; the screenshot event is one), so a CTA there would frame finals as the expected
  path — and it sits badly beside the open rules question in #341. Finished-with-no-finals hides
  the tab entirely; live-with-2+-rounds shows the projected top-5 seeding. The action bar keeps
  owning every state transition.

## Rejected

- **Per-tab status counts** (proposed, then cut by rule 3). Once the action bar sits above the
  tabs and is always visible, its guidance line already reports "Round 2 — 2 of 3 tables done"
  (`action_bar_playing_round`) and "12 of 16 checked in" (`action_bar_waiting_initial`).
- **A masthead that reports live round state during play.** Superseded: once the action bar moved
  above the tabs (#564) its guidance line already owned that, and duplicating it would break rule
  3. Settled instead by dropping the info card from check-in on, so the masthead shrinks to the
  title line and its badges rather than being replaced (#565).
- **A flat Tools dropdown.** A dozen heterogeneous items in one undifferentiated list is the
  hamburger trap: finding anything means reading all of it.
- **Tools in the tab row.** It is not a tab — it opens a sheet rather than swapping the panel —
  and putting it there would spend the width that removing Config just recovered.
