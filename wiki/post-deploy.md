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

## Re-submit the decks the archive refused

**Gated on** the commit carrying this section — *"Submit the winner's deck from a
fork we own"*, findable as `git log -1 --format=%h --grep='fork we own'` — which
moved every TWDA write onto our own fork. Before it, the auto-PR asked the
archive's installation for `contents: write`, was refused, and no winning deck
reached the TWDA since the feature went live.

**Order matters**: the fork, its installation and the two vault entries must exist
**before** the deploy. An event finishing in the gap between the deploy and the
configuration records `skipped / not_configured` instead of `failed`, and nothing
refires it — its results are already pushed, so the batch retry never looks at it
again. The query below catches both shapes for that reason.

**Run**: list the events, then for each one `POST /api/tournaments/{uid}/push-vekn`
as an admin. With the results already pushed that path skips vekn.net entirely and
re-runs only the submission.

```sql
SELECT "full"->>'uid', "full"->>'name', "full"->'twda_status'->>'outcome'
FROM objects WHERE type='tournament' AND deleted_at IS NULL
  AND ("full"->'twda_status'->>'outcome' = 'failed'
    OR ("full"->'twda_status'->>'outcome' = 'skipped'
        AND "full"->'twda_status'->>'reason' = 'not_configured'));
```

**Proves it worked**: the query returns no rows, and each event's `twda_status`
reads `submitted` with a PR URL on `GiottoVerducci/TWD`.

**Owes afterwards**: nothing to tell anyone — the organizers never saw the failure.
Delete this section.

## Correct the finalists vekn.net already recorded wrong

**Gated on** the commit carrying this section — *"Report the winner vekn.net crowns
at position 1"*, findable as `git log -1 --format=%h --grep='position 1'` — which
made the pushed placement field the final placement instead of the preliminary
standings order. Every event finished before it goes live pushes the old order, so
a list drawn earlier is stale by the time it is answered.

**Run** on production, then hand the rows to the Rulemonger: the results upload
refuses a second submission once an archon file is stored and offers no overwrite,
so each one is a manual `veknparticipant.pos` fix on vekn.net.

```sql
WITH t AS (
    SELECT uid, "full" AS f FROM objects
    WHERE type='tournament' AND deleted_at IS NULL
      AND "full"->>'state'='Finished' AND "full"->>'vekn_pushed_at' IS NOT NULL
      AND jsonb_array_length(COALESCE("full"->'rounds', '[]'::jsonb)) > 0
      AND COALESCE("full"->>'winner', '') <> ''
), paid AS (
    SELECT t.uid, array_agg(v ORDER BY v) AS paid FROM t, LATERAL (
        SELECT e->>'user_uid' AS v
        FROM jsonb_array_elements(t.f->'standings') WITH ORDINALITY AS q(e, n)
        WHERE n <= 5) s GROUP BY t.uid
), seated AS (
    SELECT t.uid, array_agg(v ORDER BY v) AS seated FROM t, LATERAL (
        SELECT e->>'player_uid' AS v
        FROM jsonb_array_elements(t.f->'finals'->'seating') AS e) s GROUP BY t.uid
)
SELECT t.uid, t.f->>'name' AS name, t.f->'external_ids'->>'vekn' AS vekn,
       t.f->>'winner' IS DISTINCT FROM (t.f->'standings'->0->>'user_uid') AS wrong_winner,
       paid.paid, seated.seated
FROM t JOIN paid USING (uid) LEFT JOIN seated USING (uid)
WHERE paid.paid IS DISTINCT FROM seated.seated
   OR t.f->>'winner' IS DISTINCT FROM (t.f->'standings'->0->>'user_uid');
```

The rounds guard keeps out VEKN and ETL imports, which carry a push stamp they
never earned here; the winner guard keeps out no-final events, which have none.

The old order corrupts the record **two** ways, and a winner check alone sees only
the first. vekn.net reads the pushed field as `finalrank`: row 1 is crowned, rows
2–5 are paid the finalist bonus. So the five rows it pays are the *preliminary*
top five, which parts from the seated five whenever a qualifier withdrew and the
next-ranked was promoted — the winner can still land on row 1 and the record be
wrong about who reached the final. Comparing the two sets catches both classes.

Event 13385, *Fee Stake: Jyväskylä 9*, is the known winner case — Ari-Pekka
Alestalo won the final from the fifth seat and vekn.net holds Lasse Pöyry at
position 1. Event 13413, *Fee Stake Melbourne 2026*, is the known finalist case —
Nathaneal Zheng withdrew and Alan Stevenson was promoted, but vekn.net credits
Zheng a finalist and pays Stevenson nothing.

**Proves it worked**: every listed event shows its actual winner at position 1 on
vekn.net and its seated five at positions 1–5, and — checked a day later, once the nightly batch has run — the rating
points have moved with the position. Whether upstream re-derives them is
[unestablished](domain/vekn.md#never-chase-veknnets-stored-rtp), so this half is
verified rather than assumed.

**Owes afterwards**: nothing to tell anyone if the points followed. If they did
not, the winner is left holding the loser's rating on vekn.net with no API able to
fix it, which is its own correction and its own board line. Delete this section
either way.
