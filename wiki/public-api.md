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
| `/v1/users/{uid_or_vekn_id}` | one member, by either identifier |
| `/v1/decks` | stream of published decks; `tournament` |
| `/v1/users` | stream of members, each carrying all four ratings; `country`, `category`, `tournament` |
| `/v1/community-links` | stream, one line per link |
| `/v1/export` | the whole corpus as the generated `api.jsonl.gz` snapshot, rebuilt within 15 minutes of any change |

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
it wants and closes the connection. That is the whole answer to "give me the ten
most recent" — every stream is ordered, so read ten lines and hang up. Handlers
batch
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

**A member is addressable by uid as well as by VEKN id**, and that is
load-bearing rather than a convenience. A tournament's `players`, `standings` and
`winner` carry `user_uid`, so without the uid lookup a consumer that wants to
attribute a single result has to stream all eighteen thousand members and build
its own map. The lookup is what makes the bulk read unnecessary, which is the
only thing that actually discourages it.

`/v1/users` therefore serves the whole membership, and its filters exist so that
the targeted read is always the easy one. `category` narrows to the members
carrying a rating in it, a few percent of the whole; `tournament` narrows to the
roster of one event, so a result set is one call rather than one per player.

Neither needed an index. Ordering by `uid` lets the `(type, uid)` index scan
backwards and drop unrated rows as it goes, where the old rating-ordered endpoint
had to sort the whole table on an unindexed expression once per batch. And
`tournament` runs the cheap direction of the relation: one primary-key read of
the event, then a primary-key read per player it names, about ninety buffers for
a thirteen-player event. The expensive direction, every event a given member
played, would need an index over each tournament's player array, and nothing
asks for it.

**Streams order by `uid` descending, not by `modified_at`**, and the two reasons
compound. A uid is a uuid7, so descending is newest-created first, which is the
order that makes reading the first N lines worth anything. And a uid never
changes, so **a row cannot move while a consumer is reading it**: it is emitted
exactly once, in a position fixed before the read began. Ordering on
`modified_at` gave neither — a row written mid-read jumped the cursor and was
duplicated or skipped depending on the direction.

Creation order is not event order, and the doc says so: a decade-old tournament
imported last week sorts as new. `start_after`/`start_before` are how you select
by when the event happened.

**Only live, visible objects are ever served** — nothing soft-deleted, nothing
unpublished — and there is deliberately **no modified-date filter**. A `since`
parameter advertises incremental diffing, and diffing needs the deletions this
API does not serve, so a consumer would build a copy that silently accumulates
rows that no longer exist. Refusing the filter refuses the trap; ordering on an
immutable key removes the last thing that made the filter look plausible.

This API is not for keeping a copy of the data in step. Third parties are expected
to build something different on top of it, not to reproduce the app: **stream it
all, and stream it all again to refresh** — that is the entire freshness model, and
`/v1/export` makes the whole corpus one gzipped pass. Filters that narrow by a
stable attribute (a tournament's country or dates, a deck's tournament) are fine;
they answer a question rather than resume a sync.

**A stream is still not a snapshot**, but the immutable sort key bounds what can
go wrong: no row is ever duplicated. A row written between two batches is served
in whichever version the batch that reaches it finds, and a row *created* mid-read
sorts above the cursor and is simply not in this read. Holding one transaction
open for the length of a client read is the actual hazard on a four-connection
pool: do not "fix" this with a held transaction.

`start_after`/`start_before` compare ISO-8601 text carrying no offset, so each
tournament is bounded in its own local time and a bare date bounds at midnight.

`/v1/export` is the pre-generated snapshot file rather than a live stream, so a
full read costs one pass and arrives gzipped — the same file the app's own
`/snapshot` serves at its levels.

Two places the response is not the column verbatim, both deliberate:
**`community-links` resolves each link's `country`** to the link's own where it
has one and the member's otherwise, so a consumer never has to know the fallback
rule, and **withholds a link a moderator hid** — the app's own clients
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

**A daemon only ever types one hostname.** `/oauth/token` and
`/oauth/revoke` are the app's endpoints, not the API's, but the API's vhost
proxies them ([deployment](#deployment)) so minting, revoking and reading share
one authority. The minting flow itself is a member account plus the DEV role an
IC grants, then a self-registered client: the reference page states that rather
than telling a reader to ask us.

**A login client types the app's hostname instead**, for the whole
authorization-code flow. Only those two endpoints are proxied here, so
`/oauth/authorize` and `/oauth/userinfo` exist on the app alone — and the
member's browser has to reach the consent screen there in any case, which makes
the app's hostname the one a login client already has. So is everything a
`event:run` token writes: the tournament routes, its scoped stream and
`/sanctions/` are not proxied here at all. An app that signs members in *and*
reads `/v1` legitimately types both.

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

**Every example is a real row**, captured from the corpus and run through
`access_levels` at capture time, because a shape full of nulls answers no
question a consumer actually has (`examples.py`; the league is constructed, there
being none to capture).

**A field documents itself**: the meaning lives on the Struct as a
`msgspec.Meta` description — what a dict's keys are, which standard a code obeys,
what a sentinel like an empty `rank` means — and `schema_components()` carries it
into the reference, so pruning a field takes its documentation with it and the two
cannot drift. `schemas.py` adds only what is true of *this API* rather than of
the stored field — that `banner_path` is relative to the API's base URL, that
`vekn_id` is the only way to address a member here — and **appends** it rather
than replacing the field's own sentence, which is what kept the two from saying
the same thing twice. Those few remain keyed by component and field name, so
**one left behind by a projection that dropped its field is a `KeyError` at
import**, not a stale sentence.

A stream's body is not one JSON document, so its response schema is a string with
a worked example, and the line union lives beside it as a `{Name}Line` component.
**Every route ends up declaring exactly one media type**, which takes a pruning
pass: FastAPI adds an `application/json` 200 of its own and `openapi_extra` merges
beside it rather than replacing it, so a stream would advertise a JSON body it
never returns — and a reader, a generator or Scalar's preview would believe it.
The line shape is spelled out in the page's own introduction as well, because it
is the first thing a consumer needs and the last place they should have to look
for it is a response schema.

The description is a **raw** string, because every shell example ends its lines
with a backslash and a normal string splices those away.

**All three grants are documented, not just the daemon one.** The reference walks
"Login with Archon" end to end — client registration, PKCE, `/consent`, the
callback, `/oauth/token`, `/oauth/userinfo`, refresh rotation, `/oauth/revoke` —
with a runnable example per step, because the audience for the flow is a third
party who has no other source for it. Two things the endpoints do not say
themselves carry their own paragraphs: that the client secret is required
*alongside* the PKCE verifier rather than instead of it — every client here is
confidential, and an RFC-habituated reader expects the public-client variant that
does not exist — and what each delegating scope actually costs the member who
approves it, `profile:read` being identity alone against `event:run`'s
one-event authority ([access](access.md#oauth2-provider)).

A recipe section closes the page, for the deck-archive and statistics apps this
API exists for: `/v1/decks` and `/v1/export`, and the publication contract they
turn on — a deck is served only once its event is Finished, only as far as
`decklists_mode` allows, and a reopen withdraws it, so an absence is a correction
in progress rather than a deletion
([architecture](architecture.md#cards-and-decks)). Attribution runs through
`user_uid`, the api projection carrying no author name.

**The reference is two APIs, split by `x-tagGroups`.** A reader arrives at a
chooser — read-only data on the API host, or writing to one event on the app host
— and the two stand as separate top-level groups, each with its own endpoints
listed. One page carrying only `/v1` operations left the member-token surface as
prose a reader had to already know to look for, which is the failure this
structure answers. `/oauth/userinfo` is listed there too, being the one endpoint a
member's token reaches whether or not it names an event. Mode-specific material lives in each group's tag description,
where Scalar gives it no sub-navigation; only what both modes need — the token
errand, the scope weights — stays in the introduction, whose headings do get it.

**The Member API group documents the app's endpoints, not this API's.**
Each path item carries its own `servers`, so a generated client targets the app
rather than the API, and none of them reuses a `/v1` component: the action answers
with the organizer-level tournament, not the pruned api projection this page
publishes elsewhere. That listing *is* the published boundary, so
`check_event_run_coverage.py` asserts it equals what `_oauth_allows` admits, in
both directions — a new tournament sub-route fails the build until the reference
names it or the allowlist bars it. The engine's full action vocabulary stays
unpublished: the spine of an event is worked through as an example and the rest is
declared to move with the engine, because publishing it would bind the engine's
internal event set to third-party consumers as a contract
([access](access.md#event-access-is-per-event)).

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
| `limit_req` on the six streaming routes | `rate=20r/m burst=10 nodelay` | egress: a whole refresh is five streams and ~7 MB gzipped (tournaments 5.3, users 1.1, decks 0.6, the rest rounding error), so 20r/m is four refreshes a minute, ~28 MB/min or 3.7 Mbit/s sustained from one address. The burst must clear a whole refresh or a legitimate one breaks halfway; ten leaves room for two |
| `limit_conn` per address | 16 | a suspended stream holds one buffered batch (~1.8 MB) and **no** connection, so concurrency queues on the pool rather than exhausting it. Sixteen is ~29 MB and a four-deep queue |
| `limit_req` on everything else under `/v1` and on `/docs` | a separate, far more generous zone | single-row lookups; a client resolving a page of event codes bursts legitimately |
| `limit_req_status`, `limit_conn_status` | 429 | nginx defaults to 503, which reads as "outage, retry" rather than "slow down" |

Three locations are proxied to the **app** rather than the API process:
`/oauth/token` and `/oauth/revoke`, so minting, revoking and reading share a
hostname, and the tournament banner path, so `banner_path` resolves. All three
keep the app's path verbatim; a rewrite here would be a second place to change
when any of them moves.

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

- **Prod rollout** — beta is live and verified; prod repeats the same three
  steps with `api.archon.vekn.net`, port 7007, unit `archon-public-api`: the A
  record, a full (not quick-lane) deploy, then a registered `api:read` client
  exercising a daemon token, the throttle and the app's rejection of that token.
  Trigger: the owner's next prod window.
- **User-level TWD opt-out** — a member asking not to have their name or deck in
  the TWDA. Trigger: a member asks.
- **League standings** — needs engine compute, or promo-stock-style cross-object
  reprojection on tournament save. Trigger: a consumer asks.
- **A static mirror of the bulk export on `static.krcg.org`**. Trigger: the owner
  wants a krcg-ecosystem entry point.
