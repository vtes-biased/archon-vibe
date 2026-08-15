---
name: upkeep
description: The maintenance loop — lint the wiki against the code and its sources, run oldest-first eviction verdicts on the board, and mine recurring review findings for harness amendments. Use every 20 completed board lines or monthly, or when asked to do a maintenance, cleanup or health-check pass.
---

# Upkeep

A recurring pass over three surfaces. **A cycle is one completed board line**; this
runs every 20 cycles, or monthly, whichever comes first. Anything untouched for 20
cycles goes on trial at the next pass.

Count cycles from history — there is no counter file:

```sh
git log --oneline -S'- ' -- BOARD.md | head -40      # commits touching board lines
git log -1 --format=%ci -- BOARD.md                  # last board movement
```

Work the three surfaces in order. Everything this pass proposes goes through
`/intake` like any other ask — **it does not write to the board directly**.

## 1. Wiki lint

**Contradictions** — two pages asserting different things. Cross-check the pairs
that overlap by construction: `tournaments.md` against `domain/tournament-rules.md`
and `domain/judging.md`; `sync.md` against `access.md`; `dogmas.md` against
whatever cites it.

**Claims stale against code** — sample the load-bearing ones and verify. Symbol
names, file paths, field lists, endpoint tables and the "adding a new object type"
checklist rot fastest. A steps-list that mentions a manual registration the code
now derives automatically is the classic case.

```sh
grep -oE '`[a-z_]+\.(py|ts|rs|svelte)`' wiki/*.md wiki/domain/*.md | sort -u
```

**Domain claims have no code to lint against.** Check their **sources** instead:
does `reference/` still say what the page cites, and is the cited section number
still right? Flag any interview-sourced claim carrying a date older than a year for
re-interview — those are the ones that silently go stale, because nothing in the
repo contradicts them.

**Orphan pages** — anything not reachable from `wiki/index.md`, and any page
nothing has cited or touched in 20 cycles. Reachability:

```sh
grep -oE '\]\(([a-z/-]+)\.md' wiki/index.md | sort -u
ls wiki/*.md wiki/domain/*.md
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
- **date** — it is real but not now; it needs a trigger, which makes it a triggered
  line with a named condition, not a vague deferral;
- **promote** — it turned out to be a subject, not an ask; it becomes wiki content
  and the line goes;
- **drop** — it is no longer wanted; delete it.

Then check the **triggered** lines: has any trigger fired? A fired trigger promotes
the line into the active list at its ranked position, which may push the active
list to its limit — resolve that here rather than at the next intake.

Check the hard limit. If the active list is at 15, the pass must produce at least
one drop or promotion before any new line can land.

A drop that was a promise to a person is something to **say**, not merely delete —
if a GitHub feedback issue is tracking it, that issue needs a reply.

## 3. Harness ratchet

Mine the recent egress reviews and owner corrections. **Three occurrences of the
same class is a harness problem, not a code problem.**

Look for: the same advisory finding recurring across unrelated diffs; the same
owner correction given more than twice; the same rule being rediscovered by an
agent that had no way to know it.

Each qualifying class becomes a proposed amendment — a new dogma line, a charter
line for the reviewer, a lint rule, a hook, or an edit to one of these skills —
filed through `/intake` as an ordinary board line. **The harness grows only through
this ratchet.** Do not add a skill, an agent or a hook because it seems useful.

HitL effort goes here rather than into the code: a correction the owner has to give
twice is a rule that should have been written down once.

## 4. Report

One short report to the owner: what the lint found, the eviction verdicts, whether
the board is trending down, and any proposed amendments. Then a slower question,
worth asking on a monthly pass: are the ranking rules still true, and is the board
actually shrinking?
