---
name: post-deploy
description: Run after a successful production deploy — tell the people who reported the bugs it fixed, and close their issues. Use when asked to follow up on user feedback after a deploy, or to close the issues a deploy has now shipped.
---

# Post-deploy

One job: **tell the people who reported it**. Saying what shipped is the other
half and happens before the tag — `/release-notes`.

An issue closes when the fix **deploys** and the reporter can see it work, which
is why commits carry a bare `Reported in #N.` and never a closing keyword
(`wiki/dogmas.md`). This pass is what that backlink is for.

**Prod only.** Beta is our testbed; the reporter is on prod. On a beta deploy,
close nothing.

## No state

There is no marker file and no commit range. Every input is derivable at the
moment you ask: an open `feedback` issue, the commit that references it, and the
first tag containing that commit. A deploy that was never followed up is picked up
by the next run for free, because a still-open issue is still open.

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

## 2. Work out what is now live

```sh
gh issue list --label feedback --state open --json number,title \
  --jq '.[] | "\(.number)\t\(.title)"'
```

For each, find its fix and the release that first carried it:

```sh
sha=$(git log -E --grep="#${N}([^0-9]|$)" --format=%H -1)
[ -n "$sha" ] && git tag --contains "$sha" --sort=creatordate | head -n1
```

Three outcomes, and only the first is actionable:

- **A containing tag at or below the deployed tag** — live. Close it.
- **A containing tag above the deployed tag, or none** — fixed, not yet deployed.
  Leave it; the next run takes it.
- **No referencing commit** — either untouched, or fixed before the backlink
  convention existed. Report, never close on a hunch: an issue closed wrongly
  costs more than one closed late.

## 3. Close what shipped

For each live issue, in order:

1. `gh issue view N --json number,title,labels,state` — confirm it is still open
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

## 4. Report

To the owner: which issues were closed, which are fixed but waiting on a deploy,
and which carry no referencing commit and need a decision.
