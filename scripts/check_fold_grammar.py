#!/usr/bin/env python3
"""Fail when a disclosure is drawn outside the app's one fold grammar.

`FoldableSection` is the single shell a section folds through. A chevron drawn
anywhere else is either a fold that drifted or an affordance that is not a fold
at all, and the two are told apart by hand here — there is no way to read intent
off the markup.

Two rules:

1. A chevron that rotates is the dead second idiom, whatever it sits on. It has
   no allowlist: a fold points right closed and down open.
2. A chevron drawn outside `FoldableSection.svelte` must be listed below with its
   reason, and two kinds land there. A **fold** that cannot be a section is also
   stated as an exception in `wiki/design.md`'s fold grammar rule, and the two
   move together. An affordance that is **not a fold** — a pagination arrow, a
   reorder control, a mockup drawing one — is listed here only: the page states
   the grammar for folds, and these are not folds.

Run: just fold-grammar
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHELL = "frontend/src/lib/components/FoldableSection.svelte"

CHEVRON = re.compile(r"<Chevron(?:Down|Right|Up|Left)\b")
ROTATING = re.compile(r"\brotate-\d")

# Why this file draws a chevron of its own. Folds that are not sections first,
# then affordances that are not folds.
ALLOW = {
    "frontend/src/lib/components/FoldableDescription.svelte": (
        "closed renders the excerpt rather than hiding the body — a preview, not a shell"
    ),
    "frontend/src/lib/components/CommunityCountryCard.svelte": (
        "a list row folds in place: the whole row is the target, the chevron trails a summary"
    ),
    "frontend/src/routes/tournaments/[uid]/PlayersTab.svelte": (
        "a list row folds in place: the whole row is the target, the chevron trails a summary"
    ),
    "frontend/src/routes/tournaments/[uid]/PlayerDecksSection.svelte": (
        "a list row folds in place: the whole row is the target, the chevron trails a summary"
    ),
    "frontend/src/routes/tournaments/[uid]/ToolsSheet.svelte": (
        "the sheet's grammar is full-bleed menu rows, which a boxed section would break"
    ),
    "frontend/src/routes/tournaments/[uid]/RoundsTab.svelte": (
        "the header row carries sibling action buttons, which cannot nest in the shell's button"
    ),
    "frontend/src/routes/rankings/+page.svelte": "pagination arrows, not a disclosure",
    "frontend/src/routes/tournaments/[uid]/TableRoomsEditor.svelte": (
        "row reorder arrows, not a disclosure"
    ),
    "frontend/src/lib/components/help/OrganizerGuide.svelte": (
        "mockups drawing the console, not live controls"
    ),
    "frontend/src/lib/components/help/PlayerGuide.svelte": (
        "mockups drawing the console, not live controls"
    ),
}


def tracked() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "frontend/*.svelte"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.split()


def main() -> int:
    rotating: list[str] = []
    undeclared: dict[str, int] = {}
    seen: set[str] = set()

    for rel in tracked():
        try:
            lines = (ROOT / rel).read_text().splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(lines, 1):
            if not CHEVRON.search(line):
                continue
            if ROTATING.search(line):
                rotating.append(f"{rel}:{lineno}: {line.strip()}")
            if rel == SHELL:
                continue
            seen.add(rel)
            if rel not in ALLOW:
                undeclared.setdefault(rel, lineno)

    stale = sorted(set(ALLOW) - seen)
    if not rotating and not undeclared and not stale:
        return 0

    if rotating:
        print("A chevron that rotates:\n")
        for v in rotating:
            print(f"  {v}")
        print(
            "\nA fold points right when closed and down when open. The rotating\n"
            "header was the second idiom and it is gone — do not bring it back.\n"
        )
    if undeclared:
        print("A chevron drawn outside FoldableSection:\n")
        for rel, lineno in sorted(undeclared.items()):
            print(f"  {rel}:{lineno}")
        print(
            "\nFold it through `FoldableSection`. A fold that structurally cannot be a\n"
            "section goes in ALLOW here *and* in the exception list in wiki/design.md's\n"
            "fold grammar rule. Something that is not a fold — an arrow, a mockup —\n"
            "goes in ALLOW here only.\n"
        )
    if stale:
        print("Allowed but no longer drawing a chevron:\n")
        for rel in stale:
            print(f"  {rel}")
        print("\nDrop the entry here, and its line in wiki/design.md if it has one.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
