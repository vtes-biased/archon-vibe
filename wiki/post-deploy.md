# Post-deploy — what a production deploy unlocks

Actions that only become safe once a specific commit is live on production. The
board holds no waiting state and a subsystem page is no place for a runbook, so
they park here: one `##` section per item, **completion is deletion**, and an
empty page is the normal state.

`/post-deploy` runs them, ahead of the feedback issues it closes. Unlike the work
deferred in [vekn-decommission](vekn-decommission.md), a fired trigger here does
**not** go back through `/intake`: that trigger fires every release, and an item
reaches this page only after passing egress review, so the one decision left is
the owner's go/no-go.

**An item belongs here only if `/post-deploy` could execute it with nothing but
that go/no-go.** Work carrying judgment — reviewing a dedup's output, diffing Hall
of Fame membership either side of a backfill — stays a board line that happens to
have a production step. Without that boundary this page becomes a second board.

A section whose first line is **Migration** followed by a slug is the standing
proof of an entry in `backend/src/migrations.py`
([architecture](architecture.md#stored-value-migrations)). It has nothing to
run — the entry rewrote the rows before the process served — but its queries are
the only record that the rewrite reached a given database, so it is deleted only
once **every** long-lived one answers 0, and the entry it names dies in the same
commit. `just migration-pairing` fails on either half outliving the other.

**Every item names the commit that gates it**, so `git tag --contains <sha>`
answers whether a given deploy has made it actionable — the same check
`/post-deploy` already runs against a feedback issue's fix. An item states what
gates it and why, what to run, what proves it worked, and what it owes afterwards:
people to tell, and the wiki text that dies with it.

## Strip deckbuilder noise from the deck comments stored before it

Gated by `3f6ce3c1`, which keeps a stamp heading a typed note and a rule past the
body's first text: the 2026-09-26 production dry run under `d24e5f4d` (271 of 2,783)
dropped both. A deck-link import strips the deckbuilder's noise, and the TWDA
export publishes the stored comment verbatim, so a comment imported earlier keeps
its restated header until this runs. Events the TWDA sync created are left out —
their comments are the archive's own text. The go/no-go is the owner's, on the
production report's count and pairs.

```sh
sudo -u archon bash -c 'set -a; . /etc/archon/archon-backend.env; set +a; \
  /opt/archon/backend/.venv/bin/python \
  /opt/archon/backend/scripts/strip_deck_comment_noise.py'
```

Rerun with `--apply` once every before/after pair reads as noise only. It worked
when a third run reports `0 of N`. Delete this section and
`backend/scripts/strip_deck_comment_noise.py` together.

## Measure the public API's filter expressions

Gated by `7fb74416`, which gives `objects_api_filter_stats` its final shape. The
schema creates the statistics object at startup but
nothing fills it until autovacuum next analyzes `objects`, and until then the
planner prices a one-sided `start` bound, a country or a sparse rating category as
a third of the corpus and walks the whole type. Running it before the deploy
measures an object that does not exist yet. The app role's statement timeout
cancels a plain `ANALYZE`, hence the override.

```sh
sudo -u archon bash -c 'set -a; . /etc/archon/archon-backend.env; set +a; \
  psql "$DATABASE_URL" -c "SET statement_timeout = 0" -c "ANALYZE objects"'
```

It worked when `EXPLAIN` of `/v1/tournaments?start_after=<last month>` names
`idx_objects_tournament_start` in its `Index Cond`
([architecture](architecture.md#indexes) has the recipe). Nothing is owed after.
