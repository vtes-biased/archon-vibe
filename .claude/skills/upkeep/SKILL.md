---
name: upkeep
model: fable
description: The maintenance loop — lint the docs against the code and its sources, run oldest-first eviction verdicts on the board, and turn recurring review findings and owner corrections into standing rules. Use every 20 completed board lines or monthly, or when asked to do a maintenance, cleanup or health-check pass.
---

# Upkeep

A recurring pass over three surfaces. **The unit of time is a completed board
line**; this runs every 20 completed lines, or monthly, whichever comes first.
Anything untouched for 20 completed lines gets a verdict at the next pass.

Count completed lines from history — there is no counter file:

```sh
git log --oneline -S'- ' -- BOARD.md | head -40      # commits touching board lines
git log -1 --format=%ci -- BOARD.md                  # last board movement
```

Run `/watch-check` first: a fired trigger may add a line this pass then ranks. Then
work the three surfaces in order. Everything this pass proposes goes through
`/intake` like any other ask — **it does not write to the board directly**.

## 1. Docs lint

**Contradictions** — two pages asserting different things. Cross-check the pairs
that overlap by construction: `tournaments.md` against `domain/tournament-rules.md`
and `domain/judging.md`; `sync.md` against `access.md`; `principles.md` against
whatever cites it.

**Claims stale against code** — sample the load-bearing ones and verify. Symbol
names, file paths, field lists, endpoint tables and the "adding a new object type"
checklist rot fastest. A steps-list that mentions a manual registration the code
now derives automatically is the classic case.

```sh
grep -oE '`[a-z_]+\.(py|ts|rs|svelte)`' docs/*.md docs/domain/*.md | sort -u
```

**Domain claims have no code to lint against.** Check their **sources** instead:
does `reference/` still say what the page cites, and is the cited section number
still right? Flag any interview-sourced claim carrying a date older than a year for
re-interview — those are the ones that silently go stale, because nothing in the
repo contradicts them.

**Orphan pages** — anything not reachable from `docs/index.md`, and any page
nothing has cited or touched in 20 completed lines. Reachability:

```sh
grep -oE '\]\(([a-z/-]+)\.md' docs/index.md | sort -u
ls docs/*.md docs/domain/*.md
```

**Eviction candidates** — a page that has become a summary of a summary, or one
whose content would read better folded into its parent. A page earns its existence
only when the summary line pointing to it is much shorter than what it holds.

**Divergence review** — `tournaments.md` states two different things about where
the app departs from the rules, and they must not blur:

- a `> **Diverges from the rules.**` callout is a **known gap**, and each one
  should have a board line fixing it. A callout with no line is either finished —
  delete it — or work that fell off the board.
- everything else is a **deliberate choice**, written as plain prose with its one
  line of why. Each pass, ask whether the reason still holds; a choice whose
  rationale has expired becomes a board line.

## 2. Board eviction

Walk the active lines **oldest first** — `git blame BOARD.md` gives line age. Every
line gets one of four verdicts, and no line is skipped twice:

- **do** — it is still right and still wanted; leave it, reordering if the ranking
  rules now place it differently;
- **watch** — it is real but not now; it moves off the board into `WATCH.md` with a
  named trigger, not a vague deferral;
- **promote** — it turned out to be a subject, not an ask; it becomes docs content
  and the line goes;
- **drop** — it is no longer wanted; delete it.

Give each `WATCH.md` item the same verdict as a line — still wanted, or dropped —
since waiting is not exemption from eviction.

Check the hard limit. If the list is at 15, the pass must produce at least
one drop or promotion before any new line can land.

A drop that was a promise to a person is something to **say**, not merely delete —
if a GitHub feedback issue is tracking it, that issue needs a reply.

`docs/post-deploy.md` gets one extra check, because its items are verifiable rather
than judged: every item's gating sha must still resolve (`git cat-file -e`), and an
item whose sha is in the deployed tag has been owed since that deploy — say so
rather than letting it age quietly. An item that turns out to have already been run
is a deletion, not a verdict.

## 3. Retrospective

The only way the harness changes. **Two occurrences of the same class is a
harness problem, not a code problem.**

**Mine.** Spawn the `miner` agent — a cheap model, read-only — over the last 30
days. Overlap with the previous pass is harmless: evidence carries a sha or a
session id, so an occurrence counted twice is visible. Its brief names the two
sources:

```sh
git log --since=30.days --format='%h %s%n%(trailers:key=Friction,valueonly)'
find ~/.claude/projects/"$(pwd | tr / -)" -maxdepth 1 -name '*.jsonl' -mtime -30
```

The trailers are what ship recorded; the transcripts hold what it missed — the
owner's own words, and the reviewer's findings as they came back. A commit
without trailers predates them, or forgot them: that absence is itself a class.

**Judge.** The miner returns classes; you decide which are one class. Look for the
same finding recurring across unrelated diffs, the same owner correction given
twice, the same rule rediscovered by an agent that had no way to know it. Each
class seen twice becomes a proposed amendment with **its evidence** (the shas or
sessions) and **a one-line reason** — the friction it prevents. The amendment is a
principle line, a reviewer charter line, a lint rule or an edit to a skill; **a
correction the owner has had to give twice becomes a hook**, since written
instructions already failed to hold it. The rule lands with its reason beside it:
a rule without a reason cannot safely be removed.

**Remove.** Walk the standing rules — `CLAUDE.md`, the skills, the agents, the
hooks, `principles.md` — and give each a verdict: **keep**, or **lapsed** when its
reason no longer holds: the subsystem it guards is gone, a hook or lint now
enforces it mechanically, or the owner reversed the preference it encodes. A rule
that merely has not fired lately is working, not lapsed. A rule with no reason
gets one written, or is proposed for removal.

Every amendment and removal is filed through `/intake` as an ordinary board line.
**Nothing joins the harness because it seems useful.**

The owner's effort goes here rather than into the code: a correction the owner has to give
twice is a rule that should have been written down once.

## 4. Report

One short report to the owner: what the lint found, the eviction verdicts, whether
the board is trending down, the friction classes mined, and the
proposed amendments and removals. Then a slower question,
worth asking on a monthly pass: are the ranking rules still true, and is the board
actually shrinking?
