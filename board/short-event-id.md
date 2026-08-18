> Elaborated context for a line in `BOARD.md`. Deleted with the line.

Doc-impact: `wiki/architecture.md`, `wiki/sync.md`, `wiki/vekn.md`.

# A short event id

## Why now

We already have a short, speakable, externally-quotable event identifier: the
VEKN event id. `12794` names the TWDA file (`decks/12794.txt`), the forum post
and the `vekn.net/event/12794` URL. The decommission retires it, and nothing
replaces it — a `Tournament.uid` is 36 characters and unsayable.

TWDA submission continuity is part of this line rather than a separate ask: the
branch and file names key on the vekn event id and `maybe_submit_twda` skips
outright without one, so the decommission silently ends archive submissions unless
this replaces the key. Whatever key it picks becomes a permanent external record in
a public archive, which is why the two cannot be sequenced apart — a stopgap would
spend the archive's future on uuids.

Evidence that uuids do not survive in external records: of the three TWDA entries
carrying `archon.vekn.net` links, **two point at uuids that resolve to nothing** —
they are *legacy-archon* uids, and the migration did not carry them forward. A
short id we mint and never reuse is what would have survived.

## Ruled out

- **A uuid prefix.** uuid7 is time-ordered — the first 48 bits are a millisecond
  timestamp — and our corpus was largely minted by bulk migration inside one
  window. Measured over 8475 live tournaments: 8-character prefixes yield **336
  distinct values (8139 collisions)**, and 12 characters still collide 2690 times.
  A random *suffix* would be unique but is not human-friendly.
- **Reusing `checkin_code`.** It is `secrets.token_urlsafe(16)`
  (`models.py:500`) and excluded from the member projection. It is a **capability
  token** — publishing it grants check-in. Different lifetime, different secrecy,
  different consumer.
- **A name+date slug.** Not stable: names are editable, and 869 pre-2014 rows are
  named `Imported VTES Event`.
- **A code minted for every event, parallel to the vekn id.** The first shape this
  line took. Owner decision: the code should *be* the external identifier the world
  already cites, so old vekn ids keep resolving after the decommission. 2211 TWDA
  entries carry vekn event links; under a parallel code every one of those numbers
  becomes dead trivia.
- **Serving the tournament page at `/tournaments/{code}`.** uid URLs can never be
  retired — they are in the TWDA, in push notifications, in every link shared to
  date, and they are the only form that works for an event created offline that has
  no code yet. Accepting both would make the route param polymorphic and land that
  on the offline path for no gain over `/t/{code}`.

## Settled shape

**The code is the identifier the outside world already uses, whatever its
provenance.** A precedence, evaluated **once**, when the row's identity settles:

1. `external_ids['vekn']` — every event vekn.net has ever numbered.
2. `external_ids['twda']` — the archive's own key, which is a vekn event id on 14
   of the 1132 reconstructions and a slug (`2010czechecq`) on the other 1118.
   `decks/2010czechecq.txt` is the file the TWDA publishes for that event.
3. A minted 6-character Crockford base32 code, never all digits.

**Never rewritten once set.** An event that mints its own code and *later* gains a
vekn id keeps the minted one — rewriting would move a published TWDA branch and
break every link already shared. The vekn id still lands in `external_ids`, and the
resolver's fallback covers it.

**When it settles.** There is no draft state below `Planned`, and
`POST /api/tournaments` already fires the VEKN calendar push as a background task
(`routes/tournaments.py:950`). So the code is decided by the outcome of the push
that already runs: an event id comes back, that is the code; nothing comes back —
push disabled, organizer without a vekn id, unmappable format, vekn.net down — we
mint. Every other ingress knows its answer at insert time and stamps inline: the
calendar sync's inbound events, the TWDA reconstructions, the archon import.

**Nothing may be left code-less.** A restart between the insert and the background
task would strip an event of a handle permanently, so a startup sweep stamps any
row still without one — not `batch_push`, which returns early when `VEKN_PUSH` is
off and so would stop sweeping at exactly the decommission. Capped at 100 like the
TWDA reconstruction's `MAX_CREATES_PER_RUN`: over that it is a corpus, and it names
the backfill script rather than minting thousands before the app answers.

**Timeouts stay as they are.** `ClientTimeout(total=20, connect=10, sock_read=15)`
and no client-side retry, so a cold push costs at most two requests. Shortening it
would convert *slow but successful* pushes into permanent mints, which is the class
this design exists to shrink. Nothing blocks on the code, so the wait is free.

**Uniqueness is the index, not the alphabet.** All three provenances live in one
column under one unique index on `lower(event_code)`, spanning soft-deleted rows so
a code is never reissued; a mint collision is rejected and retried. Codes are
resolved case-insensitively — slugs are lowercase, minted codes uppercase, vekn ids
digits, and someone will read out or type either. The all-digit exclusion stays as
hygiene so a minted code never *looks* like a vekn id.

**Projection is public**, like `external_ids`: an anonymous visitor following a
short URL must resolve it.

**`/t/{code}`** — 24 characters against 40 for the tournament route. nginx already
serves the SPA shell for any unmatched path, so the only deployment change is the
Open Graph stub's location regex; the short form is not in the proxied-prefix
allowlist. A SvelteKit `/t/[code]` route resolves and redirects to
`/tournaments/{uid}`: keeping the short form in the address bar would mean
rendering the uid page from a second route, and that page reads `params.uid`
throughout. The tournaments store gains `by-code` and `by-vekn` indexes so this
resolves offline, and without a `getAll()` scan of the corpus on the arrival path.
Both OG stubs canonicalise on `/t/{code}` where there is one.

**Share always emits the code when there is one, the uid URL otherwise** — never a
spinner, never a wait. A share that blocks is worse than one that hands over a link
that works forever. The displayed code field carries a quiet "assigning…" hint
instead: the wait is bounded by the push, not by us, and the row broadcasts when
the code lands.

## What remains

Built and green as of 2026-08-18. The line survives only for the production step:
`backfill_event_codes.py` (reports), review, `--apply` — after the TWDA backfill,
per the sequencing below. Until it runs, the corpus has no codes and the
done-condition's "every tournament carries one" is false.

## Sequencing

The code backfill runs **after** the TWDA backfill on production, or the 1118
reconstructions mint codes before their archive keys arrive and — since a code is
never rewritten — keep them forever. Both are pending prod steps on the Hall of
Fame line.

No dependency on the dedup line: production has no duplicate vekn ids and every
stored one is digits (checked 2026-08-17), so the unique index is safe to create.

## Deliberately not in scope

A short handle for **members**. The VEKN id is a player's public identifier and it
dies in the same decommission, so the problem is real — but it is a question about
member identity, not event identity, and it carries its own privacy shape. File it
separately if it matters.
