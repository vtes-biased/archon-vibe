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

## Audit results across vekn.net, the TWDA and Archon after the first tournament sync

Gated by `8db70191`, which ships the script and the round-count and archive rules,
and by `7836e944`'s legacy-sheet rules before it. The sync rewrites the stored rows
only on the first tournament sync after the deploy (or the admin *Run now*); a
check before that reads the old imports. The audit scans vekn.net itself (about a
minute) and peaks around 150 MB, so run it with the box quiet.

```sh
sudo -u archon bash -c 'set -a; . /etc/archon/archon-backend.env; set +a; \
  /opt/archon/backend/.venv/bin/python \
  /opt/archon/backend/scripts/audit_results.py' > /tmp/audit-results.txt
head -20 /tmp/audit-results.txt
```

Then the two checks the legacy-sheet rules owe, nothing to run but the queries:

```sql
SELECT "full"->'external_ids'->>'vekn' AS vekn
FROM objects
WHERE type = 'tournament' AND "full"->'external_ids' ? 'vekn'
  AND jsonb_array_length("full"->'standings')
      <> (SELECT count(DISTINCT s->>'user_uid')
          FROM jsonb_array_elements("full"->'standings') s);

SELECT count(*) FILTER (WHERE (s->>'gw')::float = 0) AS winners_at_zero,
       count(*) AS winners
FROM objects t, jsonb_array_elements(t."full"->'standings') s
WHERE t.type = 'tournament' AND t."full"->'external_ids' ? 'vekn'
  AND t."full"->>'start' < '2011' AND s->>'user_uid' = t."full"->>'winner';
```

It worked when the summary holds no `ours prelim-gw` line — the six rows over their
round count on 2026-09-23 (7300, 7396, 8450, 9474, 9667, 11962) are gone after the
re-sync — the first query returns no rows (vekn events 9915, 7713, 8754, 5793, 6580,
9166 and 2804 among them), and the second reads about 520 winners at 0 prelim GW
out of about 2,980, against about 65 before. Report all three to the owner, put the
audit's counts in the table in [vekn](vekn.md#results-across-the-three-sources) in
place of its pre-sync row, and delete this section.

## Strip deckbuilder noise from the deck comments stored before it

Gated by `d24e5f4d`. A deck-link import strips the deckbuilder's noise from that
commit on, and the TWDA export publishes the stored comment verbatim, so a comment
imported earlier keeps its restated header until this runs. Events the TWDA sync
created are left out — their comments are the archive's own text. The go/no-go is
the owner's, on the production report's count and pairs; a dev copy holding 930
archive comments reported 1, a stray score line.

```sh
sudo -u archon bash -c 'set -a; . /etc/archon/archon-backend.env; set +a; \
  /opt/archon/backend/.venv/bin/python \
  /opt/archon/backend/scripts/strip_deck_comment_noise.py'
```

Rerun with `--apply` once every before/after pair reads as noise only. It worked
when a third run reports `0 of N`. Delete this section and
`backend/scripts/strip_deck_comment_noise.py` together.

## Production's env files load silently in bash

Gated by `d15b90f9`, which single-quotes every value `deploy/deploy.py` writes.
The deploy runs from the checkout, not the release, so it takes the next
`just deploy-prod` from a tree containing that commit to rewrite the backend and
bot env files (production runs no public API) and restart both units; a check
before that reads the unquoted files. Proof, on the box — no output from either
load, two `active`, and `0` per unit:

```sh
for f in backend bot; do sudo -u archon bash -c "set -a; . /etc/archon/archon-$f.env; set +a"; done
systemctl is-active archon-backend archon-bot
for u in backend bot; do sudo cat /proc/$(systemctl show -p MainPID --value archon-$u)/environ | tr '\0' '\n' | grep -c "='"; done
```

Nothing is owed afterwards.
