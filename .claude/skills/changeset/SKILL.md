---
name: changeset
description: Write the changelog entry for what is about to ship, before `just release` cuts the tag. Use when asked to write release notes, prepare a changelog entry, or say what is going out in the next release.
---

# Changeset

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
| A bug someone actually hit | Board and wiki bookkeeping |
| Notable speed or UX change | Chrome: spacing, copy tweaks, icon swaps |
| — | Silent fixes (see below) |

### How long it is

**Ten to fifteen lines, whatever the span.** Two months and a hundred commits is
still ten to fifteen lines. Thirty means one line per commit — go back and
collapse.

Collapse by **surface, not by commit**. A page reworked is one line however many
commits and however many separate improvements went into it: "The Community page
has been reworked: easier to curate, clearer display for all links" is the whole
of a five-commit restructure.

Draft **short**. Every pass over this file has ended in a cut, never an addition.
A line the owner misses costs one message; twelve lines they have to delete is
the work done twice.

### How a line reads

One sentence, around twenty words, one clause of substance. Then stop.

- **No rationale tail.** Not "…, so nothing can render from a half-loaded state".
  They want the change, not why it was worth making.
- **No enumeration.** A line listing three surfaces is three lines badly merged,
  or one line trying too hard. Name the surface, not its parts.
- **"Fixed X" is a complete line.** A defect nobody needs to understand does not
  earn an explanation: "Fixed event display for logged-out visitors."
- **Name the symptom they saw, not the mechanism.** "not replaced by the vekn.net
  Antarctica venue anymore", not "kept when vekn.net has no venue to match it
  against". Name a precondition where it decides whether the line is about them:
  "in a multiple-active-rounds tournament".
- **Never name an internal state.** "left stuck in Invalid", "a half-loaded
  engine", "stored the same way everywhere" — a symptom that cannot be stated
  without one is a symptom nobody saw, so it is not a line.
- **Product language.** No commit hashes, no file paths, no internal references, no
  internal component names. "Ratings on a tournament page now match your profile",
  not "bind compute_rating_vp_gw to WASM".

### What is never a line

- A fix for a bug introduced in the same range — it never shipped broken.
- **A silent fix**: rare, the surface already worked at least partially, and
  nobody reported it. All three, not any one — a surface that was broken for
  everyone is a line whether or not anyone filed an issue. The evidence of a
  report is in the range itself: `git log "$last"..HEAD --grep='Reported in #'`
  names the fixes a user actually hit.
- The changelog modal itself, or anything else about how these notes reach a
  reader.
- A correctness fix whose wrong answer never reached a screen.

### Shape

**A flat list. No headings, no sections.** Twelve lines need no signposting, and a
heading invites padding the thin section out to earn itself.

Order so related lines sit together, and put the corpus last: what changed about
what Archon *knows* — an archive imported, a rank restored, a field corrected in
bulk — comes after what changed about what it does. Commit order means nothing to
the reader.

Say **tournament**, not "event". Both words are in the app; this file uses the one
the reader came for.

If nothing user-facing shipped, say exactly that — do not pad it out.

**Entries stay English.** The modal's shell is translated, the entries are not
(`wiki/i18n.md`) — do not write a translated variant.

## Write it

To `CHANGELOG.md` at the repo root, directly under the marker comment, headed
`## Unreleased` — no version, no date, because `just release` supplies both from
the tag it is cutting:

```markdown
## Unreleased

- Ratings shown on a tournament page now match the ones on your profile.
- The TWDA has been fully added, and the Hall of Fame recomputed based on it.
```

An unstamped heading carries no version, so the app skips it: notes awaiting a tag
never reach a user.

Show it in chat too. That file is the record — the GitHub Releases are not one:
`--generate-notes` lists merged PRs and this repo commits straight to main, so
their bodies are just a compare link.

Publishing it **anywhere else** (Discord, release notes) is the owner's call:
draft on request, never post unasked.

Commit it on its own. No board reference in the message.
