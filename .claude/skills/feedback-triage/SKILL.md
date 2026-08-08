---
name: feedback-triage
description: Triage user-feedback GitHub issues on vtes-biased/archon-vibe — verify each report against the code, get a product-manager verdict, validate the call with the owner, then either reply-and-close (won't do / already possible / needs info) or file a pst ticket. Use when asked to look at, triage, answer, or handle GitHub issues, user feedback, or bug reports from users.
---

# Feedback triage

In-app feedback (`backend/src/routes/feedback.py`) files GitHub issues on
`vtes-biased/archon-vibe`, labeled `feedback` plus one of `bug` / `enhancement` /
`question`. Every body ends with a `---` metadata block: submitter VEKN id + roles,
app version, page route, locale, user agent. The owner also files issues by hand
under the same `feedback` label, usually with their own analysis appended.

**The repo is public and reporters are real, named people.** Every comment is
permanent, public, and attached to someone's VEKN identity. No PII, no internal
infra detail (env vars, server paths, other reporters), no dismissive tone.

**Not all feedback is relevant.** Declining is a normal, frequent outcome. The job
is a code-grounded verdict, not a queue-drain.

## Issue states

| State | Meaning |
|---|---|
| open, no `tracked` | needs triage — this is the work queue |
| open + `tracked` | accepted, pst ticket filed, waiting to ship |
| closed | resolved, won't-do, duplicate, answered, or not actionable |

Triage always moves an issue out of the first row into one of the other two.

Pull the queue:

```sh
gh issue list --label feedback --state open --json number,title,labels \
  --jq '.[] | select(.labels|map(.name)|index("tracked")|not) | "\(.number)\t\(.title)"'
gh issue view N --json number,title,body,labels,author,comments
```

Work **oldest number first, one issue at a time**, fully through step 5 before
starting the next — the owner validates each one and shouldn't juggle several.
If invoked with an issue number, do just that one.

## 1. Ground the report in the code — be critical

Default stance: the report describes what the user **experienced**, not what the
software **does**. Do not accept a claim on plausibility. Find the file and line.

- **Does the described behavior actually exist?** A "missing feature" is often
  present but undiscoverable. (Issue #4: the score-override button exists — the
  real problem was that a judge under time pressure never found it.)
- **App version** — compare to current. A stale cached PWA can report a bug fixed
  weeks ago.
- **Role** — `role: player` explains a lot. "X doesn't work" is often correct
  access control, not a defect.
- **Data vs code** — role grants, VEKN sync gaps, migrated tournaments are ops
  problems with no code change behind them. (Issue #3: judges with no judge role →
  a grant/migration gap, not a broken permission system.)
- **Bundled reports** — one issue often carries 2–3 separable asks. Split them and
  give each its own verdict.
- Reproduce cheaply if you can; never build a repro harness at this stage.

Write down what you verified and where (`file.py:123`). That grounding is what the
owner reviews — a verdict with no file reference is not ready to present.

## 2. Dedup against the board

```sh
grep -n -i '<keyword>' .pst/tickets
```

If it's already tracked (open **or** closed — a closed ticket may mean "already
fixed, they're on a stale build"), that *is* the outcome: reply with the existing
state, label or close accordingly, file nothing new.

## 3. Product-manager verdict

Launch the `product-manager` agent with: the verbatim report, your code grounding,
the reporter's role, and the dedup result. Ask for: is this real; who benefits and
how often; the minimal viable fix; a priority; or the reason to decline.

The PM owns VEKN rules and product priority. Its verdict is **input, not a
decision** — if it contradicts what you read in the code, say so and push back
before presenting.

Every ask lands in exactly one bucket:

| Verdict | Meaning | Action |
|---|---|---|
| **Defect** | real bug | pst ticket, **p2 minimum** (any actual issue is p2 min) |
| **Improvement** | works as designed, but better is possible | pst ticket, p2/p3 |
| **Already possible** | the feature exists — discoverability or docs gap | reply pointing at it; a p3 discoverability ticket if it genuinely bit a real user |
| **Ops / data** | no code change (role grant, data fix, migration) | do the ops action or ticket it; reply |
| **Duplicate** | already on the board or another issue | reply with the tracking |
| **Needs info** | not actionable without repro/details | reply naming exactly what's missing, close, invite a re-file |
| **Won't do** | out of scope, against VEKN rules, contradicts the architecture, or cost ≫ value | reply with the reason, close as not planned |

**Every issue leaves triage either closed or filed** (`tracked` + a pst ticket).
Nothing stays open and untriaged — an issue we can't act on gets a reply and a
close, not a hold. "Needs info" is a close: say precisely what would make it
actionable and ask them to file again with it, rather than parking an open issue
nobody is working.

Cheap-and-isolated is not by itself a reason to accept — CLAUDE.md's
discuss-before-filing rule applies to feedback-derived tickets too.

## 4. Validate with the owner — MANDATORY GATE

**Never** post a comment, close an issue, apply a label, or file a ticket before
the owner signs off. One issue per round.

Present as **plain text that ends the turn**:

1. The report, in one line.
2. What you verified, with `file:line` — including anything that contradicts the report.
3. The PM verdict, and where you disagree with it.
4. Your recommendation (one bucket from the table).
5. The **draft reply, verbatim** — the exact text that would be posted publicly.
6. The **draft pst ticket body**, if any.

Then, in the **next** turn, use `AskUserQuestion` for accept / decline / edit.
Text emitted before a tool call in the same turn is not rendered in Claude Code, so
a write-up followed immediately by a tool call is invisible to the owner.

## 5. Act

**Accepted** (defect / improvement):

```sh
pst add "<body>" --tag p2
gh issue comment N --body "<approved reply>"
gh issue edit N --add-label tracked
```

**Declined / answered / duplicate:**

```sh
gh issue comment N --body "<approved reply>"
gh issue close N --reason "not planned"    # won't do, duplicate
gh issue close N --reason completed        # already possible, ops fix applied
gh issue edit N --add-label wontfix        # or: duplicate
```

**Needs info** — also a close, with `--reason "not planned"` and a reply naming
the exact missing detail plus an invitation to file again. Don't leave it open.

### Cross-reference rules — both directions matter

- **Never write a pst number in a GitHub comment.** `#12` autolinks to GitHub
  issue 12 and misleads a public reader. Say "tracked internally", never the
  number. (Same reasoning as CLAUDE.md's no-pst-numbers-in-commits rule.)
- **Never write `#N` for a GitHub issue in a pst ticket body.** In a pst body
  `#N` is a ticket reference. Use `gh-4`, or the full issue URL.
- A ticket born from feedback carries: the code grounding (`file:line`), the
  reporter's actual constraint (role, device, tournament situation), and `gh-N`.
  Close the GitHub issue when the fix **deploys** — the pst ticket closes on
  commit (CLAUDE.md), the public issue closes when the reporter can see it work.

## Reply style

English always, whatever the reporter's locale. 2–6 sentences.

Thank them → name what you actually checked → give the verdict plainly → say what
happens next. Decline in product terms, never codebase terms. Never promise a
date. Don't add @-mentions: the body already mentions the reporter, and a comment
notifies them.

**Accepted:**
> Thanks for the report — confirmed. Past-tournament entries currently show the
> event but not your finishing position, which is exactly the number you'd want
> there. It's on the list to fix; I'll close this issue once it's live.

**Already possible:**
> Thanks — this one is already supported: a judge can override any table's VP
> total from the results screen, which covers Lifeboon and every other rule that
> breaks the usual VP arithmetic. It clearly wasn't findable under time pressure
> though, so I'm looking at making that control more obvious.

**Needs info** (closed, not parked):
> Thanks for flagging this. I couldn't reproduce it from the description — to
> chase it down I'd need the tournament name and roughly when it happened, plus
> what you saw on screen at that moment. Closing this one for now; please send it
> again with those details and I'll pick it straight up.

**Won't do:**
> Thanks for taking the time. I'm going to pass on this one: it would only apply
> to a rare table configuration, and supporting it would make the scoring screen
> meaningfully harder to use for every event. Closing — but do keep the feedback
> coming.
