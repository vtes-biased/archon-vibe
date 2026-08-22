import msgspec

from ..access_levels import (
    API_SYNC_FIELDS,
    DECK_API_EXCLUDE,
    PLAYER_API_EXCLUDE,
    TOURNAMENT_API_EXCLUDE,
    USER_API_FIELDS,
)
from ..models import DeckObject, League, Tournament, User

_REF = "#/components/schemas/{name}"


def _drop(schema: dict, fields: set[str]) -> None:
    for name in fields:
        schema.get("properties", {}).pop(name, None)
    if "required" in schema:
        schema["required"] = [r for r in schema["required"] if r not in fields]


def _keep(schema: dict, fields: set[str]) -> None:
    _drop(schema, set(schema.get("properties", {})) - fields)


_STREAM_LINES = {
    "StreamHeader": {
        "type": "object",
        "description": "First line. `generated_at` is when the read started.",
        "properties": {
            "type": {"const": "header"},
            "generated_at": {"type": "string"},
        },
        "required": ["type", "generated_at"],
    },
    "StreamEof": {
        "type": "object",
        "description": (
            "Last line. Its absence means the response was cut short — read it "
            "before trusting what came before."
        ),
        "properties": {"type": {"const": "eof"}, "count": {"type": "integer"}},
        "required": ["type", "count"],
    },
}


def _line(name: str) -> dict:
    return {
        "oneOf": [
            {"$ref": _REF.format(name="StreamHeader")},
            {
                "type": "object",
                "properties": {
                    "type": {"type": "string"},
                    "data": {"$ref": _REF.format(name=name)},
                },
                "required": ["type", "data"],
            },
            {"$ref": _REF.format(name="StreamEof")},
        ]
    }


def _referenced(node, components: dict[str, dict], seen: set[str]) -> None:
    if isinstance(node, dict):
        target = node.get("$ref")
        if isinstance(target, str):
            name = target.rsplit("/", 1)[-1]
            if name not in seen:
                seen.add(name)
                _referenced(components[name], components, seen)
        for value in node.values():
            _referenced(value, components, seen)
    elif isinstance(node, list):
        for value in node:
            _referenced(value, components, seen)


def _build() -> dict[str, dict]:
    _, components = msgspec.json.schema_components(
        (Tournament, User, League, DeckObject), ref_template=_REF
    )
    _drop(components["Tournament"], TOURNAMENT_API_EXCLUDE)
    _drop(components["Player"], PLAYER_API_EXCLUDE)
    _keep(components["User"], USER_API_FIELDS)
    _drop(components["League"], API_SYNC_FIELDS)
    _drop(components["DeckObject"], DECK_API_EXCLUDE)
    components["CommunityLinkEntry"] = {
        "type": "object",
        "properties": {
            "vekn_id": {"type": "string"},
            "country": {"type": ["string", "null"]},
            "link": {"$ref": _REF.format(name="CommunityLink")},
        },
        "required": ["vekn_id", "country", "link"],
    }
    components.update(_STREAM_LINES)
    roots = {"Tournament", "User", "League", "DeckObject", "CommunityLinkEntry"}
    for name in list(roots):
        components[f"{name}Line"] = _line(name)
    roots |= {f"{name}Line" for name in roots}
    reachable = set(roots)
    for name in roots:
        _referenced(components[name], components, reachable)
    return {name: components[name] for name in sorted(reachable)}


COMPONENTS = _build()


NDJSON = "application/x-ndjson"


def ref(name: str) -> dict:
    return {"$ref": _REF.format(name=name)}


def responds(schema: dict) -> dict:
    return {
        "responses": {
            "200": {
                "description": "The stored object",
                "content": {"application/json": {"schema": schema}},
            }
        }
    }


def streams(name: str, line_type: str) -> dict:
    """The example is a string: Scalar renders nothing from a bare `oneOf`."""
    rows = [
        '{"type":"header","generated_at":"2026-08-22T15:04:05.123456"}',
        f'{{"type":"{line_type}","data":{{ … a {name} … }}}}',
        '{"type":"eof","count":1}',
    ]
    return {
        "responses": {
            "200": {
                "description": "One JSON object per line",
                "content": {
                    NDJSON: {
                        "schema": {
                            "type": "string",
                            "contentMediaType": NDJSON,
                            "description": (
                                "Newline-delimited, not a JSON array. Each line "
                                f"is a {name}Line."
                            ),
                        },
                        "examples": {
                            "stream": {
                                "summary": f"A {line_type} stream",
                                "value": "\n".join(rows),
                            }
                        },
                    }
                },
            }
        }
    }
