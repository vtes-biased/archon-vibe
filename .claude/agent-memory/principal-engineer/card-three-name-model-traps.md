---
name: card-three-name-model-traps
description: Non-obvious roles of the three krcg card-name forms + set-names-are-display-names, for reviewing cards.rs/deck.rs/DeckDisplay changes
metadata:
  type: reference
---

`cards.json` (built by `scripts/update_cards.py` from `krcg.loader.load_online`) carries
THREE name forms with distinct load-bearing roles — mixing them up is a silent bug:

- `printed_name` — bare, **display only** (group/adv shown as separate badges via CardName.svelte).
- `unique_name` — minimal disambiguator (bare for most; grouped/adv suffixed) — **text decklist export + a parse key**.
- `full_name` — ALWAYS group/adv suffixed — **a parse key AND the krcg image-filename source**:
  the static.krcg.org card image filename = `normalize(full_name)` (e.g. "Aabbt Kindred (G2)" →
  `aabbtkindredg2.jpg`, ADV → `...g2adv.jpg`). Reconstruct image URLs from `full_name`, never `printed_name`
  (printed drops the suffix → 404 for every grouped/advanced crypt card).

`sets` holds **display NAMES, not codes** ("Fifth Edition", "Fifth Edition (Anarch)", "Promo",
"Print on Demand"). `deck.rs` V5-legality string-matches these names — and `starts_with("V5")`
matches NOTHING (core V5 sets are "Fifth Edition*"). Any set-name-string check must account for
this. **Why:** the name index (cards.rs) folds accents on both index+query (`normalize_name`→`fold_ascii`);
measured 0 residual non-ASCII and 0 fold-induced collisions across the full DB, but there is no CI
guard, so a future card with an unmapped non-decomposing letter (ª/º ordinals, ŋ…) silently fails to resolve.
**How to apply:** when reviewing card-name/deck-export/image/validation code, check WHICH of the three
names is used for the job; when reviewing V5/format checks, verify the set-name strings actually match
krcg's display names. `enrich_deck` (WASM+PyO3) currently has zero callers — dead export.
