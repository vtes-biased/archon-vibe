---
name: no-git-checkout-during-mutation-tests
description: Never restore a mutation-tested source file with `git checkout` — it silently destroys uncommitted working-tree changes
metadata:
  type: feedback
---

When mutation-testing (deliberately breaking shipped code to confirm a test
fails, then restoring), NEVER restore with `git checkout <file>`. Restore from a
copy you made first (`cp file file.bak` → restore from `.bak`), or apply/revert
an in-place Edit.

**Why:** During #216 QA the source under test (`migrate_from_archon.py`) held the
feature's changes as **uncommitted working-tree state** (the repo looked "clean"
only because the diff I'd inspected was `HEAD~1` vs working tree, not a committed
range). A `git checkout` after a mutation test reverted the file to HEAD and wiped
all 165 lines of the feature. Not recoverable via reflog or stash. I had to
reconstruct it hunk-by-hunk from the `git diff` output I'd captured at the start —
recovery was only possible because that diff was still in my transcript.

**How to apply:** Before mutating any file for a fail-check, confirm whether its
changes are committed (`git log -- <file>` shows the feature commit) OR back the
file up first. If changes are uncommitted, a backup copy is mandatory; `git
checkout` is off-limits. Always keep the full `git diff` of the change in context
so a reconstruction is possible if something goes wrong. See also
[[minimal-meaningful-tests]] for the mutation-test practice itself.
