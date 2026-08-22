# Public API

A read-only HTTP API over Archon's organizational data, for third parties. It is
a **separate FastAPI app in the same wheel**
(`backend/src/public_api/`, `uvicorn backend.src.public_api.main:app`), running as
its own process on its own subdomain, serving the `api` projection
([sync](sync.md#access-levels)) and nothing else.

It publishes **VEKN IDs, never names** — the projection carries no member name,
contact, city or avatar, a player without a VEKN ID has no row at all, and
sanctions never appear. That is a property of the column, not a filter this app
applies ([dogmas](dogmas.md#product)). Card data stays krcg's.

## Endpoints

Every route is `GET` under `/v1`. **A single object comes back as JSON; a
collection streams JSON Lines** (`application/x-ndjson`) — there is no other
shape, so no route needs a judgment call about which it is. Every body is the
stored `api` column verbatim: rows are never deserialized, so a projection change
reaches consumers with no code change here.

| Route | Returns |
|---|---|
| `/v1/tournaments` | stream; filters `country`, `format`, `state`, `start_after`, `start_before` |
| `/v1/tournaments/{code_or_uid}` | one tournament, by short event code (case-insensitive) or uid |
| `/v1/leagues` | stream |
| `/v1/leagues/{uid}` | one league |
| `/v1/users/{vekn_id}` | one member |
| `/v1/decks` | stream of published decks; `tournament` |
| `/v1/rankings` | stream of rated members, highest total first; `category`, `country` |
| `/v1/community-links` | stream, one line per link |
| `/v1/export` | the whole corpus as the generated `api.jsonl.gz` snapshot |

## The stream

```
{"type":"header","generated_at":"2026-08-22T15:04:05.123456"}
{"type":"tournament","data":{ … }}
{"type":"eof","count":1}
```

**This is the app's own wire format**, not a second one: the line kinds are
`/snapshot`'s — `header`, one per object type, `eof` — and `/v1/export` *is* that
file, at the api level. Two differences, both deliberate. `/snapshot`'s header
carries the snapshot format `version` a PWA client refuses a file on; here the
`/v1` prefix is the version, so a live header carries only `generated_at`. And an
[SSE](sync.md#the-sse-endpoint) frame carries a per-frame `ts` because a live
connection advances a cursor on every event, and a stream here has no cursor to
advance at all.

**No pagination** ([dogmas](dogmas.md#data-and-sync)): a consumer reads as far as
it wants and closes the connection. That is the whole answer to "give me the top
ten" — `/v1/rankings` is ordered, so read ten lines and hang up. Handlers batch
internally on a keyset and release the pooled connection between batches, so a
slow reader never pins one of four; that keyset never reaches the client. Each
batch query is `asyncio.shield`ed, because a reader hanging up mid-stream — the
documented way to take a top-N — otherwise cancels a query in flight and the pool
discards a connection it cannot roll back.

**A batch is 250 rows, sized by weight rather than count.** A tournament row
averages ~7 KB, so the batch is what a concurrent reader costs in memory while it
is suspended at a `yield` — under 2 MB each, against a box sized for the app
([dev](dev.md#deployment)). A slow or throttled reader is therefore cheap: it
holds one batch and no connection.

`generated_at` on the **header** is when the read started, and the **`eof`**
trailer is load-bearing: a chunked response that dies mid-flight is
indistinguishable from a short one until the trailer is missing, and the consumer
has written rows by then.

**Only live, visible objects are ever served** — nothing soft-deleted, nothing
unpublished — and there is deliberately **no modified-date filter**. The two go
together: a `since` parameter advertises incremental diffing, and diffing needs the
deletions this API does not serve, so a consumer would build a copy that silently
accumulates rows that no longer exist. Refusing the filter refuses the trap.

This API is not for keeping a copy of the data in step. Third parties are expected
to build something different on top of it, not to reproduce the app: **stream it
all, and stream it all again to refresh** — that is the entire freshness model, and
`/v1/export` makes the whole corpus one gzipped pass. Filters that narrow by a
stable attribute (a tournament's country or dates, a deck's tournament) are fine;
they answer a question rather than resume a sync.

**A stream is not a snapshot.** Releasing the connection between batches means a
row modified mid-stream can arrive twice, or be missed by this read and picked up
by the next one. Nothing here promises otherwise, and the next full read settles
it. Holding one transaction open for the length of a client read is the actual
hazard on a four-connection pool: do not "fix" this with a held transaction.

`start_after`/`start_before` compare ISO-8601 wall-clock text, so a bare date
bounds at its midnight.

`/v1/export` is the pre-generated snapshot file rather than a live stream, so a
full read costs one pass and arrives gzipped — the same file the app's own
`/snapshot` serves at its levels.

Two places the response is not the column verbatim, both deliberate:
**`community-links` withholds a link a moderator hid** — the app's own clients
filter those client-side and a third party has no way to know it should — and
lookups **match on the indexed `"full"` expressions** (event code, VEKN id, a
deck's tournament) because that is where the indexes are. Only `"api"` is ever
returned.

## Auth

**Bearer token required; there is no anonymous read.** Today the app accepts a
user's `oauth_access` token, checking the `oauth_tokens` row for its `jti` so a
revoked token dies here too — with its own SQL, since the isolation lint forbids
the `db_oauth` import, so the storage shape is now asserted in two places
([hazards](hazards.md#two-implementations-of-one-gate)). The `client_credentials`
daemon grant will be accepted beside it ([access](access.md#oauth2-provider)).

`/docs` and `/openapi.json` are open. The owner's "no anonymous" decision was
about the data; a reference page nobody can read before registering is a barrier
to the consumers the API exists for.

## Documentation

`/docs` is a [Scalar](https://scalar.com) reference over the app's own OpenAPI
document. Pass-through handlers return a raw `Response`, so FastAPI derives no
response schema of its own: each route names its schema in `openapi_extra`, and
`schemas.py` builds the components with `msgspec.json.schema_components()` over
the **real Structs**, pruned by the very field sets `access_levels` projects with
(`USER_API_FIELDS`, `TOURNAMENT_API_EXCLUDE`, …). There is no second model of the
payload. Pruning a field can orphan the struct it referenced, so the components
are reduced to what is reachable from the roots — publishing the schema of a
payload the API never emits is a promise it does not keep.

A stream's body is not one JSON document, so its response schema is a string with
a worked example, and the line union lives beside it as a `{Name}Line` component.
Scalar's response preview defaults its media-type selector to `application/json`
and so shows `null` for a stream until the reader switches it to
`application/x-ndjson` — which is why the line shape is also spelled out in the
page's own introduction.

`test_public_api.py` holds both halves: a maximal object of each type is projected
through `compute_api` and its key set must equal the documented properties, and
the app itself must answer `405` to every write and `401` to every `/v1` read
without a token.

## Isolation

The app never calls the API, and the API never runs the app. Three layers:

1. **Structural** — its own subdomain, its own process, its own small pool
   (`PUBLIC_API_DB_POOL_MAX_SIZE`, default 4) sized so it cannot starve the app's,
   under a `statement_timeout` of its own so a query nobody waits for cannot hold
   a slot of four.
   The frontend has no environment variable pointing at it.
2. **`scripts/check_public_api_isolation.py`**, wired into `just lint`,
   `just lint-check` **and** `ci.yml` — nothing under `frontend/` may name the API,
   nothing under `backend/src/` outside the package may import it, and the package
   may import only `models`, `access_levels`, `jwt_config` and `snapshots` from the
   app. `..db` is excluded on purpose: its pool is a global the app's `init_db()`
   fills, so reaching for it here would hand third-party reads the app's write
   helpers over a pool nothing in this process opens.
3. **The route-table test** above, so the surface cannot grow a write.

`..models` pulls the PyO3 engine in transitively, and that is accepted: the
documented schemas are derived from the real Structs, and the alternative is a
parallel set of doc-models that drifts. Nothing in the package calls the engine —
that is what the lint holds.

## Running it

```bash
just dev-api    # :8001, against the dev database; just dev-stop stops it too
```

`/v1/export` serves the `api.jsonl.gz` the app's snapshot generator writes, so the
API process must see the same `SNAPSHOT_DIR`.

## Deferred

- **User-level TWD opt-out** — a member asking not to have their name or deck in
  the TWDA. Trigger: a member asks.
- **League standings** — needs engine compute, or promo-stock-style cross-object
  reprojection on tournament save. Trigger: a consumer asks.
- **A static mirror of the bulk export on `static.krcg.org`**. Trigger: the owner
  wants a krcg-ecosystem entry point.
- **`POST /oauth/revoke`** (RFC 7009, removed in `3abb708`) — worth restoring for
  third parties. Trigger: the daemon grant lands.
