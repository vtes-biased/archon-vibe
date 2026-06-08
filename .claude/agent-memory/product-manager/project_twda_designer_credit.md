---
name: twda-designer-credit
description: TWDA export designer-credit convention — Created by: label, anonymity = omission, names only no VEKN ids, winner always in header
metadata:
  type: project
---

TWDA (Tournament Winning Deck Archive, `GiottoVerducci/twd`) designer-credit convention for generated PR submissions. Verified against live `twd.htm` (3,805 entries) on 2026-06-08.

**The convention (attribution value → credit line):**
- Header **always** carries the player/winner name (it is the winner line, ~5th/6th header line), independent of who designed the deck.
- Designer credit is a **separate, optional** `Created by: <name>` line in the deck block (after `Deck Name:`).
- ANONYMOUS (`attribution=null`): **omit** the credit line entirely. There is NO "Anonymous"/"Withheld"/"N/A" string anywhere in the real TWDA — anonymity = omission. Also leak-safe.
- SELF (player designed own deck): **omit** — redundant with the header winner line. Recent self-designed entries (e.g. event 12957) have `Deck Name:` and no credit line.
- OTHER (designed by someone else): **emit `Created by: <designer name>`**. TWDA tolerates rich free text here ("with suggestions from X", "A & B").
- `"twda"` sentinel (historical backfill): emit `author` as-is if non-empty, else omit.

**Hard rules:**
- Canonical label is `Created by:` (381 uses) over legacy `Author:` (142) / `Designed by:` (few).
- **Names only — never VEKN ids** in credit lines (verified zero ids across all entries). Do NOT append `(#1234567)`.

**Why:** ticket #46 bug — `export_twda` emitted the credit whenever `author` was non-empty, leaking the name of designers who chose anonymity and printing a redundant self-credit. Fix gates the line on `attribution`, not on author presence.

**How to apply:** when touching `engine/src/deck.rs::export_twda` or any TWDA generation, gate the `Created by:` line on attribution (other/twda → emit; null/self → omit). Note `Deck.attribution: Option<String>` collapses null-anonymous and unset-self to `None`; the self/anonymous distinction must be passed in separately (tri-state or a resolved `credit_designer` bool from the caller). See [[project_vekn_id_detach_policy]] for how designer identity is resolved.
