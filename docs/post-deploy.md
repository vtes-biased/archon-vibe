# Post-deploy — what a production deploy unlocks

Actions that only become safe once a specific commit is live on production. The
board holds no waiting state and a subsystem page is no place for a runbook, so
they park here: one `##` section per item, **completion is deletion**, and an
empty page is the normal state.

`/post-deploy` runs them, ahead of the feedback issues it closes. Unlike the work
waiting in [`WATCH.md`](../WATCH.md), a fired trigger here does
**not** go back through `/intake`: that trigger fires every release, and an item
reaches this page only after passing review, so the one decision left is
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
commit. `mise run migration-pairing` fails on either half outliving the other.

**Every item names the commit that gates it**, so `git tag --contains <sha>`
answers whether a given deploy has made it actionable — the same check
`/post-deploy` already runs against a feedback issue's fix. An item states what
gates it and why, what to run, what proves it worked, and what it owes afterwards:
people to tell, and the docs text that dies with it.

## Count the unverified email logins

**Gated on 3e16c1d1**, which removed the password signup, the only writer of a
`verified=false` email login. Counted earlier, the number can still grow.

Run against the production database:

    docker compose exec -T db psql -U archon -d archon -c "SELECT count(*) FROM auth_methods WHERE data->>'method_type' = 'email' AND data->>'verified' = 'false'"

The count is the whole output. **Owes afterwards**: take the number through
`/intake` to decide whether `get_user_by_email` stops matching unverified email
logins, then shorten the `verified=false` paragraph in
[access](access.md#the-email-of-record) to whatever was decided.

## Re-project users so Princes receive their members' sponsor

**Gated on the commit that added this section** (`git log -1 --format=%h
-S'Re-project users so Princes' -- docs/post-deploy.md`), which put `coopted_by`
in the member user projection. Run earlier, the deployed `access_levels.py`
rewrites the old projection and the members still carry no sponsor.

Run against production, from the deployed tree:

    ssh archon.vekn.net "sudo -u archon bash -c 'set -a; . /etc/archon/archon-backend.env; set +a; \
      /opt/archon/backend/.venv/bin/python /opt/archon/backend/scripts/reproject_public.py --apply'"

It worked when a Prince's members directory, Mine filter on,
lists the members issued under their prefix. **Owes afterwards**: nothing.

## Re-apply the production Grafana dashboard without the VEKN push row

**Gated on the commit that added this section** (`git log -1 --format=%h
-S'without the VEKN push row' -- docs/post-deploy.md`), which retired the
member sync and push and removed the `VEKN push` row from `deploy/grafana.py`.

Run locally with the production Grafana token:

    GRAFANA_TOKEN=$GRAFANA_TOKEN_VTESBIASED uv run python deploy/grafana.py prod

It worked when the **Archon production** dashboard no longer has a **VEKN push**
row. **Owes afterwards**: nothing.

## Stamp `finalist` on stored decks and re-project

**Migration** `deck-finalist`

**Gated on the commit that added this section** (`git log -1 --format=%h
-S'deck-finalist' -- docs/post-deploy.md`), which added `DeckObject.finalist` and
stopped publishing `user_uid` on non-finalist decks in `member` and `api`. The
lifespan migration stamps `finalist` on every stored deck and re-saves it, which
recomputes `member` and `api` projections automatically before serving.

Verify on every long-lived database (beta and production) that zero rows remain
unmigrated:

    docker compose exec -T db psql -U archon -d archon -c "SELECT count(*) FROM objects WHERE type = 'deck' AND NOT (\"full\" ? 'finalist')"

It worked when both beta and production answer `0`. **Owes afterwards**: delete
the `deck-finalist` entry from `backend/src/migrations.py` and this section in
the same commit.
