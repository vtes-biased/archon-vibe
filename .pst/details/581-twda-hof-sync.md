# TWDA sync — rebuilding the historic Hall of Fame

Born from user report gh-7 (a player comparing our Hall of Fame against
`vekn.fr/hall_of_fame.htm`). The report reads as a display bug; it is not. Our
HoF is derived from the vekn.net event corpus, and that corpus holds roughly
half the archive the reference counts.

## The reference is a TWDA entry count

`vekn.fr/hall_of_fame.htm` states its criterion as "win a minimum of five IRL
tournaments (not online), and those tournaments must have had their results
posted on the official V:EKN Player's Forum". In practice that is exactly a
per-player count of TWDA entries — verified 2026-08-10 by counting `player`
strings in `static.krcg.org/data/twda.json`:

| Player | TWDA entries | Reference page |
|---|---|---|
| Marcin Watras | 19 | 19 |
| Tomasz Izydorczyk | 12 | 12 |
| Tomasz Pietkiewicz | 9 | 9 |
| Marcin Ruminski | 1 | absent |

The counts match line for line. So reproducing the reference needs no rule
reverse-engineering: sync the archive and count.

Ruminski is the tell in the other direction — 1 entry upstream, 5+ with us.
That difference is ours, not the corpus's (see *Two independent errors* below).

## Size of the gap

Measured over the whole `twda.json` (4538 entries):

| | count |
|---|---|
| entries total | 4538 |
| with an extractable VEKN event id (what we can match today) | 2211 |
| **dropped by `twda_import.py:133-135`** | **2327** |
| — dated 2000s | 1312 |
| — dated 2010s | 970 |
| — dated 1990s | 42 |
| — dated 2020s | 3 |
| distinct winner name strings | 1575 |
| names with >= 5 entries (i.e. the true HoF size) | 236 |

`_extract_vekn_event_id` returns `None` for anything whose `id` is not numeric
and whose `event_link` lacks `/event/`; the caller `continue`s, so more than
half the archive never enters the lookup. Of the dropped entries 2175 carry no
`event_link` at all, and the rest point at `groups.google.com` (104),
`calendar.yahoo.com` (9), `vekn.fr` (7), `web.archive.org` (5) and others.

Notably 3 dropped entries link to `archon.vekn.net/tournament/<uid>/display.html`
— **our own** tournament uid, written by our auto-PR. Recent entries use a UUID
`id` plus that link, so the current matcher is structurally blind to the events
we ourselves submit. Harmless today (we already hold those tournaments and their
decks), but the new matcher should read that form.

## What a TWDA entry carries

```
id, event, event_link, place, date, tournament_format, players_count,
player, score, name, comments, crypt{...}, library{...}
```

Enough to reconstruct an event: name, date, place, format string ("3R+F"),
player count, winner name, winner score. Missing: any player identity beyond a
display name, and any non-winner.

## Two independent errors, only one is the corpus

**Undercount** — structural, fixed by this ticket: we hold only events with a
vekn.net event id, so pre-API wins are invisible and veterans read low.

**Overcount** — ours, and it survives any corpus change unless addressed:

- `get_tournament_wins_for_users` (`backend/src/db.py:1288`) counts every
  finished non-online, non-house-format tournament with the user as `winner`.
  No player-count gate, no has-a-final gate — unlike ratings, which use the
  engine's `ranking_eligibility` (`backend/src/ratings.py:253`), and unlike our
  own TWDA auto-submission gate of 10+ players.
- `user.wins` is only ever written inside the loop at `ratings.py:315`, whose
  member set comes from pass 1 at `ratings.py:340-355` — and that pass *does*
  filter on `ranking_eligibility`. So the counting rule and the enumeration rule
  disagree: a player whose 5 wins are all in 6-player events gets no `wins`
  array and never appears, while the same player plus one appearance in any 8+
  player event gets all 5 counted and lands in the Hall of Fame. Membership
  turns on an unrelated coincidence.
- Duplicate imported events (one real event entered twice upstream under two
  vekn ids, `#521`) double-count a win. The prod dedup run is still pending and
  is deliberately sequenced post-flip in `#41`.

Once HoF membership means "TWDA-recorded wins", the gate question dissolves —
a win counts iff the archive holds it. Keep the online exclusion (`#424`)
regardless: `ranking_eligibility` does not exclude online events, since online
is a rating *category*, not an eligibility failure.

## Winner identity — the hard part

TWDA gives a name string (1575 distinct) and no VEKN id. Options, worst to best:

1. **Silent name matching.** Rejected. Homonyms, accents, transliterations and
   name changes would attach real tournament wins to the wrong member records,
   and the pollution is not cleanly unwindable once ratings and HoF read from it.
2. **Match, but hold unresolved names in a review queue.** Exact/normalised
   matches auto-attach; everything ambiguous waits for a human decision. Keeps
   the archive complete while never guessing an identity.
3. **VEKN supplies a name -> id mapping** as part of the decommission handover.
   Best if available; ask before building option 2's queue at full size.

A reconstructed tournament with an unresolved winner is still worth storing —
the event exists, the deck exists, and only the member link is pending. Model
the winner name as data, not as a dangling `winner` uid.

## Sequencing

Child of `#579` (decommission the old VEKN API). This sync is the piece that has
to outlive `vekn_tournament_sync.py`: once vekn.net stops being an upstream, the
TWDA is the only external record of historic wins, and archon becomes the system
of record for everything after.

Interacts with `#580` (reconcile against the vekn.net API record before it goes
away) — that reconciliation should run first, while the API is still reachable.

## Deliverables

1. TWDA sync task, parallel to the VEKN sync, keyed on `external_ids['twda']`.
2. Tournament reconstruction for unmatched entries; winner name captured even
   when unresolved.
3. HoF derived from TWDA-recorded wins; retire the split gate described above.
4. TWDA PR tracking beyond per-tournament `twda_status` — what the archive holds
   vs what we pushed.
5. `/users/[uid]`: the player's win list and deck list. Both are offline-first
   IndexedDB reads — the decks store already has a `by-user` index
   (`frontend/src/lib/db.ts:242`), and `user.wins` is already tournament uids.
   Label it "Decks", never "all their TWDA decks", until coverage is complete.

## Open question for the owner

`wins` sits in `_USER_MEMBER_FIELDS` (`backend/src/access_levels.py:83`), so our
Hall of Fame needs a login while `vekn.fr`'s is public. Acceptable today; worth a
deliberate decision once ours is the only Hall of Fame left.
