# Archon

Offline-first PWA for running VTES tournaments and managing VEKN membership.
Svelte + FastAPI + PostgreSQL, with a shared Rust core compiled to WASM and PyO3.

## Three lifespans

Every artifact has exactly one. Anything you cannot assign a lifespan to is noise:
delete it.

- **Code** — permanent. The source of truth for *how*.
- **Wiki** (`wiki/`) — standing. The source of truth for *what is* and *what was
  decided*. Start at [`wiki/index.md`](wiki/index.md).
- **Task context** — ephemeral. Plans, findings, reasoning. Dies when the task
  completes. An in-flight board line may park elaborated context in
  `board/<slug>.md`, deleted with the line.

There is no third place. Not a TODO file, not a plan document, not a personal
memory store: project facts go in the right wiki page.

## The board

[`BOARD.md`](BOARD.md) is a list designed to shrink. One line per ask, completion
is deletion, position is priority, hard limit 15 lines, no waiting state —
externally-gated work is deferred on the wiki page that owns it, with a named
trigger. Its own header carries the ranking rules. Read it before starting
anything.

## The loops

- **`/intake`** — no work reaches the board unchallenged. Conflict against a wiki
  decision, completability, scope, doc-impact.
- **`/ship`** — take the top line, execute, land the trinity, spawn the reviewer.
- **`/upkeep`** — the maintenance pass: wiki lint, board eviction, harness ratchet.

Two named ingress procedures feed them: **`/feedback-triage`** for GitHub feedback
issues, and **`/post-deploy`** for the release changeset and issue closing.

**A unit of work lands as one change**: code changed, the wiki pages named at
ingress updated (or their absence justified), the board line deleted. Wiki currency
is mechanical, not aspirational. Never leave the board longer than you found it,
minus the line you completed.

Scope grows in place — when exploration reveals adjacent necessary work sharing the
same abstraction, do it inside the task. Only genuinely separable discoveries go
back through ingress.

## Working rules

The paradigms are [`wiki/dogmas.md`](wiki/dogmas.md) and ingress and egress both
check against that page. The ones that bite most often:

- **Comments are for traps only.** The wiki holds the why, the code shows the how.
  No narration, no changelogs, **no TODOs** — discovered work goes through ingress
  or gets done now. Code never references the wiki.
- **Locality over DRY.** Explicit greppable local code over clever wrappers.
  Similar-looking but causally unrelated code stays repeated.
- **No red builds.** Never report done over a failing build, test or lint.
- **Read [`wiki/hazards.md`](wiki/hazards.md)** before touching the subsystems it
  names. Non-local traps are the expensive kind of mistake here.
- **Tests**: default to none. Add one only for a real regression, at an interface,
  against the shipped artifact, one per invariant. Mocks are banned by default.
- **Never put a board reference in a commit message or a comment.** `#N` in a
  commit means a **GitHub issue**, and a fix for a user-reported one carries
  `Reported in #N.` — never a closing keyword, which would auto-close on push when
  the issue should close on **deploy**.

## Human inflexion points

Built for a professional owner: decisions, not narration. Interrupt only for dogma
and paradigm choices (short option sets with a recommendation), irreversible or
outward-facing actions, genuine changes to product scope, and an egress deadlock
after two rounds. Everything else proceeds.

Effort goes into the harness, not the code: the ratchet turns a repeated correction
into a standing rule.
