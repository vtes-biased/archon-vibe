#!/usr/bin/env python3
"""Fail on an import inside a function body anywhere under `backend/`.

An in-function import hides a reference from module load: a renamed symbol breaks
only when the function runs, often inside a try/except that swallows it. An import
cycle is resolved by moving the shared code, never by deferring the import.

The one exception is a library heavy enough to matter (over 5MB resident on
import) and needed rarely (under once a week), listed below with its measurement.
A listed module that no longer imports in-function also fails, so the list
cannot outlive what it excuses.

Run: just function-imports
"""

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"

ALLOW = {
    ("backend/src/nda.py", "fpdf"): (
        "~55MB resident with PIL, fontTools and numpy; a sealed NDA PDF is rare"
    ),
    ("backend/src/nda.py", "fpdf.enums"): "same import as fpdf",
}

RULE = (
    "imports belong at module top. Resolve an import cycle by moving the shared "
    "code; only a library over 5MB needed under once a week may be listed in "
    "scripts/check_function_imports.py"
)


def nested_imports(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(), filename=str(path))
    found = []
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        for node in ast.walk(fn):
            if isinstance(node, ast.ImportFrom):
                module = "." * node.level + (node.module or "")
                found.append((node.lineno, module))
            elif isinstance(node, ast.Import):
                found.extend((node.lineno, alias.name) for alias in node.names)
    return found


def main() -> int:
    failures = []
    seen = set()
    for path in sorted(BACKEND.rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        for lineno, module in sorted(set(nested_imports(path))):
            if (rel, module) in ALLOW:
                seen.add((rel, module))
                continue
            failures.append(f"{rel}:{lineno}: in-function import of {module}")
    for rel, module in sorted(ALLOW.keys() - seen):
        failures.append(f"{rel}: listed {module} no longer imports in-function")
    if failures:
        print("\n".join(failures))
        print(f"\n{RULE}.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
