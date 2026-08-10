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

**`Page:` is always `/help`** — that's the only screen the feedback form lives on,
so the route says nothing about where the problem was. Ignore it; never treat it
as a hint about the affected page.

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

## Reply style — short, first person, human

**One or two sentences. Really.** The owner writes these as himself, not as a
project. Match that voice:

- **First person "I"** — "I'll add it", "I still have the old database". Not "we
  will investigate", not "the team".
- **Open with thanks, not agreement.** "Thanks", "Thanks for the feedback", "Nice
  catch", "Thanks for catching that". Never open with **"You're right"** — it
  reads as AI boilerplate, and it makes the reply about the verdict instead of
  about the person who bothered to write in.
- **Casual and plain.** No throat-clearing ("Thanks for taking the time to file
  this"), no corporate prose, no restating their report back at them.
- Say **what's happening and how**. That's the whole job. Skip the reasoning
  chain, the file names, the architecture.
- Decline in product terms, never codebase terms.
- English always, whatever the reporter's locale.
- Never promise a date. Never a pst number. No @-mentions — the body already
  mentions them and a comment notifies them.

The instinct to be thorough is wrong here. Long replies read as defensive; a
short one reads as someone who knows their own codebase.

**Accepted:**
> Nice catch — the finishing position isn't shown anywhere in your rating
> history. I'll add it, rank plus the size of the field, same as on a tournament page.

**Accepted, our fault:**
> Thanks for catching that — the migration dropped judge ranks for members already
> in the new system. I still have the old database, so I'll restore them.

**Already possible:**
> That's already in there — a judge can override any table's VP total from the
> results screen. Clearly too well hidden though, I'll make it more obvious.

**Needs info** (closed, not parked):
> I can't reproduce this — which tournament was it, and what did you see on
> screen? Closing for now, send me that and I'll pick it straight up.

**Won't do:**
> I'm going to pass on this one — it'd only help a rare setup and would make the
> scoring screen worse for every event. Thanks though, keep them coming.
