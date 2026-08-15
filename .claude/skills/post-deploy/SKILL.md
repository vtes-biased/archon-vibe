---
name: post-deploy
description: Run after a successful production deploy — produce a compact changeset covering everything shipped since the last run (often several releases), and close the GitHub feedback issues those changes fixed. Use when asked to announce a deploy, write release/changelog notes for what just went live, or close issues that have now shipped.
---

# Post-deploy

Two jobs, in order: **say what shipped**, then **tell the people who reported it**.

Both span *everything since this skill last ran* — not one release. Deploys bundle
several tags, and a reporter doesn't care which one carried their fix.

**Prod only.** Beta is our testbed; the reporter is on prod. On a beta deploy,
produce the changeset if asked and **close nothing**.

## State

`last-run` in this directory holds one line: the commit SHA, tag and date of the
last point that was **announced and closed out** — which is not the same as the
last thing deployed.

```
3fefe60 v1.0.0 2026-08-07
```

A release that shipped without ever being announced leaves the marker where it
is, so the next run picks its changes up too. That is the normal case, not an
error: deploys are frequent, announcements are not.

Advance it **only after** the closing pass has actually run, and commit it with
the changeset in the same commit.

First run ever, or file missing: anchor on the previous release tag
(`git tag --sort=-creatordate | sed -n 2p`) and say in your output that the range
was guessed, so the owner can widen it.

## 1. Establish what is live

Nothing auto-deploys and there is no public version endpoint, so **do not sniff
the app for a version** — ask, or take it from the invocation.

- Which environment (prod or beta) and which tag (`RELEASE_TAG=… just deploy-prod`,
  blank = latest release).
- Confirm the tag is a real release: `gh release view <tag>`.
- Sanity-check the site is up: `curl -s -m 10 https://archon.vekn.net/api/time`.

If the deploy did not actually succeed, stop. Closing an issue on a failed deploy
is the one unrecoverable mistake here — it tells a reporter their fix is live when
it isn't.

## 2. The changeset

```sh
git log <last-run-sha>..<deployed-tag> --format='%h %s%n%b'
```

**One meaningful change = one line.** The reader is a VTES player, not a
contributor.

| Include | Drop |
|---|---|
| New capability | Refactors, dead-code removal, renames |
| Behaviour a user would notice changing | Docs, CI, deps, tests, formatting |
| A bug someone could actually hit | Board and wiki bookkeeping |
| Notable speed or UX change | Chrome: spacing, copy tweaks, icon swaps |

- **Collapse.** Several commits for one change are one line. A fix for a bug
  introduced in the same range is not a line at all — it never shipped broken.
- **Product language.** No commit hashes, no file paths, no internal references, no
  internal component names. "Ratings on a tournament page now match your profile",
  not "bind compute_rating_vp_gw to WASM".
- **Lead with what changed for them**, not what we did.
- Flat list, newest-first. Only group under headings if it runs past ~15 lines.
- Name the span at the top (`v1.0.0 → v1.0.2`).
- If nothing user-facing shipped, say exactly that — do not pad it out.

Write it to `CHANGELOG.md` at the repo root, newest entry first, directly under
the marker comment. Heading is the version now live plus the date; add a
`Covers <from> → <to>.` line only when the run spans more than one release:

```markdown
## v1.0.3 — 2026-08-15

Covers v1.0.1 → v1.0.3.

- Ratings shown on a tournament page now match the ones on your profile.
```

Show it in chat too. That file is the record — the GitHub Releases are not one:
`--generate-notes` lists merged PRs and this repo commits straight to main, so
their bodies are just a compare link.

Publishing it **anywhere else** (Discord, release notes, in-app) is the owner's
call: draft on request, never post unasked.

## 3. Close what shipped

Fixing commits carry a bare `Reported in #N.` backlink and never a closing keyword
(`wiki/dogmas.md`), so the range yields its own issue list:

```sh
git log <last-run-sha>..<deployed-tag> --format='%b' | grep -oE '#[0-9]+' | sort -u
```

For each, in order:

1. `gh issue view N --json number,title,labels,state` — skip unless it is **open**
   and carries `feedback`. A commit may reference any issue; only feedback issues
   get this treatment.
2. Draft a reply in the **feedback-triage house voice** — see that skill's "Reply
   style". One or two sentences, first person, casual, no AI boilerplate. Say it's
   live and what to look for. Never an internal reference, never a date promise.
3. **Show every draft to the owner and wait for approval before posting anything.**
   Public repo, real named people — same rule as feedback-triage.
4. `gh issue comment N --body "<approved reply>"` then
   `gh issue close N --reason completed`.

One close per issue even when several commits reference it.

**Reply shape** — it shipped, so lead with that:

> That's live now — your finishing position shows in the rating history, with the
> size of the field next to it.

> This is fixed and deployed — the rating on a tournament page and the one on your
> profile are the same number now.

## 4. Stragglers

Fixes that landed before the backlink convention won't appear in step 3. After the
closing pass, list open issues that look shipped but weren't matched:

```sh
gh issue list --label feedback --label tracked --state open \
  --json number,title --jq '.[] | "\(.number)\t\(.title)"'
```

Report them with a one-line guess at status. **Don't close them on a hunch** — an
issue closed wrongly costs more than one closed late.

## 5. Finish

Rewrite `last-run` with the deployed tag's SHA, tag and date, and commit it with
the `CHANGELOG.md` entry in one commit — the file is the human record, the marker
is the machine anchor, and the two must not drift apart. No board reference in the
message.

Report to the owner: the span covered, the changeset, which issues were closed,
and any straggler needing a decision.
