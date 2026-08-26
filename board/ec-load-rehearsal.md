# EC load rehearsal — beta window runbook

Harness is written and validated; what remains is the run against beta, blocked
on remote execution (ssh/ansible to the box is denied in the building session).
Either grant it or run the box-side half below while the driver runs locally.

## Validated locally (2026-08-26)

200 member clients against a prod-scale corpus (18.9k users, 8.3k tournaments,
dev dump) with prod parity `DB_POOL_MAX_SIZE=8`, Mac localhost so times are a
floor, not a forecast:

- cold connect: snapshot TTFB p95 0.43s, full member download 84MB inflated in
  ~7.3s, stream sync_complete p95 0.18s — 0 errors.
- mass cursorless: resync directive p95 0.09s, server closes immediately. A
  fresh client carries no `av`, so it is the access-version-mismatch branch that
  answers, not the cursorless snapshot-redirect guard — same directive, earlier
  branch; attribute the numbers accordingly.
- reconnect burst: sync_complete p95 0.20s — 0 errors.
- pool: active backends capped at exactly 8, sessions delta 7 over the whole
  window (pool warm-up, no churn).
- backend RSS 136MB idle → 206MB peak.
- **finding, fixed**: with the server on the default macOS 256-fd limit, 26/200
  snapshot downloads truncated (`TransferEncodingError`). ~2 sockets per client
  plus one snapshot fd each ≈ 600+ fds at burst; the deployed units set no
  `LimitNOFILE` (systemd default soft cap 1024). Both SSE-serving unit
  templates now set `LimitNOFILE=65536` — reaches beta on its next deploy;
  meanwhile check the live value during the window.

## The window

Box side (frankfurt, `deploy@57.129.110.107`), in order:

1. `systemctl show new-archon-backend nginx -p LimitNOFILE` — nginx holds the
   larger half of the fd budget (it terminates every client connection and
   opens the upstream pair) and its unit is not covered by the template change.
   If the backend's soft cap is 1024, either deploy first (templates now set
   65536) or raise it for the window.
2. Prod parity: add `DB_POOL_MAX_SIZE=8` to
   `/etc/new_archon/new-archon-backend.env`, `systemctl restart
   new-archon-backend`. Revert both after the window.
3. Mint tokens on the box so the JWT secret stays there (adjust venv/env paths):
   `sudo -u new_archon bash -c 'set -a; . /etc/new_archon/new-archon-backend.env;
   set +a; /opt/new_archon/backend/venv/bin/python loadtest_users.py mint
   --count 200 --ttl-minutes 120 --out /tmp/tokens.txt'`
   (scp `backend/scripts/loadtest_users.py` over; it imports `backend.src` from
   the wheel). Fetch `/tmp/tokens.txt` back to the driving machine.
4. Find the postgres unit (`systemctl list-units 'postgresql*'`), then start the
   sampler: `./loadtest_sample.sh new_archon samples.csv 1 new-archon-backend
   nginx <postgres-unit>`.
5. Driver, from the driving machine:
   `python backend/scripts/loadtest_stream.py --base-url
   https://archon.krcg.org --clients 200 --tokens-file tokens.txt --out
   metrics.json`. Cold phase pulls 200 × ~9MB gzip — expect the venue-uplink
   analogue on a home connection; TTFB is the server-health number.
6. After: stop sampler, `cleanup` subcommand of loadtest_users.py (same
   invocation shape as mint), revert step 2.

Join `metrics.json` phase bounds (epoch) against `samples.csv`. Verdicts the
line asks for: active_backends never pinned at max with clients erroring
(exhaustion), total_sessions delta ≈ pool size only (churn), per-unit memory
peaks, response-time aggregates per phase.

## Landing

Numbers and any revealed limit go to `wiki/hazards.md` (known-limit entry with
the number attached) and the measured baseline to `wiki/sync.md#streaming`;
frankfurt is not the prod VPS, so memory figures carry that caveat. Then delete
this file with the line.
