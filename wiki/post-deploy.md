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

## Confirm the judge directory sync runs on production

**Gated on** the commit setting `judge_sync = "true"` in
`deploy/group_data/prod.py`. The first run was triggered by hand from the admin
panel; the daily 05:30 UTC job only exists once a deploy carries the flag.

**Run** nothing: after the first 05:30 UTC following that deploy, read the
vekn-status panel.

**Proves it worked**: *Judge directory sync* shows green with a run after the
deploy, and `preview_judge_sync.py` on the box prints `0 members would change`.

**Owes afterwards**: telling the VTES Exams maintainers the integration is live, and that
leaving the public directory or letting an accreditation lapse now removes the
Archon title. Delete this section.

## Ask organisers to re-enter their promo reports

**Gated on** the commit declaring `promos` and `stock_source_uid` on
`TournamentActionRequest`. Until it is live every `ReportPromos` still fails with
"promos required", so asking earlier only earns a second failure. Every report
since the feature shipped on 17 July was refused, and so was every raffle prize
(`prize_promo_uid`).

**Run** the reply on gh-55: promo reports save again, and organisers of events
finished since 17 July should open the event and re-enter what they handed out.

**Proves it worked**: within a few days, on production,
`SELECT count(*) FROM objects WHERE type = 'tournament' AND
jsonb_array_length(coalesce("full"->'promos_distributed', '[]'::jsonb)) > 0;`
answers above 0.

**Owes afterwards**: closing gh-55 through `/post-deploy`. Delete this section.

## Retract the decks published for players who never sat

**Gated on** the commit requiring a seat for `All`-mode publication
(`compute_deck_public`). Before it is live the old pass re-publishes a retracted
deck on the next action its event takes.

**Run** `backend/scripts/retract_noshow_decks.py` on the box, dry run first, then
`--apply`.

**Proves it worked**: a second dry run reports 0 decks, and the no-show's deck on
the event behind VEKN 13609 is gone from its public deck list.

**Owes afterwards**: closing gh-52 through `/post-deploy`. Delete the script and
this section in one commit.

## Prove league dates carry no time

**Migration** `league-calendar-dates`

Gated by the commit that made league `start` and `finish` calendar dates
([product](product.md#capabilities)). The entry rewrites every league date still
carrying a time — the legacy UTC instants and the naive midnights the routes used
to store — to its UTC calendar date. The old rows do not decode as a `date`, and a
league list raises whole on one of them.

Nothing to run: the entry rewrote the rows before the process served. It worked
when this answers 0:

```sql
SELECT count(*) FROM objects
WHERE type = 'league'
  AND (length("full"->>'start') > 10 OR length("full"->>'finish') > 10);
```

**Owes afterwards**: closing gh-56 through `/post-deploy`.
