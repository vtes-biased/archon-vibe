import os
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from scalar_fastapi import get_scalar_api_reference

from .db import close_pool, open_pool
from .schemas import COMPONENTS
from .v1 import router

SITE_URL = os.getenv("SITE_URL_BASE", "http://localhost:8000")
API_URL = os.getenv("PUBLIC_API_URL_BASE", "http://localhost:8001")

DESCRIPTION = (
    r"""
Two APIs live here. They share this page, one OAuth client, and nothing else.

| &nbsp; | Public API | Impersonate Access |
| --- | --- | --- |
| **Serves** | read-only VTES data | one tournament, read and write |
| **Host** | `{api}` | `{site}` |
| **Token** | your app's own | a member's, one per event |
| **For** | archives, statistics, ratings | bots, judge aids, play platforms |

An app may use both: read the corpus with one token, run its event with the other.

**Impersonate Access cannot use an app token.** `client_credentials` grants
`api:read` and nothing else, and `api:read` is refused at `/authorize`. Writing to
an event always means a member's grant.

**Consent is per event.** A grant is keyed to (app, member, tournament). Every new
tournament needs its own approval; there is no global "always allow". Returning to
an event already approved is silent.

Members are published by **VEKN ID, never by name**. No name, contact, city or
avatar is served here, and sanctions are never served. Card data belongs to
[krcg](https://v4.api.krcg.org/docs), not to us.

Every request needs `Authorization: Bearer <token>`. There is no anonymous read.

## App token

Opens the Public API. You need an Archon account carrying your VEKN membership and
the DEV role, which an IC grants. Open Developer in [your profile]({site}/profile),
register a client with `api:read`, keep the secret — it is shown once. No redirect
URI to declare.

```
curl -X POST {api}/oauth/token \
  -d grant_type=client_credentials -d client_id=... -d client_secret=...
```

Good for an hour. No refresh token: mint another.

## Login with Archon

Signs members in, and opens Impersonate Access. Authorization code with PKCE
(RFC 6749, RFC 7636) — any OAuth library will do this for you; below is the same
flow in curl.

**It runs against `{site}`, not this host.** The member's browser has to go there
for the consent screen, and the same endpoints answer there.

Ask for `profile:read` to learn who the member is. Add `user:impersonate` only to
run an event for them — it is the heavy one, bounded to a single tournament.

### 1. Register your application

Developer in [your profile]({site}/profile), DEV role again. Tick the scopes you
need. Declare every redirect URI: the match is exact, so
`https://example.com/callback` will not accept a trailing slash. The secret is
shown once.

### 2. Build a PKCE challenge

One fresh verifier per authorization. `S256` only; `plain` is refused.

```
code_verifier=$(openssl rand -base64 60 | tr -d '\n=+/' | cut -c1-64)
code_challenge=$(printf %s "$code_verifier" | openssl dgst -binary -sha256 \
  | openssl base64 | tr '+/' '-_' | tr -d '=\n')
```

Keep the verifier for step 5.

### 3. Send the member to the consent screen

```
{site}/consent?response_type=code&client_id=$CLIENT_ID&redirect_uri=https%3A%2F%2Fexample.com%2Fcallback&scope=profile%3Aread&state=$STATE&code_challenge=$CODE_CHALLENGE&code_challenge_method=S256
```

Send them to `/consent`, not to `/oauth/authorize` underneath it — that one is
first-party and answers your app 403.

For `user:impersonate`, add `&tournament=<tournament uid>`; the screen names the
event, and the scope without an event is refused.

`state` comes back untouched — check it. An unsigned-in member logs in first.

### 4. Take the callback

```
https://example.com/callback?code=6mB3...&state=$STATE
https://example.com/callback?error=access_denied&state=$STATE
```

The code is single-use and lives 60 seconds.

### 5. Exchange the code for tokens

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

**The client secret is required as well as the verifier, not instead of it.** Every
client here is confidential, so there is no public variant for a browser bundle or
a mobile binary: run this exchange on your server. `redirect_uri` must be the
string you sent in step 3.

### 6. Ask who the member is

```
curl {site}/oauth/userinfo -H "Authorization: Bearer $ACCESS_TOKEN"
```

```json
{"sub":"019f6a65-01d4-7214-bcc9-4e46534b9d62","vekn_id":"1000123",
 "roles":["Prince"],"capabilities":["create_tournament","sponsor_member"]}
```

`sub` is the member's uid — what `/v1/users/{uid}` takes, and what a tournament's
`players`, `standings` and `winner` carry. `capabilities` saves you a copy of the
role matrix.

Needs `profile:read`; a `user:impersonate`-only token gets 403. For both, ask for
both: `scope=profile%3Aread%20user%3Aimpersonate`.

### 7. Refresh before the hour is out

```
curl -X POST {site}/oauth/token \
  -d grant_type=refresh_token \
  -d client_id=$CLIENT_ID -d client_secret=$CLIENT_SECRET \
  -d refresh_token=eyJ...
```

Access tokens last an hour, refresh tokens 30 days, and **refreshing rotates**:
store the new refresh token before spending the new access token. Replaying a
rotated one reads as theft and kills the whole lineage.

Refresh re-checks the grant, so it can fail through no fault of yours: the member
withdrew your app, or an impersonated event finished. Neither is retryable — start
again at step 3.

### 8. Hand the tokens back

```
curl -X POST {site}/oauth/revoke \
  -d client_id=$CLIENT_ID -d client_secret=$CLIENT_SECRET -d token=eyJ...
```

Either half kills the other and the whole lineage with it. The answer is `200`
whatever you send, so it is no oracle for which tokens exist.

Revoking tokens is not withdrawing consent: the approval stands and your next
authorization is silent. Withdrawing is the member's to do, from Authorized apps
in their profile, and it cuts live tokens with it.

""".strip()
    .replace("{site}", SITE_URL)
    .replace("{api}", API_URL)
)

PUBLIC_API_TAG = (
    r"""
Read-only, on `{api}`. Nothing here changes anything.

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

IMPERSONATE_TAG = (
    r"""
Write access to **one tournament**, on `{site}` — the same endpoints the Archon
client itself calls. Get the token through Login with Archon with
`&tournament=<uid>`, and send it as an ordinary bearer token.

Every path below is on `{site}`, and a daemon token reaches none of them. The
reverse does not hold: the Public API accepts any member's token, whatever scope
it carries.

## What the grant reaches

An allowlist — anything not listed on this page is refused, including routes
Archon grows later. Beyond the endpoints below the token reaches `/oauth/token`
and `/oauth/revoke`, for its own refresh and revocation. Not `/oauth/userinfo`,
which wants `profile:read` and this scope does not imply it; not consent or
client management, which refuse third-party tokens outright.

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

**The command set is the engine's, and moves with it.** The types above are the
spine of every event; the rest — seating, tosses, overrides, raffles, archival
results — is not frozen here as a contract.
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

_IMPERSONATE_ROUTES: list[tuple[str, str, str, str, str, str]] = [
    (
        "post",
        f"{_EVENT}/action",
        "Run the event",
        "200",
        "The updated tournament.",
        "Every state change of a tournament — registration, check-in, rounds, scores,"
        " finals — is one `type` sent here. See the section intro for the sequence.",
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

# Hand-written: the app's Pydantic models are on the far side of the isolation
# line. `check_impersonate_coverage.py` pairs each with the model it names.
_IMPERSONATE_SCHEMAS: dict[str, dict] = {
    "TournamentActionRequest": {
        "type": "object",
        "required": ["type"],
        "description": (
            "One tournament event. `type` selects it; every other field belongs to"
            " some subset of the types and is omitted otherwise."
        ),
        "properties": {
            "type": {**_STR, "description": "The event, e.g. `StartRound`."},
            "user_uid": {**_STR, "description": "Register, AddPlayer, RemovePlayer."},
            "player_uid": {**_STR, "description": "CheckIn and the seat actions."},
            "display_name": {**_STR, "maxLength": 32, "description": "Display only."},
            "round": {**_INT, "description": "Zero-based index into `rounds`."},
            "table": {**_INT, "description": "Zero-based index within the round."},
            "table1": _INT,
            "seat1": _INT,
            "table2": _INT,
            "seat2": _INT,
            "seat": _INT,
            "scores": {
                "type": "array",
                "description": "SetScore: one entry per seat at the table.",
                "items": {
                    "type": "object",
                    "properties": {"player_uid": _STR, "vp": {"type": "number"}},
                },
            },
            "comment": {**_STR, "description": "Override."},
            "toss": {**_INT, "description": "SetToss."},
            "status": {**_STR, "description": "SetPaymentStatus."},
            "non_competing": _BOOL,
            "waitlisted": _BOOL,
            "seating": {
                "type": "array",
                "description": "AlterSeating: player uids, one array per table.",
                "items": {"type": "array", "items": _STR},
            },
            "player_uids": {
                "type": "array",
                "items": _STR,
                "description": "SelfOrganizeRound: the chosen pod.",
            },
            "config": {"type": "object", "description": "UpdateConfig: partial."},
            "deck": {"type": "object", "description": "UpsertDeck."},
            "multideck": _BOOL,
            "label": _STR,
            "pool": _STR,
            "exclude_drawn": _BOOL,
            "count": _INT,
            "seed": _INT,
            "winner": {**_STR, "description": "SetArchivalResults; empty clears."},
            "players": {"type": "array", "items": _STR},
            "reported_player_count": _INT,
        },
    },
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

# Which body each endpoint takes. Endpoints absent from this map take none.
_IMPERSONATE_BODIES: dict[str, str] = {
    f"{_EVENT}/action": "TournamentActionRequest",
    f"{_EVENT}/announce": "AnnounceRequest",
    f"{_EVENT}/bulk-register": "BulkRegisterRequest",
    f"{_EVENT}/call-judge": "JudgeCallRequest",
    f"{_EVENT}/timer/add-time": "AddTimeRequest",
    "/sanctions/": "CreateSanctionRequest",
}


def _impersonate_paths() -> dict:
    paths: dict = {}
    for method, path, summary, code, responds, description in _IMPERSONATE_ROUTES:
        operation = {
            "tags": ["Impersonate Access"],
            "summary": summary,
            "description": description,
            "servers": [{"url": SITE_URL}],
            "responses": {code: {"description": responds}},
        }
        schema = _IMPERSONATE_BODIES.get(path)
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
        components.setdefault("schemas", {}).update(COMPONENTS | _IMPERSONATE_SCHEMAS)
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
            {"name": "Impersonate Access", "description": IMPERSONATE_TAG},
        ]
        schema["x-tagGroups"] = [
            {"name": "Public API", "tags": ["Public API"]},
            {"name": "Impersonate Access", "tags": ["Impersonate Access"]},
        ]
        # After the pruning loop above: these carry no `content` for it to prune.
        for path, operations in _impersonate_paths().items():
            schema["paths"].setdefault(path, {}).update(operations)
        app.openapi_schema = schema
    return app.openapi_schema


app.openapi = _openapi


@app.get("/docs", include_in_schema=False)
async def docs():
    return get_scalar_api_reference(openapi_url=app.openapi_url, title=app.title)
