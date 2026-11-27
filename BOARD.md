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

- Default new tournaments' `decklists_mode` to `All` — change the tournament creation default (frontend form, backend model/route, and engine fallback) from `Winner` to `All` so organizers share full-field decklists by default now that non-finalist decks are unlinked and players control finalist attribution and deck privacy. **Done when** newly created tournaments default to `decklists_mode: All`, existing tournaments keep their stored mode, `mise run test` and `mise run lint` pass, and `docs/tournaments.md` is updated.
