---
name: snapshot-cursor-and-declare-plan-quirks
description: EXPLAIN of the bare SELECT lies about the plan a psycopg server-side cursor actually runs — cost it as a DECLARE
metadata:
  type: reference
---

**`EXPLAIN <the SELECT>` does not give the plan a server-side cursor runs.** psycopg's
`conn.cursor(name=…)` emits `DECLARE "<name>" CURSOR FOR <query>` (verified in
`psycopg/_server_cursor_base.py::_make_declare_statement` — no SCROLL, no WITH HOLD).
PostgreSQL costs a DECLARE'd cursor with `cursor_tuple_fraction` (default 0.1), i.e.
optimized for fetching 10% of rows, which biases toward low-startup plans and can pick
a different scan than the same SQL run directly — notably an Index Scan over the Bitmap
Heap Scan whose bitmap build is startup cost.

**How to apply:** `db.stream_objects_snapshot` exists to get a seq/bitmap heap scan
instead of index-order random I/O on the latency-bound prod disk, so a plan check that
EXPLAINs the bare SELECT proves nothing. EXPLAIN the `DECLARE …` inside a transaction
(what the closed snapshot-plan verification ticket did), or `SET cursor_tuple_fraction
= 1.0` on the session first — which is simply true here, the snapshot always drains
the cursor.
