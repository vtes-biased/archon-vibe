---
name: report-promos-no-state-gate
description: ReportPromos is a deliberately ungated mutating engine event (works in Finished); the missing gate is the invariant, not a bug — pinned by one test.
metadata:
  type: project
---

The `ReportPromos` TournamentEvent (engine `mod.rs` apply_event arm, parsing.rs
arm) deliberately has NO state gate and does NOT call `update_standings` — unlike
nearly every other mutating event. A future reviewer/dev will read the ungated arm
as a missing guard and be tempted to "fix" it with a state check.

**Why:** the primary entry flow is the Finished console (FinishedResults CTA), and
re-submitting corrects an already-filed report by wholesale replacement (empty array
clears it). A state gate would silently break both the corrections flow and the CTA.
Handler sets `promos_distributed` wholesale + `promo_stock_source_uid` defaulting to
`actor.uid`. It is member-visible (absent from `_TOURNAMENT_MEMBER_EXCLUDE`) and the
server NEVER writes these fields (offline device authoritative; the #497 ledger only
reads/attributes them).

**How to apply:** don't flag the missing gate as a defect and don't re-add coverage.
The invariant (post-finish success + replace-not-merge + submitter default) is pinned
by `test_report_promos_post_finish_replaces_whole_list` in `tournament/tests.rs`.
Parsing rejects qty=0 / empty promo_uid — that's plain input-validation restatement,
left untested by design. Epic context: `.pst/details/492-promo-tracking.md` (#495).
See [[trap-tournament-action-route-untested]] for the sibling post-engine route gap.
