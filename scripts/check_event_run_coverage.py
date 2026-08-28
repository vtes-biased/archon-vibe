#!/usr/bin/env python3
"""Fail the build when the public API's Member API section and the app's
`event:run` allowlist disagree.

The reference documents endpoints the API does not serve, so nothing about a
route rename or a new tournament sub-route would otherwise reach it: the listing
*is* the published boundary, and a boundary that lies is worse than none. The
allowlist in `middleware/auth.py` is the authority; this asserts the docs match it
exactly, in both directions.

Run: just event-run-coverage
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.src.main import app as site_app  # noqa: E402
from backend.src.middleware.auth import _OAUTH_BARRED_SUBPATHS  # noqa: E402
from backend.src.public_api.main import (  # noqa: E402
    _EVENT_RUN_ROUTES,
    _EVENT_RUN_SCHEMAS,
)

# Reachable outside the granted tournament's own prefix, from `_oauth_allows`.
# `/oauth/token` and `/oauth/revoke` stay prose: they are the token's own
# lifecycle, not the event's surface.
_OFF_PREFIX = {
    ("get", "/stream"),
    ("post", "/sanctions/"),
    ("get", "/sanctions/reference"),
    ("get", "/oauth/userinfo"),
}

_PREFIX = "/api/tournaments/{uid}"


def _walk(router) -> list:
    """Every route, including `include_in_schema=False` ones the OpenAPI document
    omits — the middleware admits a route whether or not it is published."""
    routes = []
    for route in router.routes:
        inner = getattr(route, "original_router", None)
        routes.extend(_walk(inner) if inner is not None else [route])
    return routes


def reachable() -> set[tuple[str, str]]:
    found = set()
    routes = _walk(site_app)
    for route in routes:
        path = getattr(route, "path", "")
        for method in {m.lower() for m in getattr(route, "methods", ())}:
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            if (method, path) in _OFF_PREFIX:
                found.add((method, path))
                continue
            if not path.startswith(_PREFIX):
                continue
            tail = path[len(_PREFIX) :].strip("/")
            if not tail:
                if method != "delete":
                    found.add((method, path))
                continue
            if tail.split("/")[0] in _OAUTH_BARRED_SUBPATHS:
                continue
            found.add((method, path))
    # FastAPI's lazy router wrappers are an internal shape; if a version change
    # breaks the walk, fail here rather than pass on an empty set.
    if not found:
        raise SystemExit(f"route walk found nothing in {len(routes)} routes")
    return found


def schema_drift() -> list[str]:
    """Each documented request body is a hand-copy of an app model; pair them by
    name and require the same fields."""
    from backend.src.routes import sanctions, tournaments

    problems = []
    for name, schema in _EVENT_RUN_SCHEMAS.items():
        model = getattr(tournaments, name, None) or getattr(sanctions, name, None)
        if model is None:
            problems.append(f"{name}: no app model of that name")
            continue
        documented = set(schema.get("properties", {}))
        actual = set(model.model_fields)
        for field in sorted(actual - documented):
            problems.append(f"{name}.{field}: on the model, not in the schema")
        for field in sorted(documented - actual):
            problems.append(f"{name}.{field}: in the schema, not on the model")
    return problems


def main() -> int:
    documented = {(method, path) for method, path, *_ in _EVENT_RUN_ROUTES}
    expected = reachable()

    missing = expected - documented
    extra = documented - expected
    drift = schema_drift()
    if not missing and not extra and not drift:
        return 0

    print("Member API documentation is out of step with the allowlist:\n")
    for problem in drift:
        print(f"  request schema: {problem}")
    for method, path in sorted(missing):
        print(f"  reachable but undocumented: {method.upper():7s} {path}")
    for method, path in sorted(extra):
        print(f"  documented but unreachable: {method.upper():7s} {path}")
    print(
        "\nThe public API reference publishes this set as the boundary of a"
        " `event:run`\ngrant. Add the route to `_EVENT_RUN_ROUTES` in"
        " backend/src/public_api/main.py, or\nbar it in `_OAUTH_BARRED_SUBPATHS`"
        " — deciding which is the point of this failure."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
