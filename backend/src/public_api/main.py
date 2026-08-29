import os
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from scalar_fastapi import get_scalar_api_reference

from .db import close_pool, open_pool
from .examples import (
    MEMBER_TOURNAMENT,
    ROUND_DECKS,
    SANCTION,
    SANCTION_REFERENCE,
    STREAM,
    USERINFO,
)
from .schemas import COMPONENTS
from .v1 import router

SITE_URL = os.getenv("SITE_URL_BASE", "http://localhost:8000")
API_URL = os.getenv("PUBLIC_API_URL_BASE", "http://localhost:8001")

DESCRIPTION = (
    r"""
There are two APIs.

| &nbsp; | Public API | Member API |
| --- | --- | --- |
| **Serves** | read-only VTES data | one tournament, read and write |
| **Host** | `{api}` | `{site}` |
| **Token** | your app's | a member's, one per event |
| **For** | archives, statistics, ratings | bots, judge aids, play platforms |

An app may use both: read the corpus with one token, run its event with the other.

In both cases, you need an Archon account carrying your VEKN membership and
the DEV role, which an IC grants. Open Developer in [your profile]({site}/profile),
register a client app, keep the secret — it is shown only once.

Select the grants your app needs:

- `api:read`: lets your app use the Public API. Does not require a callback URL.
- `profile:read`: lets you identify the member (`/oauth/userinfo`)
- `event:run`: gives you access on the member's behalf

**Note** `event:run` needs consent for each tournament you want to run on behalf of the member.

**Configuration: Register a callback URL** for `profile:read` and `event:run`.
The match is exact, so `https://example.com/callback` will not accept a trailing slash.

## Public API App token

```
curl -X POST {api}/oauth/token \
  -d grant_type=client_credentials -d client_id=... -d client_secret=...
```

Good for an hour. No refresh token: mint another.

## Member API tokens

Authorization code with PKCE (RFC 6749, RFC 7636) — any OAuth library will do this for you;
below is an example of the flow in curl.

**It runs against `{site}`.** The member's browser has to go there for the consent screen.

**Build a PKCE challenge**

One fresh verifier per authorization. `S256` only; `plain` is refused.

```
code_verifier=$(openssl rand -base64 60 | tr -d '\n=+/' | cut -c1-64)
code_challenge=$(printf %s "$code_verifier" | openssl dgst -binary -sha256 \
  | openssl base64 | tr '+/' '-_' | tr -d '=\n')
```

Keep the verifier for the exchange below.

**Send the member to the consent screen** (in browser)

```
{site}/consent?response_type=code&client_id=$CLIENT_ID&redirect_uri=https%3A%2F%2Fexample.com%2Fcallback&scope=profile%3Aread&state=$STATE&code_challenge=$CODE_CHALLENGE&code_challenge_method=S256
```

For `event:run`, add `&tournament=<tournament uid>`; if you don't, the token you'll get will **only** give you access
to the `/oauth/userinfo` endpoint, not to all the event endpoints.

`state` comes back untouched — check it.

**They land back on your callback** (in browser)

```
https://example.com/callback?code=6mB3...&state=$STATE
https://example.com/callback?error=access_denied&state=$STATE
```

The code is single-use and lives 60 seconds.

**Exchange the code for tokens** server-side:

```
curl -X POST {site}/oauth/token \
  -d grant_type=authorization_code \
  -d client_id=$CLIENT_ID -d client_secret=$CLIENT_SECRET \
  -d code=6mB3... \
  -d redirect_uri=https://example.com/callback \
  -d code_verifier=$CODE_VERIFIER
```

```json
{"access_token":"eyJ...","refresh_token":"eyJ...","token_type":"Bearer",
 "expires_in":3600,"scope":"profile:read"}
```

`redirect_uri` must be the exact string you sent to the consent screen.

**Refresh before the hour is out**, server-side too:

```
curl -X POST {site}/oauth/token \
  -d grant_type=refresh_token \
  -d client_id=$CLIENT_ID -d client_secret=$CLIENT_SECRET \
  -d refresh_token=eyJ...
```

Access tokens last an hour, refresh tokens 30 days, and **refreshing rotates**:
store the new refresh token before spending the new access token. Replaying a
rotated one reads as theft and kills the whole lineage.

**Hand the tokens back** (optional):

```
curl -X POST {site}/oauth/revoke \
  -d client_id=$CLIENT_ID -d client_secret=$CLIENT_SECRET -d token=eyJ...
```

The answer is `200` whatever you send, so it is no hint for which tokens exist.
""".strip()
    .replace("{site}", SITE_URL)
    .replace("{api}", API_URL)
)

PUBLIC_API_TAG = (
    r"""
Read-only, on `{api}`. Nothing here changes anything, and there is no anonymous
read: every request needs `Authorization: Bearer <token>`. Card data belongs to
[krcg](https://v4.api.krcg.org/docs), not to us.

A single object comes back as JSON. A collection comes back as **JSON Lines**:
one object per line, opened by `header` and closed by `eof`.

```
{"type":"header","generated_at":"2026-08-22T15:04:05.123456"}
{"type":"tournament","data":{ … }}
{"type":"eof","count":1}
```

## Reading a list

A list response is not a JSON document and will not parse as one. Read it line by
line: `iter_lines()` on a `stream=True` request in requests or httpx, the body as
an async iterator in Node, `curl --no-buffer`. Most clients can do this and most
do not by default — for `/v1/tournaments` that means buffering tens of megabytes
for nothing.

* **No pagination.** Read what you want, then close the connection. For the ten
  newest tournaments, read ten lines and hang up.
* **Trust nothing until the `eof` line.** A response cut short mid-flight looks
  exactly like a short one.
* **Rows come in blocks of 250**, holding no database connection between them, so
  a slow reader costs nothing. The boundaries are invisible; do not align on them.

## Ordering and freshness

**Newest first**, ordered by `uid`. Uids are UUIDv7, so they sort by when a record
was created, not by when the event happened — a decade-old tournament imported
last week sorts as new. Select by event date with `start_after` and `start_before`.

A `uid` never changes, so nothing moves while you read. There is also **no "what
changed since"**: deleted records are not served, so a diff by date would
accumulate rows that no longer exist. Re-read what you need, or take `/v1/export`.

## Building a deck archive

`/v1/decks` streams every published deck, newest first; `tournament=<uid>` narrows
it to one event. `/v1/export` is the whole corpus — tournaments, members, decks and
leagues — as one gzipped file, the cheapest way to take everything and to take it
again later. A member's community links ride inside their row; `/v1/community-links`
serves them one per line.

**A deck appears only once its event is finished**, and then only as far as the
tournament's own `decklists_mode` allows: `Winner`, `Finalists` or `All`.

**Reopening a finished event withdraws its decks** until it finishes again. A
deck's disappearance is far more often a correction in progress than a deletion.

**Decks carry no author name.** Attribution runs through `user_uid` — hand it to
`/v1/users/{uid}` for the VEKN ID. The same uid appears in the tournament's
`players`, `standings` and `winner`, so one lookup attributes a deck and the
result it earned.
""".strip()
    .replace("{site}", SITE_URL)
    .replace("{api}", API_URL)
)

MEMBER_API_TAG = (
    r"""
Everything a member's token reaches, on `{site}`. `/oauth/userinfo` answers any
such token. The rest is the event itself, and needs an `event:run` token that
names one: ask for the scope with `&tournament=<uid>`, and send the token back as
an ordinary bearer token.

**A token that names no event reaches `/oauth/userinfo` and nothing else here** —
that is the identity-only mode, and asking for `event:run` without a tournament is
how you get it. A daemon token reaches none of this. The reverse does not hold:
the Public API accepts any member's token, whatever scope it carries.

## What the grant reaches

An allowlist — anything not listed on this page is refused, including routes
Archon grows later. Beyond the endpoints below the token reaches `/oauth/token`
and `/oauth/revoke`, for its own refresh and revocation; consent and client
management refuse third-party tokens outright.

No other event, and nothing outside a tournament.

**Owning the event is barred even inside your own**: `organizers`, `push-vekn`,
`go-offline`, `go-online`, `force-takeover`, `force-unlock`, `sync-offline`,
`qr-checkin`, `archon-import`, `DELETE` on the tournament itself, and the
`ReopenTournament` action. What remains
is running it, and the engine gates that on the event's state exactly as it does
for the member in Archon.

## Reading the state

**There is no `GET` for the tournament document**, and you never need one. Every
action returns the whole updated tournament, so your write is also your read. For
what you did not do — a co-organizer seating a table, a player checking in at the
door — open the event's stream: it replays current state on connect, then stays
open for changes.

## Sending an action

One endpoint runs the event: a `type`, plus whatever fields that type needs. The
state machine is real, and each step is refused from the wrong state.

```
{"type":"OpenRegistration"}
{"type":"Register","user_uid":"…"}
{"type":"CloseRegistration"}
{"type":"CheckIn","player_uid":"…"}
{"type":"StartRound"}
{"type":"SetScore","round":0,"table":0,"scores":[{"player_uid":"…","vp":2.5}]}
{"type":"FinishRound"}
{"type":"FinishTournament"}
```

`CloseRegistration` is what moves the event from `Registration` to `Waiting`:
neither `CheckIn` nor `StartRound` is accepted before it.

**`round` and `table` are zero-based** indices into the tournament's own `rounds`
array — first table of the first round is `{"round":0,"table":0}`. The finals are
the index one past the last preliminary round.

**Every type is listed with its own fields** under the endpoint's request body —
pick one and you get exactly what it takes, not the union of everything. Four of
the engine's are missing on purpose: `ReopenTournament` is barred for a
third-party token, `ReportPromos` needs a field this endpoint cannot carry, and
`UploadDeck` and `UpdateDeck` are spellings of `UpsertDeck`.
""".strip()
    .replace("{site}", SITE_URL)
    .replace("{api}", API_URL)
)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await open_pool()
    try:
        yield
    finally:
        await close_pool()


_EVENT = "/api/tournaments/{uid}"

_EVENT_RUN_ROUTES: list[tuple[str, str, str, str, str, str]] = [
    (
        "post",
        f"{_EVENT}/action",
        "Run the event",
        "200",
        "The updated tournament.",
        "Every state change of a tournament — registration, check-in, rounds, scores,"
        " finals — is one `type` sent here, and each type is its own model below."
        " Answers with the whole updated tournament, so the write is also the read.",
    ),
    (
        "post",
        f"{_EVENT}/announce",
        "Post an announcement",
        "200",
        "The updated tournament.",
        "Puts a message in front of everyone watching the event.",
    ),
    (
        "delete",
        f"{_EVENT}/announce/{{announcement_id}}",
        "Delete an announcement",
        "200",
        "The updated tournament.",
        "Takes a posted announcement back down.",
    ),
    (
        "post",
        f"{_EVENT}/bulk-register",
        "Register a roster",
        "200",
        "The updated tournament.",
        "Registers many players in one call, for a roster you already hold.",
    ),
    (
        "post",
        f"{_EVENT}/call-judge",
        "Call a judge",
        "204",
        "No content.",
        "Raises a judge from a table.",
    ),
    (
        "get",
        f"{_EVENT}/decks",
        "Decks of the round in play",
        "200",
        "Every seated player's deck for the round being played.",
        "The delegated read an online-play platform makes once a round starts. This"
        " is the live round, not the published archive: `/v1/decks` serves finished"
        " events to everyone, this serves the current round to whoever runs it.",
    ),
    (
        "post",
        f"{_EVENT}/timer/start",
        "Start the round timer",
        "200",
        "The updated tournament.",
        "Starts the clock on the round in play.",
    ),
    (
        "post",
        f"{_EVENT}/timer/pause",
        "Pause the round timer",
        "200",
        "The updated tournament.",
        "Holds the clock where it is.",
    ),
    (
        "post",
        f"{_EVENT}/timer/add-time",
        "Add time to the round",
        "200",
        "The updated tournament.",
        "Extends the round.",
    ),
    (
        "post",
        f"{_EVENT}/timer/reset",
        "Reset the round timer",
        "200",
        "The updated tournament.",
        "Puts the clock back to the round's full length.",
    ),
    (
        "post",
        f"{_EVENT}/banner",
        "Upload the event banner",
        "200",
        '`{"success": true}`.',
        "Replaces the event's banner image.",
    ),
    (
        "get",
        f"{_EVENT}/banner",
        "Get the event banner",
        "200",
        "The image bytes.",
        "Serves the banner. A versioned (`?v=`) URL is immutable and cacheable.",
    ),
    (
        "delete",
        f"{_EVENT}/banner",
        "Delete the event banner",
        "200",
        '`{"success": true}`.',
        "Removes the banner image.",
    ),
    (
        "get",
        "/stream",
        "The event's live feed",
        "200",
        "An endless `text/event-stream` of `data:` lines, one JSON object each.",
        "Pass `tournament=<the granted uid>`; any other value is refused. The"
        " connection replays the event's current state, then stays open for changes,"
        " so a client that reconnects has missed nothing.",
    ),
    (
        "post",
        "/sanctions/",
        "File a sanction",
        "201",
        "The created sanction.",
        "Records a judge's ruling against a player. The sanction must name the"
        " granted tournament; any other is refused.",
    ),
    (
        "get",
        "/oauth/userinfo",
        "Who the member is",
        "200",
        "The member's uid, VEKN ID, roles and capabilities.",
        "`sub` is the member's uid — what `/v1/users/{uid}` takes on the Public API,"
        " and what a tournament's `players`, `standings` and `winner` carry."
        " `capabilities` is what the member may do anywhere, so your app need not"
        " carry its own copy of the role matrix. Answers a `profile:read` or an"
        " `event:run` token, whether or not it names an event.",
    ),
    (
        "get",
        "/sanctions/reference",
        "Sanction categories and levels",
        "200",
        "The categories, subcategories and levels a sanction may carry.",
        "The vocabulary `/sanctions/` accepts.",
    ),
]


_STR = {"type": "string"}
_INT = {"type": "integer"}
_BOOL = {"type": "boolean"}

# Fields the action variants draw on, described once each. `_ACTIONS` below says
# which type takes which; nothing outside this table can be sent, because
# `TournamentActionRequest` in the app carries no other field.
_ACTION_FIELDS: dict[str, dict] = {
    "user_uid": {
        **_STR,
        "description": "The member, as `/oauth/userinfo` reports `sub`.",
    },
    "player_uid": {
        **_STR,
        "description": "The player — the same member uid: a roster seat carries no id of its own.",
    },
    "display_name": {
        **_STR,
        "maxLength": 32,
        "description": "Shown instead of the member's name. Display only; identity stays the account's.",
    },
    "round": {
        **_INT,
        "description": "Zero-based index into `rounds`. The finals are the index one past the last.",
    },
    "table": {**_INT, "description": "Zero-based index within the round."},
    "table1": {**_INT, "description": "Zero-based, as `table`."},
    "seat1": {**_INT, "description": "Zero-based seat at `table1`."},
    "table2": {**_INT, "description": "Zero-based, as `table`."},
    "seat2": {**_INT, "description": "Zero-based seat at `table2`."},
    "seat": {**_INT, "description": "Zero-based seat at the table."},
    "scores": {
        "type": "array",
        "description": "One entry per seat at the table.",
        "items": {
            "type": "object",
            "required": ["player_uid", "vp"],
            "properties": {"player_uid": _STR, "vp": {"type": "number"}},
        },
    },
    "comment": {
        **_STR,
        "description": "Why the table was closed by hand. Not optional: an empty one is refused.",
    },
    "toss": {**_INT, "description": "Finals seeding draw. 0 is no draw."},
    "status": {
        **_STR,
        "enum": ["Pending", "Paid", "Refunded", "Cancelled"],
    },
    "non_competing": {
        **_BOOL,
        "description": "A proxy stand-in: excluded from rank, RTP and finals.",
    },
    "waitlisted": _BOOL,
    "seating": {
        "type": "array",
        "description": "Player uids, one inner array per table, in seat order.",
        "items": {"type": "array", "items": _STR},
    },
    "player_uids": {
        "type": "array",
        "items": _STR,
        "description": "The pod that chose to sit together.",
    },
    "config": {
        "type": "object",
        "description": "Only the settings you send; the rest stand.",
    },
    "deck": {
        "type": "object",
        "description": "The decklist, as `/v1/decks` publishes one.",
    },
    "multideck": {
        **_BOOL,
        "description": "Address the round's deck rather than the event's single one.",
    },
    "label": {**_STR, "description": "What the draw is for, shown with its winners."},
    "pool": {**_STR, "description": "Who is eligible — the raffle's own pool key."},
    "exclude_drawn": {
        **_BOOL,
        "default": True,
        "description": "Skip anyone a previous draw already picked.",
    },
    "count": {**_INT, "description": "How many to draw."},
    "seed": {
        **_INT,
        "description": "Drives the draw. The same seed redraws the same winners.",
    },
    "winner": {**_STR, "description": "Member uid. Empty clears the recorded winner."},
    "players": {
        "type": "array",
        "items": _STR,
        "description": "The roster that is known.",
    },
    "reported_player_count": {
        **_INT,
        "description": "What the record claims played, which may exceed the named roster.",
    },
}

# The engine's vocabulary (`engine/src/tournament/parsing.rs`), narrowed to the
# fields the app's request model carries. Required follows the engine: one model
# serves every type, so on the model itself every field is optional.
_ACTIONS: dict[str, tuple[str, tuple[str, ...], tuple[str, ...]]] = {
    "OpenRegistration": ("Take a `Planned` event to `Registration`.", (), ()),
    "CloseRegistration": (
        "`Registration` to `Waiting`. This is what opens check-in — neither `CheckIn`"
        " nor `StartRound` is accepted before it.",
        (),
        (),
    ),
    "ReopenRegistration": ("Back to `Registration` from `Waiting`.", (), ()),
    "CancelRegistration": ("Back to `Planned`, roster and all.", (), ()),
    "Register": (
        "Put a member on the roster. Their account must carry a VEKN ID — the server"
        " reads it from the account, never from you, and refuses one without.",
        ("user_uid",),
        ("display_name",),
    ),
    "Unregister": (
        "Leave the roster. Self-service: only the member who granted you the token.",
        ("user_uid",),
        (),
    ),
    "AddPlayer": (
        "Register someone as the organizer, in any state up to `Finished`, checking"
        " them in when the event is already `Waiting`. Same VEKN ID rule as `Register`.",
        ("user_uid",),
        ("display_name",),
    ),
    "RemovePlayer": ("Take a player off the roster.", ("user_uid",), ()),
    "DropOut": ("Withdraw a player from an event under way.", ("player_uid",), ()),
    "CheckIn": ("Arm a player for the next round.", ("player_uid",), ("display_name",)),
    "CheckOut": ("Undo a check-in.", ("player_uid",), ()),
    "CheckInAll": ("Check in everyone on the roster.", (), ()),
    "ResetCheckIn": ("Return every checked-in player to `Registered`.", (), ()),
    "SetPaymentStatus": ("", ("player_uid", "status"), ()),
    "MarkAllPaid": ("Move every `Pending` player to `Paid`.", (), ()),
    "SetNonCompeting": ("", ("player_uid", "non_competing"), ()),
    "SetWaitlisted": (
        "Promote off the waitlist, or demote onto it.",
        ("player_uid", "waitlisted"),
        (),
    ),
    "StartRound": (
        "Seat the checked-in players and start playing. Omit `seating` and the engine"
        " seats the round itself.",
        (),
        ("seating",),
    ),
    "FinishRound": (
        "Close the round. Every table needs a score or an override first. Omit"
        " `round` for the current one.",
        (),
        ("round",),
    ),
    "CancelRound": (
        "Throw a round away. Omit `round` for the current one.",
        (),
        ("round",),
    ),
    "RestoreRound": (
        "Put a cancelled round back. Preliminary rounds only.",
        (),
        ("round",),
    ),
    "SelfOrganizeRound": (
        "Seat one pod from the players who chose it. Needs the event configured for"
        " self-organized rounds, and is the one action a player may take unaided.",
        ("player_uids",),
        (),
    ),
    "SwapSeats": (
        "Exchange two seats.",
        ("round", "table1", "seat1", "table2", "seat2"),
        (),
    ),
    "SeatPlayer": (
        "Put a player in a seat. Omit `round` for the current one.",
        ("player_uid", "table", "seat"),
        ("round",),
    ),
    "UnseatPlayer": ("Take a player out of their seat.", ("player_uid",), ("round",)),
    "AddTable": ("Add an empty table to the round.", (), ()),
    "RemoveTable": ("Remove a table.", ("table",), ()),
    "SetScore": ("Record a table's victory points.", ("round", "table", "scores"), ()),
    "Override": (
        "Close a table on a judge's ruling, against the engine's own reading of the"
        " scores.",
        ("round", "table", "comment"),
        (),
    ),
    "Unoverride": ("Lift an override.", ("round", "table"), ()),
    "SetToss": ("Record one player's finals seeding draw.", ("player_uid", "toss"), ()),
    "RandomToss": (
        "Draw for every tied finalist at once. Needs two played rounds.",
        (),
        (),
    ),
    "StartFinals": ("Seat the finals.", (), ()),
    "FinishFinals": ("Close the finals.", (), ()),
    "CancelFinals": ("Throw the finals away.", (), ()),
    "FinishTournament": (
        "Close the event. Standings are final and ratings move.",
        (),
        (),
    ),
    "AlterSeating": ("Replace a round's seating wholesale.", ("round", "seating"), ()),
    "UpsertDeck": (
        "Attach a decklist to a player.",
        ("player_uid", "deck"),
        ("multideck",),
    ),
    "DeleteDeck": (
        "Drop a player's decklist. It cannot single out one list of a multideck set:"
        " the engine takes an index this endpoint has no field for.",
        ("player_uid",),
        ("multideck",),
    ),
    "RaffleDraw": (
        "Draw prize winners from a pool.",
        ("label", "pool", "count", "seed"),
        ("exclude_drawn",),
    ),
    "RaffleUndo": ("Undo the last draw.", (), ()),
    "RaffleClear": ("Clear every draw.", (), ()),
    "UpdateConfig": ("Change the event's settings.", ("config",), ()),
    "SetArchivalResults": (
        "Record the result of an event Archon holds no play data for. IC only.",
        ("winner", "players", "reported_player_count"),
        (),
    ),
}

# Engine actions this endpoint does not document, and why. `just event-run-coverage`
# reads it: an action the engine grows lands in `_ACTIONS` or here, never nowhere.
_UNDOCUMENTED_ACTIONS: dict[str, str] = {
    "UploadDeck": "spelling of UpsertDeck",
    "UpdateDeck": "spelling of UpsertDeck",
    "ReopenTournament": "refused for a third-party token",
    "ReportPromos": "needs `promos`, which the request model does not carry",
}


def _action_schemas() -> dict[str, dict]:
    """One schema per action, plus the discriminated union of them all. The union
    is what the endpoint takes; the variants are what a reader picks from."""
    schemas: dict[str, dict] = {}
    for name, (summary, required, optional) in _ACTIONS.items():
        properties = {"type": {**_STR, "const": name}}
        for field in (*required, *optional):
            properties[field] = _ACTION_FIELDS[field]
        schema = {
            "title": name,
            "type": "object",
            "required": ["type", *required],
            "properties": properties,
        }
        if summary:
            schema["description"] = summary
        schemas[f"Action{name}"] = schema
    ref = "#/components/schemas/Action{name}"
    schemas["TournamentActionRequest"] = {
        "description": "One tournament event. `type` picks it, and picks its fields with it.",
        "oneOf": [{"$ref": ref.format(name=name)} for name in _ACTIONS],
        "discriminator": {
            "propertyName": "type",
            "mapping": {name: ref.format(name=name) for name in _ACTIONS},
        },
    }
    return schemas


# Hand-written: the app's Pydantic models are on the far side of the isolation
# line. `check_event_run_coverage.py` pairs each with the model it names.
_EVENT_RUN_SCHEMAS: dict[str, dict] = {
    "AnnounceRequest": {
        "type": "object",
        "required": ["body"],
        "properties": {"body": {**_STR, "description": "The message text."}},
    },
    "BulkRegisterRow": {
        "type": "object",
        "properties": {
            "vekn_id": _STR,
            "email": _STR,
            "name": {**_STR, "description": "Display only, for unmatched rows."},
            "paid": {**_BOOL, "description": "Omit to take `default_paid`."},
        },
    },
    "BulkRegisterRequest": {
        "type": "object",
        "required": ["rows"],
        "properties": {
            "rows": {
                "type": "array",
                "items": {"$ref": "#/components/schemas/BulkRegisterRow"},
            },
            "default_paid": {**_BOOL, "default": True},
        },
    },
    "JudgeCallRequest": {
        "type": "object",
        "required": ["table"],
        "properties": {"table": {**_INT, "description": "Zero-based table index."}},
    },
    "AddTimeRequest": {
        "type": "object",
        "required": ["table", "seconds"],
        "properties": {
            "table": {**_STR, "description": "Table index, as a string key."},
            "seconds": _INT,
        },
    },
    "CreateSanctionRequest": {
        "type": "object",
        "required": ["user_uid", "level", "category", "description"],
        "properties": {
            "user_uid": _STR,
            "level": {**_STR, "description": "See `/sanctions/reference`."},
            "category": {**_STR, "description": "See `/sanctions/reference`."},
            "subcategory": _STR,
            "round_number": _INT,
            "description": _STR,
            "expires_at": {**_STR, "description": "`YYYY-MM-DD`."},
            "tournament_uid": {
                **_STR,
                "description": "Must be the granted tournament.",
            },
        },
    },
}


# Endpoints that answer with something other than JSON.
_RESPONSE_MEDIA: dict[tuple[str, str], str] = {
    ("get", "/stream"): "text/event-stream",
    ("get", f"{_EVENT}/banner"): "image/*",
}

# What each answer actually looks like. The tournament document is one object
# reused, because eight of these endpoints answer with exactly it.
_RESPONSE_EXAMPLES: dict[tuple[str, str], object] = {
    ("post", f"{_EVENT}/action"): MEMBER_TOURNAMENT,
    ("post", f"{_EVENT}/announce"): MEMBER_TOURNAMENT,
    ("delete", f"{_EVENT}/announce/{{announcement_id}}"): MEMBER_TOURNAMENT,
    ("post", f"{_EVENT}/bulk-register"): MEMBER_TOURNAMENT,
    ("post", f"{_EVENT}/timer/start"): MEMBER_TOURNAMENT,
    ("post", f"{_EVENT}/timer/pause"): MEMBER_TOURNAMENT,
    ("post", f"{_EVENT}/timer/add-time"): MEMBER_TOURNAMENT,
    ("post", f"{_EVENT}/timer/reset"): MEMBER_TOURNAMENT,
    ("get", f"{_EVENT}/decks"): ROUND_DECKS,
    ("post", f"{_EVENT}/banner"): {"success": True},
    ("delete", f"{_EVENT}/banner"): {"success": True},
    ("get", "/stream"): STREAM,
    ("post", "/sanctions/"): SANCTION,
    ("get", "/oauth/userinfo"): USERINFO,
    ("get", "/sanctions/reference"): SANCTION_REFERENCE,
}

# Which body each endpoint takes. Endpoints absent from this map take none.
_EVENT_RUN_BODIES: dict[str, str] = {
    f"{_EVENT}/action": "TournamentActionRequest",
    f"{_EVENT}/announce": "AnnounceRequest",
    f"{_EVENT}/bulk-register": "BulkRegisterRequest",
    f"{_EVENT}/call-judge": "JudgeCallRequest",
    f"{_EVENT}/timer/add-time": "AddTimeRequest",
    "/sanctions/": "CreateSanctionRequest",
}


def _event_run_paths() -> dict:
    paths: dict = {}
    for method, path, summary, code, responds, description in _EVENT_RUN_ROUTES:
        operation = {
            "tags": ["Member API"],
            "summary": summary,
            "description": description,
            "servers": [{"url": SITE_URL}],
            "responses": {code: {"description": responds}},
        }
        # Without a media type Scalar renders a 200 as "No Body"; the app's own
        # response shapes stay out of this document, so the schema is left open.
        if code != "204":
            media = _RESPONSE_MEDIA.get((method, path), "application/json")
            body = {
                "schema": {
                    "type": "string" if media != "application/json" else "object"
                }
            }
            example = _RESPONSE_EXAMPLES.get((method, path))
            if example is not None:
                body["example"] = example
            operation["responses"][code]["content"] = {media: body}
        schema = _EVENT_RUN_BODIES.get(path)
        if schema and method == "post":
            operation["requestBody"] = {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {"$ref": f"#/components/schemas/{schema}"}
                    }
                },
            }
        elif method == "post" and path.endswith("/banner"):
            operation["requestBody"] = {
                "required": True,
                "content": {
                    "multipart/form-data": {
                        "schema": {
                            "type": "object",
                            "required": ["file"],
                            "properties": {
                                "file": {"type": "string", "format": "binary"}
                            },
                        }
                    }
                },
            }
        names = re.findall(r"{(\w+)}", path)
        if names:
            operation["parameters"] = [
                {
                    "name": name,
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string"},
                    "description": (
                        "The tournament the token was granted for."
                        if name == "uid"
                        else ""
                    ),
                }
                for name in names
            ]
        if path == "/stream":
            operation["parameters"] = [
                {
                    "name": "tournament",
                    "in": "query",
                    "required": True,
                    "schema": {"type": "string"},
                    "description": "The tournament the token was granted for.",
                }
            ]
        paths.setdefault(path, {})[method] = operation
    return paths


app = FastAPI(
    title="Archon Public API",
    version="1",
    description=DESCRIPTION,
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["Authorization"],
)

app.include_router(router)


def _openapi() -> dict:
    if app.openapi_schema is None:
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        components = schema.setdefault("components", {})
        components.setdefault("schemas", {}).update(
            COMPONENTS | _EVENT_RUN_SCHEMAS | _action_schemas()
        )
        components["securitySchemes"] = {
            "bearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
        }
        schema["security"] = [{"bearerAuth": []}]
        # FastAPI adds an `application/json` 200 of its own and `openapi_extra`
        # merges beside it rather than replacing it, so a stream would advertise
        # a JSON body it never returns — and Scalar would preview that one.
        for methods in schema["paths"].values():
            for operation in methods.values():
                content = operation["responses"]["200"]["content"]
                if len(content) > 1:
                    content.pop("application/json", None)
        schema["tags"] = [
            {"name": "Public API", "description": PUBLIC_API_TAG},
            {"name": "Member API", "description": MEMBER_API_TAG},
        ]
        schema["x-tagGroups"] = [
            {"name": "Public API", "tags": ["Public API"]},
            {"name": "Member API", "tags": ["Member API"]},
        ]
        # After the pruning loop above: these carry no `content` for it to prune.
        for path, operations in _event_run_paths().items():
            schema["paths"].setdefault(path, {}).update(operations)
        app.openapi_schema = schema
    return app.openapi_schema


app.openapi = _openapi


@app.get("/docs", include_in_schema=False)
async def docs():
    return get_scalar_api_reference(openapi_url=app.openapi_url, title=app.title)
