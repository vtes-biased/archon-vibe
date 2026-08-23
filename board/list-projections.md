# List projections

Doc-impact: `wiki/dogmas.md`, `wiki/sync.md`, `wiki/hazards.md`.

## The defect

`getFilteredTournaments` and `getAgendaTournaments` in `frontend/src/lib/db.ts` call
`db.getAll('tournaments')` — the whole corpus — then filter and `.slice(0, 50)`. The
country and format filters go through `getAllFromIndex` and are cheap; every other
path pays the full scan. `frontend/src/routes/tournaments/+page.svelte` re-runs that
from an `$effect` on every change of search, state, country, format, online toggle,
view mode, page and auth, with no in-flight guard.

Measured on the production corpus (9,563 tournaments, 18,997 members, 7,948 decks,
4,149 cards):

| | JSON | heap after `getAll` | read |
|---|---|---|---|
| tournaments | 64.6 MB | ~60.5 MB | 1299 ms |
| users | 18.7 MB | ~14.0 MB | 331 ms |
| decks | 6.8 MB | ~15.4 MB | 201 ms |
| cards | 1.7 MB | ~2.3 MB | 64 ms |

Ten sequential full reads settle at ~85 MB — GC keeps up. Six overlapping reads, the
synthetic equivalent of a burst of filter flicks inside one 1.3 s read: **384.6 MB
used, 401.3 MB total**, still 196 MB three seconds later. On-disk IndexedDB is only 62 MB, so the
resident cost is entirely the app copying its own corpus into the heap.

## The shape

| store | full | list-view projection | ratio |
|---|---|---|---|
| tournaments | 64.56 MB | 2.37 MB | 27.2× |
| users | 18.74 MB | 2.22 MB | 8.4× |
| leagues | 0.01 MB | hold whole | — |

Both projections resident as Maps: 22.26 MB used / 24.59 MB total for the page.

A tournament carries 54 fields against the ~11 a list row reads; `players` alone is
40% of its bytes (`rounds` only 4%), so dropping the roster is most of the win.

The agenda view's "am I in this event?" must not put the roster back — carrying
`player_uids` re-adds ~3.6 KB per large event. Keep a separate `Set` of the
tournaments the signed-in member plays in or organizes: 24 entries for a real
member, rebuilt on user switch.

## Where the hooks go

Not in the sync manager. `saveTournament` has nine callers outside `db.ts` —
`tournament-actions.ts:114,249`, `api.ts:491`, `sanction-actions.ts:100`,
`stores/offline.svelte.ts:182`, `QrCheckinScanner.svelte:42`,
`tournaments/[uid]/+page.svelte:345,611`, `tournaments/new/+page.svelte:125`. SSE is
one writer among many, and a projection maintained off the stream goes stale on every
optimistic local mutation — then "server always wins" overwrites the row and hides it.

The hooks belong inside the store's own `save`/`saveBatch`/`delete`/`clear` in
`db.ts`, the choke point every writer already passes through. `patchUserIndex` and
`dropFromUserIndex` already sit exactly there (`db.ts:257, 266, 272, 384`); this
generalizes a pattern the codebase has already proven.

## The dogma

`wiki/dogmas.md` says every UI read comes from IndexedDB. A module-level projection
is not IndexedDB. The intent holds — no network, works at a venue, the data still
originates in IDB — but the letter does not, and `getUserIndex` already stretches it
silently today. The amendment is part of this work: reads come from IndexedDB
directly or through a projection maintained over it, never from the network.

## Boot cost

One full pass per store, ~1.3 s and a ~60 MB transient, once per tab instead of per
interaction. Free if built during snapshot ingest, where the objects already stream past.

## Not the cause

No leaked listeners, intervals or EventSource handles; sequential churn collects
cleanly. The WASM engine plateaus at 16.4 MB of linear memory after its first deck
validation and stays flat — see the deck-catalog line for that.
