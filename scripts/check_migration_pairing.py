#!/usr/bin/env python3
"""Fail the build when a stored-value migration and its proof drift apart.

A migration in `backend/src/migrations.py` rewrites rows the running code can no
longer decode. Nothing in the tree records that it has been applied, so its proof
lives in a `wiki/post-deploy.md` section carrying the queries that show it worked
on every long-lived database. The entry dies in the commit that deletes that
section — this gate is what makes the two moves one move.

The section marks itself with a line naming the entry:

    **Migration** `collapse-link-moderation`

A post-deploy item with no such line is a plain script and is not this gate's
business.

Run: just migration-pairing
"""

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MIGRATIONS = ROOT / "backend/src/migrations.py"
POST_DEPLOY = ROOT / "wiki/post-deploy.md"

_MARKER = re.compile(r"^\*\*Migration\*\* `([a-z0-9-]+)`", re.MULTILINE)


def declared_migrations() -> list[str]:
    """The `name=` of every `Migration(...)` built in migrations.py."""
    tree = ast.parse(MIGRATIONS.read_text(encoding="utf-8"))
    names = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not (isinstance(node.func, ast.Name) and node.func.id == "Migration"):
            continue
        for kw in node.keywords:
            if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                names.append(kw.value.value)
    return names


def main() -> int:
    declared = declared_migrations()
    # An empty list is the goal state; a parse that stopped matching is not.
    if not declared and "Migration(" in MIGRATIONS.read_text(encoding="utf-8"):
        print("check_migration_pairing.py no longer parses migrations.py")
        return 1

    proven = _MARKER.findall(POST_DEPLOY.read_text(encoding="utf-8"))

    violations = [
        f"  {name}: declared in backend/src/migrations.py, no section in "
        f"wiki/post-deploy.md"
        for name in declared
        if name not in proven
    ]
    violations += [
        f"  {name}: proven in wiki/post-deploy.md, no entry in "
        f"backend/src/migrations.py"
        for name in proven
        if name not in declared
    ]

    if not violations:
        return 0

    print("Migrations and their proofs disagree:\n")
    print("\n".join(violations))
    print(
        "\nA migration and its post-deploy section land and die together: the\n"
        "section holds the only proof the rewrite reached every long-lived\n"
        "database, and nothing else in the tree records that it ran. Add the\n"
        "section with its verification queries, or delete the entry."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
