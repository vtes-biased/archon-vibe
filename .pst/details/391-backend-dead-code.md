# Backend dead-code sweep — full list

From the 2026-07-04 codebase audit. "Dead" = zero callers verified by grep across
backend/ (src, scripts, tests), frontend/, bot/.

## Dead functions — orphans of the removed API-GET read surface

- `get_object` — db.py:451
- `get_objects_by_type` — db.py:484
- `delete_user` — db.py:641
- `delete_tournament_db` — db.py:1016
- `get_tournaments_for_league` — db.py:1163

## Dead model classes

- `Rating(BaseObject)` — models.py:378 (ratings embedded into User; no ObjectType.RATING)
- `Deck(msgspec.Struct)` — models.py:556 (superseded by DeckObject; not in ObjectType)

## Dead geonames helpers

- `get_city_by_id` — geonames.py:74-87
- `search_cities` — geonames.py:118-150
  (remains of a removed city-autocomplete endpoint; matching now happens in VEKN sync +
  client-side)

## Orphaned structs

- `AuthorizeApproval` — routes/oauth.py:195-202
- `RegisterClientRequest` — routes/oauth.py:550-553
  (delete here; properly typing the `body: dict` endpoints is ticket 397)

## Tidies

- Dead local `_encoder = msgspec.json.Encoder()` — archon_import.py:467
- Stale change-narration comment — routes/tournaments.py:1645; redundant in-function
  imports `import asyncio` (:929) and `from datetime import UTC, datetime` (:414)
- Dead `--batch-size` CLI flag — scripts/migrate_from_archon.py:1545 (cursors hardcode
  itersize 500/200)
- `except (aiohttp.ClientError, Exception)` → narrow to
  `(aiohttp.ClientError, TimeoutError, ValueError)` like sibling methods — vekn_api.py:393
- `allocate_next_vekn_id` hand-rolled getconn/BEGIN/COMMIT/ROLLBACK/putconn →
  standard `async with _pool.connection(): async with conn.transaction():` — db.py:798-837
- `get_princes_and_ncs` → rename `get_users_with_vekn_prefix` + fix docstring (query filters
  only on vekn_prefix, no role predicate; `_infer_coopted_by` semantics unchanged) — db.py:758-768
