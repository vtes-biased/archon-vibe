#!/usr/bin/env python3
"""Fail the build when a locale's message catalog disagrees with the base one.

Paraglide resolves a key it cannot find in the active locale by falling back to
the base one, so a forgotten translation ships as English to a French reader with
no error anywhere — nothing in the build, the type check or the test suite sees
it. A key left behind after its base entry was deleted is the same drift in the
other direction.

The locale list comes from the inlang project settings, so adding a sixth locale
extends this gate without touching it.

Run: just locale-parity
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MESSAGES = ROOT / "frontend" / "messages"
SETTINGS = ROOT / "frontend" / "project.inlang" / "settings.json"


def catalog(locale: str) -> set[str]:
    return set(json.loads((MESSAGES / f"{locale}.json").read_text()))


def main() -> int:
    settings = json.loads(SETTINGS.read_text())
    base_locale = settings["baseLocale"]
    base = catalog(base_locale)

    failures: list[str] = []
    for locale in settings["locales"]:
        if locale == base_locale:
            continue
        keys = catalog(locale)
        for key in sorted(base - keys):
            failures.append(f"  {locale}.json: missing {key}")
        for key in sorted(keys - base):
            failures.append(f"  {locale}.json: not in {base_locale}.json — {key}")

    if not failures:
        return 0

    print(f"Message catalogs disagree with {base_locale}.json:\n")
    print("\n".join(failures))
    print(
        f"\nA missing key ships as {base_locale} to that locale's readers with no\n"
        "error. Translate it, or delete the leftover if its base entry is gone."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
