# Old VEKN result sheets

Doc-impact: `wiki/vekn.md` (Tournaments import).

## Finals folded into the prelim totals

Measured 2026-09-23 against the TWDA winners (VEKN API per event, and the TWD
entries' own `XGWY + Z in final` lines):

- 2011 onward, vekn.net `gw`/`vp` are prelim-only: 335 of 336 TWD lines giving
  both halves match the VEKN record exactly.
- Before about October 2010 they include the final. Across 324 TWD-linked winners
  of that era, 43 carry an impossible prelim score (GW above the round count, or VP
  above 5 per round) and 46% have GW equal to the round count, against about 15%
  from 2011. Subtracting one GW and the finals VP brings both back to the modern
  rates (gw == rounds 13%, gw == 0 11% against 8%).
- Many of those events carry no `vpf` at all, so the final's VP cannot always be
  taken back out; the winner's extra GW always can.
- Only winners were measured. The cutoff and whether other finalists' rows fold
  their finals VP too must be checked across every pre-2011 event the sync holds,
  not just the TWD-linked ones.

The re-sync rebuilds a rounds-less import from VEKN whenever the standings differ,
so a hand correction is overwritten: the fix belongs in the importer.

## The same member twice on one sheet

Seven prod events list the winner twice (vekn event ids 9915, 7713, 8754, 5793,
6580, 9166, 2804). vekn.net itself carries the duplicate — 7713 lists Jordi
Bestard (3190089) at position 1 with 1GW5 and again at position 6 with nothing.
Some pairs are identical rows (5793, 6580), others carry a second real score
(9915: 1GW5 and 0GW3) that cannot be attributed to anyone else.
