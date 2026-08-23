#!/usr/bin/env python3
"""Fail the build when models.py and types.ts disagree.

The two are hand-synchronized and nothing generates one from the other, so a
field added on one side alone is invisible until it reaches a user.

Compares field names and enum values, not types: `datetime` is `string` over the
wire and every optional spelling differs, so types would be noise.

Run: just model-drift
"""

import enum
import importlib.util
import re
import sys
from pathlib import Path

import msgspec

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "backend" / "src" / "models.py"
TYPES = ROOT / "frontend" / "src" / "lib" / "types.ts"

# name -> why it has no counterpart. Anything not listed must exist on both
# sides; a new unpaired name fails here rather than drifting unnoticed.
PY_ONLY = {
    "AuthMethod": "credentials, never projected to a client",
    "OAuthAuthorizationCode": "server-side OAuth storage",
    "OAuthClient": "server-side OAuth storage",
    "OAuthConsent": "server-side OAuth storage",
    "OAuthToken": "server-side OAuth storage",
    "TournamentConfig": "a base flattened into the Tournament interface",
    "TournamentMinimal": "a base flattened into the Tournament interface",
    "AuthMethodType": "credentials, never projected to a client",
    "OAuthScope": "server-side OAuth storage",
    "ObjectType": "store and stream tags; sync.ts keys SPECS by literal",
}
TS_ONLY = {
    "City": "geography, sourced from the engine rather than stored",
    "Continent": "geography, sourced from the engine rather than stored",
    "Country": "geography, sourced from the engine rather than stored",
    "Deck": "the engine's deck payload, not the stored DeckObject",
    "LinkMedia": "display-side classification of a community link",
    "LinkPlacement": "display-side classification of a community link",
    "OfflinePlayer": "an offline bundle's player, never stored server-side",
    "VtesCard": "the card catalog, sourced from the engine rather than stored",
}


def python_side() -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    spec = importlib.util.spec_from_file_location("_models", MODELS)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    structs, enums = {}, {}
    for name in dir(module):
        obj = getattr(module, name)
        if not isinstance(obj, type):
            continue
        if issubclass(obj, msgspec.Struct):
            structs[name] = {f.encode_name for f in msgspec.structs.fields(obj)}
        elif issubclass(obj, enum.Enum) and obj.__module__ == "_models":
            enums[name] = {e.value for e in obj}
    return structs, enums


# Top-level members only: a nested object literal indents past two spaces, and
# the flattening below mirrors msgspec, which resolves inheritance for us.
_INTERFACE = re.compile(r"^export interface (\w+)(?: extends (\w+))?\s*\{$", re.M)
_MEMBER = re.compile(r"^ {2}(\w+)\??\s*:", re.M)
_ALIAS = re.compile(r"^export type (\w+) =((?:[^;])*);", re.M)


def typescript_side() -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    text = TYPES.read_text()
    own, bases = {}, {}
    for match in _INTERFACE.finditer(text):
        end = text.index("\n}", match.end())
        own[match.group(1)] = set(_MEMBER.findall(text[match.end() : end]))
        bases[match.group(1)] = match.group(2)

    def flattened(name: str) -> set[str]:
        base = bases.get(name)
        return own[name] | (flattened(base) if base and base in own else set())

    interfaces = {name: flattened(name) for name in own}
    unions = {}
    for match in _ALIAS.finditer(text):
        values = re.findall(r'"([^"]*)"', match.group(2))
        if values:
            unions[match.group(1)] = set(values)
    return interfaces, unions


def compare(kind: str, py: dict[str, set[str]], ts: dict[str, set[str]]) -> list[str]:
    problems = []
    for name in sorted(set(py) - set(ts) - set(PY_ONLY)):
        problems.append(f"{name}: a {kind} in models.py, absent from types.ts")
    for name in sorted(set(ts) - set(py) - set(TS_ONLY)):
        problems.append(f"{name}: a {kind} in types.ts, absent from models.py")
    for name in sorted(set(py) & set(ts)):
        sides = (("types.ts", py[name] - ts[name]), ("models.py", ts[name] - py[name]))
        for side, missing in sides:
            if missing:
                problems.append(f"{name}: {sorted(missing)} missing from {side}")
    return problems


def main() -> int:
    py_structs, py_enums = python_side()
    ts_interfaces, ts_unions = typescript_side()

    problems = []
    for name in sorted(PY_ONLY):
        if name not in py_structs and name not in py_enums:
            problems.append(f"{name}: listed backend-only, absent from models.py")
    for name in sorted(TS_ONLY):
        if name not in ts_interfaces and name not in ts_unions:
            problems.append(f"{name}: listed frontend-only, absent from types.ts")
    problems += compare("struct", py_structs, ts_interfaces)
    problems += compare("enum", py_enums, ts_unions)

    if not problems:
        return 0
    print("models.py and types.ts disagree:\n")
    for problem in problems:
        print(f"  {problem}")
    print(
        "\nThe two are hand-synchronized (wiki/sync.md). Mirror the change, or — if the\n"
        f"shape genuinely belongs to one side — add it to PY_ONLY or TS_ONLY in\n"
        f"{Path(__file__).relative_to(ROOT)} with the reason."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
