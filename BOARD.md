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

- Let a Prince see the members they sponsored: the members directory's Mine filter is empty for every Prince because their device never receives a member's sponsor — only IC and an NC in their own country do — so French Princes and a UK Prince find none of the members issued under their prefix. Add `coopted_by` to the member projection of a user: the id prefix and vekn.net's public registry already make a member's sponsor public. **Done when** a Prince's Mine filter lists every member whose recorded sponsor is them; a production check (owner-run) shows the members under the reported prefix carry that Prince as sponsor, or they are repaired in this change, including the case where one official's prefix starts another's; and `docs/sync.md` (user row, member column) and `docs/vekn.md` (`coopted_by`) are updated.
- Explain what the event and member city field means — the community it belongs to, usually the nearest large city, not the exact location — with a hint on the event form and the member profile in every locale, so organizers stop looking for their village (gh-89). **Done when** both forms carry that hint, the event hint points the exact location to Address, and `docs/tournaments.md` (city row) and `docs/product.md` state the field's purpose: community size and turnout for organizers and the IC, which is why only larger cities are offered.
