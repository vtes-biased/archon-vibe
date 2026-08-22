#!/usr/bin/env python3
"""Fail the build when the public API and the app reach for each other.

The API is a separate process on a separate subdomain serving a projection no app
client is ever given. Three lines hold it apart, and only the first is structural:

1. the app never calls the API — nothing under frontend/ may name it;
2. the API never imports the app's machinery — engine, scheduler, SSE, the app's
   own pool — only the four modules below, which are data shapes and pure config;
3. the app never imports the API package.

Run: just public-api-isolation
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PACKAGE = "backend/src/public_api/"

# What the API app may take from the app's package: the msgspec models the
# documented schemas are derived from, the projection field sets that prune them,
# the shared JWT secret, and the snapshot file's path.
ALLOWED_IMPORTS = {"models", "access_levels", "jwt_config", "snapshots"}

_RELATIVE_IMPORT = re.compile(r"^\s*from \.\.([A-Za-z_][A-Za-z0-9_]*)")
_ABSOLUTE_IMPORT = re.compile(r"^\s*(?:from|import) +(?:backend\.)?src\.([A-Za-z_]+)")
_ENGINE_IMPORT = re.compile(r"^\s*(?:from|import) +archon_engine\b")

# The frontend naming the API at all: its host, its version prefix, or an env var
# pointing at it. A read the app needs belongs on the app's own surface.
_FRONTEND_REFERENCE = re.compile(r"public_api|PUBLIC_API|/v1/|\bapi\.vekn\.")

_APP_REFERENCE = re.compile(r"\bpublic_api\b")


def tracked(*globs: str) -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", *globs],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.split()


def main() -> int:
    violations: list[str] = []

    for rel in tracked("frontend/*"):
        try:
            text = (ROOT / rel).read_text()
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if _FRONTEND_REFERENCE.search(line):
                violations.append(f"{rel}:{lineno}: the app names the public API")

    for rel in tracked("backend/src/*.py"):
        inside = rel.startswith(PACKAGE)
        for lineno, line in enumerate((ROOT / rel).read_text().splitlines(), 1):
            if inside:
                match = _RELATIVE_IMPORT.match(line) or _ABSOLUTE_IMPORT.match(line)
                if match and match.group(1) not in ALLOWED_IMPORTS:
                    violations.append(
                        f"{rel}:{lineno}: imports the app's {match.group(1)}"
                    )
                if _ENGINE_IMPORT.match(line):
                    violations.append(f"{rel}:{lineno}: imports the engine")
            elif _APP_REFERENCE.search(line):
                violations.append(f"{rel}:{lineno}: the app reaches into public_api")

    if not violations:
        return 0

    print("Public API isolation broken:\n")
    for v in violations:
        print(f"  {v}")
    print(
        "\nThe public API is a separate process serving third parties; the app must\n"
        "not call it and it must not import the app's machinery. Widen ALLOWED_IMPORTS\n"
        f"in {Path(__file__).relative_to(ROOT)} only for a module that is data shapes or\n"
        "pure configuration — never one that opens a connection or runs the engine."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
