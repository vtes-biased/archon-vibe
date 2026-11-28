# Board

A list designed to shrink. **The goal is zero.** Completion is deletion — there is
no closed state, no archive; git history is the record and `git blame` knows a
line's age.

**Order is priority.** Ranking rules, applied top to bottom when two unrelated
lines compete:

1. user-reported defects
2. correctness
3. blocking work and useful refactorings
4. polish
5. new capability

**Hard limit: 15 lines.** Adding a sixteenth forces a drop or a promotion to the
docs. **No waiting state**: work that waits on a date or an outside trigger is in
[WATCH.md](WATCH.md), and returns through `/intake` when its trigger fires.

**Every line must be completable** — if "done" cannot be stated, it is a subject:
promote it to a [docs](docs/index.md) page and delete the line. Context lives in
the docs; asks live here. Bulky context for an in-flight line goes in
`board/<slug>.md`, deleted with the line.

Board changes ride the commit that earns them.

- Delete the mistaken historical tournament rows in `docs/vekn-decommission.md#ic-record-curation--events-to-delete` now that ICs can delete any event. Done when every listed entry is gone and its evidence section is updated.
- Settle the winner on the rows in `docs/vekn-decommission.md#ic-record-curation--rows-that-disagree-with-the-archive-about-who-won` and correct whichever side is wrong. Done when each row's `winner` matches the record the IC accepts and its evidence section is updated.
- Settle the eight archive-reconstruction pairs in `docs/vekn-decommission.md#archive-reconstructions-of-an-event-we-already-hold` (soft-delete same-event duplicates and transplant `external_ids.twda_entry`, or record distinct events). Done when no pair is ambiguous, the mixed-vekn class of `dedup_tournaments.py` reports only pairs it can propose, and its evidence section is updated.
- Review the Prince / NC divergence in `docs/vekn-decommission.md#prince--nc-divergence--legacy-archon-vs-the-app` with someone who knows the appointments and align roles (never a blind union). Done when every divergent name has a verdict reflected in roles and its evidence section is updated.
