---
name: deck-parser-prefix-match-trap
description: Deck parser trailing-digit misparse — try_name_first count-strip + by_name prefix match interact to miscount cards like "Channel 10"/"AK-47"/"Kpist m/45"
metadata:
  type: project
---

In `engine/src/deck.rs` + `engine/src/cards.rs`, two lenient behaviours combine into a silent miscount on **count-less** card lines (bare pastes; never modern exporters or our own count-prefixed TWDA export):

- `try_name_first` (deck.rs ~266-295) treats trailing digits as a count, and its trailing-name cleanup set (~281) excludes `-`, so `AK-47` strips to name `AK-`.
- `by_name` (cards.rs ~116-138) then **prefix-matches** the truncated stem (`ak`, `channel`, `kpist m`) right back to the same card → correct card, garbage count (47/10/45).

Misparse confirmed for `Channel 10`, `AK-47`, `Kpist m/45`. `Local 1111` escapes only because its run is 4 digits (>2-digit count cap). Same prefix-leniency hazard exists in `try_strip_crypt_tail` (deck.rs ~301-309) which also calls prefix-matching `by_name`.

**Why:** the lenient prefix match in `by_name` was added for deterministic ambiguous-name resolution, but it doubles as a misparse amplifier when callers feed it truncated stems.

**How to apply:** the targeted fix is to gate the trailing-count branch AND the crypt-tail trim on an **exact** `name_index` hit (`name_index.get(normalize_name(stripped))`), not the lenient `by_name`. Do NOT port krcg's regex lookaheads for this — exact-key gating neutralizes the whole punctuation class in a few lines. Separately, group-from-crypt-tail disambiguation (Annabelle Triabell G3 vs G6) is a real, untested bug: `try_strip_crypt_tail` drops the `clan:group` tail and resolves the bare ambiguous name to the lowest-id (earliest-group) printing. See [[deck-architecture-patterns]] context if present.
