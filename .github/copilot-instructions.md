## Three lifespans

Every artifact has exactly one. Anything you cannot assign a lifespan to is noise:
delete it.

- **Code** — permanent. The source of truth for *how*.
- **Docs** (`docs/`) — standing. The source of truth for *what is* and *what was
  decided*. Start at `docs/index.md`.
- **Task context** — ephemeral. Plans and findings die when the task completes.

There is no third place: no TODO file, no plan document, no in-chat checklist.

## Work tracking

`BOARD.md` is a list designed to shrink. One line per ask, completion is deletion,
position is priority, hard limit 15 active lines. **Read it before starting
anything.** Its header carries the ranking rules.

Bulky context for an in-flight line lives in `board/<slug>.md` and is deleted with
the line.

## Working rules

The paradigms are `docs/principles.md`. The ones that bite most often:

- **Comments are for traps only** — a subtle non-local constraint invisible at the
  point of reading. No narration, no changelogs, **no TODOs**.
- **Locality over DRY.** Explicit greppable local code over clever wrappers. Facts
  live in one place; similar-looking but causally unrelated code stays repeated.
- **Tests default to zero.** Add one only for a real regression, at an interface,
  traceable to a docs claim. Mocks are banned by default.
- **No red builds.**
- Read `docs/hazards.md` before touching the subsystems it names.
- A change lands as one unit: code, the docs pages it affects, and the board line
  deleted.
