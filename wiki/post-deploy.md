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

## Mask credentials in production's shipped nginx error lines

Gated by `3fa28ae5`, whose deploy masks the `token`, `code` and `state` query
values in nginx's access lines and the backend's, but not in nginx's error log,
which has no format ([dev](dev.md#deployment)). Fluent Bit's
`journal.lua` masks them before shipping, and `setup.py` installs it rather than
the deploy, so the error lines keep shipping raw until this runs.

```sh
just setup-prod
```

It worked when, in the vtesbiased Loki, `{host="archon.vekn.net", unit="nginx.service"} |= "request: " |~ "[?&](token|code)=[^*&]"`
returns nothing from after the run. Nothing is owed after.

## Check the per-client API throttle on beta

Gated by `17a036ac`, which moves the public API's stream and lookup budgets from
nginx's per-address zones into the API process, keyed on the token's `client_id`
([public-api](public-api.md#deployment)). Before that deploy beta still throttles
per address, so the counts below prove nothing. Run on `https://api.archon.krcg.org`
after `just deploy-beta`, with two `api:read` clients registered there (A, B), each
minting a daemon token through `/oauth/token` into `$TOKEN_A` / `$TOKEN_B`:

```sh
burst() { for i in $(seq 1 15); do curl -s -o /dev/null -w '%{http_code} ' \
  -H "Authorization: Bearer $1" https://api.archon.krcg.org/v1/leagues; done; echo; }
burst "$TOKEN_A"                       # from here: 11 × 200, then 429
```

It worked when, after a minute's rest each time: A's 11 requests split across
this machine and the beta box itself (`ssh deploy@57.129.110.107` with the same
loop) 429 on the twelfth overall, exactly as from one address; and A then B, both
from one address, each get their own 11 × 200. Nothing is owed after.

## Check the `profile:email` grant on beta

Gated by `4ca6cdf6`, which adds the scope ([access](access.md#oauth2-provider)).
Before `just deploy-beta` carries it, beta refuses the scope as invalid. On
`https://archon.krcg.org`, register the vekn-forum client from Developer with
`profile:read` and `profile:email` checked, its purpose stated, and the forum's
callback as redirect URI. Then sign in through it three times, asking for
`profile:email`, for `profile:read`, and for `profile:email` as a member whose
only address is the one on their profile, and read `/oauth/userinfo` with each
access token.

It worked when the first consent page shows the purpose under `profile:email`
and its `userinfo` carries `sub`, `roles`, `vekn_id`, `capabilities` and the
member's verified `email`; the other two carry no `email`. Nothing is owed after:
vekn-forum's `wiki/archon.md` already describes the scope, and a failure goes back
through `/intake` here.
