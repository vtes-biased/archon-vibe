# Submitting the winner's deck from our own fork — context

Doc-impact: [`wiki/dev.md`](../wiki/dev.md) — the TWDA auto-PR paragraph names the
environment variables and states the grants, and both change. Check the "published
TWDA branch" wording in [`wiki/architecture.md`](../wiki/architecture.md) too; a
wording touch at most.

## Why the branch cannot live on the archive

A pull request needs a branch, a branch needs a commit, and every call that writes
one is gated on `contents: write` for the repository holding it. GitHub App
permissions are repository-wide — there is no branch-scoped write, so "may write
only to `archon/*`" cannot be expressed. Verified against GitHub's permission
reference:

| call | permission |
| --- | --- |
| create the branch — `POST /repos/…/git/refs` | Contents: write |
| commit the deck — `PUT /repos/…/contents/{path}` | Contents: write |
| sync a fork — `POST /repos/…/merge-upstream` | Contents: write |
| open the pull request — `POST /repos/…/pulls` | Pull requests: write, on the **base** repo |
| create a fork — `POST /repos/…/forks` | Contents: read |
| read a ref, list pull requests | Contents: read, Pull requests: read |

Moving the writes to a fork we own leaves the archive granting only what it already
grants: contents read, and pull requests write.

## Two installations, two tokens

An installation token is scoped to one installation, so one token cannot span both
accounts. The narrowing matters as much as the split — the present code asks a
single installation for both permissions at once, and that request is refused even
though each half is available somewhere.

1. **Fork installation**, asked for `{"contents": "write"}` — sync the fork's master
   from upstream, create or reset `archon/<event-code>`, commit
   `decks/<event-code>.txt`.
2. **Archive installation**, asked for `{"pull_requests": "write"}` — find the open
   pull request, or open one, with head `<fork-owner>:archon/<event-code>`.

The head namespace changes in both the search filter and the create body; today
both name the archive's own owner.

**The fork must stay public.** The archive's token has no access to it and can only
reference a public head. A fork of a public repository is public by default and
must not be flipped.

## One-time setup, all on our side

1. Fork the archive under the account that owns this repository. Nothing needs to
   be pushed to it — the auto-PR creates every branch it uses.
2. Install the same GitHub App on the fork, with **Contents: Read and write**. No
   webhook.
3. Add the fork's installation id and owner to both inventories, alongside the
   existing TWDA variables, with the id as a vault secret. The private key and
   client id are shared — it is one App, installed twice.

## After it ships

Every event whose submission failed while the grant was refused:

```sql
SELECT "full"->>'uid', "full"->>'name'
FROM objects WHERE type='tournament' AND deleted_at IS NULL
  AND "full"->'twda_status'->>'outcome' = 'failed';
```

Each recovers by re-running the organizer's sync: with the results already pushed,
that path skips vekn.net entirely and re-runs only the submission.
