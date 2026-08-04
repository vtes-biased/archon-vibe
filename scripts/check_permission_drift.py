#!/usr/bin/env python3
"""Fail the build when a role literal is used for GATING outside the engine.

The four-surface divergence the permission-model realignment fixed came back
the same way each time: someone adds `hasAnyRole("IC","NC")` to a new component
or `Role.IC not in user.roles` to a new route, and nothing notices until a user
hits a 403 on a button the UI offered. Authorization is a table in
engine/src/permissions.rs; everything else asks it.

The allowlist below is by path + reason, never by directory, so an addition to
it is a visible decision in review. Reading roles to compute *what a viewer
sees* (a separate axis, see SYNC.md) or *how a badge renders* is legitimate and
listed; deciding what someone may DO is not.

Run: just permission-drift
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Gating shapes, not every mention of a role. A role literal in a type, a test
# fixture or a table row is fine; testing membership to branch on it is not.
PATTERNS = {
    "*.py": re.compile(r"Role\.[A-Z][A-Za-z]* +(?:not +)?in\b"),
    "*.ts": re.compile(r"""hasAnyRole\(|roles\??\.(?:includes|some)\("""),
    "*.svelte": re.compile(r"""hasAnyRole\(|roles\??\.(?:includes|some)\("""),
}

# path -> why this file may read roles directly.
ALLOWED = {
    # The adapters themselves: they marshal to the engine and name capabilities.
    "backend/src/permissions.py": "the engine adapter",
    "frontend/src/lib/engine.ts": "the engine adapter",
    # Visibility projections — WHAT a viewer sees, not what they may do (SYNC.md).
    "backend/src/access_levels.py": "subject-side projection",
    "backend/src/broadcast.py": "entitled_level projection",
    "backend/src/db.py": "access-version fingerprint",
    "backend/src/main.py": "resync catch-up frames",
    "backend/src/routes/users.py": "resync trigger on an overlay-role change",
    # Mirrors the engine's own "empty list means unrestricted" contract.
    "backend/src/routes/tournaments.py": "engine league-gate contract",
    # Attribution, not access: which official covers a city/country, to credit
    # the sponsor of a legacy-imported member.
    "backend/src/vekn_sync.py": "sponsor attribution lookup",
    # Display: badge colours, labels, sort order, filter expansion.
    "frontend/src/lib/roles.ts": "badge classes, labels, filter expansion",
    "frontend/src/lib/db.ts": "role filter expansion",
    "frontend/src/lib/displayContext.ts": "role filter expansion",
    "frontend/src/lib/components/CommunityTab.svelte": "official sort order + directory",
    "frontend/src/lib/components/CommunitySocialSection.svelte": "official badges",
    "frontend/src/lib/components/CommunityContentSection.svelte": "official badges",
    "frontend/src/routes/profile/ProfileView.svelte": "which contact-visibility note to show",
}

# The engine owns the rules; its own file is the point of the exercise.
ENGINE_TABLE = "engine/src/permissions.rs"


def tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "*.py", "*.ts", "*.svelte"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.split()


def main() -> int:
    violations: list[str] = []
    for rel in tracked_files():
        if rel in ALLOWED or rel.startswith(("backend/tests/", "scripts/")):
            continue
        pattern = PATTERNS["*" + Path(rel).suffix]
        try:
            text = (ROOT / rel).read_text()
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if pattern.search(line):
                violations.append(f"{rel}:{lineno}: {line.strip()}")

    if not violations:
        return 0

    print("Role literals used for gating outside the engine:\n")
    for v in violations:
        print(f"  {v}")
    print(
        f"\nAuthorization is a table in {ENGINE_TABLE}. Add a capability row there and\n"
        "call it (backend/src/permissions.py, frontend/src/lib/engine.ts) instead of\n"
        "matching role strings. If this really is display or visibility rather than a\n"
        f"gate, add the file to ALLOWED in {Path(__file__).relative_to(ROOT)} with a reason."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
