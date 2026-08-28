import os
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
Read-only access to Archon's organizational data: tournaments, leagues, published
decks, member ratings and community links.

Members are published by **VEKN ID, never by name**. No name, contact, city or
avatar is served here, and sanctions are never served. Card data belongs to
[krcg](https://v4.api.krcg.org/docs), not to us.

A single object comes back as JSON. A collection comes back as **JSON Lines**:
one object per line, opened by a `header` line and closed by an `eof` line.

```
{"type":"header","generated_at":"2026-08-22T15:04:05.123456"}
{"type":"tournament","data":{ … }}
{"type":"eof","count":1}
```

## Reading a list

A list endpoint streams, and its response is not a JSON document: it will not
parse as one. Read it line by line and decode each line on its own. Most clients
have this built in and most of them do not use it by default, which for
`/v1/tournaments` means holding tens of megabytes in memory for nothing. Ask for
the streaming variant: `iter_lines()` on a `stream=True` request in Python's
requests or httpx, the response body as an async iterator in Node,
`curl --no-buffer`.

Three consequences worth knowing:

* **There is no pagination.** Read as far as you want, then close the
  connection. For the ten most recently created tournaments, read ten lines and
  hang up. Nothing is lost and nothing needs resuming.
* **Check for the `eof` line before you trust what came before it.** A response
  cut short mid-flight looks exactly like a short one until the trailer is
  missing, and by then you have already written rows.
* **The server reads in blocks of 250 rows**, holding no database connection
  between them, which is why a slow reader costs nothing. You never see those
  boundaries: they are not chunks, not packets, and not something to align on.

## Ordering and freshness

Lists arrive **newest first**, ordered by `uid`. Uids are UUIDv7, so they sort by
the moment a record was created, which is not the same as when the event
happened: a decade-old tournament imported last week sorts as new. Select by
event date with `start_after` and `start_before` instead.

A record's `uid` never changes, so a record never moves while you are reading.
It also means **there is no way to ask what changed since when**. That is
deliberate rather than missing: deleted records are not served, so anyone
diffing by date would accumulate rows that no longer exist. Read what you need
when you need it, or take `/v1/export` for the whole corpus in one gzipped pass.

## Getting a token

Every request needs `Authorization: Bearer <token>`; there is no anonymous read.
Two kinds of token are accepted here, and answered identically. **Your own
app's token** is the ordinary one: it names your application and nobody else.
**A member's token**, granted through Login with Archon below, is accepted at
any scope; it unlocks no extra data here, and exists so an app that already
signs members in need not hold a second identity.

### Your own app's token

You need an Archon account with your VEKN membership, plus the DEV role, which an
IC grants. With it, open Developer in [your profile]({site}/profile), register a
client, tick `api:read` and keep the secret: it is shown once. A client that only
needs `api:read` has no redirect URI to declare.

Exchange the secret for a token that lasts an hour:

```
curl -X POST {api}/oauth/token \
  -d grant_type=client_credentials -d client_id=... -d client_secret=...
```

Form-encoded as RFC 6749 specifies, or a JSON body with the same keys, whichever
your client prefers. There is no refresh token: mint another when it expires.
Send it as `Authorization: Bearer <token>` on every request.

## Login with Archon

Sign members in with their Archon account, and — if you run events for them —
act on their behalf. Authorization code with PKCE, RFC 6749 and RFC 7636, so any
OAuth library will do the work; what follows is the same flow in curl.

**This flow runs against the main site, {site}, not against this host.** The
member's browser has to go there for the consent screen, and the same endpoints
answer there, so a login app types one hostname. `/oauth/token` and
`/oauth/revoke` also answer on {api}, for a daemon that knows no other hostname.
An app that both signs members in and reads this API uses both.

### 1. Register your application

Same Developer section of [your profile]({site}/profile), and the same DEV role.
Tick `profile:read`; tick `user:impersonate` too only if your app runs events for
members. Declare every redirect URI you will send members back to — the match is
exact, so `https://example.com/callback` will not accept a trailing slash — and
keep the secret, which is shown once.

### 2. Build a PKCE challenge

One fresh verifier per authorization, and its SHA-256 digest as the challenge.
`S256` is the only method accepted; `plain` is refused.

```
code_verifier=$(openssl rand -base64 60 | tr -d '\n=+/' | cut -c1-64)
code_challenge=$(printf %s "$code_verifier" | openssl dgst -binary -sha256 \
  | openssl base64 | tr '+/' '-_' | tr -d '=\n')
```

Keep the verifier; you send it in step 5.

### 3. Send the member to the consent screen

```
{site}/consent?response_type=code&client_id=$CLIENT_ID&redirect_uri=https%3A%2F%2Fexample.com%2Fcallback&scope=profile%3Aread&state=$STATE&code_challenge=$CODE_CHALLENGE&code_challenge_method=S256
```

Navigate to `/consent`, the page on the site — not to `/oauth/authorize`
underneath it, which is first-party only and answers your app 403.

`state` is yours and comes back untouched; check it on the callback. A member who
is not signed in is sent to login and returns here afterwards. A member who has
already approved these scopes never sees the prompt: they bounce straight back to
your redirect URI with a code.

For `user:impersonate`, add `&tournament=<tournament uid>`. The scope is granted
for one named event, the consent screen names it to the member, and a request
carrying the scope without an event is refused.

### 4. Take the callback

```
https://example.com/callback?code=6mB3...&state=$STATE
```

or, if the member declined:

```
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

**The client secret is required here as well as the PKCE verifier, not instead of
it.** Every client is confidential and PKCE sits on top, so there is no public
variant to ship inside a browser bundle or a mobile binary: keep the secret on
your server and run this exchange there. `redirect_uri` must be the same string
you sent in step 3.

```json
{"access_token":"eyJ...","refresh_token":"eyJ...","token_type":"Bearer",
 "expires_in":3600,"scope":"profile:read"}
```

### 6. Ask who the member is

```
curl {site}/oauth/userinfo -H "Authorization: Bearer $ACCESS_TOKEN"
```

```json
{"sub":"019f6a65-01d4-7214-bcc9-4e46534b9d62","vekn_id":"1000123",
 "roles":["Prince"],"capabilities":["create_tournament","sponsor_member"]}
```

`sub` is the member's uid — the same uid `/v1/users/{uid}` takes on this API, and
the one a tournament's `players`, `standings` and `winner` carry. `capabilities`
is what the member may do anywhere, so your app need not carry its own copy of
the role matrix.

This endpoint needs `profile:read` and 403s without it, a `user:impersonate`-only
token included. An app that wants both asks for both:
`scope=profile%3Aread%20user%3Aimpersonate`.

### 7. Refresh before the hour is out

```
curl -X POST {site}/oauth/token \
  -d grant_type=refresh_token \
  -d client_id=$CLIENT_ID -d client_secret=$CLIENT_SECRET \
  -d refresh_token=eyJ...
```

Access tokens last an hour, refresh tokens 30 days, and **refreshing rotates**:
the answer carries a new refresh token and the one you sent is dead. Store the
new one before you spend the new access token. Presenting a refresh token that
has already been rotated is read as a stolen one and kills the entire lineage —
every token descended from step 5, at once — and the member has to authorize
again.

Refresh re-checks the grant, so it can fail for reasons your code did not cause:
the member withdrew your app from Authorized apps in their profile, or a
`user:impersonate` grant's event has finished. Neither is retryable; start again
at step 3, and for a finished event only for a different one.

### 8. Hand the tokens back

```
curl -X POST {site}/oauth/revoke \
  -d client_id=$CLIENT_ID -d client_secret=$CLIENT_SECRET -d token=eyJ...
```

Either half of the pair kills the other and takes the whole rotation lineage with
it; an expired access token still names its live refresh sibling. The answer is
`200` whatever you send, an unknown or malformed token included, so it is no
oracle for which tokens exist.

Revoking tokens is not withdrawing consent — the member's approval stands, and
your next authorization is a silent one-click. Withdrawing consent is theirs to
do, from Authorized apps in their profile, and it cuts live tokens with it.

### What each scope asks of the member

`profile:read` is identity and only identity: the uid, VEKN ID, roles and
capabilities above. It admits your token to the `/oauth/*` endpoints and to no
other part of the site — not the member's tournaments, not their decks, not
their account — which is what makes Login with Archon a light thing for a member
to approve.

`user:impersonate` is heavy, and bounded so that it can be. Your app acts *as*
the member on **one event**, named up front and shown on the consent screen: it
may register players, run rounds and record results there, exactly as far as that
member could in Archon itself. Every other event and every route outside that
tournament is refused, and so is the infrastructure of owning an event — deleting
it, changing its organizers, publishing it to VEKN, taking it offline, reopening
it once finished — even inside it. The grant ends with the event: once it is Finished, neither a fresh
authorization nor a refresh will work.

`api:read` is the daemon scope and is refused in this flow. It delegates nobody's
authority, so there is nothing for a member to consent to.

## Building a deck archive or a statistics site

Two endpoints carry it. `/v1/decks` streams every published deck, newest first,
and `tournament=<uid>` narrows it to one event. `/v1/export` is the whole corpus
— tournaments, members, decks and leagues — as one gzipped file, which is the
cheapest way to take everything and the cheapest way to take it again later. A
member's community links ride inside their row rather than as lines of their
own; `/v1/community-links` is what serves them one per line.

**A deck is served only once its event is finished**, and then only as far as the
organizer chose when they configured it. That choice is the tournament's own
`decklists_mode`, which you can read off its row: `Winner` publishes the winner's
deck, `Finalists` the finalists' and the winner's, `All` every deck played.
Nothing is served before the event finishes, whatever the mode.

**An organizer who reopens a finished event to correct it withdraws its decks**
until it is finished again. Treat a deck's disappearance as provisional: it is far more often a
correction in progress than a deletion.

**Decks carry no author name** — this API publishes none. Attribution runs
through `user_uid`: hand it to `/v1/users/{uid}` for the member's VEKN ID. The
same uid appears in the tournament's `players`, `standings` and `winner`, so one
lookup attributes a deck and the result it earned together.

## Running an event from your app

Everything above this line is read-only and lives on `{api}`. This section is
neither. With `user:impersonate` your app **writes**, as the member, to **one
tournament**, against the app host `{site}` — the same endpoints the Archon client
itself calls. Ask for the scope exactly as step 3 does, adding `tournament=<uid>`
beside it, and send the access token you get back as an ordinary bearer token.

### What the grant reaches

The boundary is an allowlist, so anything not named here is refused — including
routes Archon grows later. Your token reaches:

- every route under `{site}/api/tournaments/<the granted uid>/`, minus the
  exclusions below;
- `{site}/stream?tournament=<the granted uid>`, the event's live feed;
- `{site}/sanctions/` to file a sanction, and `{site}/sanctions/reference` for the
  categories and levels — a sanction naming any other tournament is refused;
- the `/oauth/*` endpoints, for `userinfo`, refresh and revocation.

It reaches no other event, and nothing outside a tournament at all.

**The infrastructure of owning the event is barred even inside your own**:
`organizers`, `push-vekn`, `go-offline`, `go-online`, `force-takeover`,
`force-unlock` and `sync-offline`, along with `DELETE` on the tournament and the
`ReopenTournament` action. What remains is running the event, and the engine gates
that on the event's state exactly as it does for the member in Archon — your app
can do what they could do, and no more.

### Reading the state

**There is no `GET` for the tournament document.** Two things hand it to you
instead, and between them you never need one.

Every action returns the whole updated tournament as JSON, so the write you just
sent is also your read. And for everything you did not do — a co-organizer seating
a table, a player checking in at the door — open the event's stream:

```
curl -N -H "Authorization: Bearer $ACCESS_TOKEN" \
  "{site}/stream?tournament=$TOURNAMENT_UID"
```

It is Server-Sent Events: `data:` lines carrying one JSON object each, the
tournament among them, restricted to this event and its sanctions. The connection
opens with a catch-up burst of current state and then stays open for live changes,
so a client that reconnects has missed nothing.

### Sending an action

One endpoint runs the event. It takes a `type` and whatever fields that type needs:

```
curl -X POST "{site}/api/tournaments/$TOURNAMENT_UID/action" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"type":"Register","user_uid":"'$MEMBER_UID'"}'
```

A tournament's life runs through the same endpoint — open registration, register
and check players in, start the round, record each table, close it:

```
{"type":"OpenRegistration"}
{"type":"CheckIn","player_uid":"…"}
{"type":"StartRound"}
{"type":"SetScore","round":1,"table":1,"scores":[{"player_uid":"…","vp":2.5}]}
{"type":"FinishRound"}
{"type":"FinishTournament"}
```

Each returns the updated tournament, so you can drive the next step off the answer
rather than guessing at it. An action the event's current state does not allow
comes back refused, which makes the state the authority on what to send next.

**The full command set is the engine's, and it moves with the engine.** The types
above are stable because they are the spine of every event; the rest of the
vocabulary — seating, tosses, overrides, raffles, archival results — is documented
by what Archon itself sends, and is not frozen here as a contract.

### Around the table

The rest of the reachable routes are the ones an organizer's app tends to want.
`POST .../announce` posts a message to everyone watching the event and
`DELETE .../announce/{announcement_id}` takes it back down. `POST .../call-judge`
raises a judge from a table. The timer is four routes — `.../timer/start`,
`.../timer/pause`, `.../timer/add-time` and `.../timer/reset`. `GET .../decks`
returns the decks of the round being played, which is a different thing from the
published archive above: it serves the current round to someone running the event,
where `/v1/decks` serves finished events to everyone.

For getting a crowd in, `POST .../bulk-register` takes a roster in one call,
`POST .../qr-checkin` redeems a self-check-in code, and `POST .../archon-import`
ingests a legacy Archon file.
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
        components.setdefault("schemas", {}).update(COMPONENTS)
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
        app.openapi_schema = schema
    return app.openapi_schema


app.openapi = _openapi


@app.get("/docs", include_in_schema=False)
async def docs():
    return get_scalar_api_reference(openapi_url=app.openapi_url, title=app.title)
