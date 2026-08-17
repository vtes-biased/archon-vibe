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
  (`models.py:591`) and excluded from the member projection. It is a **capability
  token** — publishing it grants check-in. Different lifetime, different secrecy,
  different consumer.
- **A name+date slug.** Not stable: names are editable, and 869 pre-2014 rows are
  named `Imported VTES Event`.

## The shape to settle

- **Alphabet.** Speakable and typo-resistant means dropping `0`/`O` and `1`/`I`/`L`
  — Crockford base32. Six characters is ~1B values against ~8.5k tournaments per
  decade, ample with collision-retry on a unique index.
- **Assignment is server-side, and that is the one real tension.** The app is
  offline-first with client-minted uuid7, but a short code is short *because* it is
  dense, so it needs a uniqueness check. A tournament created offline therefore has
  no code until it syncs. That is acceptable — an event nobody else can see has no
  id worth sharing — but the field is nullable and **the UI must not promise it
  pre-sync**.
- **Projection is public**, like `external_ids`: an anonymous visitor following a
  short URL must resolve it.
- **A resolving route.** Production nginx proxies only an allowlist of top-level
  path prefixes to FastAPI (`wiki/dev.md`), so a new short-URL prefix is a
  **deployment change**, not just a route. Decide whether it is a new prefix or a
  parameter on the existing tournament route before building.

## Deliberately not in scope

A short handle for **members**. The VEKN id is a player's public identifier and it
dies in the same decommission, so the problem is real — but it is a question about
member identity, not event identity, and it carries its own privacy shape. File it
separately if it matters.
