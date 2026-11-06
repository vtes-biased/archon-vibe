# Calendar feed reads

Doc-impact: `wiki/architecture.md` (Calendar, Indexes); `wiki/hazards.md` only if
the index rollout turns out to be a trap worth keeping.

## Evidence (production, measured 2026-11-06)

- The personal-feed statement (the `UNION ALL` variant, sent with a token) was
  logged slow 43 times in 7 days, 1.0–11.1 s, clustered 00:00–04:00 UTC: the
  disk spells in `wiki/hazards.md`. It often comes in pairs within the same second
  (calendar clients fetching twice).
- It hit the statement timeout in the 2026-11-06 06:59–07:04 UTC stall: iowait
  ~0.94, every SSE connection dropped at 07:03:06, nine nginx 504s.
- The feed gets about 267 requests a day.
- Since 2026-08-01, measured through the public API's projection (`full` is
  larger): 194 finished rows, ~2.8 MB, the largest 142 KB; 149 unfinished rows,
  ~470 KB.

## What is wrong

`tournament_calendar` selects `"full"` for every unfinished event, and with a
token for every event finished in the last 90 days, then filters in Python. The
agenda keeps a finished event only when the member organizes it, plays in it, or
added it (`agenda.rs` `matches_agenda` / `on_agenda`). So the finished half is
read almost entirely to be thrown away. League and country feeds filter
`league_uid` and `country` in Python, though both are indexed.

## Plan

- **Finished half:** a prefilter that is a strict superset of what the agenda
  keeps, with the engine still deciding:
  - `"full"->'organizers_uids' @> '["<uid>"]'`, on the existing GIN index
    (`jsonb_path_ops`, so `@>`, never `?`).
  - `"full"->'players' @> '[{"user_uid": "<uid>"}]'`, on a new partial GIN index
    (`jsonb_path_ops` on `"full"->'players'`, `WHERE type = 'tournament' AND
    deleted_at IS NULL AND "full"->>'state' = 'Finished'`).
  - `uid = ANY(<agenda_added>)`.
  - The existing finish-date window.
- **League feed:** `"full"->>'league_uid' = %s` in SQL
  (`idx_objects_tournament_league`).
- **Country feed:** `"full"->>'country' = ANY(%s)` in SQL, with online events
  still allowed through (`idx_objects_tournament_country_uid`).
- **Upcoming half:** leave it selecting `full`. Narrowing the columns saves no
  disk reads, because Postgres reads the whole stored document even to pull one
  field.

## Traps

- `schema.sql` runs at every boot as a single statement (`db.py` `init_db`). A
  GIN build there on production's disk can run past the database's 15 s
  `statement_timeout` and fail boot, and a plain `CREATE INDEX` blocks writes to
  `objects` while it builds. Settle how the index gets built before shipping.
- A partial index serves only a query that states its `WHERE` word for word, with
  `type` as a literal (`wiki/architecture.md#indexes`). Check every feed with the
  `EXPLAIN` recipe there.
- Hidden overrides, the online filter and the country/continent rules stay in
  `agenda.rs`; the SQL must never drop a row the engine would keep.
