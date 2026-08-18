---
name: release-notes
description: Write the changelog entry for what is about to ship, before `just release` cuts the tag. Use when asked to write release notes, prepare a changelog entry, or say what is going out in the next release.
---

# Release notes

One job: **say what is about to ship**. Runs *before* `just release`, never after a
deploy — the recipe stamps the entry with the tag it cuts, so the tag carries its
own notes, and the frontend bundle CI builds from that tag is what shows them in
the app's "what's new" modal. Written afterwards, an entry is one release late.

Telling the people who reported the bugs is the other half, and it belongs after
the deploy: `/post-deploy`.

## The span

The changelog is its own anchor — there is no marker file. The newest **stamped**
heading is the last point that was written up:

```sh
last=$(grep -m1 -oE '^## v[0-9]+\.[0-9]+\.[0-9]+' CHANGELOG.md | cut -d' ' -f2)
git log "$last"..HEAD --format='%h %s%n%b'
```

An `## Unreleased` section already at the top means notes were written and the
release was never cut. Rewrite that block from the same anchor — do not append a
second one.

## The changeset

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
- If nothing user-facing shipped, say exactly that — do not pad it out.

**Entries stay English.** The modal's shell is translated, the entries are not
(`wiki/i18n.md`) — do not write a translated variant.

## Write it

To `CHANGELOG.md` at the repo root, directly under the marker comment, headed
`## Unreleased` — no version, no date, because `just release` supplies both from
the tag it is cutting:

```markdown
## Unreleased

- Ratings shown on a tournament page now match the ones on your profile.
```

An unstamped heading carries no version, so the app skips it: notes awaiting a tag
never reach a user.

Show it in chat too. That file is the record — the GitHub Releases are not one:
`--generate-notes` lists merged PRs and this repo commits straight to main, so
their bodies are just a compare link.

Publishing it **anywhere else** (Discord, release notes) is the owner's call:
draft on request, never post unasked.

Commit it on its own. No board reference in the message.
