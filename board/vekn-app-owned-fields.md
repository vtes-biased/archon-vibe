# The app owns a filed tournament's name, finish and timezone

Doc-impact: `wiki/vekn.md` — the Inbound › Tournaments section states the three
buckets and the rule below; the `proxies` bullet is reconciled so the page stops
asserting vekn.net ownership as a general rule.

## The rule the owner set

Which side owns a field on a tournament that holds a vekn id is decided by what a
mismatch costs, not by who wrote it first:

- **vekn.net owns it, and the app freezes the field** where the two values must
  agree — either because the push mechanically depends on it (`rounds` must be
  right for the results push to succeed), because ranking has to come out the same
  on both sides (`rank`, `format`), or because a divergence misleads players trying
  to join (`start`). `proxies` sits here too: the sync reads it back, so a local
  edit would revert rather than diverge.
- **The app owns it** where the two values are free to differ and the app is
  plainly the truth — `name`, `finish`, `timezone`. The sync fills these at
  creation or adoption and **never modifies them again**.

Everything else — `country`, `venue`, `address`, `venue_url`, `map_url` — stays a
vekn.net refresh, except under the placeholder venue, where the local value already
wins (gh-9).

## What changes

`backend/src/vekn_tournament_sync.py`, both merge branches under `if existing_ref:`:

- Metadata-only refresh (`:489-541`): drop `name`, `finish`, `timezone` from the
  `meta_changed` diff (`:493`, `:497`, `:498`) and from the `msgspec.structs.replace`
  (`:512`, `:517`, `:518`).
- Full rebuild (`:545-614`): this branch constructs a **fresh `Tournament(...)`**
  rather than replacing onto `existing`, so dropping the fields is not enough —
  it must pass `existing.name`, `existing.finish`, `existing.timezone` explicitly,
  and lose them from the diff at `:550`, `:553`, `:555`.

The create path (`:622`) is untouched: a first sync still fills all three.

## Traps

- `_adopt_same_event` (`:331-374`) stamps the vekn id onto a local copy. Adoption is
  a first link, so the local values must stand — check it does not write the
  mapping's name over the adopted row.
- The `placeholder_venue` carry-over (`:474-483`) already preserves `timezone`. Once
  timezone is app-owned unconditionally that entry is redundant; remove it there
  rather than leaving two mechanisms for one field.
- `vekn_push.py:230` sends `tournament.name[:120]`. That truncation stops reaching
  the local row once the app owns the name, which is part of why this fix is worth
  more than the freeze — no separate work needed.
- `start`, `rank` and `format` are already frozen in the engine
  (`engine/src/tournament/mod.rs:2683-2703`, `VeknFrozenField`) and disabled in the
  UI (`frontend/src/routes/tournaments/[uid]/TournamentDetailsForm.svelte:140-143`).
  Do not touch them. `finish` is deliberately **not** joining them.

## The regression

`backend/tests/test_vekn_sync_preserves_registration.py:39,53` already runs a sync
over a linked tournament, but uses the same name locally and remotely. Diverging
the local name, finish and timezone from the remote payload and asserting they
survive the cycle is the one invariant, at the interface, against the shipped
artifact.
