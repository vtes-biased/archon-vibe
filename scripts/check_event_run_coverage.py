#!/usr/bin/env python3
"""Fail the build when the public API's Member API section and the app's
`event:run` allowlist disagree.

The reference documents endpoints and actions the API does not serve, so nothing
about a route rename, a new tournament sub-route or an action the engine grows
would otherwise reach it: the listing *is* the published boundary, and a boundary
that lies is worse than none. Three authorities, each asserted in both directions:
the allowlist in `middleware/auth.py` for routes, `TournamentEvent::from_json` for
which actions exist, and the app's request models for which fields reach one.

Run: just event-run-coverage
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.src.main import app as site_app  # noqa: E402
from backend.src.middleware.auth import _OAUTH_BARRED_SUBPATHS  # noqa: E402
from backend.src.public_api.main import (  # noqa: E402
    _ACTION_FIELDS,
    _ACTION_STATES,
    _ACTIONS,
    _ANY_STATE,
    _EVENT_RUN_ROUTES,
    _EVENT_RUN_SCHEMAS,
    _IC_ACTIONS,
    _PLAYER_ACTIONS,
    _UNDOCUMENTED_ACTIONS,
)

PARSING = ROOT / "engine" / "src" / "tournament" / "parsing.rs"
APPLY = ROOT / "engine" / "src" / "tournament" / "mod.rs"

# Arms whose state gate is a shape the walk below cannot read. Each is published
# from the arm's own body instead, and the reason is what a reader has to re-check
# by hand when the arm changes.
_IRREGULAR_GATES = {
    "StartRound": "an online event takes a second branch admitting Playing",
    "SetScore": "require_can_edit_results: Playing for anyone, Waiting and"
    " Finished for the organizer",
    "Override": "require_can_edit_results",
    "Unoverride": "require_can_edit_results",
    "SetNonCompeting": "gated on the finals being seeded as well as on the state",
}

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


def engine_actions() -> set[str]:
    """The event names `TournamentEvent::from_json` matches on. Its arms are the
    only authority for what the action endpoint accepts."""
    body = PARSING.read_text()
    body = body[body.index("pub fn from_json") :]
    names = {
        name
        for arm in re.findall(r'^\s*((?:"\w+"\s*\|\s*)*"\w+")\s*=>', body, re.M)
        for name in re.findall(r'"(\w+)"', arm)
    }
    # A match-arm shape this regex misses would silently pass every check below.
    if len(names) < 30:
        raise SystemExit(f"parsing.rs walk found only {len(names)} action names")
    return names


def action_drift() -> list[str]:
    """The action variants against their two authorities: the engine decides which
    types exist, the request model decides which fields can reach one."""
    from backend.src.routes.tournaments import TournamentActionRequest

    problems = []
    documented = set(_ACTIONS) | set(_UNDOCUMENTED_ACTIONS)
    engine = engine_actions()
    for name in sorted(engine - documented):
        problems.append(f"{name}: an engine action, neither documented nor excused")
    for name in sorted(documented - engine):
        problems.append(f"{name}: documented, but the engine has no such action")

    carried = set(TournamentActionRequest.model_fields) - {"type"}
    for field in sorted(carried - set(_ACTION_FIELDS)):
        problems.append(f"{field}: on the request model, described by no action")
    for field in sorted(set(_ACTION_FIELDS) - carried):
        problems.append(f"{field}: described, but the request model cannot carry it")

    used = {
        f for _, required, optional in _ACTIONS.values() for f in (*required, *optional)
    }
    for field in sorted(set(_ACTION_FIELDS) - used):
        problems.append(f"{field}: described, but no action takes it")
    return problems


def engine_gates() -> dict[str, tuple[set[str], bool]]:
    """Each apply arm's state gate and whether it demands the organizer. An arm
    with no readable gate accepts every state, which is a claim in its own right."""
    body = APPLY.read_text()
    body = body[body.index("let event = TournamentEvent::from_json") :]
    arms = [
        (m.group(1), m.start())
        for m in re.finditer(r"^        TournamentEvent::(\w+)", body, re.M)
    ]
    if len(arms) < 40:
        raise SystemExit(f"mod.rs walk found only {len(arms)} apply arms")
    gates = {}
    for i, (name, pos) in enumerate(arms):
        arm = body[pos : arms[i + 1][1] if i + 1 < len(arms) else len(body)]
        states: set[str] = set()
        for g in re.finditer(
            r"require_state(_or_finished)?\(state, TournamentState::(\w+)\)", arm
        ):
            states |= {g.group(2)} | ({"Finished"} if g.group(1) else set())
        for g in re.finditer(
            r"if state != TournamentState::(\w+)((?:\s*&&\s*state != TournamentState::\w+)*)",
            arm,
        ):
            states |= {g.group(1)} | set(
                re.findall(r"TournamentState::(\w+)", g.group(2))
            )
        for g in re.finditer(
            r"!matches!\(\s*state,\s*((?:TournamentState::\w+\s*\|?\s*)+)\)", arm
        ):
            states |= set(re.findall(r"TournamentState::(\w+)", g.group(1)))
        gates[name] = (states or set(_ANY_STATE), "require_organizer(actor)" in arm)
    return gates


def state_drift() -> list[str]:
    """The third authority: the apply arms decide which states accept an action and
    who may send it, and the reference publishes both."""
    problems = []
    gates = engine_gates()
    for name, (states, dest) in _ACTION_STATES.items():
        gate = gates.get(name)
        if gate is None:
            problems.append(
                f"{name}: given states, but the engine applies no such action"
            )
            continue
        engine_states, needs_organizer = gate
        if name not in _IRREGULAR_GATES and set(states) != engine_states:
            problems.append(
                f"{name}: documented for {sorted(states)},"
                f" the engine gate admits {sorted(engine_states)}"
            )
        documented_organizer = name not in _PLAYER_ACTIONS and name not in _IC_ACTIONS
        if needs_organizer != documented_organizer:
            problems.append(
                f"{name}: engine {'demands' if needs_organizer else 'does not demand'}"
                " the organizer, the reference says otherwise"
            )
        if dest and dest not in _ANY_STATE:
            problems.append(f"{name}: leads to {dest}, which is no state")
    for name in sorted(set(_ACTIONS) - set(_ACTION_STATES)):
        problems.append(f"{name}: documented as an action, but named in no state")
    for name in sorted(set(_ACTION_STATES) - set(_ACTIONS)):
        problems.append(f"{name}: named in a state, but documented as no action")
    for name in sorted(set(_IRREGULAR_GATES) - set(_ACTION_STATES)):
        problems.append(f"{name}: excused from the state walk, but documented nowhere")
    return problems


def main() -> int:
    documented = {(method, path) for method, path, *_ in _EVENT_RUN_ROUTES}
    expected = reachable()

    missing = expected - documented
    extra = documented - expected
    drift = schema_drift() + action_drift() + state_drift()
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
        "\nThe public API reference publishes all of this as the boundary of an"
        " `event:run`\ngrant. In backend/src/public_api/main.py: add the route to"
        " `_EVENT_RUN_ROUTES` or\nbar it in `_OAUTH_BARRED_SUBPATHS`; add the action"
        " to `_ACTIONS` and `_ACTION_STATES` or excuse\nit in `_UNDOCUMENTED_ACTIONS`; add the field to"
        " `_ACTION_FIELDS` and to the actions that\ntake it. Deciding which is the"
        " point of this failure."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
