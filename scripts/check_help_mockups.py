#!/usr/bin/env python3
"""Fail when a help-guide mockup drifts from the app it depicts.

The guides draw the console in miniature so the prose can point at it. Those
drawings are hand-built, and nothing recomputes them when the real screen moves,
so they rot into pictures of an app that no longer exists.

Two rules keep them honest:

1. A control is drawn with the component that draws it for real. A `class=` that
   carries a Button or Badge signature is a hand-rolled copy of one — it must go
   through `<Button>` / `<Badge>` instead, which then tracks the primitive.
2. A label the app translates is read from the same message key. A bare literal
   that matches an `en.json` value is a copy of a live label, and drifts the
   moment that label is reworded — the bug class `wiki/i18n.md` names.

Sample data (player names, a venue, an ID, a clock face) is not a label and stays
literal: it never appears in the catalog, so rule 2 does not see it.

Run: just help-mockups
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUIDES = ROOT / "frontend" / "src" / "lib" / "components" / "help"
CATALOG = ROOT / "frontend" / "messages" / "en.json"

# Class fragments that mean "this is a Button/Badge someone re-drew by hand".
PRIMITIVE_SIGNATURES = {
    "bg-accent-strong": "the primary Button fill",
    "btn-danger": "the danger Button",
    "btn-success": "the create Button",
    "bg-surface-hover text-ink-bright": "the secondary Button",
    "border border-line-strong text-ink": "the ghost Button",
    "rounded text-xs font-medium": "a Badge",
}

# Literals that match a catalog value but are not that label. Each needs a reason.
LITERAL_ALLOW = {
    "Standard": "the format enum renders raw in the app too (Badge{tournament.format})",
    "Discord": "the platform name is hard-coded on LinkedAccounts too, not a key",
    "Alice": "sample player",
    "Bob": "sample player",
    "Charlie": "sample player",
    "Diana": "sample player",
    "Erik": "sample player",
}


def literals(src: str) -> list[tuple[int, str]]:
    """Visible text nodes: what a reader sees that did not come from `m.*()`."""
    out = []
    for lineno, line in enumerate(src.splitlines(), 1):
        stripped = re.sub(r"<[^>]*>", "\x00", line)
        stripped = re.sub(r"\{[^{}]*\}", "\x00", stripped)
        for piece in stripped.split("\x00"):
            text = piece.strip()
            if text and not text.startswith("//"):
                out.append((lineno, text))
    return out


def main() -> int:
    catalog = set(json.loads(CATALOG.read_text()).values())
    violations: list[str] = []

    for path in sorted(GUIDES.glob("*.svelte")):
        rel = path.relative_to(ROOT)
        src = path.read_text()

        for lineno, line in enumerate(src.splitlines(), 1):
            for attr in re.findall(r'class="([^"]*)"', line):
                for sig, what in PRIMITIVE_SIGNATURES.items():
                    if sig in attr:
                        violations.append(
                            f"{rel}:{lineno}: hand-rolled {what} — use the component"
                        )

        for lineno, text in literals(src):
            if text in catalog and text not in LITERAL_ALLOW:
                violations.append(
                    f"{rel}:{lineno}: {text!r} is a live UI label — render its message key"
                )

    if not violations:
        return 0

    print("Help-guide mockups have drifted from the app:\n")
    for v in violations:
        print(f"  {v}")
    print(
        "\nA mockup must be built from the same Button/Badge and the same message\n"
        "keys as the screen it draws, so the drawing moves when the screen does."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
