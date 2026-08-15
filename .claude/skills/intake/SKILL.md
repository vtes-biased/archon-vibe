---
name: intake
description: The ingress loop — challenge an incoming request, idea or discovery before it reaches BOARD.md, then either add a line, fold it into an existing one, promote it to the wiki, or refuse it. Use whenever new work is proposed, a discovery surfaces mid-task, or the user asks to add something to the board.
---

# Intake

No work reaches the board unchallenged. Refusing a line is much cheaper than
evicting one later.

Ingress **proposes**; the owner accepts. Never write to `BOARD.md` before the owner
has said yes.

## 1. Read the board first

```sh
cat BOARD.md
```

The header carries the ranking rules, the hard limit and the no-waiting-state
rule. Everything below depends on them.

## 2. Four challenges

Run all four. Any one of them can end the intake.

**Conflict** — does this contradict a decision already recorded in the wiki, or
duplicate an existing line? Grep for it:

```sh
grep -rin '<keyword>' wiki/ BOARD.md
```

Changing a wiki decision is valid work; **silently violating one is not**. If it
conflicts, say so explicitly and make the decision change the ask, not a side
effect. If it duplicates, fold it into the existing line rather than adding one.

**Completability** — can you state "done" for it, machine-verifiably where
possible? If not, it is a subject, not an ask: it belongs on a wiki page. "Keep an
eye on X", "improve Y", "think about Z" all fail here. A subject that becomes wiki
content is a *successful* intake, not a rejection.

Externally-gated work does not go on the board — the board holds no waiting state.
If the ask is real and completable but waits on something outside our control,
record it as a **deferred item** on the wiki page that owns the subject (the VEKN
items live in `wiki/vekn-decommission.md`), stating the ask, its done-condition,
the evidence that cannot be reconstructed later, and a named trigger — a condition
someone could observe firing, not "later". `/upkeep` watches the triggers; a fired
one sends the item back through this loop as an ordinary line.

**Scope** — split only on real abstraction boundaries, so an agent can hold each
part in context. **Never split to defer.** A large cohesive change is one line.

**Doc-impact** — name the wiki pages this work will touch, before it starts. Egress
checks that list. "None" is a legitimate answer and must be justified. Domain pages
change only when the *domain* changed or a source was misread; a code change alone
never edits a domain page.

## 3. Check the limit

The board holds at most **15 lines**. If it is full, adding one means
dropping or promoting another — present that trade to the owner as part of the
proposal, oldest-first among candidates. Do not quietly exceed it.

## 4. Rank it

Place the line by the board's ranking rules, applied top to bottom:

1. user-reported defects
2. correctness
3. blocking work and useful refactorings
4. polish
5. new capability

Position *is* the priority — there are no tags, no estimates, no ids, no created
dates. The line's own text identifies it and git history knows its age.

## 5. Shape the line

One line, however long. It carries the ask in a verb you would recognise "done"
for, a **Done when** clause, and where the context is. Bulky elaboration — scope,
hazards, plan, measured evidence — goes in `board/<slug>.md` and dies with the
line.

Record the **doc-impact durably**: name the wiki pages in the line's **Done when**
("…and the index table in `wiki/sync.md` updated"), or in a `Doc-impact:` line at
the top of `board/<slug>.md` when the line has one. `/ship` confirms the contract
from what the line and its file say — a doc-impact that lives only in this
conversation is lost on the next session.

Write it in product language. No file paths in place of an explanation, no ticket
numbers, and never a `#N`, which reads as a GitHub issue.

## 6. Propose, then act

Present as **plain text that ends the turn**: the ask in one line, what the four
challenges found, the doc-impact list, the proposed position and the line verbatim.
Pre-tool-call text is not rendered in Claude Code, so a write-up followed
immediately by a tool call is invisible.

Then, in the **next** turn, ask for accept / decline / edit, and only then write
`BOARD.md`.

## Sources that feed this loop

- **Conversation** — the owner, or a discovery mid-task that is genuinely separable
  from the work in hand.
- **`/feedback-triage`** — GitHub feedback issues. It terminates here for anything
  it accepts.
- **`/upkeep`** — the wiki lint and the harness ratchet both propose work, and both
  come through this loop.
