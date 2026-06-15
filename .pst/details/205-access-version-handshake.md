# 205 — Access-version SSE handshake + targeted overlay invalidation

Supersedes the timestamp heuristic shipped in #204. Principal-engineer reviewed the
concrete design below (transcript-level critique folded in). **Design LOCKED — ready to
decompose + implement.** Core sync code: implement in the order in §Decomposition, each
ticket behind its merge gate.

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

## Decision: connect-time entitlement FINGERPRINT (not a stored int, not a hybrid)

The open question (stored `access_version` int vs. per-connect fingerprint vs. hybrid) is
**resolved in favour of a fingerprint computed at connect**. The deciding insight:

> The only entitlement input that needs a DB query is the **organizer-tournament set** —
> and `_overlay_frames` **already runs that exact query on every member-level connect**
> (`main.py:831-856`, `organizers_uids ? viewer.uid`). So computing the fingerprint *from
> that query's result* costs **zero marginal query**, while staying **self-maintaining**
> (derived from current truth — no write paths to enumerate, no silent-missed-bump leak).

This collapses the trade-off: we get the hash's correctness AND O(1)-ish connect, without
the stored-int's "miss a write path = silent stale entitlement" failure mode and without
the hybrid's enumerate-every-write-path burden. Owner's locality/"a missed path is silent"
instinct → self-maintaining wins.

### The fingerprint

```
fp = hash( DATA_SCHEMA_VERSION,                     # global wire-shape lever (was MINIMUM_SYNC_EPOCH)
           base_level,                              # _viewer_level: FULL | MEMBER | PUBLIC
           sorted({IC, NC, PRINCE} ∩ roles),        # overlay-granting roles only
           country if (NC or PRINCE in roles) else None,   # scopes the NC/Prince overlay
           sorted(organizer_tournament_uids) )      # from the overlay query (member only)
# computed BACKEND-ONLY; opaque to the client (stored + echoed, never parsed/recomputed).
```

- **All fields are on the already-resolved `stream_user`** except the org-set, which comes
  from the overlay query that already runs. IC/anon/PUBLIC viewers have an empty org-set
  (no overlay) → fp is a pure field hash, no query.
- **`DATA_SCHEMA_VERSION` folded in** (the global wire-shape lever, replacing the
  `MINIMUM_SYNC_EPOCH` timestamp) so there is exactly ONE resync mechanism: a shape change
  bumps it → every client's stored fp mismatches → one resync. Retire the separate epoch
  compare (`main.py:899-905`). See §What enters the hash for why it stays a dedicated lever
  (not release semver, not the frontend IDB version).
- **Country only participates when NC/Prince** — otherwise a cosmetic country edit by a
  plain member would needlessly trip a resync. (Note: #206 makes an official's country a
  gated, authority-only change; this design makes an official country change correctly
  invalidate via the `country` term — see §Interactions.)
- **Non-overlay roles excluded** (playtester/PT/Judge/...) — they don't branch in
  `_viewer_level` or `access_levels.py`. (This is exactly the #204 narrowing, now structural.)

### What enters the hash — and who computes it

**Backend-only, opaque blob.** The client never computes or parses the fp — it stores the
string and echoes it. This is load-bearing: because the input-set lives entirely
server-side, we can add/remove inputs anytime with **zero client coordination** (the client
just sees "blob changed → resync"). It also keeps the security invariant — a lying client
can only over/under-resync *itself*. Delivered at initial sync (the `X-Access-Version` header
on `/snapshot`, §Transport). The bot/tournament-scoped path needs no tag (replays full state
every connect; deployed in lockstep with the backend).

There are **three** version-like concepts; only two belong in the hash, and they are not the
same thing:

1. **Per-user entitlement** (varies by user) — `base_level`, `{IC,NC,PRINCE}` roles,
   `country`-if-official, org-set. **In the hash.**
2. **Backend wire-shape version** (`DATA_SCHEMA_VERSION`, global, one per deploy) — the
   "the projected JSON shape changed, cached clients must refetch" lever. **In the hash.**
   Its *narrow real job* is a **backend-only** shape change that does NOT bump the frontend
   `DB_VERSION` — e.g. promoting a field from full-only into the **member** projection: the
   frontend already knows the field and needs no IDB migration, but cached member objects
   only receive it on a resync. Bump it on any such wire-shape change (`models.py` field
   rename/remove, an `access_levels.py` projection-policy change, a nested engine-struct
   change).
3. **Frontend IndexedDB version** (`DB_VERSION`, `db.ts:77`, currently 15) — **NOT in the
   hash.** It is client-owned and *self-heals*: bumping it makes the browser's
   `onupgradeneeded` wipe + recreate every store (`db.ts:212-216`) → fresh snapshot on next
   connect. Putting it in the backend hash would require the client to send it (breaking the
   opacity above) and would be redundant with the wipe it already triggers. So any shape
   change that *does* ride a `DB_VERSION` bump needs no backend lever at all — which is why
   `DATA_SCHEMA_VERSION` is a narrow backstop, not the primary mechanism.

**No auto-net (considered + rejected).** We considered deriving `DATA_SCHEMA_VERSION`
automatically by hashing the projection field-sets. It does not work cleanly: there is **no
`full` field-set** — `full` is a pass-through (user = everything minus `calendar_token`,
`access_levels.py:145`; tournament/deck = `dict(d)`; sanction/league = `_identity`), and
*only* public + member have explicit field policy. So a field-set hash is **blind to
full/model shape changes** — exactly the changes most likely to break a full-level
(IC/organizer/NC) client. Hashing the model structs instead would *over*-trigger (a
full-only field change would resync member/public clients whose wire shape didn't change).
The manual lever is *complete* (covers public, member, and full/model); the auto-net was
*incomplete and riskier*. Keep it manual. (Aside: `_USER_FULL_EXTRA`, `access_levels.py:82`,
is **defined but never used** — a one-line dead-code cleanup to do alongside.)

**Why not reuse the release semver `major.minor`?** Tempting (one fewer number), but
deferred: the repo versions are all a static `0.1.0` today (root/`frontend`/`bot`
`pyproject.toml`/`package.json`) with no live versioning discipline and no runtime
`__version__` plumbed into the backend. Adopting "bump minor on shape change" is the *same*
discipline as maintaining `DATA_SCHEMA_VERSION`, just relocated onto a currently-inert number
(plus version plumbing). And full semver `minor` *over-triggers* — every feature release
would resync all online clients even with no shape change (benign outside live events, since
releases freeze during them, but it couples cache-resync to release cadence, which a
dedicated lever avoids). **Revisit post-1.0** once a real, plumbed release version exists; at
that point reusing `major.minor` is reasonable.

### Why the org-set MUST be in the fingerprint (the demote question)

The crux we worked through: *how does a demoted organizer get the stale full data out of
their IndexedDB?* Split by what actually leaks:

- **The tournament object self-heals.** member vs full differs only by `checkin_code` +
  `vekn_pushed_at` (`_TOURNAMENT_MEMBER_EXCLUDE`). Removing an organizer writes the
  tournament row → `modified_at` advances → the `since`-catchup re-sends it at member level
  → `saveTournament` does `db.put` (full *replace*, verified `db.ts:546`) → the two
  full-only fields drop. No action needed.
- **Private decks LEAK.** `compute_deck_member → None` for a non-public deck, so a private
  tournament deck the organizer held at full is **never in the member stream** — the
  catch-up can neither re-send nor evict it. Same shape for any object whose lower
  projection is null (e.g. a plain user dropping out of an NC's same-country view).

Cleanup, by connectivity:

- **Online (connected) demote** → targeted push (§Targeted invalidation) evicts the private
  decks and downgrades the tournament. No resync.
- **Offline (was disconnected) demote** → the targeted push never arrived. The *only* thing
  that purges IDB without a per-user server-side revocation log (which the owner explicitly
  rejected — multi-device wrinkle) is a **resync**. That is why the org-set is in the
  fingerprint: an offline org change → fp mismatch → resync → IDB cleared + refetched clean.

**Accepted trade-off:** the hash can't distinguish org-set *growth* (promote — additive, a
resync is strictly unnecessary) from *shrink* (demote — resync genuinely needed), so an
**offline organizer *promote* also triggers one resync**. This is rare (an organizer is
typically the connected, active user) and the online path — the mid-event "add a
co-organizer" case — gets the smooth targeted push. If offline-promote resyncs are ever
measured as a problem, a later refinement can compare org-*sets* (not the hash) to skip the
additive case. Out of scope for v1.

### Prerequisite: index the organizer lookup

That `organizers_uids ? uid` query is **not index-backed today** (`schema.sql:136-169` has
no GIN on `organizers_uids`); it sequential-scans all non-deleted tournaments per
member reconnect. Cheap now, but it runs on *every reconnect* (not just resync — the
overlay is ungated by `since`), so at #197 scale (mass reconnect on flaky venue WiFi) it
adds up. One-line fix, independently valuable to the existing overlay:

```sql
CREATE INDEX IF NOT EXISTS idx_objects_tournament_organizers
ON objects USING GIN (("full"->'organizers_uids') jsonb_path_ops)
WHERE type = 'tournament';
```

### Why NOT a bloom filter (considered + rejected)

A user-maintained membership digest (bloom/etc.) was considered to *avoid* the org query.
Rejected: (1) it optimizes a query we can't remove — the overlay must fetch the actual
org-tournament rows to push them regardless; (2) wrong structure for a correctness check —
a lossy digest collides, so two different org-sets can hash equal → "match" → **miss a real
change = silent leak**; (3) incremental maintenance reintroduces the very "miss a write
path / cross-object bump" burden the connect-time hash escapes. Plain hash of the sorted
uid list, computed from the query that already runs, is collision-safe and self-maintaining.

### Transport (the snapshot CANNOT carry the fp)

The `/snapshot` is one **per-LEVEL static gzip** shared across all users at that level
(`snapshots.py`); the fingerprint is **per-user** (country/roles/org-set vary among users
sharing a level file), so it cannot live in the snapshot body.

- **Seed:** `/snapshot` sets an **`X-Access-Version` response header** computed per-request
  from the already-resolved viewer (`main.py:581`). The header is per-response, not the
  shared body. The client fetches the snapshot via `fetch()` (`sync.ts` `fetchSnapshot`) and
  *can* read headers, so it has the fp **before** opening `/stream` — no spurious first-load
  resync.
- **Echo:** client persists the fp (IDB `metadata`) and sends it as `/stream?av=<fp>`
  (EventSource can't set headers; query param, same as `since`).
- **Compare:** server recomputes the current fp from the resolved `stream_user` + org query;
  `av != current_fp` (or absent) → resync.
- **Live no-resync refresh:** a targeted push (§below) carries the **new fp** in its frame so
  the client updates its persisted `av` without a resync; otherwise it would mismatch on the
  next reconnect and resync needlessly. (All resync-triggering live changes refetch the
  snapshot → re-seed via the header, so `/stream` itself never needs to emit the fp.)

**Security invariant (unchanged):** the fp is a *resync hint only*. The server always serves
every object at the JWT-recomputed level, so the tag needs no signing — a lying client can
only over/under-resync *itself*, never escalate access.

### Align the resync path with #200/#204

On `av` mismatch, **emit the `resync` line then RETURN** — do not also stream the whole
corpus via `effective_since=None` (the client tears down on `resync`, cancelling that
`fetchall` mid-flight → discarded pooled conn churn). #204 already did this; the fp path
inherits it. Suppress the no-op `resync` line for tournament-scoped (bot) streams.

## Targeted overlay invalidation (owner refinement — the live optimization)

New primitive `broadcast_personal(user_uid, obj_type, uid, ...)`: one object, one viewer,
that viewer's personal projection. Mirrors `broadcast_resync`/`broadcast_judge_call`'s
per-connection loop (`broadcast.py`), NOT the per-*level* shared-frame `broadcast_precomputed`.

Rule, by new entitled level for that user (compute via existing `entitled_level`,
`broadcast.py:62`, then the matching `compute_*` projection):

- **promote** → push the object at its **full** projection (upgrade the one object in IDB).
- **demote, lower projection non-null** (e.g. tournament → member) → push the lower
  projection; `db.put` replaces, full-only fields drop.
- **demote, lower projection NULL** (e.g. a private deck → member is `None`; a plain user →
  public is `None`) → **push a tombstone frame** (`deleted_at` set). The frontend already
  routes `item.deleted_at` to `spec.del` (`sync.ts:335`, and `deleteDeck` actually removes
  it) — so the client evicts just that object. **This null→tombstone branch is the single
  most important correctness rule of the primitive** (it's the private-deck leak fix).
- Every targeted frame also carries the recomputed **fp** so the client updates `av`.

Note: the tombstone is a per-user IDB eviction, not a server-side soft-delete — the object
still exists for everyone else; `broadcast_personal` only reaches the demoted user's
connection(s).

## Entitlement-transition matrix (the full picture)

| transition | ONLINE (connected) | OFFLINE (caught at reconnect) |
|---|---|---|
| base level ↑ (vekn gain→MEMBER, IC gain→FULL) | `broadcast_resync` → resync | fp mismatch (level) → resync |
| base level ↓ (vekn lose, IC lose) | `broadcast_resync` → resync | fp mismatch (level) → resync |
| NC/Prince gain | `broadcast_resync` → resync | fp mismatch (roles) → resync |
| NC/Prince lose | `broadcast_resync` → resync (purge same-country full) | fp mismatch (roles) → resync |
| official country change | `broadcast_resync` → resync | fp mismatch (country) → resync |
| **organizer add** | `broadcast_personal`: tournament+decks @full, carries fp | fp mismatch (org-set) → resync* |
| **organizer remove** | `broadcast_personal`: tournament@member + tombstone private decks, carries fp | fp mismatch (org-set) → resync |

\* offline promote resync is the accepted-trade-off above (additive; hash can't tell grow
from shrink). `broadcast_resync` **stays** as the live nudge for the whole-corpus
re-projection rows — the fingerprint only fires at connect.

## League overlay = NO-OP (drop from scope)

League is `_identity` at public/member/full (`access_levels.py:250/258/266`) — byte-identical
at every level, and `_overlay_frames` never touches it. There is no full-vs-member league
projection to invalidate, so "league overlay invalidation" in the epic is **moot as
written**. Real league-derived entitlement (if a league role ever conferred organizer rights
on the league's *tournaments*) would flow through the *tournament* targeted-push path, not a
league one. Do **not** build a league primitive. (Flag to epic author: drop/restate the
"league overlay" bullet.)

## Migration & rollout

- **Tagless clients** (pre-deploy cursors, no `av`) → mismatch → one forced resync, then they
  carry the fp from the snapshot header. Keep #204's `generated_at` staleness guard as the
  belt-and-suspenders fallback during rollout.
- **`resync_after` stays as backstop** until tagged clients are the floor — only then retire
  the threshold/3-day guard, then drop the column. Sequenced last (see §Decomposition) so an
  early deploy can't strand clients.

## Interactions

- **#204** (shipped): `generated_at` staleness guard + the role-narrowing + emit-resync-and-
  return. This epic absorbs all three structurally; keep `generated_at` as fallback.
- **#206** (open): an official's country change must invalidate. The `country` term in the fp
  handles the offline case; #206's own `broadcast_resync` on country-change handles online.
  When #206 lands, ensure it routes through the same live-nudge as role changes.
- **#200** (open): resync = emit + client refetches `/snapshot` (don't stream `since=None`).
  The fp resync path follows this; coordinate so we don't reintroduce the corpus stream.
- **#197 / #35**: land before big live events. The GIN index (205a) is an immediate #197 win.

## Decomposition (children of #205) + merge-gate ordering

1. **205a — GIN index for organizer lookup.** The one-liner above. Independent; helps the
   *existing* overlay now. *Gate: none — ship anytime.*
2. **205b — `broadcast_personal` primitive + frontend tombstone path.** Add the per-user/
   per-object frame; **null lower projection ⇒ tombstone frame.** Verify `sync.ts` per-store
   delete handling + `db.put` full-replace. *Gate: unit test the private-deck demote →
   tombstone case.* Additive, no protocol change — ship early to de-risk.
3. **205c — fingerprint compute + transport.** Server fp (incl. epoch + org-set from the
   hoisted overlay query); `X-Access-Version` header on `/snapshot`; `?av=` compare on
   `/stream`; resync = emit + return. Frontend persists/echoes `av`. **Keep `resync_after`
   + 3-day guard as backstop.** Update SYNC.md. *Gate: deploy-order — tagless old client
   still works (one resync); tagged client does NOT loop on a quiet system.* Depends 205a.
4. **205d — organizer add/remove → `broadcast_personal`.** Replace `set_user_resync_after`
   + `broadcast_resync` at `tournaments.py:385`; **add the missing organizer-REMOVE path**;
   carry the new fp. *Gate: verify organizer-remove still writes the tournament row (the
   self-heal invariant).* Depends 205b + 205c.
5. **205e — retire `resync_after` threshold + 3-day wall-clock guard** + the
   `set_user_resync_after` callers now covered by fp(offline) + `broadcast_resync`(online)
   (vekn.py, users.py). Update SYNC.md. *Gate: 205c soaked in prod, tagged clients are the
   floor. Only ticket that can strand clients — merge LAST of the behavioural set.*
6. **205f — drop the `resync_after` column** (`models.py:321`, `access_levels.py:92`, schema).
   *Gate: 205e deployed, no readers remain.*

**Order:** 205a, 205b (parallel) → 205c → 205d → [prod soak] → 205e → 205f. Hard rule: no
client-stranding ticket (205e) merges until the fp path has a prod soak proving tagged
clients don't loop.

## Scope notes
- Tournament-scoped (bot) streams (`tournament=<uid>`, `_scoped_catchup_frames`) replay full
  state every connect and never force-resync — **leave them alone**; no `av` tag.
