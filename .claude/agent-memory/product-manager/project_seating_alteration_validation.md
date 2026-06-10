---
name: seating-alteration-validation
description: Hard-block vs warn rules for altering/dealing a round's seating; add-table belongs inside the edit-seating draft, not as a live action
metadata:
  type: project
---

Round seating-alteration (RoundsTab.svelte AlterSeating / SwapSeats / SeatPlayer / UnseatPlayer / AddTable / RemoveTable) validation policy, grounded in VEKN rules:

**Hard block on save** (an unscoreable / illegal seating must never be committed):
- Any *formed* table with <4 players (no legal VTES table under 4; judge re-forms or fills, never plays a 3p table — judges-guide-v2 §5.1 lines 437-439).
- Any table >5 (VEKN max 5, §3.1.2).
- Empty (0-player) tables — allowed transiently *while editing the draft*, never committed.
- The block is "every formed table is in {4,5}", NOT "all tables equal size": mixed 4p+5p is normal (count not divisible by 5), and 6/7/11 use staggered/sit-out byes. Don't trip those.

**Warning only** (never block):
- Repeated predator-prey relationships. §3.1.2 says prevent "when possible" — judge may knowingly accept a repeat when no impartial alternative exists. Current engine AlterSeating hard-validates no-R1-repeat; that should be downgraded to a soft warn naming the offending pair.

**Add-table is a seating-construction op, not a live action.** Owner's instinct is VEKN-correct: appending an empty table to a round with games underway has no sanctioned scenario (late arrivals join *next* round, §3.3.1; drops re-form tables, not add them). AddTable should live inside the edit-seating draft, not as an instant append.

**Legitimacy window:** seating alteration is only legitimate *pre-play* (round dealt but games not started). Mid-game seating is frozen; only drops mutate a table (shrink, never reshuffle). App's `Playing` state conflates "dealt, not started" with "underway" — the alter feature really serves the pre-play sliver.

**Why:** Owner reconsidering the feature (2026-06-10) flagged that <4p repartitions can currently be saved and that add-table is wrongly a standalone live action.

**How to apply:**
- Scope call: minimal correctness fix FIRST (p2) — save-time {4,5} block + empty-table block + downgrade repeat to warn + gate AddTable behind draft. Cheap, isolated, no architecture risk.
- Unifying swap/seat/unseat/add/remove into one "edit seating" draft with a changed-player-set save is a larger p3 — it breaks AlterSeating's same-player-set invariant (must absorb SeatPlayer/UnseatPlayer), so it's an engine-contract change needing principal-engineer review, not just Svelte. File separately; don't bundle.
- Reuse the existing `check_table_vps` "size 4 or 5" guard (TOURNAMENTS.md ~line 218) at the AlterSeating save path, not only at scoring.
- See [[vekn-standings-toss-scope]] for the "when possible" / best-effort framing precedent.
