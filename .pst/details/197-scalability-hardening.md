# Backend scalability hardening for 300-400 live users (#197)

Investigation of sync/SSE + tournament-event handling for a big live event
(300-400 players using the PWA at once), targeting the ~500MB small-VPS budget.

## Verdict

Steady-state design is **sound** and holds 300-400 live users *if drains stay
healthy*:

- Live SSE connections hold **no DB connection** — just an `asyncio.Queue`. The
  pool (`max_size=20`) is only touched during catch-up/overlay, then released.
  400 idle connections cost a few MB.
- Broadcast frames are built **once per access level** and put into every queue
  **by reference** (Python strings are immutable + shared), so prompt drains are
  cheap regardless of connection count.
- Access projections are **pre-computed at write time** — no per-viewer DB
  filtering at read time.
- The `QueueFull -> mark closed -> evict -> client reconnects + catches up`
  safety valve is correct.

The risk is **transient memory peaks** under exactly big-event conditions
(mass connect at doors-open; congested venue WiFi stalling many phones). Three
of them can exceed 500MB. All fixable surgically — no rearchitecting.

## The peaks (ranked)

### Peak 1 — whole-tournament broadcast x stalled queues  (#198, p2, lead)
`Tournament` embeds everything inline — all `players`, `rounds`
(list[list[Table]] with seating), `standings`, `finals` (`models.py:581`). The
member projection strips only `checkin_code`/`vekn_pushed_at`
(`access_levels.py:177`), so a live 400-player frame is **~250-300KB**. Every
action rebroadcasts the **entire** object (`tournaments.py:974`).

Shared-by-reference => prompt drains are cheap. But `maxsize=100`
(`broadcast.py:23`) lets a stalled queue accumulate **100 x 300KB = 30MB**
before overflow-close. 20-40 stalled clients on bad WiFi = **0.3-1.2GB**.

Fix: coalesce the queue to **latest frame per (type,uid)** — successive whole
snapshots of the same tournament supersede each other, bounding a stalled
viewer to ~1 object (~300KB), a 100x cut, and delivering current state on drain
instead of replaying 100 stale frames. Lower `maxsize` to ~20-30 as insurance.

### Peak 2 — /snapshot read_bytes() per request  (#199, p2)
`get_snapshot` does `read_bytes()` of the whole gzip per request, no caching
(`main.py:594`). Snapshot carries the **entire global VEKN roster**
(`fetch_all_members()`, ~15-30k users) + all tournaments. At doors-open 300-400
clients hit it near-simultaneously -> hundreds x full-file in heap. Comment says
prod intends `X-Accel-Redirect` but it isn't wired. Fix: `FileResponse` /
X-Accel-Redirect (never in app heap), or a module-level bytes cache invalidated
per 15-min regen so concurrent requests share one buffer.

### Peak 3 — forced full-resync streams whole corpus via fetchall  (#200, p2)
`stream_objects_new` does a single `.fetchall()` + one yield (`db.py:405`),
NOT the keyset/batch_size=1000 SYNC.md:32 claims (doc drift). Fine for small
`since` deltas. But forced resync (epoch bump / `resync_after` / `since`>3 days)
sets `effective_since=None` (`main.py:903-917`) and streams the whole corpus
through fetchall **per connection**, up to 20 concurrent (pool cap). Fix:
server-side named cursor with `itersize` (the user's psycopg-streaming
instinct), or bounce force_resync clients to /snapshot (the designed full-sync
path) instead of streaming `since=None` through the app. Same cursor win for
`snapshots.py:74` (lower stakes — 15-min bg task). Realign SYNC.md.

## Secondary tails (CPU / DB, not memory)

### Per-action whole-tournament churn  (#201, p3)
Each action serializes/parses the full object ~5-6x (`tournaments.py:887-963`:
encode-for-engine -> json.loads -> re-encode -> re-decode at :918 -> 3
projections). Heavy event-loop CPU during an 80-table scoring burst -> slows
drains -> feeds Peak 1. Cheap wins: skip the public projection when no public
viewer is connected; drop the redundant encode->decode at :918.

### Post-finish rating recompute N+1  (#202, p3)
`recompute_ratings_for_players` (`ratings.py`) loops `get_user_by_uid` per
player (400 sequential round-trips at finish) and re-runs on **every** action
while finished (`tournaments.py:980` `... or is_finished`). Batch-fetch users
(mirror `get_tournament_wins_for_users`) + gate to result-affecting actions.

## Non-issues (verified, don't touch)

- **Indexes** are appropriate: `idx_objects_type_modified (type, modified_at,
  uid)` covers catch-up ordering; deck/sanction tournament indexes exist.
  Queries are not the bottleneck — materialization volume is.
- **Pool size 20** is correct. Live SSE is connectionless; the 20-cap usefully
  throttles the catch-up thundering herd. Do NOT raise it to "fix" connect
  storms — fix per-connection materialization (Peaks 2/3) instead.
- **Broadcast fan-out** is O(connections) of cheap pure-Python `entitled_level`
  + `put_nowait`; fine at 400.

## Memory picture

- Baseline (400 idle SSE + pool + app): tens of MB. Fine.
- Steady-state scoring with prompt drains: short-lived shared frames, tens of
  MB. Fine, well under 500MB.
- Budget-breaking peaks: (1) stalled queues on bad WiFi, (2) mass /snapshot,
  (3) mass forced-resync. Peaks 1 & 2 are the must-dos.

## Sequencing vs prod

Should land **before** big real events on prod (relates #39 Phase-1 parallel
run, where officials run live events; #35 epic). Peaks surface only at real
300-400 scale, so they won't show on beta — land the two budget-protecting
fixes (#198, #199) before the first large event, #200 before any mid-event
release/epoch bump, polish (#201, #202) as capacity allows.
