Doc-impact: `wiki/sync.md` (Snapshots serving paragraph) and `wiki/hazards.md`
(the unbuffered-snapshot trap and the room-sized-cold-connect known limit — both
rewritten with re-measured numbers once the new shape is verified on beta).

## Measured basis (2026-08-26, local M-series + the EC rehearsal's beta data)

- Beta's 735MB backend cold-burst peak decomposes into 349MB post-burst idle
  plus ~385MB transient. The steady Python cost per held stream is ~130KB
  (uvicorn awaits drain at asyncio's 64KB write high-water).
- The byte path allocates every response byte twice: 1.81GB in
  `_iter_file_chunks` (200 clients × 9MB, memray) and 1.78GB again in uvicorn's
  chunked framing `b"".join()` — ~3.6GB of user-space churn per room-sized
  burst, reclaimed lazily (local RSS spiked ~190MB, then decayed to baseline
  while all 200 streams were still held).
- The rest of the transient is kernel TCP send-buffer memory absorbing
  client-speed backpressure, once per proxy hop.
- Not the problem: pre-body work (JWT + user load + access-version) for all 200
  clients completes in 50ms total through a pool of 8; idle heap is
  imports-dominated (~79MB tracked).

## Shape

- Production: the app authenticates, resolves the level, computes
  `X-Access-Version`, then answers with `X-Accel-Redirect` to an internal nginx
  location aliasing the snapshot directory; nginx serves the pre-gzipped file
  via sendfile, page-cache-shared across all clients.
- **nginx drops custom upstream headers on an internal redirect.** The internal
  location must re-emit the load-bearing `X-Access-Version` with
  `add_header ... $upstream_http_x_access_version;` and set explicit
  `Content-Encoding: gzip` plus the media type — the client reads that header
  before `/stream`.
- The app's own streaming path remains for dev (no nginx), for `download=1`
  (the zip re-envelope cannot be accel-served) and as the fallback. It gains
  `Content-Length`, which switches uvicorn to unframed writes and halves the
  copy churn — the size must come from `fstat` on the SAME fd being served,
  never a separate `stat`: the 15-minute regeneration's atomic rename otherwise
  races size against body and uvicorn raises mid-response.
- Gate the accel header on deployment (env set by the ansible `static_site` /
  backend role pairing), so a backend without nginx in front never emits it.
- Out of scope: the public API bulk export (own vhost and unit, `FileResponse`).

## Verification

- The EC rehearsal harness re-verifies on beta:
  `backend/scripts/loadtest_stream.py`, `loadtest_users.py` (mint against beta
  only — never a VEKN_PUSH=true deployment), `loadtest_sample.sh` for the
  per-unit memory series.
- Tried and disqualified during profiling: raising the chunk size to 256KB
  silently truncated 3–6% of responses locally (macOS loopback, unexplained)
  for a ~0.3s CPU win per burst — do not resurrect without an explanation.
