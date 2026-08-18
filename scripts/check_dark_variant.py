#!/usr/bin/env python3
"""Fail the build on Tailwind's `dark:` variant.

It keys on the OS `prefers-color-scheme`, not the theme the user picked in the
app, so every `dark:` utility lands on the wrong side whenever the two disagree.
The palette is `light-dark()` role tokens; rendered markdown takes `doc-prose`.

A `dark:` followed by a space is an object key or a type annotation, not a
variant, and is left alone.

Run: just dark-variant
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SUFFIXES = (".svelte", ".ts", ".html", ".css")

VARIANT = re.compile(r"(?<![\w-])dark:(?=[a-z\[])")


def tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", *(f"frontend/*{suffix}" for suffix in SUFFIXES)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.split()


def hits(rel: str) -> list[tuple[int, str]]:
    try:
        lines = (ROOT / rel).read_text().splitlines()
    except (OSError, UnicodeDecodeError):
        return []
    return [
        (lineno, line.strip())
        for lineno, line in enumerate(lines, 1)
        if VARIANT.search(line)
    ]


def main() -> int:
    violations = [
        f"{rel}:{lineno}: {text}"
        for rel in tracked_files()
        for lineno, text in hits(rel)
    ]
    if not violations:
        return 0

    print("Tailwind `dark:` variant used:\n")
    for v in violations:
        print(f"  {v}")
    print(
        "\n`dark:` follows the OS preference, not the app theme, so it inverts the\n"
        "wrong way for anyone whose theme disagrees with their OS. Use the role\n"
        "tokens, which resolve through light-dark(), or `doc-prose` for markdown."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
