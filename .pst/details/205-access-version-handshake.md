# 205 — Access-version SSE handshake + targeted overlay invalidation

Supersedes the timestamp heuristic shipped in #204. Principal-engineer endorsed the
direction; **review the concrete design before implementing** — this is core sync code.

## Why the timestamp approach is fundamentally lossy

Two category errors live in today's `/stream` connect logic (`main.py:896-919`):

1. **Wall-clock vs. data-cursor.** The 3-day stale guard compares `now()` against
   `since` — but `since` is a *data* timestamp (`max(modified_at)`), used as a proxy for
   a *wall-clock* "how long has this client been away" quantity. They diverge on a quiet
   system. #204 patches this with a snapshot `generated_at`, which is correct for
   *staleness* but doesn't touch the *entitlement* half.

2. **`resync_after` can't tell "stale" from "already fixed."** It's a per-user datetime;
   a connect with `since < resync_after` force-resyncs. But after the client reloads the
   *correct* post-change snapshot and reconnects, its cursor is still `< resync_after`
   (the cached snapshot predates the change), so it resyncs again — the loop. #204 only
   *bounds* this to ≤15 min (until the next snapshot regen lands past the change).

The fix for #2 is to stop comparing timestamps and instead ask the precise question:
**"is the client based on the entitlements it currently has?"**

## Core design: per-user access version

The inputs to a user's entitlements are a **closed, finite set**:
- base level (`_viewer_level`): `IC → FULL`, `vekn_id → MEMBER`, else `PUBLIC`
- NC/Prince → full overlay for **same-country** users + tournaments (`country` is an input)
- organizer → full overlay for **their** tournaments (the organizer-tournament set)

Because it's closed, we can maintain a monotonic **`access_version: int`** per user, bumped
at write time whenever any input changes. Replaces `resync_after` entirely:
- `/snapshot` stamps the user's current `access_version` into the snapshot tag.
- Client persists + echoes it on `/stream`.
- Server reads the user's *current* `access_version`; `tag.version != current → resync`.

Wins over the timestamp: no ≤15 min window (a version match settles immediately regardless
of snapshot age), multi-device clean (each device's tag validates independently — no shared
server flag to clear, which `resync_after` couldn't do), and it's exact (no false trips).

**Invariant to preserve:** the tag is a *hint for when to resync only*. The server must keep
serving every object at the JWT-recomputed level. So the tag needs no signing — a lying
client can only over/under-resync *itself*, never escalate access.

## Open design question — version int vs. per-connect fingerprint

| | access_version int | per-connect fingerprint hash |
|---|---|---|
| connect cost | O(1) field read | recompute `hash(level, country, roles, organizer-set)` — needs the organizer query every connect |
| maintenance | **every** entitlement-mutating write path must bump it, incl. the cross-object case (a tournament organizer-edit must bump the *affected user's* version) — miss a path = silent stale entitlement = missed resync | self-maintaining (derived from current truth) |
| failure mode | silent under-resync if a bump is missed | always correct, just costs a query |

Owner leans locality / "a missed path is silent" wary → the hash's self-maintenance is
attractive despite the per-connect query. **Decide this first.** A hybrid is possible:
store the hash as the "version" (bump = recompute-and-store at write time on the closed set),
getting O(1) connect *and* derived-from-truth, at the cost of enumerating the write paths.

## Owner refinement — targeted overlay invalidation (do better than ANY resync)

For organizer/league overlays specifically, a full resync is overkill: promote/demote only
changes the projection of **one** tournament/league for that user. Instead of resync:
- **promote** → push that single tournament/league at FULL projection to just that user
  (upgrade the one object already in their IndexedDB).
- **demote** → push that single object at MEMBER/PUBLIC projection, or a targeted delete,
  so the client drops just that object.

This needs a **live per-user, per-object frame** primitive. Today `broadcast_precomputed`
sends per-*level* frames shared by reference across all connections (`broadcast.py:128`);
this is a new shape: one object, one viewer, that viewer's personal projection. Relates to
the personal overlay (`_overlay_frames`, `main.py:765`) but live/incremental instead of
connect-time. If this primitive exists, organizer changes need neither `resync_after` nor an
`access_version` bump — they're just a targeted push. (Base-level changes — VEKN identity,
IC — still need the version handshake, since those re-project the *whole* corpus.)

## Migration
- Tagless clients (pre-deploy cursors, no version) → treat as mismatch → one forced resync,
  then they carry the tag. Keep #204's `generated_at` guard as the staleness fallback.

## Scope notes
- Tournament-scoped (bot) streams (`tournament=<uid>`, `_scoped_catchup_frames`) replay full
  state every connect and never force-resync — **leave them alone**; no tag needed.
- Land before big live events (relates #197 scalability epic; #200 full-corpus-on-resync).
