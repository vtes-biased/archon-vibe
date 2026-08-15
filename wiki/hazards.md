# Hazards

Non-local traps: behavior not evident from reading the code where it lives. These
are what [KISS](dogmas.md#code) means here — read this before touching the
subsystems named.

Hazards that belong to one subsystem are stated where that subsystem is
documented; this page carries the cross-cutting ones and indexes the rest.

## Fields silently dropped

**Hand-rebuilt models drop new fields.** Several call sites reconstruct a `User` or
`Sanction` from an enumerated field list rather than copying. When a model gains a
field, every one of those constructors silently drops it. Prefer
`msgspec.structs.replace` over hand-listing.

Two rebuilds of an *existing* user sit on routine paths and are the ones that bite:

- the member sync's cooptation inference, a nightly job, which already drops
  several fields;
- the detach path's **null-list**, which is the inverse trap — a new
  personal/login field must be **added** to the null-list or it leaks onto the
  abandoned VEKN record for the next claimant.

Every other `User(...)` site is a fresh-uid create with nothing to drop.

**A new backend-only Tournament field must join go-online's server-wins re-pull
block**, or an offline round-trip silently reverts it —
[sync](sync.md#offline-lifecycle).

**A new Tournament field reaches members by default**, because the member
projection is a denylist. An organizer-only secret must be added to it or it leaks
— [sync](sync.md#access-levels).

**A tournament config field must be added to BOTH** the create path's literal
**and** `UpdateConfig`'s field array. Shared validation belongs in the shared
validator.

## Two implementations of one gate

**Online create bypasses the engine.** `POST /tournaments` builds the Tournament
directly in Python with no PyO3 call, so engine create-time gates run **only** on
the offline/WASM create path and on `UpdateConfig`. A ticket saying "enforce X at
create in the engine" silently misses the online path.

**Authorization runs at two layers** — the REST endpoint and the engine — with the
decision single-sourced in Rust. Frontend wrappers are UX-only and fail closed
([access](access.md)).

**A frontend figure the backend also computes must call the same Rust binding with
the same inputs**, and must match the backend's *inclusion filter* as well as its
formula ([dogmas](dogmas.md#product)).

## Renames and references

**Lazy imports hide references.** Function-level imports are used across the
tournament routes, the VEKN push and the archon import to break cycles. Renaming a
symbol can therefore break a caller invisibly — invisible to module load, invisible
to a green test suite, and swallowed by the try/except blocks around post-effects.
**Grep all references including in-function imports.**

**Reassigning object references** — sanctions, decks, cooptation on merge or detach
— **must return `BroadcastData` and broadcast**, or other clients stay stale until
their next snapshot resync. Preserve that in any new merge-like flow.

**`finals.seed_order` holds player user_uids**, easily missed in a per-player UID
remap. The offline remap itself uses a naive JSON string replace, whose
substring-collision risk is mitigated only by UUID v7 length.

**Svelte 5 `$props()`**: props must be listed in the destructure, not merely in the
type annotation.

## Consumers that must move together

**The DQ signal is two signals** — `player.state == "Disqualified"` **or** an active
disqualification sanction. Audit every consumer for the combined signal, and make
any DQ create, lift or delete recompute standings.

**Proxy players are excluded-but-not-zeroed**, the inverse of DQ. Consumers
iterating standings unfiltered — league scoring and the VEKN push among them —
leak proxy scores. Filter on `disqualified || non_competing`.

**The SA −1 VP has three consumers**: preliminary standings, the rating path, and
`SetScore`. All must share the one effective-round resolver or VP, GW and TP
silently diverge. The resolver is Cancelled-aware — a soft-cancelled seat cannot
anchor an SA — and its redirect can land later than the stored round.

**League RTP and global RTP use different bases.** League points use prelim-only
standings VP/GW; the global rating uses totals including finals. Verify the
`points` field, not just the displayed GW/VP.

**Role writes have two out-of-band consumers** — the Discord Linked Roles push,
which fires on any role delta with no periodic reconcile, and the resync
fingerprint, which moves only for IC and NC. A role writer outside the users route
skips both silently ([access](access.md#capabilities)).

**A new full-access branch in `entitled_level` wires only the live path.** A
non-country, non-own-object full grant must also be added to the overlay frames, or
a resync re-delivers the lower projection ([sync](sync.md#access-entitlement)).

**Adding a precomputed access column** is warranted only when projection *content*
must vary by viewer at the same level. Otherwise collapse onto an existing column
and shrink the lower one. The base64 contact obfuscation is a harvester speed-bump,
not access control.

## Concurrency and connections

**Never start a DB-touching task inside a transaction** — the full connection
discipline is [architecture](architecture.md#database-access), and the ambient
connection raises if reached from another task.

**The pool is autocommit**, so a multi-statement write needing consistency must
take an explicit transaction. The object-delete and purge paths are the fixed
exemplar; don't re-fix them.

**Web Push VAPID, backwards from intuition**: the claims dict **is** mutated per
send, so each send needs a fresh one; the Vapid instance is **not**, so it is safe
to share across threads.

**The sync resync branch reconnects with no delay.** Route any resync reconnect
through the backoff, or a persistent cause spins a full-speed clear-and-reconnect
loop ([sync](sync.md#resync)).

## Cards and decks

**The card model has three name fields plus variants**, all four being parser
lookup keys, with distinct roles: printed (display), unique (text export), full
(the image filename is the normalized full name).

**Card sets are display *names*, not codes**, so a prefix test like
`starts_with("V5")` against a set field matches nothing.

**The deck parser's count-strip and prefix match miscount count-less lines** —
card names ending in digits or containing a slash are the failure cases. The fix is
exact-key gating, not a looser regex.

The accent fold has no CI ASCII guard, and the non-NFD fold branch (ł, ø, œ — a
dozen real cards) is untested.

## Rounds and the bot

**Round lifecycle**: `RestoreRound` can re-derive to fully Finished; the finals are
not in `rounds`; the timer is online-only. Check these when reviewing any
round-lifecycle hook.

**The bot's active-table detection tags "finals" on seating truthiness, not
completion**, so consumers that should stop at completion — the timer reminders —
over-trigger. There is no top-level table result to gate on; gate on the pending
predicate instead.

**On the bot's live path the tournament frame precedes participant identity
frames**, so reconcile logic using the name cache for a just-added organizer or
player is one message stale. Catch-up is safe
([sync](sync.md#the-sse-endpoint)).

## Ratings and migration

**The ratings no-change guard converges only if its denormalized inputs are
stable** — the entry's embedded tournament name and its date fallback chain. A
flip-flopping name or a both-null date makes the daily job re-save forever.

**Dropping VEKN-less members is not reference-free.** Measured: dropping the 142
VEKN-less members orphans 9 references — 4 players and 5 seats — across 3 finished
tournaments, because legacy archon never enforced a VEKN id at registration.

**The `vekn_id` unique index spans tombstones**: a soft-deleted user still reserves
its number while `deleted_at`-filtered lookups disagree, so a seed insert can crash
on a reserved number. Reachable on steady-state nightly merges, since an admin
user-delete keeps the `vekn_id`.

## Deploy

**Production nginx proxies only an allowlist of top-level prefixes.** A new route
under an existing prefix is fine; a new top-level segment 404s in production while
passing dev CORS and the test suite ([access](access.md#deployment-gate)).

**A `ClientTimeout` breach raises `asyncio.TimeoutError`, not an
`aiohttp.ClientError`**, so `except aiohttp.ClientError` misses timeouts on every
external-proxy route — feedback, TWDA, web push ([vekn](vekn.md#outage-resilience)).

**`EXPLAIN` the `DECLARE … CURSOR FOR`, not the bare `SELECT`** — a named cursor is
costed with `cursor_tuple_fraction` and can report a different scan than the one
that runs ([sync](sync.md#streaming)).

**A backend-first deploy is safe by design**: an unknown snapshot type is counted
toward the `eof` total and ignored. Do not "fix" that by counting only recognised
types ([sync](sync.md#adding-a-new-object-type)).
