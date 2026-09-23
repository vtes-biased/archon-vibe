# Results reconciliation

Doc-impact: `wiki/vekn.md` (Tournaments, TWDA → Inbound), `wiki/post-deploy.md`.

The provenance rule already agrees with the wiki: "the VEKN record outranks the
archive" and "authority follows content". The TWDA fills only what a vekn.net
sheet does not carry, which on legacy sheets is exactly the round count and the
final VP.

## Measured 2026-09-23 on a full vekn.net scan (8,291 events)

The scan was a throwaway cache. Re-fetch with `VEKNAPIClient.fetch_all_events`
(about 15 minutes).

- **Legacy format, 2004-04 to 2010-12-19:** `rounds` "0R", no `vpf`, winner at
  pos 1, the other finalists all at pos 2, everyone else at pos 6. The final is
  folded into `gw`/`vp`. The sync now takes the winner's final GW back out unless
  that drops the winner below an eliminated player's GW (about 7% of sheets, never
  folded). After that, winners at 0 prelim GW rise from about 65 to about 520 of
  2,984, and the rate matches modern sheets by field-size band. The finalists'
  folded VP stays: no `vpf` to subtract.
- **The TWDA as the filler:** about 320 legacy winners have a TWD entry. Its
  `XGWY + Z in final` line gives the round count and the final VP. Only winners
  are covered, so the other finalists' final VP stays folded unless another source
  turns up.
- **Newer-format sheets whose GW exceeds their own round count:** vekn events
  7300, 7396, 8450, 8523, 9474, 9667, 11962, 12009, 12503, 12704, 12719 and 12804
  (2013 to 2025). Most are winners at exactly rounds+1, which looks like an
  organizer folding the final in. Some look like a wrong round count instead: 12009
  has 123 players over "3R+F", and 12503 has 5 players, 2 rounds and 14 VP.
- **Duplicated members** were far more common than the seven winners first found:
  117 sheets across all eras. The sync now keeps one row per member.
- **Not yet compared:** events with rounds in Archon, whether native or legacy v1
  archon, against the vekn.net sheet they were pushed as; and TWDA-only
  reconstructions against any vekn.net event that appeared later.
