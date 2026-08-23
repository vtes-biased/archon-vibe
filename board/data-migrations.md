# One place to migrate stored values

## Why there is anything to migrate at all

`objects` is schemaless, so a field's *meaning* lives in the Python and Rust that
reads it, not in the table. When that code changes, every row written under the
old reading is now wrong, and `msgspec` decodes strictly — an unknown enum value
or a stale nested shape raises `ValidationError` on **every read of any list
containing the row**, not just on that row. The dogma's "no schema migrations"
holds and is not in tension with this: there is no schema to migrate, which is
precisely why the values need a home.

## The two that exist, and how they disagree

**The role rename** (`c92fe3f`) rewrites `Judgekin` → `Sheriff` in four guarded
`UPDATE`s at the end of `backend/src/schema.sql`. `init_db` applies that file on
startup, so the rows move before the process serves — no window. Two problems:
the statements are permanent cruft nothing owns the deletion of, and `init_db` is
called by **14 ops scripts**, so a report-only run pointed at a DSN silently
mutates it.

**The link-moderation collapse** (`2d6190f`) ships
`backend/scripts/collapse_link_moderation.py`, run by `/post-deploy`. Its own
docstring states the cost: a row still carrying the object shape "raises on every
read of that member until this runs." That is an accepted outage window on every
member with a moderated link.

Each got one half right. The rename got the **placement** — pre-serve, zero
window. The collapse got the **mechanism** — Python re-saving through
`save_object`, which recomputes all four projections from `full`. That matters
whenever a projection's *shape* changed and not merely a value: hand-written
per-column SQL would have to restate `compute_public/member/api/full`, putting one
fact in two places. Its per-row transactions also give distinct `modified_at`
values, which the single-statement SQL cannot — a shared timestamp can be split by
a catch-up cursor's strict `modified_at > since`.

## Hazards

**A pre-serve migration that raises takes the backend down.** Worse than the
window it replaces: `wiki/testing.md` records the lightbulb v2→v3 migration
crash-looping 69 times in production while CI stayed green. Two consequences. The
runner's failure behaviour is a real decision — refuse to serve half-migrated, or
log and serve with the old window — and it should be made deliberately rather than
fallen into. And a migration lands only after being run against a copy of
production data; the rename's four `UPDATE`s were validated that way against 21
real rows, the collapse has not been.

**Deletion needs proof from every long-lived database.** `/post-deploy` is a
production procedure, but beta is long-lived too. An entry deleted on prod-only
proof strands beta on the old values permanently, with nothing left in the tree to
re-apply.

**Bounded row counts only.** A pre-serve migration extends deploy downtime by its
own runtime. Tens to low thousands of rows is the range; a corpus-scale rewrite
stays a post-deploy script with a stated, accepted window. The rule is worth
writing down beside the mechanism, or it will be misapplied.

**Self-guarding costs a query per boot.** No ledger table means each entry
re-asks "is there anything to do" on every startup, and those guards are jsonb
scans. Tolerable only because the lint keeps the entry count near zero — which is
the argument for the lint, not a detail of it.

## Sequencing

Nothing has deployed. Both migrations can be restructured freely right now, and
the mechanism ships with two real entries rather than none. After a deploy the
rename is applied everywhere and its port becomes archaeology, while the collapse
has already spent its window on real members.
