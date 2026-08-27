#!/usr/bin/env python3
"""Fail the build on a contiguous comment block over three lines.

Every comment token counts, so the ceiling is not a question of which one you
write in. Python docstrings are strings rather than comments, and are exempt.

Run: just comment-blocks
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MAX_LINES = 3

LINE_MARKER = {
    ".py": "#",
    ".rs": "//",
    ".ts": "//",
    ".svelte": "//",
    ".html": "//",
    ".css": "//",
    ".j2": "#",
}

BLOCK_MARKERS = {
    ".py": (),
    ".rs": (("/*", "*/"),),
    ".ts": (("/*", "*/"),),
    ".svelte": (("/*", "*/"), ("<!--", "-->")),
    ".html": (("<!--", "-->"),),
    ".css": (("/*", "*/"),),
    ".j2": (("{#", "#}"),),
}

TYPESCRIPT_DIRECTIVE = "/// <reference"


def tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", *(f"*{suffix}" for suffix in LINE_MARKER)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.split()


def blocks(rel: str) -> list[tuple[int, int]]:
    suffix = Path(rel).suffix
    marker, pairs = LINE_MARKER[suffix], BLOCK_MARKERS[suffix]
    try:
        lines = (ROOT / rel).read_text().splitlines()
    except (OSError, UnicodeDecodeError):
        return []

    found: list[tuple[int, int]] = []
    start = length = 0
    closing = ""
    for lineno, line in enumerate(lines, 1):
        stripped = line.strip()
        if closing:
            length += 1
            if closing in stripped:
                closing = ""
            continue
        opening = next((o for o, _ in pairs if stripped.startswith(o)), "")
        if opening:
            close = dict(pairs)[opening]
            if close not in stripped[len(opening) :]:
                closing = close
        elif not stripped.startswith(marker) or stripped.startswith(
            TYPESCRIPT_DIRECTIVE
        ):
            if length > MAX_LINES:
                found.append((start, length))
            start = length = 0
            continue
        start = start or lineno
        length += 1

    if length > MAX_LINES:
        found.append((start, length))
    return found


def main() -> int:
    violations = [
        f"{rel}:{start}: {length} comment lines"
        for rel in tracked_files()
        for start, length in blocks(rel)
    ]
    if not violations:
        return 0

    print(f"Comment blocks over {MAX_LINES} lines:\n")
    for v in violations:
        print(f"  {v}")
    print(
        "\nA comment states a trap: the non-local constraint that is invisible where\n"
        "the code sits. Compress it to that. If it explains a decision, the wiki page\n"
        "owning the subsystem already holds it — delete the comment instead."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
