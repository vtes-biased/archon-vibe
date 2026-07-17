---
name: entitled-level-vs-overlay-catchup-asymmetry
description: A new full-access entitlement added to entitled_level only wires the LIVE broadcast path; the full-corpus catch-up uses base_data_level snapshot + _overlay_frames, which must be extended separately or holdings/full fields silently miss on resync
metadata:
  type: feedback
---

Adding a full-access branch to `entitled_level` (broadcast.py) only covers the **live**
SSE path (broadcast_precomputed / broadcast_personal). The **full-corpus browser
catch-up** does NOT call entitled_level — it serves the snapshot at
`base_data_level(viewer)` (db.py) then layers `_overlay_frames` (main.py). So a
non-standard full grant is only half-wired unless you ALSO add a matching branch to
`_overlay_frames`.

**Why:** the promo type (child #493 of epic #492) grants NC→full for promos regardless
of country. entitled_level got the branch (broadcast.py ~:153), but `_overlay_frames`
only upgrades own-profile, own-decks, same-country users/tournaments, and organized
tournaments — NOT promos. base_data_level(NC)="member", so an NC gets the member
projection (holdings stripped) on every snapshot/resync and only ever sees full
`holdings` via a later live save. Latent until #497 writes real holdings, then NC
officials silently show empty stock after any resync (DB_VERSION bump, av mismatch,
3-day staleness all trigger resync).

**How to apply:** whenever a review adds/【sees】 a new full-access rule that is NOT
country-scoped and NOT own-object (the two cases _overlay_frames already handles),
check `_overlay_frames` in main.py for a symmetric branch. The fingerprint
(_OVERLAY_ROLES, db.py:230 = IC/NC/PRINCE) correctly fires the resync on role change —
the bug is that the resync re-delivers the wrong (lower) projection. Fix = stream the
type at full in _overlay_frames for the entitled role. See [[projection-tier-column-vs-content-split]]
and [[tournament-member-projection-is-exclude-list]] for related projection traps.
