Doc-impact: wiki/hazards.md (shrink the `Tournament.country` entry to the
cross-corpus comparison note).

# Normalize Tournament.country — measured context

## Writers (5) and their current behavior

| Writer | Site | Behavior |
|---|---|---|
| Create route | `backend/src/routes/tournaments.py:804` (field), `:937` | Raw client string, no validation |
| Engine `UpdateConfig` / create | `engine/src/tournament/mod.rs:2428` (field array), `:170` | Raw JSON copy; `validate_config_fields` does not touch country |
| **Legacy merge (daily)** | `backend/scripts/migrate_from_archon.py:1052` | **Source of the 208 name rows, still running** |
| VEKN tournament sync (6h) | `backend/src/vekn_tournament_sync.py:120`, written `:258,:286,:469,:517` | ISO from vekn.net; the only writer that can store `XX` |
| Go-online | `backend/src/routes/tournaments.py:2456`, `:2707` | Whole client dict via `msgspec.convert`, raw |

The one clean writer: `twda_import.py:159` runs `normalize_country` before
storing. The frontend create form is a select whose values are already ISO
(`TournamentFields.svelte:373-376`).

## The forced order

`migrate_from_archon.build_tournament` (`:885`) uses `existing` only for
`external_ids` (`:1027`); country comes from the legacy dict. Merge mode
(`:1310`) does a full-struct comparison (`same_but_modified`) and re-saves on any
diff — so a normalized row is rewritten back to the name within 24h, plus daily
SSE churn. Hence:

1. Normalize in `build_tournament` so the daily merge converges.
2. Validate/normalize the three raw write paths (create route, engine config
   copy or a backend-side check around it, go-online convert). Precedent for the
   validator shape: `community_links.validated_country`
   (`backend/src/community_links.py:83-92`) — uppercase, 422 on non-2-alpha.
3. Only then the one-time re-save. Running it first burns the run.

## Coverage is total (measured)

Every distinct spelling in the legacy dump (`archondb.dump.gz`, ~50 values:
Spain, Brazil, United States, … French Polynesia) resolves through the existing
`normalize_country` + its 5-entry alias map. Zero misses, zero 2-letter codes,
zero `XX` in the legacy corpus. The hazard's `Czechia`/`South Korea`/`UK`
examples come from other corpora (TWDA tails, user input), not this field.

## Consumers wrong on the 208 rows today (~18 raw comparisons)

The two guarded sites stay guarded: `db.py:1146` (`find_same_event_tournaments`,
`country_key`) and `reconcile_twda.py:165,:459` (`normalize_country`,
tie-break). The rest compare raw and are silently wrong, notably:

- Engine `in_own_country()` via `permissions.py:37,43,50` — NC implicit
  organizer rights, offline-take gate; and `:202` — sanction lifting.
- Same-country FULL projection overlay: `db.py:264,361`, `broadcast.py:120`.
- **`routes/tournaments.py:2371` → `:2258` — go-online mints users with
  `country="Brazil"`, propagating the corruption into a permission-bearing
  field on `User`.** Fix the stamping; decide whether existing bad `User.country`
  values need their own sweep (measure first).
- Calendar agenda + iCal filters (`routes/calendar.py:125-127,229`), VEKN drift
  detection (`vekn_tournament_sync.py:449,492`), report JSON, OG description,
  frontend `by-country` index, agenda, venue autocomplete, offline gate, social
  share text.

## The one active regression risk

`routes/tournaments.py:346` → `engine/src/deck.rs:544,553`: the TWDA export
publishes the raw value as the archive `place` line, whose convention is
`City, Country` in **names**. After normalization it would publish `"BR"` unless
the export expands the code back through the geonames name. This writes to a
permanent external archive — do it in the same change.

## Re-save script

Follow the four existing templates in `backend/scripts/` (`--dsn`/`--apply`,
report-by-default, idempotent). `reproject_public.py` is the precedent for not
touching `modified` (nobody edited these rows); `backfill_event_codes.py` for
suppressing broadcast and regenerating snapshots at the end on a whole-corpus
pass. No SQL lane exists — architecture is no-migrations, re-save only.

## Residue (stays in the hazard note)

- `XX` (~8 rows): vekn.net's own unknown-country venue code, re-supplied by the
  6h sync; both helpers already treat it correctly (`normalize_country` → None,
  `country_key` → itself). Not fixable here.
- `Online`: never stored in the field — a TWDA place tail normalized to `None`
  at import, load-bearing in `reconcile_twda`.
- `""`/null: 405 legacy rows; `find_same_event_tournaments` already keeps null
  in. Decide whether the re-save collapses `""` to null.
- `country_key` stays: `find_same_event_tournaments` and `reconcile_twda`
  compare against corpora we do not control (legacy dumps, vekn.net, the TWDA
  archive), and the fail-closed property (`da454e0`) is independent of the
  stored corpus.
