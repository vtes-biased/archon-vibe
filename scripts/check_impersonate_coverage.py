#!/usr/bin/env python3
"""Fail the build when the public API's Impersonate Access section and the app's
`user:impersonate` allowlist disagree.

The reference documents endpoints the API does not serve, so nothing about a
route rename or a new tournament sub-route would otherwise reach it: the listing
*is* the published boundary, and a boundary that lies is worse than none. The
allowlist in `middleware/auth.py` is the authority; this asserts the docs match it
exactly, in both directions.

Run: just impersonate-coverage
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.src.main import app as site_app  # noqa: E402
from backend.src.middleware.auth import _OAUTH_BARRED_SUBPATHS  # noqa: E402
from backend.src.public_api.main import _IMPERSONATE_ROUTES  # noqa: E402

# Reachable outside the granted tournament's own prefix, from `_oauth_allows`.
# `/oauth/*` is documented in prose, not as endpoints: those are the token's own
# lifecycle rather than the event's surface.
_OFF_PREFIX = {
    ("get", "/stream"),
    ("post", "/sanctions/"),
    ("get", "/sanctions/reference"),
}

_PREFIX = "/api/tournaments/{uid}"


def reachable() -> set[tuple[str, str]]:
    found = set()
    # The generated document, not `app.routes`: the paths a consumer is given.
    for path, operations in site_app.openapi()["paths"].items():
        for method in operations:
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            if (method, path) in _OFF_PREFIX:
                found.add((method, path))
                continue
            if not path.startswith(_PREFIX):
                continue
            tail = path[len(_PREFIX) :].strip("/")
            # DELETE on the tournament itself is barred; so is each sub-route named
            # in the frozenset, whatever the method.
            if not tail:
                if method != "delete":
                    found.add((method, path))
                continue
            if tail.split("/")[0] in _OAUTH_BARRED_SUBPATHS:
                continue
            found.add((method, path))
    return found


def main() -> int:
    documented = {(method, path) for method, path, *_ in _IMPERSONATE_ROUTES}
    expected = reachable()

    missing = expected - documented
    extra = documented - expected
    if not missing and not extra:
        return 0

    print("Impersonate Access documentation is out of step with the allowlist:\n")
    for method, path in sorted(missing):
        print(f"  reachable but undocumented: {method.upper():7s} {path}")
    for method, path in sorted(extra):
        print(f"  documented but unreachable: {method.upper():7s} {path}")
    print(
        "\nThe public API reference publishes this set as the boundary of a"
        " `user:impersonate`\ngrant. Add the route to `_IMPERSONATE_ROUTES` in"
        " backend/src/public_api/main.py, or\nbar it in `_OAUTH_BARRED_SUBPATHS`"
        " — deciding which is the point of this failure."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
