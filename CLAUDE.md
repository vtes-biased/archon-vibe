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
memory store: project facts go in the right wiki page, and a standing correction
goes in this file, a skill or an agent. Claude Code's auto-memory is off here
(`.claude/settings.json`).

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

Three named procedures feed them: **`/feedback-triage`** for GitHub feedback
issues, **`/changeset`** for what is about to ship, before the tag is cut, and
**`/post-deploy`** for the actions a deploy unlocks and the issues it made live.

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
  or gets done now. Code never references the wiki. `just lint` fails on a
  comment block over three lines, and egress deletes what the wiki already says.
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

## Git

- **Trunk-based.** Work lands on `main`: a short-lived branch is fast-forwarded in
  and deleted. Commit only when asked; pushing is the owner's call.
- **Parallel sessions land on `main` mid-task.** Before writing `BOARD.md` or
  committing, re-read `git log --oneline -3`, `git status --short` and
  `git diff --cached --stat`: an index behind HEAD would revert a sibling's work.
- **Stage explicit paths, never `git add -A` or `commit -a`**, and read every `??`
  line first. Removing an ignore rule while its file was still on disk once pushed
  the beta vault password to this public repo. Check `git show --stat HEAD` before
  pushing.

## Operating the environments

- **Beta** (`deploy@57.129.110.107`) is yours to operate over ssh: restarts, env
  edits, script runs. Restore the deploy-managed state after a window.
- **Production** (`ubuntu@46.226.104.123`) is the owner's hand only: every command
  against it, read-only probes included, is handed over as text and its output
  awaited. The owner's shell history is the audit trail.
- **Secret material never enters context**: no `sops -d` or `sops` edit of
  `deploy/secrets/`, no private keys, no printed tokens. Derive the answer from the
  readable identifiers and hand the command over.
- **Grafana without the MCP servers**: the shell exports `GRAFANA_TOKEN_CODEX`
  (beta, `https://codexofthedamned.grafana.net`) and `GRAFANA_TOKEN_VTESBIASED`
  (production, `https://vtesbiased.grafana.net`) for `curl -H "Authorization:
  Bearer $GRAFANA_TOKEN_…"`. Reference the variable, never its value.

## Human inflexion points

Built for a professional owner: decisions, not narration. Interrupt only for dogma
and paradigm choices (short option sets with a recommendation), irreversible or
outward-facing actions, genuine changes to product scope, and an egress deadlock
after two rounds. Everything else proceeds.

- **A decision write-up ends its turn.** Text before a tool call is not shown in
  the console, so a write-up followed by `AskUserQuestion` reaches the owner as bare
  chips. Paste the code extracts, walk the failure, give the options, stop; the
  question form comes next turn, if at all.
- **Spikes and evaluations go one step at a time.** Name the smallest next step
  and do only that; a real run against a box, secrets or a design choice stops for
  the owner first.
- **Fan-out edit passes use the `mass-edit` agent**, pinned to Sonnet with no
  sub-agents, never `general-purpose` with a model override, whose forks run on the
  session model.
- **The owner holds IC and Rulemonger** and can grant any role in the app. A role
  or credential fix is never routed to "an official".

Effort goes into the harness, not the code: the ratchet turns a repeated correction
into a standing rule.
