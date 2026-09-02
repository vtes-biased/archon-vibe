---
name: ship
description: Take a line off BOARD.md and land it as one change — code, wiki, and the deleted board line — then send the diff to a fresh-context egress reviewer. Use when asked to work the board, pick up the next thing, or implement a specific board line.
---

# Ship

One line in, one change out. The unit of work is the **trinity**: code changed,
doc-impact wiki pages updated, board line deleted — in one commit.

## 1. Claim the line

```sh
cat BOARD.md
```

Take the **top** line unless the owner named a different one.

Read its `board/<slug>.md` if it has one. Read the wiki pages the line touches, and
`wiki/hazards.md` if it names any subsystem you are about to change.

**Assume a sibling agent is working the board beside you.** Nothing announces one:
`git status` is how you find out, so read it when you claim the line and again
before every commit — foreign paths mean someone is mid-line. Say in chat which
line you are taking and keep to your own commits.

**Commit explicit paths — `git commit -- <paths>`**, the only form that ignores
whatever else is staged. Naming paths to `git add` is not enough and `git add -A`
is worse: a plain `git commit` writes the *index*, so a sibling's staged deletion
rides along under your message.

Explicit paths still commit the **worktree** content of those paths, so a file you
share with a sibling carries their half-finished hunks under your message — and if
their half is what your half depends on, the commit does not run. **`BOARD.md` and
`wiki/` are shared by construction** — every board agent edits them — so diff them
by name and confirm every hunk is yours, however clean the code paths came back.
When one is not, stage that file as HEAD-plus-your-edits instead: reconstruct it
from `git show HEAD:<path>`, write it with `git hash-object -w`, and place it with
`git update-index --cacheinfo <mode>,<sha>,<path>`. Otherwise imperfect isolation
is acceptable when files genuinely overlap.

**Run that diff in the same shell invocation as the commit.** Across two calls a
sibling deletes their own board line in the gap, and `git commit -- BOARD.md`
takes the worktree rather than the hunks you just read and approved.

**`--amend` carries the same hazard from the other end**: the commit you mean to
amend may no longer be HEAD. Gate the write on the sha inside one invocation —
`[ "$(git rev-parse HEAD)" = <sha> ] || exit 1` — because `git log -1 && git
commit --amend` prints the answer without checking it, and reading it as its own
call opens the very gap the check exists to close. Diff against what you expected
after. If you do amend a sibling's commit you have reverted their work inside
their own message: restore it index-only with `git read-tree <their-sha>` then a
fresh `--amend`, never a `--hard` reset, which would take their worktree with it.

**Never `--amend --no-edit` bare.** Amend writes the whole *index*, so a sibling
who staged anything since your commit has their entire change absorbed under your
message — the same hazard as a plain `git commit`, reached from a command that
looks like it only edits your own work. To reshape a commit, build the tree you
mean without going near the real index: `git read-tree` into a `GIT_INDEX_FILE`
of your own, `git update-index --cacheinfo` your paths onto it, then
`git commit-tree` and `git update-ref`. That touches neither the index nor the
worktree, so a sibling mid-line never feels it.

**Once a sibling has committed on top of yours, a foreign hunk inside your commit
stands.** Rewriting it rewrites theirs, which is strictly worse than the
misattribution. Leave it, and say so in the report.

## 2. Confirm the contract

Before writing code, state — to yourself, and to the owner if anything moved:

- the **done-condition**, from the line;
- the **doc-impact**: which wiki pages change, or why none do — intake recorded it
  in the line's **Done when** or a `Doc-impact:` line in its `board/<slug>.md`;
- anything the line assumed that turns out to be false.

A line whose premise is wrong goes back through `/intake`; do not silently
reinterpret it.

## 3. Execute

Fan out explorers freely — reading is cheap, and a wrong assumption about a
subsystem is what actually costs here.

**Scope grows in place.** When exploration reveals adjacent necessary work sharing
the same abstraction, do it inside this task rather than filing a follow-up. Only
genuinely separable discoveries go back through `/intake`. Never leave the board
longer than you found it, minus the line you completed.

### How to write the code

The full statement is `wiki/dogmas.md`; these are the rules that decide most
diffs, and the reviewer checks every one of them.

**Comments are for traps only.** The wiki holds the why, the code shows the how. A
comment is justified only by a subtle **non-local** constraint invisible at the
point of reading — "this must fire post-commit or it deadlocks", "server wins here
because the device's copy is stale". Never restate the code, never narrate what
changed, never leave a changelog. If an inline comment runs past ~2 lines it is
narrating: cut it, or move the detail to the wiki page that owns the subsystem.
**No TODOs** — a discovered task is done now or goes through `/intake`.

**Locality over DRY.** Co-locate what changes together. Prefer explicit, greppable
local code over a clever wrapper. Extract a module only behind an interface much
narrower than what it hides; a wrapper that forwards, a layer that re-exports, or a
class holding one method is pure token cost and misuse surface. Layering ceremony —
clean-architecture and hexagonal indirection — is an anti-pattern here.

**DRY applies to facts, not to shapes.** A schema, a constant, a protocol rule, a
permission predicate lives in exactly one place. Two blocks that merely *look*
alike but change for different reasons stay repeated — never factor on
resemblance. Deduplicate only large or genuinely hazardous duplication, not a few
near-identical lines.

**KISS means avoiding hazard, not avoiding work.** A big rewrite is cheap; a
non-local interdependency is not. Prefer the design a fresh agent can understand
from the files in front of it. Before touching a subsystem named in
`wiki/hazards.md`, read that entry — those are the traps that have already bitten.

**Tests: the default is zero.** Add one only for a real regression with
consequences, asserted at an interface, against the shipped artifact, one per
invariant. Import shared constants rather than copying them. **Mocks are banned by
default** — a mock that mirrors the code tests the code against itself; use a real
dependency or don't test that path. Never encode an engine-impossible state. Every
test must trace to a claim in the wiki; if you cannot name the claim, the test does
not belong. Weakening or deleting an existing test is a rejection unless a
wiki-declared behavior changed in the same diff.

**Delete as you go.** A compatibility shim for a case that no longer exists, a dead
branch, a defensive check the caller already excludes — remove it in the change
that made it dead rather than leaving it for the reviewer to demand.

## 4. Land the trinity

**Code.** Run the gates that cover what you touched and confirm green — there are
no red builds. `just test`, `just lint`, or the narrower target for the stack you
changed (`wiki/testing.md`).

**Wiki.** Update the pages named at ingress in the same change. Pivots are edits:
when a decision is overturned the wiki changes now, and it never preserves the
deprecated fact — git holds the history. A standing decision gets **one line** of
rationale, and only when the rejected alternative is attractive enough that a
future agent would plausibly redo it. No reasoning journeys, no ADRs, no
"Resolved:" annotations.

A **domain page** changes only when the domain itself changed, or a source was
misread. A code change alone never edits one — if the code now contradicts a domain
page, that is a divergence to record on the implementation page, not a domain edit.

**Board.** Delete the line. Delete its `board/<slug>.md` too. Deletion is the
completion gesture — there is no closed state to move it to.

**A production step is part of the trinity, not a note to yourself.** When the work
leaves something that must be run or set on production once the commit is live — a
one-time re-save, a backfill, a console setting — it goes in `wiki/post-deploy.md`
in this same commit, naming the gating commit and why running it earlier is wrong.
Never into a subsystem page's prose: that is where such items got lost, and the
subsystem page holds the standing fact, not the runbook. If the remaining work
carries judgment rather than execution — output to review, membership to diff — it
is a board line with a production step, not a post-deploy item.

**Run the comment pass yourself before committing.** Read every comment line the
diff adds or leaves beside changed code — `git diff | grep -E '^\+.*(#|//|<!--)'`
is a start — and delete any that states what the wiki (including the page this
change edits), another comment or the code already says. The reviewer runs the
same pass by name; a comment it has to trim is a review round you could have
skipped.

**Commit.** One commit carrying all three. Reference a GitHub issue as
`Reported in #N.` when the work fixes a user-reported one; never a closing keyword,
and never a board reference.

## 5. Egress

**Only a change that touches code gets a review.** A doc-only change — a wiki
edit, a board eviction, a decision written down, a line promoted to a wiki page —
lands on the commit and is reported to the owner directly. The reviewer guards
code the owner is not reading line by line; prose the owner *is* reading does not
need a second reader, and spawning one spends tokens and wall-clock to tell them
what they can already see.

Otherwise, spawn the `reviewer` subagent, which has **not** seen this
conversation. Give it exactly three things and nothing else:

- the diff (`git diff <base>..HEAD`, or the staged diff);
- the wiki, by pointing it at `wiki/`;
- the board line's text and done-condition, verbatim.

Do not include your reasoning, your plan, or a summary of what you meant to do. The
review is worthless if it reads the diff through your explanation of it.

Its findings come back **blocking** (a charter violation) or **advisory**
(non-gating). **Every finding is addressed.** Advisory means it does not stop the
landing, never that it may be dropped.

- Blocking findings get fixed, and the reviewer runs again on the new diff.
- Advisory findings are fixed in this same change, unless the fix is genuinely
  separable — then it goes through `/intake` and rides this commit as a board
  line. Nothing leaves this loop unresolved.
- A finding you believe is wrong is escalated to the owner, not dropped.
- Expect **"looks good"** to be a common verdict. It is not the reviewer's job to
  find something, and report-everything must not become find-something.

**After two rejection rounds, stop and escalate to the owner**, compressed to the
inflexion point: the one disagreement the rounds turn on, each side in a sentence,
and your recommendation. Do not open a third round.

First-review scope growth — the reviewer demanding the refactor now rather than a
follow-up line — is normal and you do it. Second-round growth should be
exceptional; if it happens, that is an escalation, not a third round.

## 6. Report

Tell the owner what shipped, which wiki pages moved, which line is gone, and what
became of each finding — fixed here, or a new board line. Short.
