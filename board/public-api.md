# Daemon identity and deploy — context for the remaining board line

Doc-impact: `wiki/access.md`, `wiki/dev.md`, `wiki/public-api.md`.

The API app itself has landed — its surface, its docs, its isolation lint and
its deferred list are [`wiki/public-api.md`](../wiki/public-api.md). What remains
is the identity third parties authenticate with, and putting it online.

`client_credentials` grant on the existing `/oauth/token`, gated on the client's
existing registration (DEV/IC-managed CRUD). Issues a short-lived **stateless**
JWT of new type `oauth_client` carrying `client_id` + `api:read` — deliberately
no `oauth_tokens` row: `OAuthToken.user_uid` is non-optional and the main
middleware unconditionally resolves a User, so the new type never touches either.
Revocation = the client's `active` flag, checked by the API app's own auth
dependency. The main app's middleware never learns the type and rejects daemon
tokens by construction. The API accepts both daemon tokens and user
`oauth_access` tokens; same response either way (user tokens are attribution).

Deploy mirrors the Discord bot's ansible role: own `service.j2`/`env.j2`, own
nginx vhost on `api.<domain>`, wide-open CORS (GET-only public data), added to
`deploy.yml`/`deploy-beta.yml`. Beta first. The unit must see the same
`SNAPSHOT_DIR` as the app, or `/v1/export` has no file to serve, and
`PUBLIC_API_DB_POOL_MAX_SIZE` sizes its pool against the app's. The vhost needs
`gzip_types application/x-ndjson` — the streams are the bulk of the traffic and go
out uncompressed otherwise — and `proxy_buffering off`, or a reader taking the
first N lines waits for the whole corpus, which is the documented top-N idiom.

**Throttling belongs on the vhost, never in the handler.** nginx sees the client;
the app behind a proxy does not, and pacing a stream in Python would hold server
resources longer to achieve what the proxy does for free.

**What is throttled is repetition, not size.** A single full download runs at full
speed — "stream it all again" *is* the refresh model, so slowing one read punishes
exactly the usage the API is designed around. Explicitly **no `limit_rate`**: it
would tax the intended case to defend against the pathological one. What gets
limited is a client pulling the corpus over and over in a tight window.

Measured against the current corpus (29k objects, 71 MB uncompressed, 7.9 MB
gzipped as `/v1/export`): a full `/v1/tournaments` read is 8249 rows, **56 MB
uncompressed and ~5.3 MB gzipped**, and it dominates everything else —
`/v1/rankings` is ~5 MB uncompressed (rated members only), `/v1/decks` 2 MB. One
complete refresh is **five** stream requests — tournaments, leagues, decks,
rankings, community links — and about **6.5 MB gzipped** on the wire.

- **`limit_req` on the stream locations**, its own zone keyed on
  `$binary_remote_addr`: `rate=20r/m burst=10 nodelay` to start. Size it as an
  egress budget rather than a feeling — at 6.5 MB a refresh, 20r/m is four
  refreshes a minute, ~26 MB/min or 3.4 Mbit/s sustained from one address, which
  is a real ceiling against a hot loop and invisible to anyone using the API as
  intended. This is the directive NAT punishes hardest, so err high: everyone
  behind one address shares the budget. The burst must clear a whole refresh —
  five requests — or a legitimate refresh breaks halfway through; ten leaves room
  for two, or for a coincidence behind a shared address.
- **`limit_conn` per address, 16.** Rate limiting counts requests, not the ones
  still running, so this is the only stop on a runaway fan-out. Keep it generous:
  an address is a *place*, not a client — a club, an office, a university or a
  carrier NAT is one address for everybody behind it, and a tight cap breaks
  unrelated consumers for each other. It is affordable because a stream holds a DB
  connection only *during* a batch query, never while suspended waiting on the
  reader: concurrent streams queue on the four-connection pool rather than exhaust
  it, so what concurrency actually costs is a buffered batch each (~1.8 MB for
  tournaments) and slower turns for everyone. Sixteen is ~29 MB and a four-deep
  queue; it also leaves a whole five-stream refresh able to run in parallel.
- **`limit_req` on the direct reads**, a separate and far more generous zone —
  those are single-row lookups and a client resolving a page of event codes will
  burst them legitimately.

Set `limit_req_status 429` and `limit_conn_status 429`; nginx defaults to 503,
which tells a third-party client "outage, retry" rather than "slow down".

Per-address is the wrong unit, and knowingly so: behind NAT, several clients are
throttled as one, and one client on several addresses is not throttled at all. The
daemon grant is what makes a better key possible — `client_id` is in the token —
but that is token-aware work in the app, not nginx config. Generous limits are the
mitigation until a real consumer proves it needs more; do not build per-client
throttling pre-emptively.

Owner decisions (intake 2026-08-22) that still bind: auth required (no anonymous),
Archon-native rather than under the krcg umbrella — krcg stays the card-data
authority, Archon is the system of record for organizational data.
