import json

import msgspec

from ..access_levels import (
    API_SYNC_FIELDS,
    DECK_API_EXCLUDE,
    LINK_MODERATION_API_FIELDS,
    PLAYER_API_EXCLUDE,
    TOURNAMENT_API_EXCLUDE,
    USER_API_FIELDS,
)
from ..models import DeckObject, League, Tournament, User
from .examples import COMMUNITY_LINK_ENTRY, DECK, LEAGUE, TOURNAMENT, USER

EXAMPLES = {
    "Tournament": TOURNAMENT,
    "User": USER,
    "League": LEAGUE,
    "DeckObject": DECK,
    "CommunityLinkEntry": COMMUNITY_LINK_ENTRY,
}

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
            "Last line. Its absence means the response was cut short, so read it "
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


# A missing key here is a KeyError at import: a projection that drops a field
# must drop its documentation with it.
_FIELD_DOCS = {
    "Tournament": {
        "country": "ISO 3166-1 alpha-2 code of the host country. Empty when the "
        "event predates the field, which many imported records do.",
        "timezone": "IANA name, such as `Europe/Stockholm`. The one to read "
        "`start` and `finish` in.",
        "start": "Local start, ISO 8601 and carrying no offset. Pair it with "
        "`timezone` to get an instant.",
        "finish": "Local finish, same convention as `start`.",
        "rank": "Championship level. Empty for an ordinary event.",
        "event_code": "The event's permanent public handle, usable in place of "
        "the uid. Empty on records imported from an archive.",
        "banner_path": "Path to the event's image on this host, already "
        "versioned. Append it to this API's base URL. Null when there is none.",
        "table_extra_time": "Extra seconds granted per table, keyed by the "
        "table's index within its round as a string.",
        "external_ids": "This event's id on other systems, keyed by system "
        "name. `vekn` is a vekn.net event id.",
        "winner": "Uid of the winning member, null while undecided.",
        "league_uid": "Uid of the league this event counts towards, null if none.",
        "organizers_uids": "Uids of the members organizing the event.",
        "max_rounds": "Preliminary rounds planned. 0 means it was never set.",
        "round_time": "Round length in seconds. 0 means untimed.",
        "finals_time": "Finals length in seconds. 0 means untimed.",
    },
    "Table": {
        "organized_by": "Uid of the player who seated this table themselves, in "
        "a tournament that allows it. Null on a table the organizer seated.",
    },
    "FinalsTable": {
        "organized_by": "Always null: a final is never self-organized. The "
        "field is inherited from the preliminary table shape.",
    },
    "DeckObject": {
        "cards": "Card id to count. Ids are krcg's, resolvable at "
        "https://v4.api.krcg.org.",
        "attribution": "Designer credit: a VEKN id, the sentinel `twda` when "
        "the credit lives in the archive rather than with us, or null for "
        "anonymous.",
        "round": "The round this deck was played in, null when it is the "
        "event's single registered deck.",
        "tournament_uid": "Uid of the tournament the deck was played in.",
        "user_uid": "Uid of the member who played it.",
    },
    "User": {
        "vekn_id": "The member's VEKN number, and the only way to address them here.",
        "country": "ISO 3166-1 alpha-2 code of the member's country.",
        "wins": "Uids of the tournaments this member won.",
        "roles": "Organizational roles held, if any.",
    },
    "CommunityLink": {
        "languages": "ISO 639-1 codes. Empty means the link is not language-specific.",
        "country": "ISO 3166-1 alpha-2 code of the country the link serves.",
    },
    "CategoryRating": {
        "total": "Rating points across the listed tournaments.",
        "tournaments": "Every rated result contributing to the total.",
    },
}

_ENUM_DOCS = {
    "TournamentRank": "An empty string is an ordinary event, which is most of them.",
}


def _build() -> dict[str, dict]:
    _, components = msgspec.json.schema_components(
        (Tournament, User, League, DeckObject), ref_template=_REF
    )
    _drop(components["Tournament"], TOURNAMENT_API_EXCLUDE)
    _drop(components["Player"], PLAYER_API_EXCLUDE)
    _keep(components["User"], USER_API_FIELDS)
    _drop(components["League"], API_SYNC_FIELDS)
    _drop(components["DeckObject"], DECK_API_EXCLUDE)
    _keep(components["LinkModeration"], LINK_MODERATION_API_FIELDS)
    components["CommunityLinkEntry"] = {
        "type": "object",
        "description": "One member's link. The link's `country` is resolved: it "
        "is the link's own where it has one, the member's otherwise.",
        "properties": {
            "vekn_id": {"type": "string"},
            "link": {"$ref": _REF.format(name="CommunityLink")},
        },
        "required": ["vekn_id", "link"],
    }
    for name, fields in _FIELD_DOCS.items():
        properties = components[name]["properties"]
        for field, text in fields.items():
            properties[field]["description"] = text
    for name, text in _ENUM_DOCS.items():
        components[name]["description"] = text
    for name, example in EXAMPLES.items():
        components[name]["example"] = example
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


def responds(name: str) -> dict:
    return {
        "responses": {
            "200": {
                "description": "The stored object",
                "content": {
                    "application/json": {
                        "schema": ref(name),
                        "example": EXAMPLES[name],
                    }
                },
            }
        }
    }


def streams(name: str, line_type: str) -> dict:
    """The example is a string: Scalar renders nothing from a bare `oneOf`."""
    data = json.dumps(EXAMPLES[name], separators=(",", ":"), ensure_ascii=False)
    rows = [
        '{"type":"header","generated_at":"2026-08-22T15:04:05.123456"}',
        f'{{"type":"{line_type}","data":{data}}}',
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
