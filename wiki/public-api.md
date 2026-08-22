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

**Bearer token required; there is no anonymous read.** Two token types are
accepted and answered identically. A third party's **daemon token** — the
`client_credentials` grant's `oauth_client` JWT
([access](access.md#the-daemon-grant)) — is the intended one: it carries a
`client_id` and `api:read`, has no row anywhere, and is checked against the
client's `active` flag, which is the whole of its revocation. A **user's
`oauth_access` token** is accepted beside it at any scope, checked against its
`oauth_tokens` row so a revoked token dies here too; it grants nothing extra, and
exists so a user-facing client need not mint a second identity.

Both checks run on this app's own SQL, since the isolation lint forbids the
`db_oauth` import — so `oauth_tokens` *and* `oauth_clients` now have their storage
shape asserted in two places
([hazards](hazards.md#two-implementations-of-one-gate)).

The token endpoint is **not on this host**: `/oauth/token` belongs to the app, and
the reference page says so, rendering the worked `curl` against `SITE_URL_BASE`.

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
**Every route ends up declaring exactly one media type**, which takes a pruning
pass: FastAPI adds an `application/json` 200 of its own and `openapi_extra` merges
beside it rather than replacing it, so a stream would advertise a JSON body it
never returns — and a reader, a generator or Scalar's preview would believe it.
The line shape is spelled out in the page's own introduction as well, because it
is the first thing a consumer needs and the last place they should have to look
for it is a response schema.

`test_public_api.py` holds both halves: a maximal object of each type is projected
through `compute_api` and its key set must equal the documented properties, and
the app itself must answer `405` to every write and `401` to every `/v1` read
without a token.

## Deployment

A second systemd unit off the **backend's own wheel and venv** — nothing is
installed for it — on its own vhost at `api.<domain>`, ansible role `public_api`.
The unit is `PartOf` the backend's, so the deploy that restarts the app for a new
wheel restarts this process too; without that it would serve yesterday's code
after a quick-lane deploy, and the role is untagged precisely because it needs no
lane of its own. Its environment is derived from the app's in the inventory rather
than repeated: one `JWT_SECRET` (or no token it is handed ever verifies), one
`DATABASE_URL`, one `SNAPSHOT_DIR` (or `/v1/export` has no file).

**Throttling lives on the vhost, never in a handler.** nginx sees the client and
the app behind a proxy does not, and pacing a stream in Python would hold server
resources longer to achieve what the proxy does for free.

**What is throttled is repetition, not size.** One full corpus read runs at full
speed — "stream it all again" *is* the refresh model, so slowing a single read
punishes exactly the usage this API is designed around. There is deliberately no
`limit_rate`. What is limited is pulling the corpus over and over in a tight
window.

| Directive | Value | Sized by |
|---|---|---|
| `limit_req` on the six streaming routes | `rate=20r/m burst=10 nodelay` | egress: a whole refresh is five streams and ~6.5 MB gzipped, so 20r/m is four refreshes a minute, ~3.4 Mbit/s sustained from one address. The burst must clear a whole refresh or a legitimate one breaks halfway; ten leaves room for two |
| `limit_conn` per address | 16 | a suspended stream holds one buffered batch (~1.8 MB) and **no** connection, so concurrency queues on the pool rather than exhausting it. Sixteen is ~29 MB and a four-deep queue |
| `limit_req` on everything else under `/v1` and on `/docs` | a separate, far more generous zone | single-row lookups; a client resolving a page of event codes bursts legitimately |
| `limit_req_status`, `limit_conn_status` | 429 | nginx defaults to 503, which reads as "outage, retry" rather than "slow down" |

The zones are `limit_req_zone`/`limit_conn_zone` and so live in a `conf.d` file —
they are http-context directives and cannot go in the server block. The streams
are matched **exactly**, so a single-object lookup under the same prefix falls
through to the generous zone; **a new streaming route must be added to that list**
or it is throttled as a lookup ([access](access.md#deployment-gate)). The vhost
also sets `gzip_types application/x-ndjson` with `gzip_proxied any` — the streams
are the bulk of the egress and nginx skips proxied responses by default — and
`proxy_buffering off`, or a reader taking the first N lines waits for the whole
corpus, which is the documented top-N idiom.

Per-address is the wrong unit, and knowingly so: behind NAT several clients are
throttled as one, and one client on several addresses is not throttled at all. The
daemon grant makes a better key possible — `client_id` is in the token — but that
is token-aware work in the app, not nginx config. Generous limits are the
mitigation until a real consumer proves it needs more.

The figures are sized against the corpus of the day they were set (8249
tournaments at ~7 KB): substantial growth moves the egress budget, and the rate
should be re-derived rather than inherited.

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
