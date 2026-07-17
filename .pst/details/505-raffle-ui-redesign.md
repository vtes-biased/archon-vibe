# Raffle UI redesign — staff-frontend-engineer proposal (2026-07-17)

Owner beta feedback: the raffle menu is "hard to grasp / understand". UI-only pass on
`frontend/src/routes/tournaments/[uid]/RaffleSection.svelte`; engine semantics (pools,
exclude-drawn, seeded RaffleDraw) untouched. The component is embedded two ways:
organizer controls + results inside the collapsible "Raffle" card (`PlayersTab.svelte`),
results-only in `PlayerView.svelte` (which already has an outer `h3` "Raffle" —
don't double the header there).

## Root cause

The form is a label-less cluster where three concepts collide with no hierarchy: the
free-text `label` field (placeholder **"Prize name"**) sits right next to a separate
**"Prize promo"** select — two "prize" things, indistinguishable. Nothing says what a
raffle is, no field is named, the Draw button is silently gated (`!label.trim() ||
currentEligible === 0`). Fix = naming + grouping + a pre-filled fast path, not new
capability.

## Target layout (mobile-first, single column, replaces the flex-wrap row)

```
┌ (inside the existing "Raffle" card) ───────────────────────────┐
│ Randomly draw winners from a pool of players.  ← hint, 0 draws │
│ Draw name                                                      │
│ [ Raffle #1 ]                                   ← PRE-FILLED   │
│ Draw from                                                      │
│ [ All players (12)                          ▾ ]                │
│ Winners                                                        │
│ [ − ] [ 1 ] [ + ]                    ← stepper, 44px targets   │
│ Prize (optional)                                               │
│ [ No prize                                  ▾ ]  ← ALWAYS      │
│    when none eligible: one disabled row explaining why         │
│ ▸ More options                                                 │
│      ☑ Exclude previous winners                                │
│ [ 🎲 Draw 1 winner ]        ← primary CTA, full-width, dynamic │
│   No eligible players in this pool.  ← helper when disabled    │
├────────────────────────────────────────────────────────────────┤
│ Past draws                          ← organizer-only header    │
│  │ Raffle #3  🎁 Prize: Foo │ [Latest] badge, newest first     │
│  │ [Alice] [Bob]            │                                  │
│  [ ↩ Undo last draw ]  [ 🗑 Clear all draws ]  ← under results │
└────────────────────────────────────────────────────────────────┘
```

## Field order / behavior

1. **Draw name** — pre-fill `label` with `Raffle #{raffles.length + 1}` ($derived
   default); reset to the new default (not "") after each draw. Fast path = open card,
   tap Draw. Still editable.
2. **Draw from** — same select, keep `(N)` counts, add a visible label.
3. **Winners** — replace bare `w-16` number input with a −/n/+ stepper, 44×44 buttons.
   Clamp `[1, max(currentEligible,1)]` as today.
4. **Prize (optional)** — always render (fixes the raffle half of #503). When
   `eligiblePromos.length === 0` but catalog non-empty: one disabled option naming the
   reason (rank/league gating); catalog empty: disabled "No promos configured". Never
   vanish.
5. **More options** — fold `Exclude previous winners` behind a collapsed disclosure;
   checkbox default stays `true`.
6. **Draw button** — dynamic label `Draw {n} winner(s)`; full-width on mobile; when
   disabled show the reason as helper text (no silent gate).
7. **Undo / Clear** — relocate beneath the results (they act on results, not the form),
   explicit labels "Undo last draw" / "Clear all draws"; keep confirm() on Clear and
   ghost/danger variants.
8. **Results** — "Past draws" eyebrow header (organizer branch ONLY); mark newest draw
   with `border-accent-soft-border` + "Latest" badge (projected-screen readability).

## i18n keys (all 5 locales via i18n-translator)

| Key | English | Notes |
|-----|---------|-------|
| raffle_help | Randomly draw winners from a pool of players. | teaching hint / empty state |
| raffle_name_label | Draw name | replaces misleading "Prize name" placeholder |
| raffle_name_default | Raffle {n} | parameterized default value |
| raffle_pool_label | Draw from | pool select label |
| raffle_winners | Winners | exists — reuse as stepper label |
| raffle_prize_optional | Prize (optional) | visible label (currently aria-only) |
| raffle_prize_none | No prize | exists as "No promo prize" — reword |
| raffle_prize_gated | {n} promo(s) hidden by this event's rank/league | #503 disabled-reason row |
| raffle_prize_empty | No promos configured | catalog truly empty |
| raffle_more_options | More options | disclosure toggle |
| raffle_draw_one / raffle_draw_many | Draw {count} winner / Draw {count} winners | two keys — flat i18n, no plural rules |
| raffle_no_eligible | No eligible players in this pool | why-disabled helper |
| raffle_results_header | Past draws | organizer-only results header |
| raffle_latest | Latest | badge on newest draw |
| raffle_undo_last | Undo last draw | reword existing raffle_undo |
| raffle_clear | Clear all draws | exists as "Clear all" — extend |

## DESIGN.md compliance (defects found in passing)

- **Focus indicator broken (a11y):** the text input uses `focus:outline-none
  focus:border-line-strong` — resting border color, so no visible focus change at all.
  Use `focus:border-accent` or drop outline-none; apply to new selects/stepper too.
- **Touch targets:** pool/prize selects (~30px), winners input (~28px), checkbox,
  Undo/Clear icons all sub-44px → `min-h-11`, stepper 44×44, checkbox row `py-2 min-h-11`.
- **Tokens:** stay on role tokens already used (`bg-surface-hover`, `border-line-strong`,
  `text-ink-*`, `badge-highlight`, `accent-soft-border`); Button variants correct as-is.
- **Motion:** any newest-draw highlight gated behind `motion-reduce:`.

## Prioritization

- **Must:** visible labels on every control; fix "Prize name" placeholder; pre-filled
  name + why-disabled helper (kill the silent gate); always-present prize select with
  disabled reason (#503 raffle half); 44px targets; focus indicator.
- **Should:** More-options disclosure; Past-draws header + Latest badge; explicit
  Undo/Clear labels under results; dynamic Draw label; teaching hint.
- **Consider:** Gift-icon placeholder when a prize has no image (today renders nothing);
  motion-reduced newest-draw highlight; the single-column layout itself.

One self-contained edit to RaffleSection.svelte + locale keys. Closes the raffle half of
#503 as a side effect — the PromosDistributedEditor half of #503 stays separate.
