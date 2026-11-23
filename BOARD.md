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

- Retire the two-way VEKN tournament calendar and results sync (Stage 1) and lift the limitations it imposed — stopping inbound tournament sync and outbound event/results push while keeping member sync and member push intact, lifting the 2–4 round cap and post-push round lock, unfreezing rank/format/start/proxies on linked events (keeping the Standard/Limited-only championship rank policy), lifting the VEKN delete block (gh-6) while restricting Finished tournament deletion to IC only and hiding Delete on offline-locked events, removing the vekn-linked guard on archival result corrections, stamping event codes inline at creation without a boot sweep, and removing the dead vekn.net calendar links, sync buttons, status badges, and push warnings from the UI and guides — detailed in `board/retire-vekn-tournament-sync.md`. **Done when** no scheduled job, admin action, or route syncs or pushes tournaments to vekn.net, member sync/push and TWDA submission keep working, all listed limitations are lifted in engine, backend, and frontend (including all 5 locales), `mise run test` passes, and the docs and watch items listed in `board/retire-vekn-tournament-sync.md` are updated.
- Explain what the event and member city field means — the community it belongs to, usually the nearest large city, not the exact location — with a hint on the event form and the member profile in every locale, so organizers stop looking for their village (gh-89). **Done when** both forms carry that hint, the event hint points the exact location to Address, and `docs/tournaments.md` (city row) and `docs/product.md` state the field's purpose: community size and turnout for organizers and the IC, which is why only larger cities are offered.
